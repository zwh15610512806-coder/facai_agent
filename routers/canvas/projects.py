"""Thin HTTP boundary for Product Canvas project and SKU services."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from services.canvas import projects as project_service
from services.canvas.composition import CompositionValidationError
from services.canvas.project_state import ProjectStateSizeError, upgrade_project_state
from services.canvas.schemas import (
    CanvasLayoutState,
    CanvasSemanticState,
    CanvasWireModel,
    Identifier,
    Name,
    Prompt,
    SkuCreate,
    SkuUpdate,
)


router = APIRouter()


def get_canvas_session_factory() -> Callable[[], Session]:
    """Return the session factory used by post-response project cleanup."""

    return SessionLocal


class ProjectCreateRequest(CanvasWireModel):
    name: Name


class ProjectUpdateRequest(CanvasWireModel):
    revision: int = Field(ge=1)
    name: Name


class ProjectStateRequest(CanvasWireModel):
    revision: int = Field(ge=1)
    semantic_state: CanvasSemanticState
    layout_state: CanvasLayoutState

    @model_validator(mode="before")
    @classmethod
    def migrate_raw_v1_state(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        semantic = value.get("semanticState")
        layout = value.get("layoutState")
        if not isinstance(semantic, dict) or not isinstance(layout, dict):
            return value
        if not (
            isinstance(semantic.get("compositionGroups"), list)
            and isinstance(semantic.get("nodes"), list)
            and isinstance(layout.get("productLayers"), list)
            and isinstance(layout.get("objectTransforms"), dict)
        ):
            return value
        upgraded_semantic, upgraded_layout, _ = upgrade_project_state(
            semantic_state=semantic,
            layout_state=layout,
            schema_version=1,
        )
        return {
            **value,
            "semanticState": upgraded_semantic,
            "layoutState": upgraded_layout,
        }


class RevisionRequest(CanvasWireModel):
    revision: int = Field(ge=1)


class SkuCreateRequest(CanvasWireModel):
    revision: int = Field(ge=1)
    name: Name
    reference_asset_id: Identifier | None = None
    prompt: Prompt = ""
    config: dict[str, Any] = Field(default_factory=dict)


class SkuUpdateRequest(CanvasWireModel):
    revision: int = Field(ge=1)
    name: Name | None = None
    reference_asset_id: Identifier | None = None
    prompt: Prompt | None = None
    config: dict[str, Any] | None = None
    sort_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_patch_field(self) -> "SkuUpdateRequest":
        if self.model_fields_set <= {"revision"}:
            raise ValueError("at least one SKU field is required")
        return self


_KNOWN_DOMAIN_ERRORS = (
    project_service.CanvasProjectNotFound,
    project_service.CanvasSkuNotFound,
    project_service.CanvasRevisionConflict,
    project_service.CanvasProjectStatusConflict,
    project_service.CanvasProjectActivityConflict,
    project_service.CanvasStateOwnershipError,
    project_service.CanvasProjectStateValidationError,
    project_service.CanvasSkuReferenceConflict,
    CompositionValidationError,
    ProjectStateSizeError,
)


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(
        exc,
        (
            project_service.CanvasProjectNotFound,
            project_service.CanvasSkuNotFound,
            project_service.CanvasStateOwnershipError,
        ),
    ):
        return JSONResponse(
            {
                "detail": "Canvas resource not found",
                "code": "canvas_resource_not_found",
            },
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
    if isinstance(exc, project_service.CanvasProjectStatusConflict):
        return JSONResponse(
            {
                "detail": "Canvas project status conflict",
                "code": "canvas_project_status_conflict",
                "status": exc.status,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, project_service.CanvasProjectActivityConflict):
        return JSONResponse(
            {
                "detail": "Canvas project has active work",
                "code": "canvas_project_activity_conflict",
                "activities": exc.activities,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, project_service.CanvasSkuReferenceConflict):
        return JSONResponse(
            {
                "detail": "Canvas SKU is still referenced",
                "code": "canvas_sku_reference_conflict",
                "references": list(exc.references),
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, ProjectStateSizeError):
        return JSONResponse(
            {
                "detail": "Canvas project state is too large",
                "code": "canvas_state_too_large",
            },
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if isinstance(exc, project_service.CanvasProjectStateValidationError):
        return JSONResponse(
            {
                "detail": "Canvas project state is invalid",
                "code": "canvas_state_invalid",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if isinstance(exc, CompositionValidationError):
        return JSONResponse(
            {
                "detail": "Canvas composition state is invalid",
                "code": "canvas_composition_invalid",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    raise AssertionError(f"unmapped known Canvas domain error: {type(exc).__name__}")


def _call_service(function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except _KNOWN_DOMAIN_ERRORS as exc:
        return _error_response(exc)


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def project_summary_json(project: Any) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "status": project.status,
        "schemaVersion": project.schema_version,
        "revision": project.revision,
        "createdAt": _timestamp(project.created_at),
        "updatedAt": _timestamp(project.updated_at),
        "archivedAt": _timestamp(project.archived_at),
    }


def project_snapshot_json(snapshot: project_service.ProjectSnapshot) -> dict[str, Any]:
    project = {
        **project_summary_json(snapshot.project),
        "semanticState": snapshot.semantic_state.model_dump(
            by_alias=True,
            mode="json",
            warnings=False,
        ),
        "layoutState": snapshot.layout_state.model_dump(
            by_alias=True,
            mode="json",
            warnings=False,
        ),
    }
    skus = [
        {
            "id": sku.id,
            "projectId": sku.project_id,
            "name": sku.name,
            "sortOrder": sku.sort_order,
            "referenceAssetId": sku.reference_asset_id,
            "prompt": sku.prompt,
            "config": json.loads(sku.config_json),
        }
        for sku in snapshot.skus
    ]
    return {"project": project, "skus": skus, "revision": snapshot.revision}


@router.get("/projects")
def list_projects(
    q: str | None = Query(default=None, max_length=200),
    include_archived: bool = Query(default=False, alias="includeArchived"),
    db: Session = Depends(get_db),
):
    result = _call_service(
        project_service.list_projects,
        db,
        query=q,
        include_archived=include_archived,
    )
    if isinstance(result, Response):
        return result
    return {"projects": [project_summary_json(project) for project in result]}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreateRequest, db: Session = Depends(get_db)):
    result = _call_service(project_service.create_project, db, name=payload.name)
    if isinstance(result, Response):
        return result
    snapshot = _call_service(
        project_service.get_project_snapshot,
        db,
        project_id=result.id,
    )
    if isinstance(snapshot, Response):
        return snapshot
    return project_snapshot_json(snapshot)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    snapshot = _call_service(
        project_service.get_project_snapshot,
        db,
        project_id=project_id,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    db: Session = Depends(get_db),
):
    snapshot = _call_service(
        project_service.update_project_metadata,
        db,
        project_id=project_id,
        expected_revision=payload.revision,
        name=payload.name,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


@router.put("/projects/{project_id}/state")
def save_project_state(
    project_id: str,
    payload: ProjectStateRequest,
    db: Session = Depends(get_db),
):
    snapshot = _call_service(
        project_service.save_project_state,
        db,
        project_id=project_id,
        expected_revision=payload.revision,
        semantic_state=payload.semantic_state,
        layout_state=payload.layout_state,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


def _transition_project(
    transition: Callable[..., Any],
    *,
    db: Session,
    project_id: str,
    revision: int,
):
    snapshot = _call_service(
        transition,
        db,
        project_id=project_id,
        expected_revision=revision,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


@router.post("/projects/{project_id}/archive")
def archive_project(
    project_id: str,
    payload: RevisionRequest,
    db: Session = Depends(get_db),
):
    return _transition_project(
        project_service.archive_project,
        db=db,
        project_id=project_id,
        revision=payload.revision,
    )


@router.post("/projects/{project_id}/restore")
def restore_project(
    project_id: str,
    payload: RevisionRequest,
    db: Session = Depends(get_db),
):
    return _transition_project(
        project_service.restore_project,
        db=db,
        project_id=project_id,
        revision=payload.revision,
    )


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    payload: RevisionRequest,
    background_tasks: BackgroundTasks,
    session_factory: Callable[[], Session] = Depends(get_canvas_session_factory),
    db: Session = Depends(get_db),
):
    result = _transition_project(
        project_service.request_project_deletion,
        db=db,
        project_id=project_id,
        revision=payload.revision,
    )
    if isinstance(result, Response):
        return result
    background_tasks.add_task(
        project_service.finalize_deleting_project,
        session_factory,
        project_id=project_id,
    )
    return result


@router.get("/projects/{project_id}/skus")
def list_skus(project_id: str, db: Session = Depends(get_db)):
    snapshot = _call_service(
        project_service.get_project_snapshot,
        db,
        project_id=project_id,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


@router.post("/projects/{project_id}/skus", status_code=status.HTTP_201_CREATED)
def create_sku(
    project_id: str,
    payload: SkuCreateRequest,
    db: Session = Depends(get_db),
):
    request = SkuCreate.model_validate(
        payload.model_dump(
            by_alias=True,
            exclude={"revision"},
            warnings=False,
        )
    )
    snapshot = _call_service(
        project_service.create_sku,
        db,
        project_id=project_id,
        expected_revision=payload.revision,
        request=request,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


@router.patch("/projects/{project_id}/skus/{sku_id}")
def update_sku(
    project_id: str,
    sku_id: str,
    payload: SkuUpdateRequest,
    db: Session = Depends(get_db),
):
    request = SkuUpdate.model_validate(
        payload.model_dump(
            by_alias=True,
            exclude={"revision"},
            exclude_unset=True,
            warnings=False,
        )
    )
    snapshot = _call_service(
        project_service.update_sku,
        db,
        project_id=project_id,
        sku_id=sku_id,
        expected_revision=payload.revision,
        request=request,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)


@router.delete("/projects/{project_id}/skus/{sku_id}")
def delete_sku(
    project_id: str,
    sku_id: str,
    payload: RevisionRequest,
    db: Session = Depends(get_db),
):
    snapshot = _call_service(
        project_service.delete_sku,
        db,
        project_id=project_id,
        sku_id=sku_id,
        expected_revision=payload.revision,
    )
    return snapshot if isinstance(snapshot, Response) else project_snapshot_json(snapshot)
