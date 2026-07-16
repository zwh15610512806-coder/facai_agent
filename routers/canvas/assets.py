"""Asset upload, content, retry, and reference-safe delete HTTP boundary."""
from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import JSONResponse
from PIL import Image
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasAsset,
    CanvasAssetOperation,
    CanvasProject,
    CanvasProjectSku,
)
from config import CANVAS_MAX_UPLOAD_BYTES
from database import get_db
from services.canvas import assets as asset_service
from services.canvas import previews, storage, transparency
from services.canvas.events import append_canvas_event
from services.canvas.project_state import (
    collect_asset_reference_sections,
    load_layout_state,
    load_semantic_state,
)
from services.canvas.schemas import CanvasWireModel, Identifier


router = APIRouter()
_READ_CHUNK_BYTES = 1024 * 1024


class CutoutRetryRequest(CanvasWireModel):
    client_request_id: Identifier


class CanvasAssetApiError(ValueError):
    def __init__(self, code: str, *, status_code: int):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class CanvasAssetReferenceConflict(CanvasAssetApiError):
    def __init__(self, references: set[str]):
        self.references = tuple(sorted(references))
        super().__init__(
            "canvas_asset_reference_conflict",
            status_code=status.HTTP_409_CONFLICT,
        )


def _operation_service():
    """Import lazily so transparent uploads do not initialize the worker layer."""
    from services.canvas import operations

    return operations


def _error_payload(code: str, *, detail: str, status_code: int, **extra: Any):
    return JSONResponse(
        {"detail": detail, "code": code, **extra},
        status_code=status_code,
    )


def _api_error_response(exc: CanvasAssetApiError) -> JSONResponse:
    if isinstance(exc, CanvasAssetReferenceConflict):
        return _error_payload(
            exc.code,
            detail="Canvas asset is still referenced",
            status_code=exc.status_code,
            references=list(exc.references),
        )
    details = {
        status.HTTP_404_NOT_FOUND: "Canvas asset not found",
        status.HTTP_409_CONFLICT: "Canvas asset request conflicts with current state",
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "Canvas upload is too large",
    }
    return _error_payload(
        exc.code,
        detail=details.get(exc.status_code, "Canvas asset request failed"),
        status_code=exc.status_code,
    )


