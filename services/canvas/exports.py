"""Persistent authoritative Product Canvas export queue and builders."""
from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from PIL import Image, ImageColor
from sqlalchemy import select

from canvas_models import (
    CanvasAsset,
    CanvasAssetOperation,
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
)
from config import CANVAS_MAX_IMAGE_PIXELS
from services.canvas import assets, operations, projects
from services.canvas.compose_operations import (
    CanvasComposeProcessingFailed,
    ComposeRequestSnapshot,
    build_compose_request_snapshot,
    read_compose_request_inputs,
)
from services.canvas.compositor import LockedProductLayer, compose_image
from services.canvas.export_schemas import (
    CanvasExportCreate,
    ExportRequestSnapshot,
    ExportSelectionSnapshot,
)


EXPORT_PROCESSOR_VERSION = "canvas-authoritative-export-v1"
_WINDOWS_DEVICES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
})
_CONTROL_OR_SEPARATOR = re.compile(r"[\x00-\x1f\x7f/\\]+")
_SPACES = re.compile(r"\s+")


class CanvasExportError(ValueError):
    """Safe export request failure."""


class CanvasExportClaimLost(RuntimeError):
    pass


class CanvasExportProcessingFailed(RuntimeError):
    safe_error = {
        "code": "canvas_export_failed",
        "message": "Canvas export could not be completed",
        "retryable": True,
    }


def safe_export_component(value: str) -> str:
    """Return one bounded filename component safe on Windows and in ZIPs."""

    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = _CONTROL_OR_SEPARATOR.sub(" ", normalized)
    normalized = _SPACES.sub(" ", normalized).strip(" .")
    while ".." in normalized:
        normalized = normalized.replace("..", " ")
        normalized = _SPACES.sub(" ", normalized).strip(" .")
    if not normalized:
        normalized = "unnamed"
    stem = normalized.split(".", 1)[0].upper()
    if stem in _WINDOWS_DEVICES:
        normalized = f"_{normalized}"
    return normalized[:120].rstrip(" .") or "unnamed"


def unique_export_names(values: Iterable[str]) -> list[str]:
    counts: dict[str, int] = {}
    result: list[str] = []
    for value in values:
        base = safe_export_component(value)
        key = base.casefold()
        count = counts.get(key, 0) + 1
        counts[key] = count
        if count == 1:
            result.append(base)
        else:
            suffix = f" ({count})"
            result.append(f"{base[:120 - len(suffix)].rstrip(' .')}{suffix}")
    return result


def encode_export_image(
    image: Image.Image,
    *,
    format: str,
    jpeg_background: str | None,
) -> bytes:
    output = io.BytesIO()
    if format == "png":
        canonical = image.convert("RGBA")
        try:
            canonical.info.clear()
            canonical.save(output, format="PNG", optimize=False, compress_level=9)
        finally:
            canonical.close()
    elif format == "jpeg":
        if jpeg_background is None:
            raise CanvasExportError("JPEG exports require an explicit background")
        try:
            color = ImageColor.getrgb(jpeg_background)
        except ValueError as exc:
            raise CanvasExportError("JPEG background is invalid") from exc
        canonical = image.convert("RGBA")
        flattened = Image.new("RGB", canonical.size, color)
        try:
            flattened.paste(canonical, mask=canonical.getchannel("A"))
            flattened.info.clear()
            flattened.save(
                output,
                format="JPEG",
                quality=95,
                subsampling=0,
                optimize=False,
                progressive=False,
            )
        finally:
            canonical.close()
            flattened.close()
    elif format == "webp":
        canonical = image.convert("RGBA")
        try:
            canonical.info.clear()
            canonical.save(output, format="WEBP", lossless=True, method=6, exact=True)
        finally:
            canonical.close()
    else:
        raise CanvasExportError("export format is unsupported")
    return output.getvalue()


def stack_detail_images(images: Sequence[Image.Image]) -> Image.Image:
    if not images:
        raise CanvasExportError("detail long export requires images")
    width = max(image.width for image in images)
    height = sum(image.height for image in images)
    if width <= 0 or height <= 0 or width * height > CANVAS_MAX_IMAGE_PIXELS:
        raise CanvasExportError("detail long export exceeds the image limit")
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    y = 0
    for image in images:
        canonical = image.convert("RGBA")
        try:
            result.alpha_composite(canonical, dest=(0, y))
        finally:
            canonical.close()
        y += image.height
    result.info.clear()
    return result


