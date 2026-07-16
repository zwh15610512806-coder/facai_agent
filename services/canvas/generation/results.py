"""Recoverable Provider-result promotion and immutable generation composition."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasAsset,
    CanvasAssetOperation,
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
)
from config import CANVAS_MAX_IMAGE_PIXELS, CANVAS_REMOTE_IMAGE_MAX_BYTES
from services.canvas import assets, operations, previews, storage
from services.canvas.events import append_generation_progress_event
from services.canvas.composition import composition_layout_hash, map_product_to_board
from services.canvas.composition_schema import CompositionLayout, CompositionSpec
from services.canvas.compose_operations import ComposeRequestSnapshot
from services.canvas.font_resource import FONT_FAMILY, FONT_RESOURCE_VERSION, FONT_SHA256
from services.canvas.generation.repository import release_generation_reservation
from services.canvas.generation.state import (
    aggregate_generation_status,
    transition_attempt,
    transition_generation,
    transition_item,
)
from services.canvas.provider_schemas import ControlledImageBytes, ControlledRemoteImage
from services.canvas.remote_images import (
    RemoteImageValidationError,
    download_remote_image,
    verify_remote_image,
)


class GenerationResultError(RuntimeError):
    """A safe failure while receiving or promoting a Provider image."""


@dataclass(frozen=True)
class MaterializedProviderResult:
    """A verified, metadata-free PNG stored in the project temporary area."""

    attempt_id: str
    project_id: str
    source_format: str
    sha256: str


def _result_filename(attempt_id: str, suffix: str) -> str:
    try:
        normalized = str(UUID(attempt_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise GenerationResultError("generation attempt id is invalid") from exc
    return f"{normalized}.provider-result.{suffix}"


def _temporary_result_path(project_id: str, attempt_id: str, suffix: str) -> Path:
    root = storage.ensure_project_tree(project_id)
    # Keep the actively-written partial in ``tmp``.  Windows' no-replace
    # pinned-handle primitive cannot rename an open file within the same
    # directory, so the verified hand-off uses the fixed generated directory
    # before it is atomically promoted to a DB-backed generated asset.  Both
    # directories are capacity-accounted and neither name is Provider-derived.
    directory = "tmp" if suffix == "partial" else "generated"
    path = root / directory / _result_filename(attempt_id, suffix)
    try:
        storage._assert_safe_path(path.parent, root=storage._data_root(), must_exist=True, expected_kind="directory")
        storage._assert_safe_path(path, root=storage._data_root())
    except storage.CanvasStorageError as exc:
        raise GenerationResultError("generation result path is unavailable") from exc
    return path


def _write_verified_temporary_result(
    *, project_id: str, attempt_id: str, data: bytes
) -> Path:
    """Fsync a canonical PNG before it can be promoted by a DB transaction.

    Both fixed staging directories are capacity-accounted.  Names are
    UUID-derived only and all IO is carried out through Canvas' pinned storage
    helpers, so a Provider response never controls a filesystem path.
    """

    if not isinstance(data, bytes) or not data or len(data) > CANVAS_REMOTE_IMAGE_MAX_BYTES:
        raise GenerationResultError("generation result exceeds the configured limit")
    partial_path = _temporary_result_path(project_id, attempt_id, "partial")
    verified_path = _temporary_result_path(project_id, attempt_id, "verified")
    try:
        with (
            storage._pin_directory_chain(
                partial_path.parent,
                writable_final=True,
            ) as source_chain,
            storage._pin_directory_chain(
                verified_path.parent,
                writable_final=True,
            ) as destination_chain,
        ):
            parent = source_chain[-1]
            destination_parent = destination_chain[-1]
            records = {
                record.name: record
                for record in storage._directory_records(
                    parent, max_entries=storage.CANVAS_MAX_TREE_ENTRIES
                )
            }
            destination_records = {
                record.name: record
                for record in storage._directory_records(
                    destination_parent, max_entries=storage.CANVAS_MAX_TREE_ENTRIES
                )
            }
            verified_record = destination_records.get(verified_path.name)
            if verified_record is not None:
                if verified_record.is_directory:
                    raise GenerationResultError("generation result path is unavailable")
                pin = storage._open_record(destination_parent, verified_record)
                try:
                    existing = storage._pinned_file_bytes(pin)
                finally:
                    pin.close()
                if existing != data:
                    raise GenerationResultError("generation result conflicts with saved recovery data")
                return verified_path
            if partial_path.name in records:
                raise GenerationResultError("generation result is already being received")
            pin = storage._create_pinned_file(parent, partial_path.name)
            try:
                storage._write_pinned_file(pin, data)
                storage._flush_pinned_file(pin)
                storage._rename_pinned_file_no_replace(
                    pin,
                    destination_parent,
                    verified_path.name,
                )
                storage._flush_pinned_file(pin)
            finally:
                pin.close()
        return verified_path
    except GenerationResultError:
        raise
    except storage.CanvasStorageError as exc:
        raise GenerationResultError("generation result could not be saved") from exc


def read_verified_temporary_result(*, project_id: str, attempt_id: str) -> bytes:
    path = _temporary_result_path(project_id, attempt_id, "verified")
    try:
        with storage._pin_directory_chain(path.parent) as chain:
            parent = chain[-1]
            records = {
                record.name: record
                for record in storage._directory_records(
                    parent, max_entries=storage.CANVAS_MAX_TREE_ENTRIES
                )
            }
            record = records.get(path.name)
            if record is None or record.is_directory:
                raise GenerationResultError("generation recovery data is unavailable")
            pin = storage._open_record(parent, record)
            try:
                return storage._pinned_file_bytes(pin)
            finally:
                pin.close()
    except GenerationResultError:
        raise
    except storage.CanvasStorageError as exc:
        raise GenerationResultError("generation recovery data is unavailable") from exc


def remove_verified_temporary_result(*, project_id: str, attempt_id: str) -> None:
    """Best-effort, identity-checked cleanup after a committed promotion."""

    path = _temporary_result_path(project_id, attempt_id, "verified")
    try:
        with storage._pin_directory_chain(path.parent) as chain:
            parent = chain[-1]
            record = next(
                (
                    item
                    for item in storage._directory_records(
                        parent, max_entries=storage.CANVAS_MAX_TREE_ENTRIES
                    )
                    if item.name == path.name
                ),
                None,
            )
            if record is None:
                return
            if record.is_directory:
                raise GenerationResultError("generation result path is unavailable")
            pin = storage._open_record(parent, record, delete=True)
            try:
                storage._dispose_pinned_entry(pin)
            finally:
                if not pin.closed:
                    pin.close()
    except GenerationResultError:
        raise
    except storage.CanvasStorageError as exc:
        raise GenerationResultError("generation result cleanup failed") from exc


async def materialize_provider_result(
    *,
    project_id: str,
    attempt_id: str,
    image: ControlledRemoteImage | ControlledImageBytes,
    transport: Any | None = None,
) -> MaterializedProviderResult:
    """Complete every network await before opening a Canvas database Session."""

    try:
        if isinstance(image, ControlledRemoteImage):
            verified = await download_remote_image(
                image.remote_url,
                transport=transport,
                max_bytes=CANVAS_REMOTE_IMAGE_MAX_BYTES,
            )
        elif isinstance(image, ControlledImageBytes):
            data = image.data
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                mime_type = "image/png"
            elif data.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                mime_type = "image/webp"
            else:
                raise RemoteImageValidationError("Provider image type is invalid")
            verified = verify_remote_image(
                data,
                declared_mime=mime_type,
                max_bytes=CANVAS_REMOTE_IMAGE_MAX_BYTES,
            )
        else:  # pragma: no cover - static Protocol boundary defense
            raise RemoteImageValidationError("Provider image result is invalid")
    except RemoteImageValidationError as exc:
        raise GenerationResultError("Provider image could not be verified") from exc
    _write_verified_temporary_result(
        project_id=project_id,
        attempt_id=attempt_id,
        data=verified.data,
    )
    return MaterializedProviderResult(
        attempt_id=attempt_id,
        project_id=project_id,
        source_format=verified.source_format,
        sha256=verified.sha256,
    )


def _load_layout_snapshot(item: CanvasGenerationItem) -> dict[str, Any]:
    try:
        snapshot = json.loads(item.layout_snapshot_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise GenerationResultError("saved generation layout is invalid") from exc
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise GenerationResultError("saved generation layout is invalid")
    return snapshot


def _compose_request_from_item(
    *,
    generation: CanvasGeneration,
    item: CanvasGenerationItem,
    background: CanvasAsset,
) -> ComposeRequestSnapshot:
    """Rebuild compose input solely from Item's immutable submission snapshot."""

    snapshot = _load_layout_snapshot(item)
    try:
        layout = CompositionLayout.model_validate(snapshot["composition"])
        if composition_layout_hash(layout) != item.layout_hash:
            raise ValueError("layout hash mismatch")
        layer = snapshot["productLayer"]
        if not isinstance(layer, dict):
            raise ValueError("product layer missing")
        source_width = int(layer["sourceWidth"])
        source_height = int(layer["sourceHeight"])
        if source_width <= 0 or source_height <= 0:
            raise ValueError("source dimensions invalid")
        spec = CompositionSpec.model_validate(
            {
                "schemaVersion": 1,
                "projectId": generation.project_id,
                "compositionGroupId": snapshot["compositionGroupId"],
                "skuId": item.sku_id_snapshot,
                "productLayerId": layer["id"],
                "sourceAssetId": layer["sourceAssetId"],
                "renderAssetId": layer["renderAssetId"],
                "allowOpaqueFallback": layer["allowOpaqueFallback"],
                "layout": layout.model_dump(by_alias=True),
                "layoutHash": item.layout_hash,
                "sourceSize": {"width": source_width, "height": source_height},
                "outputRatio": {"width": item.width, "height": item.height},
            }
        )
        placement = map_product_to_board(
            layout,
            source_size=(source_width, source_height),
            output_size=(item.width, item.height),
        )
        texts = snapshot.get("textSnapshots", [])
        if not isinstance(texts, list):
            raise ValueError("text snapshots invalid")
        return ComposeRequestSnapshot.model_validate(
            {
                "schemaVersion": 1,
                "projectRevision": generation.project_revision,
                "boardId": item.board_id,
                "outputSize": {"width": item.width, "height": item.height},
                "background": {
                    "assetId": background.id,
                    "assetType": "generated_background",
                    "sha256": background.sha256,
                    "width": background.width,
                    "height": background.height,
                },
                "products": [
                    {
                        "spec": spec.model_dump(by_alias=True),
                        "placement": placement.model_dump(by_alias=True),
                        "sourceSha256": layer["sourceAssetSha256"],
                        "renderSha256": layer["renderAssetSha256"],
                    }
                ],
                "textLayers": texts,
                "font": {
                    "family": FONT_FAMILY,
                    "version": FONT_RESOURCE_VERSION,
                    "sha256": FONT_SHA256,
                },
                "processorVersion": "pillow-12.3.0-compose-v1",
            }
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GenerationResultError("saved generation layout is invalid") from exc


def _aggregate_generation(db: Session, generation: CanvasGeneration, *, now: datetime) -> None:
    # Queue callers deliberately use ``autoflush=False`` in some workers; the
    # terminal Item transition must be visible before deriving Generation state.
    db.flush()
    statuses = list(
        db.scalars(
            select(CanvasGenerationItem.status).where(
                CanvasGenerationItem.generation_id == generation.id
            )
        ).all()
    )
    target = aggregate_generation_status(statuses, generation.status)
    if target != generation.status:
        transition_generation(generation.status, target)
        generation.status = target
    generation.succeeded_items = statuses.count("succeeded")
    generation.failed_items = statuses.count("failed")
    generation.cancelled_items = statuses.count("cancelled")
    generation.unknown_items = statuses.count("unknown")
    if target in {"succeeded", "partially_failed", "failed", "cancelled", "unknown"}:
        generation.completed_at = now
        release_generation_reservation(db, generation_id=generation.id)


def promote_materialized_provider_result(
    db: Session,
    *,
    attempt_id: str,
    claim_token: str | None,
    provider_request_id: str | None,
    external_task_id: str | None,
    now: datetime,
) -> CanvasAssetOperation:
    """Atomically publish background+preview and queue its immutable compose work.

    This function deliberately does not look up an output board or current
    project snapshot.  The Item snapshot is the historical truth, so deleting
    a board during a paid request cannot discard or recreate a result.
    """

    attempt = db.get(CanvasGenerationAttempt, attempt_id)
    if attempt is None:
        raise GenerationResultError("generation attempt is unavailable")
    item = db.get(CanvasGenerationItem, attempt.item_id)
    generation = db.get(CanvasGeneration, item.generation_id) if item is not None else None
    if item is None or generation is None:
        raise GenerationResultError("generation result owner is unavailable")
    if attempt.background_asset_id is not None and attempt.compose_operation_id is not None:
        operation = db.get(CanvasAssetOperation, attempt.compose_operation_id)
        if operation is None:
            raise GenerationResultError("generation compose operation is unavailable")
        return operation
    active_claim = (
        attempt.status in {"submitting", "polling", "cancel_requested"}
        and claim_token is not None
        and attempt.worker_id == claim_token
        and attempt.lease_expires_at is not None
        and attempt.lease_expires_at >= now
    )
    recoverable_local_stage = (
        claim_token is None
        and attempt.status in {"submitting", "polling", "succeeded"}
        and attempt.provider_result_stage == "receiving"
        and (
            attempt.worker_id is None
            or attempt.lease_expires_at is None
            or attempt.lease_expires_at < now
        )
    )
    if not active_claim and not recoverable_local_stage:
        raise GenerationResultError("generation attempt is not ready for result promotion")
    data = read_verified_temporary_result(project_id=generation.project_id, attempt_id=attempt.id)
    background = assets.persist_derived_image(
        db,
        project_id=generation.project_id,
        asset_type="generated_background",
        data=data,
        mime_type="image/png",
        source_asset_id=None,
        metadata={
            "attemptId": attempt.id,
            "providerId": attempt.provider_id,
            "providerRequestId": attempt.provider_request_id,
            "sourceFormat": "provider-normalized",
            "verifiedSha256": hashlib.sha256(data).hexdigest(),
        },
        processor_version="provider-result-v1",
        generation_id=generation.id,
    )
    if background.width * background.height > CANVAS_MAX_IMAGE_PIXELS:
        raise GenerationResultError("Provider image dimensions are unsafe")
    background_preview = previews.create_preview_proxy(
        db,
        project_id=generation.project_id,
        source_asset=background,
        generation_id=generation.id,
    )
    request = _compose_request_from_item(
        generation=generation,
        item=item,
        background=background,
    )
    operation = operations.enqueue_asset_operation(
        db,
        project_id=generation.project_id,
        operation_type="compose",
        input_asset_id=background.id,
        idempotency_key=f"generation-compose:{attempt.id}",
        request_snapshot=request.model_dump(by_alias=True),
    )
    operation.processor_version = "pillow-12.3.0-compose-v1"
    if attempt.status != "succeeded":
        transition_attempt(attempt.status, "succeeded")
        attempt.status = "succeeded"
    attempt.provider_accepted_at = attempt.provider_accepted_at or now
    attempt.submitted_at = attempt.submitted_at or now
    attempt.provider_request_id = provider_request_id or attempt.provider_request_id
    attempt.external_task_id = external_task_id or attempt.external_task_id
    attempt.worker_id = None
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.background_asset_id = background.id
    attempt.background_preview_asset_id = background_preview.id
    attempt.compose_operation_id = operation.id
    attempt.provider_result_stage = "composing"
    item.latest_background_asset_id = background.id
    transition_item(item.status, "composing")
    item.status = "composing"
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=attempt,
        event_type="generation.item.composing",
    )
    return operation