def _storage_error_response(exc: storage.CanvasStorageError) -> JSONResponse:
    code = exc.code
    if code in {
        "canvas_asset_project_not_found",
        "canvas_asset_source_not_found",
        "canvas_asset_source_deleted",
        "canvas_preview_missing",
        "canvas_preview_source_not_found",
        "canvas_storage_asset_deleted",
        "canvas_storage_asset_missing",
    }:
        status_code = status.HTTP_404_NOT_FOUND
        detail = "Canvas asset not found"
    elif code in {
        "canvas_asset_project_inactive",
        "canvas_asset_source_project_mismatch",
        "canvas_preview_ambiguous",
        "canvas_preview_source_changed",
    }:
        status_code = status.HTTP_409_CONFLICT
        detail = "Canvas asset request conflicts with current state"
    elif code in {
        "canvas_image_too_large",
    }:
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        detail = "Canvas upload is too large"
    elif code in {
        "canvas_storage_low_disk",
        "canvas_storage_project_quota_exceeded",
        "canvas_storage_total_quota_exceeded",
    }:
        status_code = status.HTTP_507_INSUFFICIENT_STORAGE
        detail = "Canvas storage capacity is unavailable"
    elif code.startswith("canvas_image_") or code in {
        "canvas_asset_filename_invalid",
        "canvas_asset_metadata_invalid",
        "canvas_preview_source_invalid",
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = "Canvas image is invalid"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "Canvas asset storage failed"
    return _error_payload(code, detail=detail, status_code=status_code)


def _operation_error_response(exc: Exception) -> JSONResponse | None:
    """Map only known operation-domain failures without exposing identifiers."""
    from services.canvas import operations as operation_service
    from services.canvas import projects as project_service

    if isinstance(exc, operation_service.CanvasOperationNotFound):
        return _error_payload(
            "canvas_operation_not_found",
            detail="Canvas operation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, operation_service.CanvasOperationStatusConflict):
        return _error_payload(
            "canvas_operation_status_conflict",
            detail="Canvas operation status conflict",
            status_code=status.HTTP_409_CONFLICT,
            status=exc.status,
        )
    if isinstance(exc, operation_service.CanvasOperationIdempotencyConflict):
        return _error_payload(
            "canvas_operation_idempotency_conflict",
            detail="Canvas operation idempotency conflict",
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, project_service.CanvasProjectStatusConflict):
        return _error_payload(
            "canvas_project_status_conflict",
            detail="Canvas project status conflict",
            status_code=status.HTTP_409_CONFLICT,
            status=exc.status,
        )
    return None


def _metadata_json(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def asset_json(asset: CanvasAsset) -> dict[str, Any]:
    """Return an asset summary without exposing its server-side relative path."""
    return {
        "id": asset.id,
        "projectId": asset.project_id,
        "assetType": asset.asset_type,
        "originalFilename": asset.original_filename,
        "mimeType": asset.mime_type,
        "byteCount": int(asset.byte_count),
        "width": int(asset.width),
        "height": int(asset.height),
        "sha256": asset.sha256,
        "sourceAssetId": asset.source_asset_id,
        "transparencyStatus": asset.transparency_status,
        "processorVersion": asset.processor_version,
        "metadata": _metadata_json(asset.metadata_json),
    }


def operation_json(operation: CanvasAssetOperation) -> dict[str, Any]:
    return {
        "id": operation.id,
        "projectId": operation.project_id,
        "operationType": operation.operation_type,
        "status": operation.status,
        "attemptCount": int(operation.attempt_count),
        "inputAssetId": operation.input_asset_id,
        "outputAssetId": operation.output_asset_id,
        "createdAt": _timestamp(operation.created_at),
        "updatedAt": _timestamp(operation.updated_at),
        "startedAt": _timestamp(operation.started_at),
        "completedAt": _timestamp(operation.completed_at),
    }


def _active_asset(db: Session, asset_id: str) -> CanvasAsset:
    asset = db.scalar(
        select(CanvasAsset).where(
            CanvasAsset.id == asset_id,
            CanvasAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise CanvasAssetApiError(
            "canvas_asset_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return asset


def _require_project(db: Session, project_id: str) -> CanvasProject:
    project = db.get(CanvasProject, project_id)
    if project is None:
        raise CanvasAssetApiError(
            "canvas_project_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return project


def _require_active_asset_project(db: Session, asset: CanvasAsset) -> None:
    project_status = db.scalar(
        select(CanvasProject.status).where(CanvasProject.id == asset.project_id)
    )
    if project_status is None:
        raise CanvasAssetApiError(
            "canvas_asset_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if project_status != "active":
        raise CanvasAssetApiError(
            "canvas_asset_project_inactive",
            status_code=status.HTTP_409_CONFLICT,
        )


async def _bounded_upload_bytes(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > CANVAS_MAX_UPLOAD_BYTES:
            raise CanvasAssetApiError(
                "canvas_upload_too_large",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _verified_asset_bytes(db: Session, asset: CanvasAsset) -> bytes:
    return asset_service.read_verified_asset_bytes(
        db,
        asset=asset,
        project_id=asset.project_id,
    )


def _set_transparency_status(db: Session, working: CanvasAsset) -> str:
    data = _verified_asset_bytes(db, working)
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        is_transparent = transparency.has_effective_transparent_background(image)
    detected = "transparent" if is_transparent else "opaque"
    metadata = _metadata_json(working.metadata_json)
    metadata["transparencyProcessorVersion"] = transparency.TRANSPARENCY_PROCESSOR_VERSION
    working.metadata_json = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    working.transparency_status = detected
    return detected


def _asset_references(db: Session, asset: CanvasAsset) -> set[str]:
    references = asset_service.collect_generation_asset_references(
        db,
        project_id=asset.project_id,
        asset_id=asset.id,
    )
    references.update(
        asset_service.collect_export_asset_references(
            db,
            project_id=asset.project_id,
            asset_id=asset.id,
        )
    )
    if db.scalar(
        select(CanvasProjectSku.id).where(
            CanvasProjectSku.project_id == asset.project_id,
            CanvasProjectSku.reference_asset_id == asset.id,
            CanvasProjectSku.deleted_at.is_(None),
        ).limit(1)
    ) is not None:
        references.add("skuReference")

    project = db.get(CanvasProject, asset.project_id)
    if project is not None:
        semantic = load_semantic_state(
            project.semantic_state,
            schema_version=project.schema_version,
        )
        layout = load_layout_state(
            project.layout_state,
            schema_version=project.schema_version,
        )
        references.update(
            f"project:{section}"
            for section in collect_asset_reference_sections(
                semantic,
                layout,
                asset_id=asset.id,
            )
        )

    if db.scalar(
        select(CanvasAsset.id).where(
            CanvasAsset.project_id == asset.project_id,
            CanvasAsset.source_asset_id == asset.id,
        ).limit(1)
    ) is not None:
        references.add("derivedAsset")

    operation_directions = db.execute(
        select(
            CanvasAssetOperation.input_asset_id,
            CanvasAssetOperation.output_asset_id,
        ).where(
            CanvasAssetOperation.project_id == asset.project_id,
            or_(
                CanvasAssetOperation.input_asset_id == asset.id,
                CanvasAssetOperation.output_asset_id == asset.id,
            ),
        )
    ).all()
    if any(row.input_asset_id == asset.id for row in operation_directions):
        references.add("operationInput")
    if any(row.output_asset_id == asset.id for row in operation_directions):
        references.add("operationOutput")
    return references


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, db: Session = Depends(get_db)):
    try:
        _require_project(db, project_id)
        rows = db.scalars(
            select(CanvasAsset)
            .where(
                CanvasAsset.project_id == project_id,
                CanvasAsset.deleted_at.is_(None),
            )
            .order_by(CanvasAsset.id.asc())
        ).all()
        return {"assets": [asset_json(asset) for asset in rows]}
    except CanvasAssetApiError as exc:
        return _api_error_response(exc)


@router.post(
    "/projects/{project_id}/assets",
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        _require_project(db, project_id)
        data = await _bounded_upload_bytes(file)
        uploaded = asset_service.persist_uploaded_source(
            db,
            project_id=project_id,
            filename=file.filename or "",
            declared_mime=file.content_type or "",
            data=data,
        )
        detected = _set_transparency_status(db, uploaded.working)
        preview = previews.create_preview_proxy(
            db,
            project_id=project_id,
            source_asset=uploaded.working,
        )
        operation = None
        if detected == "opaque":
            operation = _operation_service().enqueue_automatic_cutout(
                db,
                project_id=project_id,
                input_asset_id=uploaded.working.id,
            )
        append_canvas_event(
            db,
            project_id=project_id,
            event_type="asset.uploaded",
            payload={
                "projectId": project_id,
                "sourceAssetId": uploaded.source.id,
                "workingAssetId": uploaded.working.id,
                "previewAssetId": preview.id,
                "transparencyStatus": detected,
            },
        )
        db.commit()
        return {
            "source": asset_json(uploaded.source),
            "working": asset_json(uploaded.working),
            "preview": asset_json(preview),
            "operation": operation_json(operation) if operation is not None else None,
        }
    except CanvasAssetApiError as exc:
        db.rollback()
        return _api_error_response(exc)
    except storage.CanvasStorageError as exc:
        db.rollback()
        return _storage_error_response(exc)
    except Exception as exc:
        db.rollback()
        mapped = _operation_error_response(exc)
        if mapped is not None:
            return mapped
        raise
    finally:
        await file.close()


@router.get("/assets/{asset_id}/content")
def get_asset_content(
    asset_id: str,
    variant: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        if variant not in {None, "preview"}:
            raise CanvasAssetApiError(
                "canvas_asset_variant_invalid",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        asset = _active_asset(db, asset_id)
        selected = previews.resolve_preview_asset(db, asset=asset) if variant else asset
        data = _verified_asset_bytes(db, selected)
        return Response(
            content=data,
            media_type=selected.mime_type,
            headers={
                "Content-Length": str(len(data)),
                "X-Content-Type-Options": "nosniff",
            },
        )
    except CanvasAssetApiError as exc:
        return _api_error_response(exc)
    except storage.CanvasStorageError as exc:
        return _storage_error_response(exc)


@router.get("/assets/{asset_id}/download")
def download_export(asset_id: str, db: Session = Depends(get_db)):
    try:
        asset = _active_asset(db, asset_id)
        if asset.asset_type != "export":
            raise CanvasAssetApiError(
                "canvas_export_not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        data = _verified_asset_bytes(db, asset)
        fallback = "canvas-export" + {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "application/zip": ".zip",
        }.get(asset.mime_type, "")
        encoded = quote(asset.original_filename, safe="")
        return Response(
            content=data,
            media_type=asset.mime_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'
                ),
                "Content-Length": str(len(data)),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )
    except CanvasAssetApiError as exc:
        return _api_error_response(exc)
    except storage.CanvasStorageError as exc:
        return _storage_error_response(exc)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    try:
        asset = _active_asset(db, asset_id)
        _require_active_asset_project(db, asset)
        references = _asset_references(db, asset)
        if references:
            raise CanvasAssetReferenceConflict(references)
        deleted_at = datetime.now(UTC).replace(tzinfo=None)
        deleted = db.execute(
            update(CanvasAsset)
            .where(
                CanvasAsset.id == asset.id,
                CanvasAsset.project_id == asset.project_id,
                CanvasAsset.deleted_at.is_(None),
                CanvasAsset.project_id.in_(
                    select(CanvasProject.id).where(CanvasProject.status == "active")
                ),
            )
            .values(deleted_at=deleted_at)
            .returning(CanvasAsset)
            .execution_options(synchronize_session="fetch")
        ).scalar_one_or_none()
        if deleted is None:
            _require_active_asset_project(db, asset)
            raise CanvasAssetApiError(
                "canvas_asset_not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        append_canvas_event(
            db,
            project_id=asset.project_id,
            event_type="asset.deleted",
            payload={
                "projectId": asset.project_id,
                "assetId": asset.id,
                "status": "deleted",
            },
        )
        db.commit()
        return {"assetId": asset.id, "status": "deleted"}
    except CanvasAssetApiError as exc:
        db.rollback()
        return _api_error_response(exc)
    except Exception:
        db.rollback()
        raise


@router.post("/assets/{asset_id}/cutout/retry")
def retry_asset_cutout(
    asset_id: str,
    payload: CutoutRetryRequest,
    db: Session = Depends(get_db),
):
    try:
        asset = _active_asset(db, asset_id)
        if asset.asset_type != "working":
            raise CanvasAssetApiError(
                "canvas_cutout_input_invalid",
                status_code=status.HTTP_409_CONFLICT,
            )
        operation = _operation_service().retry_cutout_for_asset(
            db,
            input_asset_id=asset.id,
            client_request_id=payload.client_request_id,
        )
        db.commit()
        return operation_json(operation)
    except CanvasAssetApiError as exc:
        db.rollback()
        return _api_error_response(exc)
    except Exception as exc:
        db.rollback()
        mapped = _operation_error_response(exc)
        if mapped is not None:
            return mapped
        raise
