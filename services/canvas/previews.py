"""Deterministic preview proxies and strict explicit preview resolution."""
from __future__ import annotations

import hashlib
import io
import warnings
from types import SimpleNamespace
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from canvas_models import CanvasAsset
from config import CANVAS_PREVIEW_MAX_EDGE
from services.canvas import assets, storage


PREVIEW_PROCESSOR_VERSION = "preview-proxy-v1"
PREVIEW_MAX_EDGE = min(CANVAS_PREVIEW_MAX_EDGE, 2048)
_PREVIEW_SOURCE_TYPES = {
    "working",
    "cutout",
    "generated_background",
    "composed",
}


class CanvasPreviewError(assets.CanvasAssetPersistenceError):
    """Stable preview creation or lookup failure."""


def _reject(code: str, message: str) -> None:
    raise CanvasPreviewError(code, message)


def _source_record(db: Session, source_asset: Any, *, project_id: str | None) -> Any:
    source_id = getattr(source_asset, "id", None)
    if not isinstance(source_id, str):
        _reject("canvas_preview_source_not_found", "preview source asset does not exist")
    try:
        with db.no_autoflush:
            row = db.execute(
                select(
                    CanvasAsset.id,
                    CanvasAsset.project_id,
                    CanvasAsset.asset_type,
                    CanvasAsset.relative_path,
                    CanvasAsset.mime_type,
                    CanvasAsset.byte_count,
                    CanvasAsset.width,
                    CanvasAsset.height,
                    CanvasAsset.sha256,
                    CanvasAsset.deleted_at,
                ).where(CanvasAsset.id == source_id)
            ).mappings().one_or_none()
    except Exception as exc:
        raise CanvasPreviewError(
            "canvas_preview_database_failed",
            "preview source lookup failed",
        ) from exc
    if row is None or row["deleted_at"] is not None:
        _reject("canvas_preview_source_not_found", "preview source asset does not exist")
    if project_id is not None and row["project_id"] != project_id:
        _reject("canvas_preview_source_not_found", "preview source asset does not exist")
    if row["asset_type"] not in _PREVIEW_SOURCE_TYPES:
        _reject(
            "canvas_preview_source_invalid",
            "preview source type is not a full render asset",
        )
    return SimpleNamespace(**row)


def _validated_max_edge(max_edge: object) -> int:
    if type(max_edge) is not int or not 0 < max_edge <= PREVIEW_MAX_EDGE:
        _reject(
            "canvas_preview_max_edge_invalid",
            "preview max edge exceeds the configured limit",
        )
    return max_edge


def _read_verified_source(record: Any) -> bytes:
    try:
        path = storage.resolve_asset_path(record, project_id=record.project_id)
        with storage._pin_directory_chain(path.parent) as parent_chain:
            parent = parent_chain[-1]
            records = storage._directory_records(
                parent,
                max_entries=storage.CANVAS_MAX_TREE_ENTRIES,
            )
            source_record = next(
                (candidate for candidate in records if candidate.name == path.name),
                None,
            )
            if source_record is None:
                storage._reject("canvas_storage_asset_missing", "canvas asset file is missing")
            if source_record.is_directory or source_record.attributes & getattr(
                storage.stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            ):
                storage._reject(
                    "canvas_storage_unsafe_entry",
                    "canvas preview source is not a regular file",
                )
            pin = storage._open_record(parent, source_record)
            try:
                storage._refresh_pinned_file(pin)
                if pin.byte_count != record.byte_count:
                    _reject("canvas_preview_source_changed", "preview source content changed")
                data = storage._pinned_file_bytes(pin)
            finally:
                pin.close()
    except storage.CanvasStorageError:
        raise
    except OSError as exc:
        raise CanvasPreviewError(
            "canvas_preview_source_read_failed",
            "preview source could not be read",
        ) from exc
    if len(data) != record.byte_count or hashlib.sha256(data).hexdigest() != record.sha256:
        _reject("canvas_preview_source_changed", "preview source content changed")
    return data


def _proxy_dimensions(width: int, height: int, max_edge: int) -> tuple[int, int]:
    if max(width, height) <= max_edge:
        return width, height
    if width >= height:
        return max_edge, max(1, round(height * max_edge / width))
    return max(1, round(width * max_edge / height)), max_edge


def _render_proxy(data: bytes, *, record: Any, max_edge: int) -> bytes:
    canonical: Image.Image | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format != "PNG":
                    _reject("canvas_preview_source_invalid", "preview source must be PNG")
                source.load()
                if source.size != (record.width, record.height):
                    _reject("canvas_preview_source_changed", "preview source dimensions changed")
                has_alpha = "A" in source.getbands() or "transparency" in source.info
                canonical = source.convert("RGBA" if has_alpha else "RGB")
        target_size = _proxy_dimensions(record.width, record.height, max_edge)
        if canonical.size != target_size:
            resized = canonical.resize(target_size, Image.Resampling.LANCZOS)
            canonical.close()
            canonical = resized
        canonical.info.clear()
        output = io.BytesIO()
        canonical.save(
            output,
            format="PNG",
            optimize=False,
            compress_level=9,
        )
        return output.getvalue()
    except CanvasPreviewError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise CanvasPreviewError(
            "canvas_preview_source_invalid",
            "preview source exceeds safe decode limits",
        ) from exc
    except Exception as exc:
        raise CanvasPreviewError(
            "canvas_preview_source_invalid",
            "preview source could not be decoded",
        ) from exc
    finally:
        if canonical is not None:
            canonical.close()


def create_preview_proxy(
    db: Session,
    *,
    project_id: str,
    source_asset: CanvasAsset,
    max_edge: int = PREVIEW_MAX_EDGE,
    generation_id: str | None = None,
) -> CanvasAsset:
    """Create one explicit same-origin preview without committing the caller Session."""
    edge = _validated_max_edge(max_edge)
    record = _source_record(db, source_asset, project_id=project_id)
    source_data = _read_verified_source(record)
    proxy_data = _render_proxy(source_data, record=record, max_edge=edge)
    return assets.persist_derived_image(
        db,
        project_id=record.project_id,
        asset_type="preview",
        data=proxy_data,
        mime_type="image/png",
        source_asset_id=record.id,
        metadata={
            "maxEdge": edge,
            "processorVersion": PREVIEW_PROCESSOR_VERSION,
            "sourceAssetId": record.id,
            "sourceHeight": record.height,
            "sourceWidth": record.width,
        },
        processor_version=PREVIEW_PROCESSOR_VERSION,
        generation_id=generation_id,
    )


def resolve_preview_asset(db: Session, *, asset: CanvasAsset) -> CanvasAsset:
    """Resolve exactly one explicit active preview; never fall back to the source."""
    source = _source_record(db, asset, project_id=None)
    try:
        with db.no_autoflush:
            candidates = db.scalars(
                select(CanvasAsset)
                .where(
                    CanvasAsset.project_id == source.project_id,
                    CanvasAsset.source_asset_id == source.id,
                    CanvasAsset.asset_type == "preview",
                    CanvasAsset.deleted_at.is_(None),
                )
                .order_by(CanvasAsset.id)
                .limit(2)
            ).all()
    except Exception as exc:
        raise CanvasPreviewError(
            "canvas_preview_database_failed",
            "preview lookup failed",
        ) from exc
    if not candidates:
        _reject("canvas_preview_missing", "preview asset is missing")
    if len(candidates) != 1:
        _reject("canvas_preview_ambiguous", "preview asset relation is ambiguous")
    preview = candidates[0]
    storage.resolve_asset_path(preview, project_id=source.project_id)
    return preview