def build_export_zip(entries: Sequence[tuple[str, bytes]]) -> bytes:
    if not entries or len(entries) > 50:
        raise CanvasExportError("export ZIP entry count is invalid")
    output = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for raw_name, data in entries:
            path = PurePosixPath(raw_name)
            if (
                not isinstance(data, bytes)
                or not data
                or path.is_absolute()
                or len(path.parts) != 1
                or path.name != raw_name
                or path.name in {".", ".."}
                or path.name.casefold() in seen
                or safe_export_component(path.stem) != path.stem
            ):
                raise CanvasExportError("export ZIP entry is unsafe")
            seen.add(path.name.casefold())
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            info.flag_bits |= 0x800
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _live_composed_asset(
    db: Any,
    *,
    project_id: str,
    asset_id: str,
    expected_sha256: str | None = None,
) -> CanvasAsset:
    asset = db.scalar(
        select(CanvasAsset).where(
            CanvasAsset.id == asset_id,
            CanvasAsset.project_id == project_id,
            CanvasAsset.asset_type == "composed",
            CanvasAsset.deleted_at.is_(None),
        )
    )
    if asset is None or (
        expected_sha256 is not None and asset.sha256 != expected_sha256
    ):
        raise CanvasExportError("selected composed version is unavailable")
    return asset


def _successful_version(
    db: Any,
    *,
    project_id: str,
    board_id: str,
    version_id: str,
    composed_asset_id: str,
) -> tuple[CanvasGenerationAttempt, CanvasGenerationItem]:
    row = db.execute(
        select(CanvasGenerationAttempt, CanvasGenerationItem)
        .join(CanvasGenerationItem, CanvasGenerationItem.id == CanvasGenerationAttempt.item_id)
        .join(CanvasGeneration, CanvasGeneration.id == CanvasGenerationItem.generation_id)
        .where(
            CanvasGeneration.project_id == project_id,
            CanvasGenerationAttempt.id == version_id,
            CanvasGenerationAttempt.status == "succeeded",
            CanvasGenerationAttempt.provider_result_stage == "complete",
            CanvasGenerationAttempt.composed_asset_id == composed_asset_id,
            CanvasGenerationItem.board_id == board_id,
        )
    ).one_or_none()
    if row is None:
        raise CanvasExportError("selected board version is not a completed project result")
    return row


def enqueue_canvas_export(
    db: Any,
    *,
    project_id: str,
    request: CanvasExportCreate,
    idempotency_key: str,
) -> CanvasAssetOperation:
    """Capture the current saved board state and enqueue one durable export."""

    project = projects.get_project_snapshot(db, project_id=project_id)
    if project.project.status != "active":
        raise projects.CanvasProjectStatusConflict(project.project.status)
    if project.revision != request.project_revision:
        raise projects.CanvasRevisionConflict(project.revision)
    boards = {board.id: board for board in project.semantic_state.output_boards}
    selections: list[ExportSelectionSnapshot] = []
    for selected in sorted(request.selected_boards, key=lambda item: item.order):
        board = boards.get(selected.board_id)
        if board is None or board.selected_result_asset_id != selected.composed_asset_id:
            raise CanvasExportError("selected result is not the current saved board version")
        if request.mode in {"detail_slices_zip", "detail_long"} and board.output_type != "detail":
            raise CanvasExportError("detail exports require detail boards only")
        attempt, item = _successful_version(
            db,
            project_id=project_id,
            board_id=board.id,
            version_id=selected.version_id,
            composed_asset_id=selected.composed_asset_id,
        )
        if attempt.background_asset_id is None:
            raise CanvasExportError("selected board version has no completed background")
        composed = _live_composed_asset(
            db,
            project_id=project_id,
            asset_id=selected.composed_asset_id,
        )
        if composed.source_asset_id != attempt.background_asset_id:
            raise CanvasExportError("selected board version lineage is invalid")
        _, authoritative = build_compose_request_snapshot(
            db,
            project_id=project_id,
            expected_revision=request.project_revision,
            board_id=board.id,
            background_asset_id=attempt.background_asset_id,
        )
        selections.append(
            ExportSelectionSnapshot.model_validate(
                {
                    "boardId": board.id,
                    "versionId": attempt.id,
                    "composedAssetId": composed.id,
                    "composedSha256": composed.sha256,
                    "outputType": board.output_type,
                    "skuId": item.sku_id_snapshot,
                    "skuName": item.sku_name_snapshot,
                    "order": selected.order,
                    "authoritativeRender": authoritative.model_dump(by_alias=True),
                }
            )
        )
    snapshot = ExportRequestSnapshot.model_validate(
        {
            "schemaVersion": 1,
            "projectId": project_id,
            "projectName": project.project.name,
            "projectRevision": project.revision,
            "mode": request.mode,
            "format": request.format,
            "jpegBackground": request.jpeg_background,
            "selectedBoards": [
                selection.model_dump(by_alias=True) for selection in selections
            ],
            "processorVersion": EXPORT_PROCESSOR_VERSION,
        }
    )
    operation = operations.enqueue_asset_operation(
        db,
        project_id=project_id,
        operation_type="export",
        input_asset_id=selections[0].composed_asset_id,
        idempotency_key=idempotency_key,
        request_snapshot=snapshot.model_dump(by_alias=True),
    )
    operation.processor_version = EXPORT_PROCESSOR_VERSION
    db.flush([operation])
    return operation


