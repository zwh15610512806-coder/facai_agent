"""Transactional project, state, lifecycle, and SKU services for Product Canvas."""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasAsset,
    CanvasAssetOperation,
    CanvasEvent,
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
    CanvasGenerationItemInput,
    CanvasProject,
    CanvasProjectSku,
)
from services.canvas import storage
from services.canvas.composition import build_composition_specs, validate_composition_state
from services.canvas.events import append_canvas_event
from services.canvas.graph import CanvasGraphValidationError, validate_canvas_graph
from services.canvas.project_state import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    MAX_PROJECT_STATE_BYTES,
    collect_asset_ids,
    collect_sku_ids,
    collect_sku_reference_sections,
    dump_project_state,
    empty_project_state_json,
    load_layout_state,
    load_semantic_state,
    upgrade_project_state,
)
from services.canvas.schemas import (
    CanvasLayoutState,
    CanvasSemanticState,
    Name,
    SkuCreate,
    SkuUpdate,
)


class CanvasProjectError(Exception):
    """Base class for Canvas project domain errors."""


class CanvasProjectNotFound(CanvasProjectError, LookupError):
    def __init__(self, project_id: str):
        self.project_id = project_id
        super().__init__(f"canvas project does not exist: {project_id}")


class CanvasSkuNotFound(CanvasProjectError, LookupError):
    def __init__(self, sku_id: str):
        self.sku_id = sku_id
        super().__init__(f"active canvas SKU does not exist: {sku_id}")


class CanvasRevisionConflict(CanvasProjectError):
    current_revision: int

    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__(f"canvas project revision is now {current_revision}")


class CanvasProjectStatusConflict(CanvasProjectError):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"canvas project status does not allow this write: {status}")


class CanvasProjectActivityConflict(CanvasProjectError):
    def __init__(self, activities: list[dict[str, Any]]):
        self.activities = activities
        super().__init__("canvas project has non-terminal or unresolved activity")


class CanvasStateOwnershipError(CanvasProjectError):
    def __init__(
        self,
        *,
        sku_ids: Iterable[str] = (),
        asset_ids: Iterable[str] = (),
    ):
        self.sku_ids = frozenset(sku_ids)
        self.asset_ids = frozenset(asset_ids)
        super().__init__("canvas state references SKUs or Assets outside the project")


class CanvasProjectStateValidationError(CanvasProjectError, ValueError):
    """Raised when a persisted project graph violates a system invariant."""


class CanvasSkuReferenceConflict(CanvasProjectError):
    def __init__(self, *, sku_id: str, references: Iterable[str]):
        self.sku_id = sku_id
        self.references = tuple(sorted(set(references)))
        super().__init__(f"canvas SKU is still referenced by live project state: {sku_id}")


@dataclass(frozen=True)
class ProjectSnapshot:
    project: CanvasProject
    skus: list[CanvasProjectSku]
    semantic_state: CanvasSemanticState
    layout_state: CanvasLayoutState

    @property
    def revision(self) -> int:
        return self.project.revision


ProjectActivityGuard = Callable[[Session, str], Any]
PROJECT_ACTIVITY_GUARDS: list[ProjectActivityGuard] = []

_TERMINAL_ACTIVITY_STATUSES = {
    "abandoned",
    "cancelled",
    "canceled",
    "completed",
    "done",
    "failed",
    "succeeded",
    "success",
}

_name_adapter = TypeAdapter(Name)


def register_canvas_project_activity_guard(guard: ProjectActivityGuard) -> None:
    if not callable(guard):
        raise TypeError("canvas project activity guard must be callable")
    if guard not in PROJECT_ACTIVITY_GUARDS:
        PROJECT_ACTIVITY_GUARDS.append(guard)


register_project_activity_guard = register_canvas_project_activity_guard


def _normalize_activity_result(result: Any) -> list[dict[str, Any]]:
    if result is None or result is False:
        return []
    if result is True:
        return [{"status": "active"}]
    if isinstance(result, str):
        return [{"status": result}]
    if isinstance(result, Mapping):
        return [dict(result)]
    try:
        entries = list(result)
    except TypeError as exc:
        raise TypeError("activity guards must return a mapping, iterable, bool, or None") from exc
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, str):
            normalized.append({"status": entry})
        elif isinstance(entry, Mapping):
            normalized.append(dict(entry))
        elif entry:
            normalized.append({"status": "active", "summary": str(entry)})
    return normalized


