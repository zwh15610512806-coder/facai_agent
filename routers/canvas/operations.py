"""Thin HTTP boundary for Product Canvas operation reads and retries."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.orm import Session

from database import get_db
from services.canvas import operations as operation_service
from services.canvas import projects as project_service
from services.canvas import compose_operations as compose_service
from services.canvas.composition import CompositionValidationError
from services.canvas.events import _safe_operation_error
from services.canvas.schemas import CanvasWireModel, Identifier


router = APIRouter()


_KNOWN_DOMAIN_ERRORS = (
    operation_service.CanvasOperationNotFound,
    operation_service.CanvasOperationIdempotencyConflict,
    operation_service.CanvasOperationStatusConflict,
    project_service.CanvasProjectStatusConflict,
    project_service.CanvasProjectNotFound,
    project_service.CanvasRevisionConflict,
    compose_service.CanvasComposeRequestError,
    CompositionValidationError,
)


class ComposeRequest(CanvasWireModel):
    revision: int = Field(ge=1)
    board_id: Identifier
    background_asset_id: Identifier
    idempotency_key: Identifier


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, operation_service.CanvasOperationNotFound):
        return JSONResponse(
            {
                "detail": "Canvas resource not found",
                "code": "canvas_resource_not_found",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, project_service.CanvasProjectNotFound):
        return JSONResponse(
            {"detail": "Canvas resource not found", "code": "canvas_resource_not_found"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, project_service.CanvasRevisionConflict):
        return JSONResponse(
            {
                "detail": "Canvas project revision conflict",
                "code": "canvas_revision_conflict",
                "currentRevision": exc.current_revision,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, operation_service.CanvasOperationIdempotencyConflict):
        return JSONResponse(
            {
                "detail": "Canvas operation idempotency conflict",
                "code": "canvas_operation_idempotency_conflict",
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, operation_service.CanvasOperationStatusConflict):
        return JSONResponse(
            {
                "detail": "Canvas operation status conflict",
                "code": "canvas_operation_status_conflict",
                "status": exc.status,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, project_service.CanvasProjectStatusConflict):
        return JSONResponse(
            {
                "detail": "Canvas project status conflict",
                "code": "canvas_project_status_conflict",
                "status": exc.status,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, (compose_service.CanvasComposeRequestError, CompositionValidationError)):
        return JSONResponse(
            {
                "detail": "Canvas composition request is invalid",
                "code": "canvas_composition_invalid",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    raise AssertionError(f"unmapped known Canvas operation error: {type(exc).__name__}")


def _call_service(function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except _KNOWN_DOMAIN_ERRORS as exc:
        return _error_response(exc)


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        loaded = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def operation_json(operation: Any) -> dict[str, Any]:
    return {
        "id": operation.id,
        "projectId": operation.project_id,
        "operationType": operation.operation_type,
        "status": operation.status,
        "attemptCount": operation.attempt_count,
        "workerId": operation.worker_id,
        "leaseExpiresAt": _timestamp(operation.lease_expires_at),
        "heartbeatAt": _timestamp(operation.heartbeat_at),
        "nextAttemptAt": _timestamp(operation.next_attempt_at),
        "cancelRequestedAt": _timestamp(operation.cancel_requested_at),
        "inputAssetId": operation.input_asset_id,
        "outputAssetId": operation.output_asset_id,
        "requestSnapshot": _json_object(operation.request_snapshot_json),
        "processorVersion": operation.processor_version,
        "idempotencyKey": operation.idempotency_key,
        "safeError": (
            _safe_operation_error(operation.safe_error_json)
            if operation.safe_error_json is not None
            else None
        ),
        "createdAt": _timestamp(operation.created_at),
        "updatedAt": _timestamp(operation.updated_at),
        "startedAt": _timestamp(operation.started_at),
        "completedAt": _timestamp(operation.completed_at),
    }


@router.get("/projects/{project_id}/operations")
def list_project_operations(project_id: str, db: Session = Depends(get_db)):
    operations = _call_service(
        operation_service.list_project_operations,
        db,
        project_id=project_id,
    )
    if isinstance(operations, Response):
        return operations
    return {"operations": [operation_json(operation) for operation in operations]}


@router.post(
    "/projects/{project_id}/compose",
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_compose(
    project_id: str,
    payload: ComposeRequest,
    db: Session = Depends(get_db),
):
    operation = _call_service(
        compose_service.enqueue_compose_operation,
        db,
        project_id=project_id,
        expected_revision=payload.revision,
        board_id=payload.board_id,
        background_asset_id=payload.background_asset_id,
        idempotency_key=payload.idempotency_key,
    )
    if isinstance(operation, Response):
        return operation
    try:
        db.commit()
        db.refresh(operation)
    except Exception:
        db.rollback()
        raise
    return operation_json(operation)


@router.get("/operations/{operation_id}")
def get_operation(operation_id: str, db: Session = Depends(get_db)):
    operation = _call_service(
        operation_service.get_asset_operation,
        db,
        operation_id=operation_id,
    )
    if isinstance(operation, Response):
        return operation
    return operation_json(operation)


@router.post("/operations/{operation_id}/retry")
def retry_operation(operation_id: str, db: Session = Depends(get_db)):
    operation = _call_service(
        operation_service.retry_asset_operation,
        db,
        operation_id=operation_id,
    )
    if isinstance(operation, Response):
        return operation
    try:
        db.commit()
        db.refresh(operation)
    except Exception:
        db.rollback()
        raise
    return operation_json(operation)


__all__ = ["ComposeRequest", "operation_json", "router"]