def _claimed_export(
    db: Any,
    *,
    operation_id: str,
    worker_id: str | None,
    attempt_count: int | None,
) -> tuple[CanvasAssetOperation, ExportRequestSnapshot]:
    operation = db.get(CanvasAssetOperation, operation_id)
    if operation is None or operation.operation_type != "export":
        raise CanvasExportClaimLost("export operation is unavailable")
    effective_worker = operation.worker_id if worker_id is None else worker_id
    effective_attempt = operation.attempt_count if attempt_count is None else attempt_count
    if (
        operation.status != "running"
        or not effective_worker
        or operation.worker_id != effective_worker
        or operation.attempt_count != effective_attempt
    ):
        raise CanvasExportClaimLost("export operation claim is no longer current")
    try:
        request = ExportRequestSnapshot.model_validate_json(operation.request_snapshot_json)
    except Exception as exc:
        raise CanvasExportProcessingFailed() from exc
    if (
        request.project_id != operation.project_id
        or request.selected_boards[0].composed_asset_id != operation.input_asset_id
    ):
        raise CanvasExportProcessingFailed()
    return operation, request


def _render_authoritative(
    request: ComposeRequestSnapshot,
    *,
    background_bytes: bytes,
    product_bytes: Sequence[bytes],
) -> Image.Image:
    opened: list[Image.Image] = []
    try:
        with Image.open(io.BytesIO(background_bytes)) as decoded:
            decoded.load()
            if decoded.format != "PNG" or decoded.size != (
                request.background.width,
                request.background.height,
            ):
                raise CanvasExportProcessingFailed()
            background = decoded.copy()
        opened.append(background)
        products: list[LockedProductLayer] = []
        for product, data in zip(request.products, product_bytes, strict=True):
            with Image.open(io.BytesIO(data)) as decoded:
                decoded.load()
                if decoded.format != "PNG" or decoded.size != (
                    product.spec.source_size.width,
                    product.spec.source_size.height,
                ):
                    raise CanvasExportProcessingFailed()
                product_image = decoded.copy()
            opened.append(product_image)
            products.append(
                LockedProductLayer(image=product_image, placement=product.placement)
            )
        return compose_image(
            background=background,
            products=products,
            text_layers=request.text_layers,
            output_size=(request.output_size.width, request.output_size.height),
        )
    finally:
        for image in opened:
            image.close()


def _output_extension(format: str) -> str:
    return {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}[format]


def _output_mime(format: str) -> str:
    return {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}[format]


def _selection_names(request: ExportRequestSnapshot) -> list[str]:
    raw: list[str] = []
    for selected in request.selected_boards:
        label = selected.sku_name or selected.sku_id or selected.output_type
        raw.append(f"{selected.order + 1:02d} {label}")
    return unique_export_names(raw)


def _build_deliverable(
    request: ExportRequestSnapshot,
    images: Sequence[Image.Image],
) -> tuple[bytes, str, str, int, int]:
    extension = _output_extension(request.format)
    project_name = safe_export_component(request.project_name)
    if request.mode == "single":
        image = images[0]
        return (
            encode_export_image(
                image,
                format=request.format,
                jpeg_background=request.jpeg_background,
            ),
            _output_mime(request.format),
            f"{project_name}{extension}",
            image.width,
            image.height,
        )
    if request.mode == "detail_long":
        combined = stack_detail_images(images)
        try:
            return (
                encode_export_image(
                    combined,
                    format=request.format,
                    jpeg_background=request.jpeg_background,
                ),
                _output_mime(request.format),
                f"{project_name} detail long{extension}",
                combined.width,
                combined.height,
            )
        finally:
            combined.close()
    names = _selection_names(request)
    entries = [
        (
            f"{name}{extension}",
            encode_export_image(
                image,
                format=request.format,
                jpeg_background=request.jpeg_background,
            ),
        )
        for name, image in zip(names, images, strict=True)
    ]
    suffix = "detail slices" if request.mode == "detail_slices_zip" else "category"
    return build_export_zip(entries), "application/zip", f"{project_name} {suffix}.zip", 0, 0


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
                safe_error=CanvasExportProcessingFailed.safe_error,
                now=_utcnow(),
            )
            if not updated:
                raise CanvasExportClaimLost("export claim was lost before failure persistence")
            db.commit()
        except Exception:
            db.rollback()
            raise