def _blocking_activities(db: Session, project_id: str) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for guard in tuple(PROJECT_ACTIVITY_GUARDS):
        for activity in _normalize_activity_result(guard(db, project_id)):
            status = str(activity.get("status", "unknown")).casefold()
            resolved_unknown = bool(
                activity.get("resolved")
                or activity.get("unknownResolved")
                or activity.get("unknown_resolved")
            )
            if status in _TERMINAL_ACTIVITY_STATUSES:
                continue
            if status == "unknown" and resolved_unknown:
                continue
            blocked.append(activity)
    return blocked


def _assert_no_blocking_activity(db: Session, project_id: str) -> None:
    activities = _blocking_activities(db, project_id)
    if activities:
        raise CanvasProjectActivityConflict(activities)


def _validate_expected_revision(expected_revision: int) -> None:
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise TypeError("expected_revision must be an integer")
    if expected_revision < 1:
        raise ValueError("expected_revision must be at least 1")


def _current_project_row(db: Session, project_id: str) -> tuple[int, str] | None:
    return db.execute(
        select(CanvasProject.revision, CanvasProject.status).where(CanvasProject.id == project_id)
    ).one_or_none()


def _raise_compare_and_swap_failure(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
) -> None:
    row = _current_project_row(db, project_id)
    if row is None:
        raise CanvasProjectNotFound(project_id)
    current_revision, current_status = row
    if current_revision != expected_revision:
        raise CanvasRevisionConflict(current_revision)
    raise CanvasProjectStatusConflict(current_status)


def _advance_project_revision(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
    allowed_statuses: tuple[str, ...] = ("active",),
    values: Mapping[str, Any] | None = None,
) -> int:
    """Atomically compare-and-swap one project revision and optional fields."""
    _validate_expected_revision(expected_revision)
    update_values: dict[str, Any] = dict(values or {})
    update_values.update(
        revision=CanvasProject.revision + 1,
        updated_at=func.now(),
    )
    statement = (
        update(CanvasProject)
        .where(
            CanvasProject.id == project_id,
            CanvasProject.revision == expected_revision,
            CanvasProject.status.in_(allowed_statuses),
        )
        .values(**update_values)
        .execution_options(synchronize_session=False)
    )
    result = db.execute(statement)
    if result.rowcount != 1:
        _raise_compare_and_swap_failure(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
        )
    return expected_revision + 1


def _detach_snapshot_rows(db: Session, project: CanvasProject, skus: list[CanvasProjectSku]) -> None:
    for row in [project, *skus]:
        if row in db:
            db.expunge(row)


def create_project(db: Session, *, name: str) -> CanvasProject:
    validated_name = _name_adapter.validate_python(name)
    semantic_json, layout_json = empty_project_state_json()
    project = CanvasProject(
        id=str(uuid4()),
        name=validated_name,
        status="active",
        semantic_state=semantic_json,
        layout_state=layout_json,
        schema_version=CURRENT_PROJECT_SCHEMA_VERSION,
        revision=1,
    )
    try:
        db.add(project)
        db.flush()
        append_canvas_event(
            db,
            project_id=project.id,
            event_type="project.created",
            payload={"projectId": project.id, "revision": 1, "status": "active"},
        )
        db.commit()
        db.refresh(project)
        return project
    except BaseException:
        db.rollback()
        raise