def complete_generation_compose(
    db: Session,
    *,
    operation_id: str,
    composed: CanvasAsset,
    composed_preview: CanvasAsset,
    now: datetime,
) -> bool:
    """Link a successful local compose operation to its immutable Item result."""

    attempt = db.scalar(
        select(CanvasGenerationAttempt).where(
            CanvasGenerationAttempt.compose_operation_id == operation_id
        )
    )
    if attempt is None:
        return False
    item = db.get(CanvasGenerationItem, attempt.item_id)
    generation = db.get(CanvasGeneration, item.generation_id) if item is not None else None
    if item is None or generation is None:
        raise GenerationResultError("generation compose owner is unavailable")
    if attempt.status != "succeeded" or attempt.provider_result_stage != "composing":
        raise GenerationResultError("generation compose is not current")
    attempt.composed_asset_id = composed.id
    attempt.composed_preview_asset_id = composed_preview.id
    attempt.provider_result_stage = "complete"
    attempt.completed_at = now
    item.latest_composed_asset_id = composed.id
    transition_item(item.status, "succeeded")
    item.status = "succeeded"
    item.completed_at = now
    _aggregate_generation(db, generation, now=now)
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=attempt,
        event_type="generation.item.succeeded",
    )
    return True


def fail_generation_compose(
    db: Session,
    *,
    operation_id: str,
    now: datetime,
) -> bool:
    """Terminally fail only the Item whose immutable compose work failed."""

    attempt = db.scalar(
        select(CanvasGenerationAttempt).where(
            CanvasGenerationAttempt.compose_operation_id == operation_id
        )
    )
    if attempt is None:
        return False
    item = db.get(CanvasGenerationItem, attempt.item_id)
    generation = db.get(CanvasGeneration, item.generation_id) if item is not None else None
    if item is None or generation is None:
        raise GenerationResultError("generation compose owner is unavailable")
    if item.status in {"succeeded", "failed", "cancelled"}:
        return False
    transition_item(item.status, "failed")
    item.status = "failed"
    item.safe_current_error_code = "canvas_compose_failed"
    item.safe_current_error_summary = "Canvas composition could not be completed"
    item.completed_at = now
    _aggregate_generation(db, generation, now=now)
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=attempt,
        event_type="generation.item.compose_failed",
    )
    return True


__all__ = [
    "GenerationResultError",
    "MaterializedProviderResult",
    "complete_generation_compose",
    "fail_generation_compose",
    "materialize_provider_result",
    "promote_materialized_provider_result",
    "read_verified_temporary_result",
    "remove_verified_temporary_result",
]
