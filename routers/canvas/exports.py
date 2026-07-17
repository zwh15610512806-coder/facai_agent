"""HTTP boundary for authoritative Product Canvas exports."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from routers.canvas.operations import operation_json
from services.canvas import operations, projects, storage
from services.canvas.composition import CompositionValidationError
from services.canvas.compose_operations import CanvasComposeRequestError
from services.canvas.export_schemas import CanvasExportCreate
from services.canvas.exports import CanvasExportError, enqueue_canvas_export


router = APIRouter()


def _domain_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, (projects.CanvasProjectNotFound, operations.CanvasOperationNotFound)):
        return JSONResponse(
            {"detail": "Canvas resource not found", "code": "canvas_resource_not_found"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, projects.CanvasRevisionConflict):
        return JSONResponse(
            {
                "detail": "Canvas project revision conflict",
                "code": "canvas_revision_conflict",
                "currentRevision": exc.current_revision,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, projects.CanvasProjectStatusConflict):
        return JSONResponse(
            {
                "detail": "Canvas project status conflict",
                "code": "canvas_project_status_conflict",
                "status": exc.status,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, operations.CanvasOperationIdempotencyConflict):
        return JSONResponse(
            {
                "detail": "Canvas export idempotency conflict",
                "code": "canvas_export_idempotency_conflict",
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, storage.CanvasStorageError):
        return JSONResponse(
            {"detail": "Canvas export has insufficient storage capacity", "code": exc.code},
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
        )
    if isinstance(
        exc,
        (CanvasExportError, CanvasComposeRequestError, CompositionValidationError),
    ):
        return JSONResponse(
            {"detail": str(exc), "code": "canvas_export_invalid"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    raise exc


@router.post(
    "/projects/{project_id}/exports",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_export(
    project_id: str,
    payload: CanvasExportCreate,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=16, max_length=128),
    ],
    db: Session = Depends(get_db),
):
    try:
        operation = enqueue_canvas_export(
            db,
            project_id=project_id,
            request=payload,
            idempotency_key=idempotency_key,
        )
        db.commit()
        db.refresh(operation)
        return operation_json(operation)
    except Exception as exc:
        db.rollback()
        return _domain_error(exc)


__all__ = ["router"]
