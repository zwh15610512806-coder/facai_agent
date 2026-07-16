"""Authoritative saved-state composition requests and leased worker handler."""
from __future__ import annotations

import io
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from PIL import Image
from config import CANVAS_MAX_IMAGE_PIXELS
from pydantic import Field, model_validator
from sqlalchemy import select

from canvas_models import CanvasAsset, CanvasAssetOperation, CanvasProject
from services.canvas import assets, operations, previews, projects
from services.canvas.composition import (
    CompositionValidationError,
    build_composition_specs,
    composition_layout_hash,
    map_product_to_board,
)
from services.canvas.composition_schema import (
    CompositionSpec,
    CompositionWireModel,
    PixelPlacement,
    PixelSize,
)
from services.canvas.compositor import (
    COMPOSE_PROCESSOR_VERSION,
    LockedProductLayer,
    compose_image,
    compose_to_asset,
    encode_composed_png,
)
from services.canvas.font_resource import (
    FONT_FAMILY,
    FONT_RESOURCE_VERSION,
    FONT_SHA256,
)
from services.canvas.schemas import Identifier, TextSnapshot


_BACKGROUND_TYPES = frozenset({"generated_background", "working"})


class CanvasComposeError(ValueError):
    """Base class for safe authoritative composition failures."""


class CanvasComposeRequestError(CanvasComposeError):
    """Raised when saved state cannot produce one authoritative request."""


class CanvasComposeClaimLost(RuntimeError):
    """Raised when a worker no longer owns the exact compose attempt."""


class CanvasComposeProcessingFailed(RuntimeError):
    safe_error = {
        "code": "canvas_compose_failed",
        "message": "Canvas composition could not be completed",
        "retryable": True,
    }


class ComposeAssetSnapshot(CompositionWireModel):
    asset_id: Identifier
    asset_type: Literal["cutout", "generated_background", "working"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0, le=32_768)
    height: int = Field(gt=0, le=32_768)


class ComposeProductSnapshot(CompositionWireModel):
    spec: CompositionSpec
    placement: PixelPlacement
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    render_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ComposeFontSnapshot(CompositionWireModel):
    family: Literal["Noto Sans CJK SC"]
    version: Literal[
        "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
    ]
    sha256: Literal[
        "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
    ]