def list_projects(
    db: Session,
    *,
    query: str | None,
    include_archived: bool,
) -> list[CanvasProject]:
    statuses = ("active", "archived") if include_archived else ("active",)
    statement = select(CanvasProject).where(CanvasProject.status.in_(statuses))
    normalized_query = query.strip().casefold() if query else ""
    if normalized_query:
        escaped = (
            normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        statement = statement.where(
            func.lower(CanvasProject.name).like(f"%{escaped}%", escape="\\")
        )
    statement = statement.order_by(CanvasProject.updated_at.desc(), CanvasProject.id.desc())
    return list(db.execute(statement).scalars().all())


def list_project_skus(db: Session, *, project_id: str) -> list[CanvasProjectSku]:
    if _current_project_row(db, project_id) is None:
        raise CanvasProjectNotFound(project_id)
    return list(
        db.execute(
            select(CanvasProjectSku)
            .where(
                CanvasProjectSku.project_id == project_id,
                CanvasProjectSku.deleted_at.is_(None),
            )
            .order_by(CanvasProjectSku.sort_order, CanvasProjectSku.id)
        ).scalars().all()
    )


def get_project_snapshot(db: Session, *, project_id: str) -> ProjectSnapshot:
    project = db.execute(
        select(CanvasProject)
        .where(CanvasProject.id == project_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if project is None:
        raise CanvasProjectNotFound(project_id)
    skus = list(
        db.execute(
            select(CanvasProjectSku)
            .where(
                CanvasProjectSku.project_id == project_id,
                CanvasProjectSku.deleted_at.is_(None),
            )
            .order_by(CanvasProjectSku.sort_order, CanvasProjectSku.id)
            .execution_options(populate_existing=True)
        ).scalars().all()
    )
    semantic_wire, layout_wire, _ = upgrade_project_state(
        semantic_state=project.semantic_state,
        layout_state=project.layout_state,
        schema_version=project.schema_version,
    )
    snapshot = ProjectSnapshot(
        project=project,
        skus=skus,
        semantic_state=load_semantic_state(semantic_wire),
        layout_state=load_layout_state(layout_wire),
    )
    _detach_snapshot_rows(db, project, skus)
    return snapshot


def _commit_project_event(
    db: Session,
    *,
    project_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> ProjectSnapshot:
    append_canvas_event(
        db,
        project_id=project_id,
        event_type=event_type,
        payload=payload,
    )
    db.commit()
    return get_project_snapshot(db, project_id=project_id)


def update_project_metadata(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
    name: str,
) -> ProjectSnapshot:
    validated_name = _name_adapter.validate_python(name)
    try:
        revision = _advance_project_revision(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
            values={"name": validated_name},
        )
        return _commit_project_event(
            db,
            project_id=project_id,
            event_type="project.updated",
            payload={"projectId": project_id, "revision": revision, "status": "active"},
        )
    except BaseException:
        db.rollback()
        raise


def _owned_active_ids(
    db: Session,
    *,
    model: type[CanvasAsset] | type[CanvasProjectSku],
    project_id: str,
    identifiers: set[str],
) -> set[str]:
    if not identifiers:
        return set()
    return set(
        db.execute(
            select(model.id).where(
                model.id.in_(identifiers),
                model.project_id == project_id,
                model.deleted_at.is_(None),
            )
        ).scalars().all()
    )


def _validate_state_ownership(
    db: Session,
    *,
    project_id: str,
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> None:
    sku_ids = collect_sku_ids(semantic_state, layout_state)
    asset_ids = collect_asset_ids(semantic_state, layout_state)
    invalid_skus = sku_ids - _owned_active_ids(
        db,
        model=CanvasProjectSku,
        project_id=project_id,
        identifiers=sku_ids,
    )
    invalid_assets = asset_ids - _owned_active_ids(
        db,
        model=CanvasAsset,
        project_id=project_id,
        identifiers=asset_ids,
    )
    if invalid_skus or invalid_assets:
        raise CanvasStateOwnershipError(sku_ids=invalid_skus, asset_ids=invalid_assets)


def _validate_main_product_pipeline(
    *,
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> None:
    """Require the uploaded main product's immutable source/cutout projection.

    A blank project has no main layer and is deliberately valid.  Once a main
    product layer exists, however, the only product source and auto-cutout
    nodes are the system nodes owned by the upload pipeline.  The source edge
    is immutable; the cutout may only feed ordinary model-generation nodes.
    """

    main_layers = [layer for layer in layout_state.product_layers if layer.sku_id is None]
    if not main_layers:
        return
    if len(main_layers) != 1 or not main_layers[0].locked:
        raise CanvasProjectStateValidationError("main product projection must be singular and locked")
    main_layer = main_layers[0]
    nodes_by_id = {node.id: node for node in semantic_state.nodes}
    if len(nodes_by_id) != len(semantic_state.nodes):
        raise CanvasProjectStateValidationError("canvas node identifiers must be unique")
    source_nodes = [node for node in semantic_state.nodes if node.kind == "product_source"]
    cutout_nodes = [node for node in semantic_state.nodes if node.kind == "auto_cutout"]
    if len(source_nodes) != 1 or len(cutout_nodes) != 1:
        raise CanvasProjectStateValidationError("main product system nodes are missing or duplicated")
    source = source_nodes[0]
    cutout = cutout_nodes[0]

    def matches_system_node(node: Any, *, node_id: str, kind: str, asset_id: str) -> bool:
        return (
            node.id == node_id
            and node.kind == kind
            and node.managed_by is None
            and node.sku_id is None
            and node.asset_id == asset_id
            and node.model_profile_id is None
            and node.prompt is None
            and node.composition_group_id is None
            and node.text_snapshot_id is None
            and node.output_board_id is None
            and node.parameters == {}
        )

    if not matches_system_node(
        source,
        node_id="main-product-source",
        kind="product_source",
        asset_id=main_layer.source_asset_id,
    ) or not matches_system_node(
        cutout,
        node_id="main-product-cutout",
        kind="auto_cutout",
        asset_id=main_layer.render_asset_id,
    ):
        raise CanvasProjectStateValidationError("main product system nodes do not match the locked layer")

    canonical_edges = [
        edge
        for edge in semantic_state.edges
        if (
            edge.kind == "product_asset"
            and edge.source_node_id == source.id
            and edge.source_port == "product"
            and edge.target_node_id == cutout.id
            and edge.target_port == "reference"
            and edge.sku_id is None
        )
    ]
    if len(canonical_edges) != 1:
        raise CanvasProjectStateValidationError("main product source/cutout edge is missing or duplicated")

    for edge in semantic_state.edges:
        touches_source = edge.source_node_id == source.id or edge.target_node_id == source.id
        touches_cutout = edge.source_node_id == cutout.id or edge.target_node_id == cutout.id
        if not (touches_source or touches_cutout):
            continue
        is_canonical_edge = edge.id == canonical_edges[0].id
        if touches_source or edge.target_node_id == cutout.id:
            if not is_canonical_edge:
                raise CanvasProjectStateValidationError("main product source/cutout edge was rewired")
            continue
        target = nodes_by_id.get(edge.target_node_id)
        if (
            edge.kind != "cutout_asset"
            or edge.source_port != "cutout"
            or edge.target_port != "reference"
            or edge.sku_id is not None
            or target is None
            or target.kind != "model_generation"
        ):
            raise CanvasProjectStateValidationError("main product cutout has an invalid graph output")


def _is_successful_result_version(
    db: Session,
    *,
    project_id: str,
    board_id: str,
    composed_asset_id: str,
) -> bool:
    candidates = db.execute(
        select(CanvasGenerationAttempt, CanvasGenerationItem)
        .join(CanvasGenerationItem, CanvasGenerationItem.id == CanvasGenerationAttempt.item_id)
        .join(CanvasGeneration, CanvasGeneration.id == CanvasGenerationItem.generation_id)
        .where(
            CanvasGeneration.project_id == project_id,
            CanvasGenerationItem.board_id == board_id,
            CanvasGenerationAttempt.status == "succeeded",
            CanvasGenerationAttempt.provider_result_stage == "complete",
            CanvasGenerationAttempt.completed_at.is_not(None),
            CanvasGenerationAttempt.composed_asset_id == composed_asset_id,
        )
    ).all()
    for attempt, item in candidates:
        identifiers = (
            attempt.background_asset_id,
            attempt.background_preview_asset_id,
            attempt.composed_asset_id,
            attempt.composed_preview_asset_id,
        )
        if any(identifier is None for identifier in identifiers):
            continue
        assets = {
            asset.id: asset
            for asset in db.scalars(
                select(CanvasAsset).where(
                    CanvasAsset.id.in_(identifiers),
                    CanvasAsset.project_id == project_id,
                    CanvasAsset.deleted_at.is_(None),
                )
            ).all()
        }
        if len(assets) != 4:
            continue
        background = assets.get(attempt.background_asset_id)
        background_preview = assets.get(attempt.background_preview_asset_id)
        composed = assets.get(attempt.composed_asset_id)
        composed_preview = assets.get(attempt.composed_preview_asset_id)
        if None in (background, background_preview, composed, composed_preview):
            continue
        assert background is not None
        assert background_preview is not None
        assert composed is not None
        assert composed_preview is not None
        if (
            background.asset_type == "generated_background"
            and composed.asset_type == "composed"
            and background_preview.asset_type == "preview"
            and composed_preview.asset_type == "preview"
            and background_preview.source_asset_id == background.id
            and composed.source_asset_id == background.id
            and composed_preview.source_asset_id == composed.id
            and (background.width, background.height) == (item.width, item.height)
            and (composed.width, composed.height) == (item.width, item.height)
            and background_preview.width > 0
            and background_preview.height > 0
            and composed_preview.width > 0
            and composed_preview.height > 0
            and max(background_preview.width, background_preview.height) <= 2_048
            and max(composed_preview.width, composed_preview.height) <= 2_048
        ):
            return True
    return False


def _validate_selected_result_versions(
    db: Session,
    *,
    project_id: str,
    semantic_state: CanvasSemanticState,
) -> None:
    for board in semantic_state.output_boards:
        if board.selected_result_asset_id is None:
            continue
        if not _is_successful_result_version(
            db,
            project_id=project_id,
            board_id=board.id,
            composed_asset_id=board.selected_result_asset_id,
        ):
            raise CanvasProjectStateValidationError("selected result is not a successful board version")


def _coerce_semantic_state(value: CanvasSemanticState | Mapping[str, Any]) -> CanvasSemanticState:
    if isinstance(value, CanvasSemanticState):
        value = value.model_dump(by_alias=True, warnings=False)
    return CanvasSemanticState.model_validate(value)


def _coerce_layout_state(value: CanvasLayoutState | Mapping[str, Any]) -> CanvasLayoutState:
    if isinstance(value, CanvasLayoutState):
        value = value.model_dump(by_alias=True, warnings=False)
    return CanvasLayoutState.model_validate(value)


def save_project_state(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> ProjectSnapshot:
    semantic_wire, layout_wire, _ = upgrade_project_state(
        semantic_state=(
            semantic_state.model_dump(by_alias=True, warnings=False)
            if isinstance(semantic_state, CanvasSemanticState)
            else semantic_state
        ),
        layout_state=(
            layout_state.model_dump(by_alias=True, warnings=False)
            if isinstance(layout_state, CanvasLayoutState)
            else layout_state
        ),
        schema_version=CURRENT_PROJECT_SCHEMA_VERSION,
    )
    semantic = _coerce_semantic_state(semantic_wire)
    layout = _coerce_layout_state(layout_wire)
    try:
        validate_canvas_graph(semantic)
    except CanvasGraphValidationError as exc:
        raise CanvasProjectStateValidationError(str(exc)) from exc
    validate_composition_state(semantic, layout)
    _validate_main_product_pipeline(semantic_state=semantic, layout_state=layout)
    _validate_state_ownership(
        db,
        project_id=project_id,
        semantic_state=semantic,
        layout_state=layout,
    )
    _validate_selected_result_versions(
        db,
        project_id=project_id,
        semantic_state=semantic,
    )
    _validate_composition_ownership(
        db,
        project_id=project_id,
        semantic_state=semantic,
        layout_state=layout,
    )
    semantic_json = dump_project_state(semantic)
    layout_json = dump_project_state(layout)
    if len(semantic_json.encode("utf-8")) + len(layout_json.encode("utf-8")) > MAX_PROJECT_STATE_BYTES:
        from services.canvas.project_state import ProjectStateSizeError

        raise ProjectStateSizeError(
            f"combined project state exceeds {MAX_PROJECT_STATE_BYTES} UTF-8 bytes"
        )
    try:
        revision = _advance_project_revision(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
            values={
                "semantic_state": semantic_json,
                "layout_state": layout_json,
                "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            },
        )
        return _commit_project_event(
            db,
            project_id=project_id,
            event_type="project.state_saved",
            payload={
                "projectId": project_id,
                "revision": revision,
                "status": "active",
                "summary": {
                    "nodeCount": len(semantic.nodes),
                    "edgeCount": len(semantic.edges),
                    "outputBoardCount": len(semantic.output_boards),
                },
            },
        )
    except BaseException:
        db.rollback()
        raise


def _validate_composition_ownership(
    db: Session,
    *,
    project_id: str,
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> None:
    if not semantic_state.composition_groups:
        return
    sku_ids = {
        sku_id
        for group in semantic_state.composition_groups
        for sku_id in group.sku_ids
    }
    sku_references = dict(
        db.execute(
            select(CanvasProjectSku.id, CanvasProjectSku.reference_asset_id).where(
                CanvasProjectSku.project_id == project_id,
                CanvasProjectSku.id.in_(sku_ids),
                CanvasProjectSku.deleted_at.is_(None),
            )
        ).all()
    )
    asset_ids = {
        asset_id
        for layer in layout_state.product_layers
        if layer.composition_group_id is not None
        for asset_id in (layer.source_asset_id, layer.render_asset_id)
    }
    assets = {
        asset.id: asset
        for asset in db.execute(
            select(CanvasAsset).where(
                CanvasAsset.project_id == project_id,
                CanvasAsset.id.in_(asset_ids),
                CanvasAsset.deleted_at.is_(None),
            )
        ).scalars()
    }
    output_ratios: dict[str, dict[str, int]] = {}
    for output in semantic_state.complete_set.outputs:
        if output.output_type != "sku" or output.sku_id is None:
            continue
        if output.width is not None and output.height is not None:
            output_ratios[output.sku_id] = {
                "width": output.width,
                "height": output.height,
            }
            continue
        if output.aspect_ratio and ":" in output.aspect_ratio:
            width_text, height_text = output.aspect_ratio.split(":", 1)
            try:
                width, height = int(width_text), int(height_text)
            except ValueError:
                continue
            if width > 0 and height > 0:
                output_ratios[output.sku_id] = {"width": width, "height": height}
    build_composition_specs(
        project_id=project_id,
        semantic_state=semantic_state,
        layout_state=layout_state,
        sku_reference_asset_ids=sku_references,
        assets=assets,
        output_ratios=output_ratios,
    )


def _coerce_sku_create(value: SkuCreate | Mapping[str, Any]) -> SkuCreate:
    if isinstance(value, SkuCreate):
        value = value.model_dump(by_alias=True, warnings=False)
    return SkuCreate.model_validate(value)


def _coerce_sku_update(value: SkuUpdate | Mapping[str, Any]) -> SkuUpdate:
    if isinstance(value, SkuUpdate):
        value = value.model_dump(by_alias=True, warnings=False, exclude_unset=True)
    return SkuUpdate.model_validate(value)


def _validate_reference_asset(
    db: Session,
    *,
    project_id: str,
    reference_asset_id: str | None,
) -> None:
    if reference_asset_id is None:
        return
    owned = _owned_active_ids(
        db,
        model=CanvasAsset,
        project_id=project_id,
        identifiers={reference_asset_id},
    )
    if reference_asset_id not in owned:
        raise CanvasStateOwnershipError(asset_ids={reference_asset_id})


def _canonical_config(config: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def create_sku(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
    request: SkuCreate,
) -> ProjectSnapshot:
    parsed = _coerce_sku_create(request)
    try:
        revision = _advance_project_revision(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
        )
        _validate_reference_asset(
            db,
            project_id=project_id,
            reference_asset_id=parsed.reference_asset_id,
        )
        next_sort_order = db.execute(
            select(func.coalesce(func.max(CanvasProjectSku.sort_order), -1) + 1).where(
                CanvasProjectSku.project_id == project_id
            )
        ).scalar_one()
        sku = CanvasProjectSku(
            id=str(uuid4()),
            project_id=project_id,
            name=parsed.name,
            sort_order=next_sort_order,
            reference_asset_id=parsed.reference_asset_id,
            prompt=parsed.prompt,
            config_json=_canonical_config(parsed.config),
        )
        db.add(sku)
        db.flush()
        return _commit_project_event(
            db,
            project_id=project_id,
            event_type="sku.created",
            payload={
                "projectId": project_id,
                "skuId": sku.id,
                "revision": revision,
                "status": "active",
            },
        )
    except BaseException:
        db.rollback()
        raise


def _active_sku(db: Session, *, project_id: str, sku_id: str) -> CanvasProjectSku:
    sku = db.execute(
        select(CanvasProjectSku).where(
            CanvasProjectSku.id == sku_id,
            CanvasProjectSku.project_id == project_id,
            CanvasProjectSku.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if sku is None:
        raise CanvasSkuNotFound(sku_id)
    return sku


def _set_sku_sort_order(
    db: Session,
    *,
    sku: CanvasProjectSku,
    sort_order: int,
) -> None:
    if sku.sort_order == sort_order:
        return
    occupant = db.execute(
        select(CanvasProjectSku).where(
            CanvasProjectSku.project_id == sku.project_id,
            CanvasProjectSku.sort_order == sort_order,
            CanvasProjectSku.id != sku.id,
        )
    ).scalar_one_or_none()
    if occupant is None:
        sku.sort_order = sort_order
        return

    previous_sort_order = sku.sort_order
    temporary_sort_order = db.execute(
        select(func.coalesce(func.max(CanvasProjectSku.sort_order), -1) + 1).where(
            CanvasProjectSku.project_id == sku.project_id
        )
    ).scalar_one()
    occupant.sort_order = temporary_sort_order
    db.flush()
    sku.sort_order = sort_order
    db.flush()
    occupant.sort_order = previous_sort_order


def update_sku(
    db: Session,
    *,
    project_id: str,
    sku_id: str,
    expected_revision: int,
    request: SkuUpdate,
) -> ProjectSnapshot:
    parsed = _coerce_sku_update(request)
    try:
        revision = _advance_project_revision(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
        )
        sku = _active_sku(db, project_id=project_id, sku_id=sku_id)
        fields = parsed.model_fields_set
        if "reference_asset_id" in fields:
            _validate_reference_asset(
                db,
                project_id=project_id,
                reference_asset_id=parsed.reference_asset_id,
            )
        if "name" in fields:
            sku.name = parsed.name
        if "reference_asset_id" in fields:
            sku.reference_asset_id = parsed.reference_asset_id
        if "prompt" in fields:
            sku.prompt = parsed.prompt
        if "config" in fields:
            sku.config_json = _canonical_config(parsed.config or {})
        if "sort_order" in fields:
            _set_sku_sort_order(db, sku=sku, sort_order=parsed.sort_order)
        db.flush()
        return _commit_project_event(
            db,
            project_id=project_id,
            event_type="sku.updated",
            payload={
                "projectId": project_id,
                "skuId": sku_id,
                "revision": revision,
                "status": "active",
            },
        )
    except BaseException:
        db.rollback()
        raise


def delete_sku(
    db: Session,
    *,
    project_id: str,
    sku_id: str,
    expected_revision: int,
) -> ProjectSnapshot:
    try:
        revision = _advance_project_revision(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
        )
        sku = _active_sku(db, project_id=project_id, sku_id=sku_id)
        project_state = db.execute(
            select(
                CanvasProject.semantic_state,
                CanvasProject.layout_state,
                CanvasProject.schema_version,
            ).where(CanvasProject.id == project_id)
        ).one()
        semantic = load_semantic_state(
            project_state.semantic_state,
            schema_version=project_state.schema_version,
        )
        layout = load_layout_state(
            project_state.layout_state,
            schema_version=project_state.schema_version,
        )
        references = collect_sku_reference_sections(semantic, layout, sku_id=sku_id)
        if references:
            raise CanvasSkuReferenceConflict(sku_id=sku_id, references=references)

        sku.deleted_at = func.now()
        sku.reference_asset_id = None
        db.flush()
        return _commit_project_event(
            db,
            project_id=project_id,
            event_type="sku.deleted",
            payload={
                "projectId": project_id,
                "skuId": sku_id,
                "revision": revision,
                "status": "deleted",
            },
        )
    except BaseException:
        db.rollback()
        raise


def _transition_project_status(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
    from_statuses: tuple[str, ...],
    to_status: str,
    event_type: str,
    archived_at: Any,
) -> ProjectSnapshot:
    try:
        _assert_no_blocking_activity(db, project_id)
        revision = _advance_project_revision(
            db,
            project_id=project_id,
            expected_revision=expected_revision,
            allowed_statuses=from_statuses,
            values={"status": to_status, "archived_at": archived_at},
        )
        return _commit_project_event(
            db,
            project_id=project_id,
            event_type=event_type,
            payload={
                "projectId": project_id,
                "revision": revision,
                "status": to_status,
            },
        )
    except BaseException:
        db.rollback()
        raise


def archive_project(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
) -> ProjectSnapshot:
    return _transition_project_status(
        db,
        project_id=project_id,
        expected_revision=expected_revision,
        from_statuses=("active",),
        to_status="archived",
        event_type="project.archived",
        archived_at=func.now(),
    )


def restore_project(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
) -> ProjectSnapshot:
    return _transition_project_status(
        db,
        project_id=project_id,
        expected_revision=expected_revision,
        from_statuses=("archived",),
        to_status="active",
        event_type="project.restored",
        archived_at=None,
    )


def request_project_deletion(
    db: Session,
    *,
    project_id: str,
    expected_revision: int,
) -> ProjectSnapshot:
    return _transition_project_status(
        db,
        project_id=project_id,
        expected_revision=expected_revision,
        from_statuses=("active", "archived"),
        to_status="deleting",
        event_type="project.deleting",
        archived_at=None,
    )


mark_project_deleting = request_project_deletion
delete_project = request_project_deletion


def finalize_deleting_project(
    db_factory: Callable[[], Session],
    *,
    project_id: str,
) -> None:
    """Idempotently delete the contained file tree before deleting database rows."""
    with db_factory() as db:
        status = db.execute(
            select(CanvasProject.status).where(CanvasProject.id == project_id)
        ).scalar_one_or_none()
    if status is None:
        return
    if status != "deleting":
        raise CanvasProjectStatusConflict(status)
    with db_factory() as db:
        _assert_no_blocking_activity(db, project_id)

    storage.remove_project_tree(project_id)

    with db_factory() as db:
        try:
            status = db.execute(
                select(CanvasProject.status).where(CanvasProject.id == project_id)
            ).scalar_one_or_none()
            if status is None:
                return
            if status != "deleting":
                raise CanvasProjectStatusConflict(status)
            _assert_no_blocking_activity(db, project_id)
            db.execute(delete(CanvasEvent).where(CanvasEvent.project_id == project_id))
            generation_ids = select(CanvasGeneration.id).where(
                CanvasGeneration.project_id == project_id
            )
            generation_item_ids = select(CanvasGenerationItem.id).where(
                CanvasGenerationItem.generation_id.in_(generation_ids)
            )
            # Generation attempts retain FK links to their composing operation
            # and items retain their input assets. Delete the owned result graph
            # from leaves to roots before removing project-wide operations and
            # assets.
            db.execute(
                delete(CanvasGenerationItemInput).where(
                    CanvasGenerationItemInput.item_id.in_(generation_item_ids)
                )
            )
            db.execute(
                delete(CanvasGenerationAttempt).where(
                    CanvasGenerationAttempt.item_id.in_(generation_item_ids)
                )
            )
            db.execute(
                delete(CanvasGenerationItem).where(
                    CanvasGenerationItem.generation_id.in_(generation_ids)
                )
            )
            db.execute(delete(CanvasGeneration).where(CanvasGeneration.project_id == project_id))
            db.execute(
                delete(CanvasAssetOperation).where(
                    CanvasAssetOperation.project_id == project_id
                )
            )
            db.execute(delete(CanvasProjectSku).where(CanvasProjectSku.project_id == project_id))
            db.execute(delete(CanvasAsset).where(CanvasAsset.project_id == project_id))
            db.execute(
                delete(CanvasProject).where(
                    CanvasProject.id == project_id,
                    CanvasProject.status == "deleting",
                )
            )
            db.commit()
        except BaseException:
            db.rollback()
            raise


def recover_deleting_projects(db_factory: Callable[[], Session]) -> int:
    with db_factory() as db:
        project_ids = list(
            db.execute(
                select(CanvasProject.id)
                .where(CanvasProject.status == "deleting")
                .order_by(CanvasProject.id)
            ).scalars().all()
        )
    for project_id in project_ids:
        finalize_deleting_project(db_factory, project_id=project_id)
    return len(project_ids)