def run_export_operation(
    operation_id: str,
    *,
    db_factory: Callable[[], Any] | None = None,
    worker_id: str | None = None,
    attempt_count: int | None = None,
) -> CanvasAsset:
    """Render current saved-state snapshots and publish one durable export asset."""

    if db_factory is None:
        from database import SessionLocal

        db_factory = SessionLocal
    effective_worker: str | None = None
    effective_attempt: int | None = None
    try:
        with db_factory() as db:
            operation, request = _claimed_export(
                db,
                operation_id=operation_id,
                worker_id=worker_id,
                attempt_count=attempt_count,
            )
            effective_worker = operation.worker_id
            effective_attempt = operation.attempt_count
            inputs: list[tuple[bytes, list[bytes]]] = []
            total_pixels = 0
            for selected in request.selected_boards:
                _live_composed_asset(
                    db,
                    project_id=request.project_id,
                    asset_id=selected.composed_asset_id,
                    expected_sha256=selected.composed_sha256,
                )
                render = selected.authoritative_render
                total_pixels += render.output_size.width * render.output_size.height
                if total_pixels > CANVAS_MAX_IMAGE_PIXELS:
                    raise CanvasExportProcessingFailed()
                inputs.append(
                    read_compose_request_inputs(
                        db,
                        project_id=request.project_id,
                        request=render,
                    )
                )
    except CanvasExportClaimLost:
        raise
    except Exception as exc:
        if effective_worker is not None and effective_attempt is not None:
            _persist_failure(
                db_factory,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
            )
        raise CanvasExportProcessingFailed() from exc

    rendered: list[Image.Image] = []
    try:
        for selected, (background, products) in zip(
            request.selected_boards,
            inputs,
            strict=True,
        ):
            rendered.append(
                _render_authoritative(
                    selected.authoritative_render,
                    background_bytes=background,
                    product_bytes=products,
                )
            )
        output_bytes, mime_type, filename, width, height = _build_deliverable(
            request,
            rendered,
        )
    except Exception as exc:
        _persist_failure(
            db_factory,
            operation_id=operation_id,
            worker_id=effective_worker,
            attempt_count=effective_attempt,
        )
        raise CanvasExportProcessingFailed() from exc
    finally:
        for image in rendered:
            image.close()

    with db_factory() as db:
        try:
            current, persisted = _claimed_export(
                db,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
            )
            if persisted != request:
                raise CanvasExportClaimLost("export snapshot changed during processing")
            for selected in request.selected_boards:
                _live_composed_asset(
                    db,
                    project_id=request.project_id,
                    asset_id=selected.composed_asset_id,
                    expected_sha256=selected.composed_sha256,
                )
                read_compose_request_inputs(
                    db,
                    project_id=request.project_id,
                    request=selected.authoritative_render,
                )
            exported = assets.persist_export_file(
                db,
                project_id=request.project_id,
                data=output_bytes,
                mime_type=mime_type,
                original_filename=filename,
                source_asset_id=request.selected_boards[0].composed_asset_id,
                width=width,
                height=height,
                metadata={
                    "mode": request.mode,
                    "format": request.format,
                    "projectRevision": request.project_revision,
                    "selectedBoards": [
                        {
                            "boardId": selected.board_id,
                            "versionId": selected.version_id,
                            "composedAssetId": selected.composed_asset_id,
                            "order": selected.order,
                        }
                        for selected in request.selected_boards
                    ],
                },
                processor_version=EXPORT_PROCESSOR_VERSION,
            )
            completed = operations.mark_claimed_operation_succeeded(
                db,
                operation_id=current.id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
                output_asset_id=exported.id,
                now=_utcnow(),
            )
            if completed is None:
                raise CanvasExportClaimLost("export claim was lost before result persistence")
            db.flush()
            db.expunge(exported)
            db.commit()
            return exported
        except CanvasExportClaimLost:
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
            raise CanvasExportProcessingFailed() from exc


__all__ = [
    "CanvasExportClaimLost",
    "CanvasExportError",
    "CanvasExportProcessingFailed",
    "EXPORT_PROCESSOR_VERSION",
    "build_export_zip",
    "encode_export_image",
    "enqueue_canvas_export",
    "run_export_operation",
    "safe_export_component",
    "stack_detail_images",
    "unique_export_names",
]