class ComposeRequestSnapshot(CompositionWireModel):
    schema_version: Literal[1]
    project_revision: int = Field(ge=1)
    board_id: Identifier
    output_size: PixelSize
    background: ComposeAssetSnapshot
    products: list[ComposeProductSnapshot] = Field(min_length=1, max_length=500)
    text_layers: list[TextSnapshot] = Field(max_length=500)
    font: ComposeFontSnapshot
    processor_version: Literal["pillow-12.3.0-compose-v1"]

    @model_validator(mode="after")
    def background_type_is_safe(self) -> "ComposeRequestSnapshot":
        if self.background.asset_type not in _BACKGROUND_TYPES:
            raise ValueError("composition background type is unsupported")
        return self


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _live_asset(db: Any, *, project_id: str, asset_id: str) -> CanvasAsset:
    asset = db.execute(
        select(CanvasAsset).where(
            CanvasAsset.id == asset_id,
            CanvasAsset.project_id == project_id,
            CanvasAsset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if asset is None:
        raise CanvasComposeRequestError("composition asset is unavailable")
    return asset


def _selected_output(snapshot: projects.ProjectSnapshot, board: Any) -> Any:
    outputs = [
        output
        for output in snapshot.semantic_state.complete_set.outputs
        if output.output_type == board.output_type and output.sku_id == board.sku_id
    ]
    if len(outputs) != 1:
        raise CanvasComposeRequestError("composition board has no unique saved output settings")
    return outputs[0]


def build_compose_request_snapshot(
    db: Any,
    *,
    project_id: str,
    expected_revision: int,
    board_id: str,
    background_asset_id: str,
) -> tuple[CanvasAsset, ComposeRequestSnapshot]:
    """Build one immutable authoritative render request from the saved revision."""

    snapshot = projects.get_project_snapshot(db, project_id=project_id)
    if snapshot.project.status != "active":
        raise projects.CanvasProjectStatusConflict(snapshot.project.status)
    if snapshot.revision != expected_revision:
        raise projects.CanvasRevisionConflict(snapshot.revision)
    board = next(
        (candidate for candidate in snapshot.semantic_state.output_boards if candidate.id == board_id),
        None,
    )
    if board is None:
        raise CanvasComposeRequestError("composition board does not exist")
    output = _selected_output(snapshot, board)
    if output.composition_group_id is None:
        raise CanvasComposeRequestError("composition board has no saved composition group")
    background = _live_asset(
        db,
        project_id=project_id,
        asset_id=background_asset_id,
    )
    if (
        background.asset_type not in _BACKGROUND_TYPES
        or background.mime_type != "image/png"
        or background.width <= 0
        or background.height <= 0
    ):
        raise CanvasComposeRequestError("composition background is not a supported PNG asset")
    if (output.width is None) != (output.height is None):
        raise CanvasComposeRequestError("composition output dimensions must be saved together")
    output_size = (
        (background.width, background.height)
        if output.width is None
        else (output.width, output.height)
    )
    if output_size[0] * output_size[1] > CANVAS_MAX_IMAGE_PIXELS:
        raise CanvasComposeRequestError(
            "composition output exceeds the configured pixel limit"
        )
    live_assets = {
        asset.id: asset
        for asset in db.scalars(
            select(CanvasAsset).where(
                CanvasAsset.project_id == project_id,
                CanvasAsset.deleted_at.is_(None),
            )
        ).all()
    }
    sku_references = {sku.id: sku.reference_asset_id for sku in snapshot.skus}
    ratios = {
        (layer.sku_id or ""): {"width": output_size[0], "height": output_size[1]}
        for layer in snapshot.layout_state.product_layers
    }
    specs = build_composition_specs(
        project_id=project_id,
        semantic_state=snapshot.semantic_state,
        layout_state=snapshot.layout_state,
        sku_reference_asset_ids=sku_references,
        assets=live_assets,
        output_ratios=ratios,
    )
    selected_specs = [
        spec
        for spec in specs
        if spec.composition_group_id == output.composition_group_id and spec.sku_id == board.sku_id
    ]
    if len(selected_specs) != 1:
        raise CanvasComposeRequestError("composition board has no unique locked product")
    product_snapshots: list[dict[str, Any]] = []
    for spec in selected_specs:
        source = live_assets[spec.source_asset_id]
        render = live_assets[spec.render_asset_id]
        placement = map_product_to_board(
            spec.layout,
            source_size=(render.width, render.height),
            output_size=output_size,
        )
        product_snapshots.append(
            {
                "spec": spec.model_dump(by_alias=True),
                "placement": placement.model_dump(by_alias=True),
                "sourceSha256": source.sha256,
                "renderSha256": render.sha256,
            }
        )
    nodes = {node.id: node for node in snapshot.semantic_state.nodes}
    text_layers = [
        layer
        for layer in snapshot.layout_state.text_snapshots
        if (node := nodes.get(layer.node_id)) is not None
        and node.kind == "text_layer"
        and node.output_board_id in {None, board.id}
    ]
    request = ComposeRequestSnapshot.model_validate(
        {
            "schemaVersion": 1,
            "projectRevision": snapshot.revision,
            "boardId": board.id,
            "outputSize": {"width": output_size[0], "height": output_size[1]},
            "background": {
                "assetId": background.id,
                "assetType": background.asset_type,
                "sha256": background.sha256,
                "width": background.width,
                "height": background.height,
            },
            "products": product_snapshots,
            "textLayers": [layer.model_dump(by_alias=True) for layer in text_layers],
            "font": {
                "family": FONT_FAMILY,
                "version": FONT_RESOURCE_VERSION,
                "sha256": FONT_SHA256,
            },
            "processorVersion": COMPOSE_PROCESSOR_VERSION,
        }
    )
    return background, request


def enqueue_compose_operation(
    db: Any,
    *,
    project_id: str,
    expected_revision: int,
    board_id: str,
    background_asset_id: str,
    idempotency_key: str,
) -> CanvasAssetOperation:
    """Build a bounded immutable request from the saved revision and enqueue it."""

    background, request = build_compose_request_snapshot(
        db,
        project_id=project_id,
        expected_revision=expected_revision,
        board_id=board_id,
        background_asset_id=background_asset_id,
    )
    operation = operations.enqueue_asset_operation(
        db,
        project_id=project_id,
        operation_type="compose",
        input_asset_id=background.id,
        idempotency_key=idempotency_key,
        request_snapshot=request.model_dump(by_alias=True),
    )
    operation.processor_version = COMPOSE_PROCESSOR_VERSION
    db.flush([operation])
    return operation


def _claimed_operation(
    db: Any,
    *,
    operation_id: str,
    worker_id: str | None,
    attempt_count: int | None,
) -> tuple[CanvasAssetOperation, ComposeRequestSnapshot]:
    operation = db.get(CanvasAssetOperation, operation_id)
    if operation is None or operation.operation_type != "compose":
        raise CanvasComposeClaimLost("compose operation is unavailable")
    effective_worker = operation.worker_id if worker_id is None else worker_id
    effective_attempt = operation.attempt_count if attempt_count is None else attempt_count
    if (
        operation.status != "running"
        or not effective_worker
        or operation.worker_id != effective_worker
        or operation.attempt_count != effective_attempt
    ):
        raise CanvasComposeClaimLost("compose operation claim is no longer current")
    try:
        request = ComposeRequestSnapshot.model_validate_json(operation.request_snapshot_json)
    except Exception as exc:
        raise CanvasComposeProcessingFailed() from exc
    if request.background.asset_id != operation.input_asset_id:
        raise CanvasComposeProcessingFailed()
    return operation, request


def _asset_for_snapshot(db: Any, *, project_id: str, snapshot: ComposeAssetSnapshot) -> CanvasAsset:
    asset = _live_asset(db, project_id=project_id, asset_id=snapshot.asset_id)
    if (
        asset.asset_type != snapshot.asset_type
        or asset.sha256 != snapshot.sha256
        or asset.width != snapshot.width
        or asset.height != snapshot.height
        or asset.mime_type != "image/png"
    ):
        raise CanvasComposeProcessingFailed()
    return asset


def _product_assets(
    db: Any,
    *,
    project_id: str,
    product: ComposeProductSnapshot,
    output_size: tuple[int, int],
) -> tuple[CanvasAsset, CanvasAsset]:
    spec = product.spec
    if spec.project_id != project_id or spec.layout_hash != composition_layout_hash(spec.layout):
        raise CanvasComposeProcessingFailed()
    expected = map_product_to_board(
        spec.layout,
        source_size=(spec.source_size.width, spec.source_size.height),
        output_size=output_size,
    )
    if expected != product.placement:
        raise CanvasComposeProcessingFailed()
    source = _live_asset(db, project_id=project_id, asset_id=spec.source_asset_id)
    render = _live_asset(db, project_id=project_id, asset_id=spec.render_asset_id)
    if (
        source.asset_type != "working"
        or source.sha256 != product.source_sha256
        or (source.width, source.height) != (spec.source_size.width, spec.source_size.height)
        or render.sha256 != product.render_sha256
        or (render.width, render.height) != (source.width, source.height)
        or render.mime_type != "image/png"
    ):
        raise CanvasComposeProcessingFailed()
    if render.id == source.id:
        if source.transparency_status != "transparent" and not spec.allow_opaque_fallback:
            raise CanvasComposeProcessingFailed()
    elif render.asset_type != "cutout" or render.source_asset_id != source.id:
        raise CanvasComposeProcessingFailed()
    return source, render


def read_compose_request_inputs(
    db: Any,
    *,
    project_id: str,
    request: ComposeRequestSnapshot,
) -> tuple[bytes, list[bytes]]:
    """Revalidate one immutable compose snapshot and return verified bytes."""

    background = _asset_for_snapshot(
        db,
        project_id=project_id,
        snapshot=request.background,
    )
    background_bytes = assets.read_verified_asset_bytes(
        db,
        asset=background,
        project_id=project_id,
    )
    product_bytes: list[bytes] = []
    for product in request.products:
        source, render = _product_assets(
            db,
            project_id=project_id,
            product=product,
            output_size=(request.output_size.width, request.output_size.height),
        )
        # Both the locked source and the effective render are part of the
        # authoritative snapshot. A replaced source must invalidate the export
        # even when its cutout happens to remain readable.
        assets.read_verified_asset_bytes(db, asset=source, project_id=project_id)
        product_bytes.append(
            assets.read_verified_asset_bytes(db, asset=render, project_id=project_id)
        )
    return background_bytes, product_bytes


def _persist_failure(
    db_factory: Callable[[], Any],
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
) -> None:
    with db_factory() as db:
        try:
            updated = operations.mark_claimed_operation_failed(
                db,
                operation_id=operation_id,
                worker_id=worker_id,
                attempt_count=attempt_count,
                safe_error=CanvasComposeProcessingFailed.safe_error,
                now=_utcnow(),
            )
            if not updated:
                raise CanvasComposeClaimLost("compose claim was lost before failure persistence")
            # A compose Operation can be owned by a Generation Attempt.  Keep
            # the historical result terminal without changing live project
            # state; ordinary compose operations simply have no matching row.
            from services.canvas.generation.results import fail_generation_compose

            fail_generation_compose(
                db,
                operation_id=operation_id,
                now=_utcnow(),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise


def run_compose_operation(
    operation_id: str,
    *,
    db_factory: Callable[[], Any] | None = None,
    worker_id: str | None = None,
    attempt_count: int | None = None,
) -> CanvasAsset:
    """Read verified inputs, compose without a Session, then publish atomically."""

    if db_factory is None:
        from database import SessionLocal

        db_factory = SessionLocal
    effective_worker: str | None = None
    effective_attempt: int | None = None
    try:
        with db_factory() as db:
            operation, request = _claimed_operation(
                db,
                operation_id=operation_id,
                worker_id=worker_id,
                attempt_count=attempt_count,
            )
            effective_worker = operation.worker_id
            effective_attempt = operation.attempt_count
            project_id = operation.project_id
            background_bytes, product_bytes = read_compose_request_inputs(
                db,
                project_id=project_id,
                request=request,
            )
    except CanvasComposeClaimLost:
        raise
    except Exception as exc:
        if effective_worker is not None and effective_attempt is not None:
            _persist_failure(
                db_factory,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
            )
        raise CanvasComposeProcessingFailed() from exc

    opened: list[Image.Image] = []
    result: Image.Image | None = None
    try:
        with Image.open(io.BytesIO(background_bytes)) as decoded_background:
            decoded_background.load()
            if decoded_background.format != "PNG" or decoded_background.size != (
                request.background.width,
                request.background.height,
            ):
                raise CanvasComposeProcessingFailed()
            background_image = decoded_background.copy()
        opened.append(background_image)
        locked_products: list[LockedProductLayer] = []
        for product, data in zip(request.products, product_bytes, strict=True):
            with Image.open(io.BytesIO(data)) as decoded_product:
                decoded_product.load()
                if decoded_product.format != "PNG" or decoded_product.size != (
                    product.spec.source_size.width,
                    product.spec.source_size.height,
                ):
                    raise CanvasComposeProcessingFailed()
                image = decoded_product.copy()
            opened.append(image)
            locked_products.append(
                LockedProductLayer(image=image, placement=product.placement)
            )
        result = compose_image(
            background=background_image,
            products=locked_products,
            text_layers=request.text_layers,
            output_size=(request.output_size.width, request.output_size.height),
        )
        output_bytes = encode_composed_png(result)
    except CanvasComposeProcessingFailed:
        _persist_failure(
            db_factory,
            operation_id=operation_id,
            worker_id=effective_worker,
            attempt_count=effective_attempt,
        )
        raise
    except Exception as exc:
        _persist_failure(
            db_factory,
            operation_id=operation_id,
            worker_id=effective_worker,
            attempt_count=effective_attempt,
        )
        raise CanvasComposeProcessingFailed() from exc
    finally:
        if result is not None:
            result.close()
        for image in opened:
            image.close()

    with db_factory() as db:
        try:
            current, persisted_request = _claimed_operation(
                db,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
            )
            if persisted_request != request:
                raise CanvasComposeClaimLost("compose snapshot changed during processing")
            background = _asset_for_snapshot(
                db, project_id=project_id, snapshot=request.background
            )
            assets.read_verified_asset_bytes(db, asset=background, project_id=project_id)
            for product in request.products:
                source, render = _product_assets(
                    db,
                    project_id=project_id,
                    product=product,
                    output_size=(request.output_size.width, request.output_size.height),
                )
                assets.read_verified_asset_bytes(db, asset=source, project_id=project_id)
                assets.read_verified_asset_bytes(db, asset=render, project_id=project_id)
            from canvas_models import CanvasGenerationAttempt, CanvasGenerationItem

            generation_attempt = db.scalar(
                select(CanvasGenerationAttempt).where(
                    CanvasGenerationAttempt.compose_operation_id == current.id
                )
            )
            generation_id: str | None = None
            if generation_attempt is not None:
                generation_item = db.get(CanvasGenerationItem, generation_attempt.item_id)
                if generation_item is None:
                    raise CanvasComposeProcessingFailed()
                generation_id = generation_item.generation_id
            composed = compose_to_asset(
                db,
                project_id=project_id,
                spec=request.model_dump(by_alias=True),
                operation_id=operation_id,
                data=output_bytes,
                background_asset_id=background.id,
                generation_id=generation_id,
            )
            composed.transparency_status = "opaque"
            composed_preview = previews.create_preview_proxy(
                db,
                project_id=project_id,
                source_asset=composed,
                generation_id=generation_id,
            )
            completed = operations.mark_claimed_operation_succeeded(
                db,
                operation_id=current.id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
                output_asset_id=composed.id,
                now=_utcnow(),
            )
            if completed is None:
                raise CanvasComposeClaimLost("compose claim was lost before result persistence")
            if generation_attempt is not None:
                from services.canvas.generation.results import complete_generation_compose

                complete_generation_compose(
                    db,
                    operation_id=current.id,
                    composed=composed,
                    composed_preview=composed_preview,
                    now=_utcnow(),
                )
            db.flush()
            db.expunge(composed)
            db.commit()
            return composed
        except CanvasComposeClaimLost:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            _persist_failure(
                db_factory,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
            )
            raise CanvasComposeProcessingFailed() from exc


__all__ = [
    "CanvasComposeClaimLost",
    "CanvasComposeProcessingFailed",
    "CanvasComposeRequestError",
    "ComposeRequestSnapshot",
    "build_compose_request_snapshot",
    "enqueue_compose_operation",
    "read_compose_request_inputs",
    "run_compose_operation",
]
