"""Transactional event appends for Product Canvas project streams."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasAssetOperation,
    CanvasEvent,
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
    CanvasProject,
)


MAX_EVENT_PAYLOAD_BYTES = 64 * 1024
EVENT_REPLAY_BATCH_SIZE = 200

SUBJECT_MODEL_REGISTRY: dict[str, type[Any] | None] = {
    "operation_id": CanvasAssetOperation,
    "generation_id": CanvasGeneration,
    "item_id": CanvasGenerationItem,
}

_FULL_PROJECT_STATE_KEYS = {
    "completeSet",
    "complete_set",
    "compositionGroups",
    "composition_groups",
    "edges",
    "generationHistory",
    "generation_history",
    "semantic_state",
    "semanticState",
    "layout_state",
    "layoutState",
    "nodePositions",
    "node_positions",
    "nodes",
    "objectTransforms",
    "object_transforms",
    "outputBoards",
    "output_boards",
    "productLayers",
    "product_layers",
    "textSnapshots",
    "text_snapshots",
    "versionHistory",
    "version_history",
}


class CanvasEventValidationError(ValueError):
    """Raised when an event would be unsafe or reference an invalid owner."""


_UNAVAILABLE_OPERATION_ERROR = {
    "code": "canvas_operation_error_unavailable",
    "message": "Operation error details are unavailable",
    "retryable": False,
}


def _safe_operation_error(raw_value: str | None) -> dict[str, Any] | None:
    if raw_value is None:
        return None
    try:
        value = json.loads(raw_value)
    except (TypeError, ValueError):
        return dict(_UNAVAILABLE_OPERATION_ERROR)
    if not isinstance(value, dict):
        return dict(_UNAVAILABLE_OPERATION_ERROR)
    code = value.get("code")
    message = value.get("message")
    retryable = value.get("retryable")
    if (
        not isinstance(code, str)
        or not code
        or len(code) > 100
        or not isinstance(message, str)
        or not message
        or len(message) > 500
        or type(retryable) is not bool
    ):
        return dict(_UNAVAILABLE_OPERATION_ERROR)
    return {
        "code": code,
        "message": message.replace("\r", " ").replace("\n", " "),
        "retryable": retryable,
    }


def _snapshot_timestamp(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def operation_snapshot_json(db: Session, *, project_id: str) -> list[dict[str, Any]]:
    """Return safe local-operation summaries for one replay-gap snapshot."""
    rows = db.execute(
        select(
            CanvasAssetOperation.id,
            CanvasAssetOperation.project_id,
            CanvasAssetOperation.operation_type,
            CanvasAssetOperation.status,
            CanvasAssetOperation.attempt_count,
            CanvasAssetOperation.input_asset_id,
            CanvasAssetOperation.output_asset_id,
            CanvasAssetOperation.safe_error_json,
            CanvasAssetOperation.created_at,
            CanvasAssetOperation.updated_at,
            CanvasAssetOperation.started_at,
            CanvasAssetOperation.completed_at,
        )
        .where(CanvasAssetOperation.project_id == project_id)
        .order_by(CanvasAssetOperation.created_at.asc(), CanvasAssetOperation.id.asc())
    ).all()
    return [
        {
            "id": row.id,
            "projectId": row.project_id,
            "type": row.operation_type,
            "status": row.status,
            "attemptCount": int(row.attempt_count),
            "inputAssetId": row.input_asset_id,
            "outputAssetId": row.output_asset_id,
            "error": _safe_operation_error(row.safe_error_json),
            "createdAt": _snapshot_timestamp(row.created_at),
            "updatedAt": _snapshot_timestamp(row.updated_at),
            "startedAt": _snapshot_timestamp(row.started_at),
            "completedAt": _snapshot_timestamp(row.completed_at),
        }
        for row in rows
    ]


_ACTIVE_GENERATION_STATUSES = frozenset(
    {"queued", "running", "interrupted", "cancel_requested", "unknown"}
)
_TERMINAL_GENERATION_STATUSES = frozenset(
    {"succeeded", "partially_failed", "failed", "cancelled"}
)


def _attempt_snapshot(attempt: CanvasGenerationAttempt | None) -> dict[str, Any] | None:
    if attempt is None:
        return None
    return {
        "id": attempt.id,
        "attemptNo": int(attempt.attempt_no),
        "status": attempt.status,
        "providerResultStage": attempt.provider_result_stage,
        "providerRequestId": attempt.provider_request_id,
        "externalTaskId": attempt.external_task_id,
        "backgroundAssetId": attempt.background_asset_id,
        "composedAssetId": attempt.composed_asset_id,
        "composeOperationId": attempt.compose_operation_id,
        "safeErrorCode": attempt.normalized_error_code,
        "safeErrorSummary": attempt.safe_error_summary,
        "createdAt": _snapshot_timestamp(attempt.created_at),
        "completedAt": _snapshot_timestamp(attempt.completed_at),
    }


def generation_snapshot(
    db: Session,
    *,
    project_id: str,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """Return safe progress for active/unknown and recently terminal work."""

    query = select(CanvasGeneration).where(CanvasGeneration.project_id == project_id)
    if generation_id is not None:
        query = query.where(CanvasGeneration.id == generation_id)
    else:
        recent_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        query = query.where(
            (CanvasGeneration.status.in_(tuple(_ACTIVE_GENERATION_STATUSES)))
            | (
                CanvasGeneration.status.in_(tuple(_TERMINAL_GENERATION_STATUSES))
                & (CanvasGeneration.updated_at >= recent_cutoff)
            )
        ).order_by(CanvasGeneration.updated_at.desc(), CanvasGeneration.id.desc()).limit(100)
    generations = list(db.scalars(query).all())
    generation_ids = [generation.id for generation in generations]
    item_rows = (
        list(
            db.scalars(
                select(CanvasGenerationItem)
                .where(CanvasGenerationItem.generation_id.in_(generation_ids))
                .order_by(CanvasGenerationItem.generation_id, CanvasGenerationItem.ordinal)
            ).all()
        )
        if generation_ids
        else []
    )
    item_ids = [item.id for item in item_rows]
    attempts = (
        list(
            db.scalars(
                select(CanvasGenerationAttempt)
                .where(CanvasGenerationAttempt.item_id.in_(item_ids))
                .order_by(
                    CanvasGenerationAttempt.item_id,
                    CanvasGenerationAttempt.attempt_no.desc(),
                    CanvasGenerationAttempt.id.desc(),
                )
            ).all()
        )
        if item_ids
        else []
    )
    latest_attempts: dict[str, CanvasGenerationAttempt] = {}
    for attempt in attempts:
        latest_attempts.setdefault(attempt.item_id, attempt)
    items_by_generation: dict[str, list[dict[str, Any]]] = {
        generation.id: [] for generation in generations
    }
    for item in item_rows:
        items_by_generation[item.generation_id].append(
            {
                "id": item.id,
                "ordinal": int(item.ordinal),
                "outputType": item.output_type,
                "boardId": item.board_id,
                "nodeId": item.node_id,
                "status": item.status,
                "attemptCount": int(item.attempt_count),
                "latestBackgroundAssetId": item.latest_background_asset_id,
                "latestComposedAssetId": item.latest_composed_asset_id,
                "safeErrorCode": item.safe_current_error_code,
                "safeErrorSummary": item.safe_current_error_summary,
                "latestAttempt": _attempt_snapshot(latest_attempts.get(item.id)),
            }
        )
    return {
        "projectId": project_id,
        "generations": [
            {
                "id": generation.id,
                "status": generation.status,
                "mode": generation.mode,
                "totalItems": int(generation.total_items),
                "succeededItems": int(generation.succeeded_items),
                "failedItems": int(generation.failed_items),
                "cancelledItems": int(generation.cancelled_items),
                "unknownItems": int(generation.unknown_items),
                "safeStorageBlockReason": generation.safe_storage_block_reason,
                "createdAt": _snapshot_timestamp(generation.created_at),
                "updatedAt": _snapshot_timestamp(generation.updated_at),
                "completedAt": _snapshot_timestamp(generation.completed_at),
                "items": items_by_generation[generation.id],
            }
            for generation in generations
        ],
    }


def project_activity_snapshot(
    db: Session,
    *,
    project_id: str,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """One safe stream snapshot, including local and paid Canvas activity."""

    snapshot = generation_snapshot(
        db,
        project_id=project_id,
        generation_id=generation_id,
    )
    snapshot["operations"] = operation_snapshot_json(db, project_id=project_id)
    return snapshot


@dataclass(frozen=True)
class CanvasEventReplay:
    snapshot: dict[str, Any] | None
    cursor: int
    events: list[dict[str, Any]]
    replay_gap: bool


def prepare_event_replay(
    db: Session,
    *,
    project_id: str,
    last_event_id: int | None,
    generation_id: str | None = None,
) -> CanvasEventReplay:
    """Prepare one coherent project/generation replay page on a short Session."""

    if db.get(CanvasProject, project_id) is None:
        raise CanvasEventValidationError("canvas project does not exist")
    if last_event_id is not None and (
        isinstance(last_event_id, bool) or not isinstance(last_event_id, int) or last_event_id < 0
    ):
        raise CanvasEventValidationError("last event id is invalid")
    subject_filter = [CanvasEvent.project_id == project_id]
    if generation_id is not None:
        subject_filter.append(CanvasEvent.generation_id == generation_id)
    high_water = db.scalar(select(func.max(CanvasEvent.id)).where(*subject_filter))
    cursor = int(high_water or 0)
    earliest = db.execute(
        select(CanvasEvent.id, CanvasEvent.event_type)
        .where(*subject_filter)
        .order_by(CanvasEvent.id.asc())
        .limit(1)
    ).one_or_none()
    replay_gap = last_event_id is not None and (
        earliest is None
        or (
            last_event_id < int(earliest.id)
            and str(earliest.event_type) != "project.created"
        )
    )
    if last_event_id is None or replay_gap:
        snapshot = project_activity_snapshot(
            db,
            project_id=project_id,
            generation_id=generation_id,
        )
        snapshot["highWaterEventId"] = cursor
        return CanvasEventReplay(
            snapshot=snapshot,
            cursor=cursor,
            events=[],
            replay_gap=replay_gap,
        )
    rows = db.execute(
        select(CanvasEvent.id, CanvasEvent.event_type, CanvasEvent.payload_json)
        .where(*subject_filter, CanvasEvent.id > last_event_id)
        .order_by(CanvasEvent.id.asc())
        .limit(EVENT_REPLAY_BATCH_SIZE)
    ).all()
    return CanvasEventReplay(
        snapshot=None,
        cursor=last_event_id,
        events=[
            {"id": int(row.id), "event_type": str(row.event_type), "payload_json": str(row.payload_json)}
            for row in rows
        ],
        replay_gap=False,
    )


def prune_canvas_events(
    db: Session,
    *,
    project_id: str,
    now: datetime,
    keep_count: int = 10_000,
    keep_days: int = 7,
    batch_size: int = 500,
) -> int:
    """Delete one bounded batch that is both old and outside count retention."""

    if (
        isinstance(keep_count, bool)
        or not isinstance(keep_count, int)
        or keep_count < 0
        or isinstance(keep_days, bool)
        or not isinstance(keep_days, int)
        or keep_days < 0
        or isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size < 1
    ):
        raise CanvasEventValidationError("event retention values are invalid")
    if not isinstance(now, datetime):
        raise CanvasEventValidationError("event pruning time is invalid")
    boundary = db.scalar(
        select(CanvasEvent.id)
        .where(CanvasEvent.project_id == project_id)
        .order_by(CanvasEvent.id.desc())
        .offset(keep_count)
        .limit(1)
    )
    if boundary is None:
        return 0
    cutoff = now - timedelta(days=keep_days)
    candidate_ids = list(
        db.scalars(
            select(CanvasEvent.id)
            .where(
                CanvasEvent.project_id == project_id,
                CanvasEvent.id <= int(boundary),
                CanvasEvent.created_at < cutoff,
            )
            .order_by(CanvasEvent.id.asc())
            .limit(batch_size)
        ).all()
    )
    if not candidate_ids:
        return 0
    result = db.execute(delete(CanvasEvent).where(CanvasEvent.id.in_(candidate_ids)))
    return int(result.rowcount or 0)


def prune_all_canvas_events(
    session_factory: Callable[[], Session],
    *,
    now: datetime | None = None,
    keep_count: int = 10_000,
    keep_days: int = 7,
    batch_size: int = 500,
) -> int:
    """Run bounded retention batches with a fresh Session for each batch."""

    current = now or datetime.now(UTC).replace(tzinfo=None)
    with session_factory() as db:
        project_ids = list(db.scalars(select(CanvasProject.id).order_by(CanvasProject.id)).all())
    deleted = 0
    for project_id in project_ids:
        while True:
            with session_factory() as db:
                count = prune_canvas_events(
                    db,
                    project_id=project_id,
                    now=current,
                    keep_count=keep_count,
                    keep_days=keep_days,
                    batch_size=batch_size,
                )
                db.commit()
            deleted += count
            if count < batch_size:
                break
    return deleted


def append_generation_progress_event(
    db: Session,
    *,
    generation: CanvasGeneration,
    event_type: str,
    item: CanvasGenerationItem | None = None,
    attempt: CanvasGenerationAttempt | None = None,
) -> CanvasEvent:
    """Append an ID-only, credential-safe progress event with state changes."""

    payload: dict[str, Any] = {
        "generationId": generation.id,
        "generationStatus": generation.status,
        "totalItems": int(generation.total_items),
        "succeededItems": int(generation.succeeded_items),
        "failedItems": int(generation.failed_items),
        "cancelledItems": int(generation.cancelled_items),
        "unknownItems": int(generation.unknown_items),
        "safeStorageBlockReason": generation.safe_storage_block_reason,
    }
    if item is not None:
        payload.update(
            {
                "itemId": item.id,
                "itemStatus": item.status,
                "outputType": item.output_type,
                "safeErrorCode": item.safe_current_error_code,
                "safeErrorSummary": item.safe_current_error_summary,
            }
        )
    if attempt is not None:
        payload.update(
            {
                "attemptId": attempt.id,
                "attemptNo": int(attempt.attempt_no),
                "attemptStatus": attempt.status,
                "providerResultStage": attempt.provider_result_stage,
                "safeErrorCode": attempt.normalized_error_code
                or payload.get("safeErrorCode"),
                "safeErrorSummary": attempt.safe_error_summary
                or payload.get("safeErrorSummary"),
            }
        )
    return append_canvas_event(
        db,
        project_id=generation.project_id,
        event_type=event_type,
        payload=payload,
        generation_id=generation.id,
        item_id=item.id if item is not None else None,
    )


def register_canvas_event_subject_model(subject_field: str, model: type[Any]) -> None:
    """Register a later-slice subject model without changing the append API."""
    if subject_field not in SUBJECT_MODEL_REGISTRY:
        raise ValueError(f"unsupported canvas event subject field: {subject_field}")
    if not all(hasattr(model, attribute) for attribute in ("id", "__table__")):
        raise TypeError("canvas event subject models require id and a mapped table")
    SUBJECT_MODEL_REGISTRY[subject_field] = model


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanvasEventValidationError("event payload numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanvasEventValidationError("event payload object keys must be strings")
            if key in _FULL_PROJECT_STATE_KEYS:
                raise CanvasEventValidationError("event payload must not embed full project state")
            _validate_json_value(item)
        return
    raise CanvasEventValidationError("event payload contains a non-JSON value")


def _serialize_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise CanvasEventValidationError("event payload must be a JSON object")
    try:
        _validate_json_value(payload)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        payload_size = len(serialized.encode("utf-8"))
    except CanvasEventValidationError:
        raise
    except (OverflowError, RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise CanvasEventValidationError("event payload is not JSON-safe") from exc
    if payload_size > MAX_EVENT_PAYLOAD_BYTES:
        raise CanvasEventValidationError(
            f"event payload exceeds {MAX_EVENT_PAYLOAD_BYTES} UTF-8 bytes"
        )
    return serialized


def _subject_project_id(
    db: Session,
    *,
    subject_field: str,
    subject_id: str,
) -> str:
    if not isinstance(subject_id, str) or not subject_id:
        raise CanvasEventValidationError(f"{subject_field} must be a non-empty string")
    model = SUBJECT_MODEL_REGISTRY[subject_field]
    if model is None:
        raise CanvasEventValidationError(f"{subject_field} is unavailable in this schema slice")

    table = model.__table__
    bind = db.get_bind(mapper=model)
    if not inspect(bind).has_table(table.name, schema=table.schema):
        raise CanvasEventValidationError(f"{subject_field} target table is unavailable")

    if subject_field == "item_id":
        owner_id = db.execute(
            select(CanvasGeneration.project_id)
            .join(CanvasGenerationItem, CanvasGenerationItem.generation_id == CanvasGeneration.id)
            .where(CanvasGenerationItem.id == subject_id)
        ).scalar_one_or_none()
    else:
        owner_id = db.execute(
            select(model.project_id).where(model.id == subject_id)
        ).scalar_one_or_none()
    if owner_id is None:
        raise CanvasEventValidationError(f"{subject_field} target does not exist")
    return owner_id


def append_canvas_event(
    db: Session,
    *,
    project_id: str,
    event_type: str,
    payload: dict[str, Any],
    operation_id: str | None = None,
    generation_id: str | None = None,
    item_id: str | None = None,
) -> CanvasEvent:
    """Append an owner-validated event without committing the caller's transaction."""
    if not isinstance(event_type, str) or not event_type.strip():
        raise CanvasEventValidationError("event_type must be a non-empty string")
    if len(event_type) > 100:
        raise CanvasEventValidationError("event_type exceeds 100 characters")

    payload_json = _serialize_payload(payload)
    project_exists = db.execute(
        select(CanvasProject.id).where(CanvasProject.id == project_id)
    ).scalar_one_or_none()
    if project_exists is None:
        raise CanvasEventValidationError("canvas project does not exist")

    subjects = {
        "operation_id": operation_id,
        "generation_id": generation_id,
        "item_id": item_id,
    }
    for subject_field, subject_id in subjects.items():
        if subject_id is None:
            continue
        owner_id = _subject_project_id(
            db,
            subject_field=subject_field,
            subject_id=subject_id,
        )
        if owner_id != project_id:
            raise CanvasEventValidationError(
                f"{subject_field} target belongs to a different canvas project"
            )

    event = CanvasEvent(
        project_id=project_id,
        event_type=event_type,
        operation_id=operation_id,
        generation_id=generation_id,
        item_id=item_id,
        payload_json=payload_json,
    )
    db.add(event)
    return event
