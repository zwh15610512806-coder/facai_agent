"""Thin HTTP boundary for durable Product Canvas generations."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from canvas_models import CanvasGenerationItem
from database import get_db
from services.canvas.access import require_canvas_paid_access
from services.canvas.generation.repository import (
    CanvasGenerationActiveConflict,
    CanvasGenerationIdempotencyConflict,
    CanvasGenerationNotFound,
    CanvasGenerationTransactionError,
    CanvasGenerationValidationError,
    create_generation,
    get_generation_detail,
    list_board_result_versions,
)
from services.canvas.generation.recovery import (
    CanvasGenerationActionConflict,
    request_generation_cancel,
    resolve_unknown_item,
    retry_generation_item,
)
from services.canvas.generation.schemas import (
    CanvasGenerationCreate,
    GenerationDetail,
    ResultVersionPage,
)
from services.canvas.projects import (
    CanvasProjectNotFound,
    CanvasProjectStatusConflict,
    CanvasRevisionConflict,
)
from services.canvas.storage import CanvasStorageError


router = APIRouter()


class UnknownResolutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["abandon", "retry"]


def _domain_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, (CanvasProjectNotFound, CanvasGenerationNotFound)):
        return JSONResponse(
            {"detail": "Canvas resource not found", "code": "canvas_resource_not_found"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, CanvasRevisionConflict):
        return JSONResponse(
            {
                "detail": "Canvas project revision conflict",
                "code": "canvas_revision_conflict",
                "currentRevision": exc.current_revision,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, CanvasProjectStatusConflict):
        return JSONResponse(
            {
                "detail": "Canvas project status conflict",
                "code": "canvas_project_status_conflict",
                "status": exc.status,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, CanvasGenerationIdempotencyConflict):
        return JSONResponse(
            {"detail": str(exc), "code": "canvas_generation_idempotency_conflict"},
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, CanvasGenerationActiveConflict):
        return JSONResponse(
            {"detail": str(exc), "code": "canvas_generation_active_conflict"},
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, CanvasGenerationActionConflict):
        return JSONResponse(
            {"detail": str(exc), "code": "canvas_generation_action_conflict"},
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, CanvasGenerationTransactionError):
        return JSONResponse(
            {"detail": "Canvas generation is temporarily busy", "code": "canvas_generation_busy"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, CanvasStorageError):
        return JSONResponse(
            {"detail": "Canvas generation has insufficient storage capacity", "code": exc.code},
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
        )
    if isinstance(exc, CanvasGenerationValidationError):
        return JSONResponse(
            {"detail": str(exc), "code": "canvas_generation_invalid"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    raise exc


@router.post(
    "/projects/{project_id}/generations",
    response_model=GenerationDetail,
    dependencies=[Depends(require_canvas_paid_access)],
)
def post_generation(
    project_id: str,
    payload: CanvasGenerationCreate,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=16, max_length=128),
    ],
    db: Session = Depends(get_db),
):
    try:
        generation, created = create_generation(
            db,
            project_id=project_id,
            request=payload,
            idempotency_key=idempotency_key,
        )
        response.status_code = (
            status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
        return get_generation_detail(db, generation_id=generation.id)
    except Exception as exc:
        return _domain_error(exc)


@router.get("/generations/{generation_id}", response_model=GenerationDetail)
def get_generation(generation_id: str, db: Session = Depends(get_db)):
    try:
        return get_generation_detail(db, generation_id=generation_id)
    except Exception as exc:
        return _domain_error(exc)


@router.post(
    "/generations/{generation_id}/cancel",
    response_model=GenerationDetail,
    dependencies=[Depends(require_canvas_paid_access)],
)
def cancel_generation(generation_id: str, db: Session = Depends(get_db)):
    try:
        generation = request_generation_cancel(db, generation_id=generation_id)
        db.commit()
        return get_generation_detail(db, generation_id=generation.id)
    except Exception as exc:
        db.rollback()
        return _domain_error(exc)


@router.post(
    "/generation-items/{item_id}/retry",
    response_model=GenerationDetail,
    dependencies=[Depends(require_canvas_paid_access)],
)
def retry_generation_item_route(item_id: str, db: Session = Depends(get_db)):
    try:
        retry_generation_item(db, item_id=item_id)
        item = db.get(CanvasGenerationItem, item_id)
        if item is None:
            raise CanvasGenerationNotFound("generation item does not exist")
        generation_id = item.generation_id
        db.commit()
        return get_generation_detail(db, generation_id=generation_id)
    except Exception as exc:
        db.rollback()
        return _domain_error(exc)


@router.post(
    "/generation-items/{item_id}/resolve-unknown",
    response_model=GenerationDetail,
    dependencies=[Depends(require_canvas_paid_access)],
)
def resolve_unknown_generation_item(
    item_id: str,
    payload: UnknownResolutionPayload,
    db: Session = Depends(get_db),
):
    try:
        item = db.get(CanvasGenerationItem, item_id)
        if item is None:
            raise CanvasGenerationNotFound("generation item does not exist")
        generation_id = item.generation_id
        resolve_unknown_item(db, item_id=item_id, action=payload.action)
        db.commit()
        return get_generation_detail(db, generation_id=generation_id)
    except Exception as exc:
        db.rollback()
        return _domain_error(exc)


@router.get(
    "/projects/{project_id}/result-versions",
    response_model=ResultVersionPage,
)
def get_result_versions(
    project_id: str,
    board_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=1024),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        return list_board_result_versions(
            db,
            project_id=project_id,
            board_id=board_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        return _domain_error(exc)


__all__ = ["router"]
