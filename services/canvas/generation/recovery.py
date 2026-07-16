"""Safe restart recovery and explicit operator actions for Canvas generations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasAssetOperation,
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
)
from services.canvas import operations
from services.canvas.events import append_generation_progress_event
from services.canvas.generation.repository import (
    CanvasGenerationNotFound,
    CanvasGenerationValidationError,
    release_generation_reservation,
    restore_generation_reservation,
)
from config import CANVAS_REMOTE_IMAGE_MAX_BYTES
from services.canvas.generation.fingerprints import (
    encoded_rgba_png_upper_bound,
    proxy_dimensions,
)
from services.canvas.generation.results import (
    GenerationResultError,
    promote_materialized_provider_result,
    read_verified_temporary_result,
)
from services.canvas.generation.state import (
    aggregate_generation_status,
    transition_attempt,
    transition_generation,
    transition_item,
)
from services.canvas import projects as project_service


_TERMINAL_GENERATION_STATUSES = frozenset(
    {"succeeded", "partially_failed", "failed", "cancelled"}
)
_ACTIVE_GENERATION_STATUSES = frozenset(
    {"queued", "running", "interrupted", "cancel_requested", "unknown"}
)


class CanvasGenerationActionConflict(CanvasGenerationValidationError):
    pass


@dataclass(frozen=True)
class RecoverySummary:
    queued_untouched: int = 0
    polling_resumed: int = 0
    marked_unknown: int = 0
    local_results_promoted: int = 0


@dataclass(frozen=True)
class ItemRetryResult:
    item_id: str
    attempt_id: str | None
    compose_operation_id: str | None
    paid_retry: bool


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generation_for_item(db: Session, item: CanvasGenerationItem) -> CanvasGeneration:
    generation = db.get(CanvasGeneration, item.generation_id)
    if generation is None:
        raise CanvasGenerationValidationError("generation owner is unavailable")
    return generation


def _latest_attempt(db: Session, item_id: str) -> CanvasGenerationAttempt | None:
    return db.scalar(
        select(CanvasGenerationAttempt)
        .where(CanvasGenerationAttempt.item_id == item_id)
        .order_by(
            CanvasGenerationAttempt.attempt_no.desc(),
            CanvasGenerationAttempt.id.desc(),
        )
        .limit(1)
    )


def _attempt_supports_cancel(attempt: CanvasGenerationAttempt) -> bool:
    try:
        snapshot = json.loads(attempt.model_config_snapshot_json)
    except (TypeError, json.JSONDecodeError):
        return False
    capabilities = snapshot.get("capabilities") if isinstance(snapshot, dict) else None
    return bool(capabilities.get("supports_cancel")) if isinstance(capabilities, dict) else False


def _compose_retry_reservation(item: CanvasGenerationItem) -> int:
    proxy_width, proxy_height = proxy_dimensions(item.width, item.height)
    return (
        encoded_rgba_png_upper_bound(item.width, item.height)
        + encoded_rgba_png_upper_bound(proxy_width, proxy_height)
    )


def _paid_retry_reservation(item: CanvasGenerationItem) -> int:
    """Return the original per-item provider/background/compose peak."""

    return 2 * CANVAS_REMOTE_IMAGE_MAX_BYTES + _compose_retry_reservation(item) + (
        encoded_rgba_png_upper_bound(*proxy_dimensions(item.width, item.height))
    )


def _refresh_generation(db: Session, generation: CanvasGeneration, *, now: datetime) -> None:
    db.flush()
    statuses = list(
        db.scalars(
            select(CanvasGenerationItem.status).where(
                CanvasGenerationItem.generation_id == generation.id
            )
        ).all()
    )
    target = aggregate_generation_status(statuses, generation.status)
    if target != generation.status:
        transition_generation(generation.status, target)
        generation.status = target
    generation.succeeded_items = statuses.count("succeeded")
    generation.failed_items = statuses.count("failed")
    generation.cancelled_items = statuses.count("cancelled")
    generation.unknown_items = statuses.count("unknown")
    if target in _TERMINAL_GENERATION_STATUSES or target == "unknown":
        generation.completed_at = now
        release_generation_reservation(db, generation_id=generation.id)


def _mark_attempt_unknown(
    db: Session,
    *,
    attempt: CanvasGenerationAttempt,
    now: datetime,
    code: str,
    summary: str,
) -> None:
    item = db.get(CanvasGenerationItem, attempt.item_id)
    if item is None:
        return
    generation = _generation_for_item(db, item)
    if attempt.status not in {"unknown", "succeeded", "failed", "cancelled"}:
        transition_attempt(attempt.status, "unknown")
        attempt.status = "unknown"
    attempt.worker_id = None
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.normalized_error_code = code
    attempt.safe_error_summary = summary
    if item.status not in {"succeeded", "failed", "cancelled", "unknown"}:
        transition_item(item.status, "unknown")
        item.status = "unknown"
        item.safe_current_error_code = code
        item.safe_current_error_summary = summary
        item.completed_at = now
    _refresh_generation(db, generation, now=now)
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=attempt,
        event_type="generation.item.unknown",
    )


def recover_canvas_generation_work(
    db: Session,
    *,
    now: datetime | None = None,
) -> RecoverySummary:
    """Recover local work only; unknown upstream acceptance is never re-submitted."""

    current = now or _utcnow()
    summary = RecoverySummary()
    values = {
        "queued_untouched": 0,
        "polling_resumed": 0,
        "marked_unknown": 0,
        "local_results_promoted": 0,
    }
    attempts = list(
        db.scalars(
            select(CanvasGenerationAttempt)
            .join(CanvasGenerationItem, CanvasGenerationItem.id == CanvasGenerationAttempt.item_id)
            .join(CanvasGeneration, CanvasGeneration.id == CanvasGenerationItem.generation_id)
            .where(CanvasGeneration.status.in_(tuple(_ACTIVE_GENERATION_STATUSES)))
            .order_by(CanvasGenerationAttempt.created_at, CanvasGenerationAttempt.id)
        ).all()
    )
    for attempt in attempts:
        item = db.get(CanvasGenerationItem, attempt.item_id)
        if item is None:
            continue
        generation = _generation_for_item(db, item)
        if attempt.status == "queued":
            values["queued_untouched"] += 1
            continue
        # A verified local result is authoritative recovery input.  It must be
        # promoted before considering any upstream action, so restarts never
        # submit a second paid request.
        if attempt.status in {"submitting", "polling", "succeeded"}:
            try:
                read_verified_temporary_result(
                    project_id=generation.project_id,
                    attempt_id=attempt.id,
                )
            except GenerationResultError:
                pass
            else:
                attempt.provider_result_stage = "receiving"
                attempt.worker_id = None
                attempt.lease_expires_at = None
                try:
                    promote_materialized_provider_result(
                        db,
                        attempt_id=attempt.id,
                        claim_token=None,
                        provider_request_id=attempt.provider_request_id,
                        external_task_id=attempt.external_task_id,
                        now=current,
                    )
                    values["local_results_promoted"] += 1
                    continue
                except GenerationResultError:
                    _mark_attempt_unknown(
                        db,
                        attempt=attempt,
                        now=current,
                        code="generation_result_recovery_failed",
                        summary="The saved Provider image could not be recovered",
                    )
                    values["marked_unknown"] += 1
                    continue
        if attempt.status == "polling" and attempt.external_task_id:
            attempt.worker_id = None
            attempt.lease_expires_at = None
            attempt.heartbeat_at = current
            attempt.next_poll_at = current
            values["polling_resumed"] += 1
            continue
        if attempt.status == "submitting":
            _mark_attempt_unknown(
                db,
                attempt=attempt,
                now=current,
                code="provider_acceptance_unknown",
                summary="The Provider may have accepted this request; explicit resolution is required",
            )
            values["marked_unknown"] += 1
    return RecoverySummary(**values)


def request_generation_cancel(
    db: Session,
    *,
    generation_id: str,
    now: datetime | None = None,
) -> CanvasGeneration:
    current = now or _utcnow()
    generation = db.get(CanvasGeneration, generation_id)
    if generation is None:
        raise CanvasGenerationNotFound("generation does not exist")
    if generation.status in _TERMINAL_GENERATION_STATUSES:
        return generation
    if generation.status != "cancel_requested":
        transition_generation(generation.status, "cancel_requested")
        generation.status = "cancel_requested"
        generation.cancel_requested_at = current
    items = list(
        db.scalars(
            select(CanvasGenerationItem).where(
                CanvasGenerationItem.generation_id == generation.id
            )
        ).all()
    )
    for item in items:
        attempt = _latest_attempt(db, item.id)
        if item.status == "queued":
            transition_item(item.status, "cancelled")
            item.status = "cancelled"
            item.completed_at = current
            if attempt is not None and attempt.status == "queued":
                transition_attempt(attempt.status, "cancelled")
                attempt.status = "cancelled"
                attempt.completed_at = current
        elif item.status in {"running", "composing"}:
            transition_item(item.status, "cancel_requested")
            item.status = "cancel_requested"
            if attempt is not None and attempt.status in {"submitting", "polling"}:
                attempt.cancel_requested_at = current
                if attempt.status == "polling" and attempt.external_task_id and not _attempt_supports_cancel(attempt):
                    # The Provider cannot cancel an accepted async task.  Keep
                    # its saved task ID polling so final usage/result state is
                    # captured without any second submission.
                    attempt.normalized_error_code = "provider_cancel_unsupported"
                    attempt.safe_error_summary = "The Provider may continue executing and billing this task"
                else:
                    transition_attempt(attempt.status, "cancel_requested")
                    attempt.status = "cancel_requested"
            if attempt is not None and attempt.compose_operation_id:
                operation = db.get(CanvasAssetOperation, attempt.compose_operation_id)
                if operation is not None and operation.status == "queued":
                    operation.status = "cancelled"
                    operation.completed_at = current
                    transition_item(item.status, "cancelled")
                    item.status = "cancelled"
                    item.completed_at = current
    _refresh_generation(db, generation, now=current)
    for item in items:
        if item.status not in {"cancel_requested", "cancelled"}:
            continue
        append_generation_progress_event(
            db,
            generation=generation,
            item=item,
            attempt=_latest_attempt(db, item.id),
            event_type="generation.item.cancel_requested"
            if item.status == "cancel_requested"
            else "generation.item.cancelled",
        )
    return generation


def retry_generation_item(
    db: Session,
    *,
    item_id: str,
    now: datetime | None = None,
) -> ItemRetryResult:
    current = now or _utcnow()
    item = db.get(CanvasGenerationItem, item_id)
    if item is None:
        raise CanvasGenerationNotFound("generation item does not exist")
    generation = _generation_for_item(db, item)
    latest = _latest_attempt(db, item.id)
    if (
        item.status == "queued"
        and latest is not None
        and latest.status == "queued"
        and latest.attempt_no > 1
    ):
        return ItemRetryResult(
            item_id=item.id,
            attempt_id=latest.id,
            compose_operation_id=None,
            paid_retry=True,
        )
    if item.status == "composing" and latest is not None and latest.compose_operation_id:
        operation = db.get(CanvasAssetOperation, latest.compose_operation_id)
        if operation is not None and operation.status == "queued" and operation.attempt_count > 0:
            return ItemRetryResult(
                item_id=item.id,
                attempt_id=latest.id,
                compose_operation_id=operation.id,
                paid_retry=False,
            )
    if item.status not in {"failed", "unknown"}:
        raise CanvasGenerationActionConflict("generation item is not retryable")
    if latest is None:
        raise CanvasGenerationActionConflict("generation item has no attempt history")
    # Local compose retries preserve a successfully paid background and never
    # invoke a Provider again.
    if latest.background_asset_id and latest.compose_operation_id:
        operation = db.get(CanvasAssetOperation, latest.compose_operation_id)
        if operation is not None and operation.status in {"failed", "interrupted"}:
            restore_generation_reservation(
                db,
                generation_id=generation.id,
                required_bytes=_compose_retry_reservation(item),
            )
            operations.retry_asset_operation(db, operation_id=operation.id)
            transition_item(item.status, "composing")
            item.status = "composing"
            item.safe_current_error_code = None
            item.safe_current_error_summary = None
            if generation.status != "running":
                transition_generation(generation.status, "running")
                generation.status = "running"
            generation.completed_at = None
            append_generation_progress_event(
                db,
                generation=generation,
                item=item,
                attempt=latest,
                event_type="generation.item.compose_retried",
            )
            return ItemRetryResult(
                item_id=item.id,
                attempt_id=latest.id,
                compose_operation_id=operation.id,
                paid_retry=False,
            )
    restore_generation_reservation(
        db,
        generation_id=generation.id,
        required_bytes=_paid_retry_reservation(item),
    )
    next_no = latest.attempt_no + 1
    next_attempt = CanvasGenerationAttempt(
        id=str(uuid4()),
        item_id=item.id,
        attempt_no=next_no,
        provider_id=latest.provider_id,
        provider_config_version=latest.provider_config_version,
        model_profile_id=latest.model_profile_id,
        model_config_version=latest.model_config_version,
        provider_config_snapshot_json=latest.provider_config_snapshot_json,
        model_config_snapshot_json=latest.model_config_snapshot_json,
        status="queued",
        provider_result_stage="awaiting_provider",
        upstream_idempotency_key=f"canvas:{generation.id}:{item.id}:{next_no}",
        usage_json="{}",
    )
    db.add(next_attempt)
    transition_item(item.status, "queued")
    item.status = "queued"
    item.attempt_count = next_no
    item.safe_current_error_code = None
    item.safe_current_error_summary = None
    if generation.status != "running":
        transition_generation(generation.status, "running")
        generation.status = "running"
    generation.completed_at = None
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=next_attempt,
        event_type="generation.item.retried",
    )
    return ItemRetryResult(
        item_id=item.id,
        attempt_id=next_attempt.id,
        compose_operation_id=None,
        paid_retry=True,
    )


def resolve_unknown_item(
    db: Session,
    *,
    item_id: str,
    action: Literal["abandon", "retry"],
    now: datetime | None = None,
) -> CanvasGenerationAttempt | None:
    item = db.get(CanvasGenerationItem, item_id)
    if item is None:
        raise CanvasGenerationNotFound("generation item does not exist")
    if item.status != "unknown":
        raise CanvasGenerationActionConflict("generation item is not unresolved")
    if action == "retry":
        result = retry_generation_item(db, item_id=item_id, now=now)
        return db.get(CanvasGenerationAttempt, result.attempt_id) if result.attempt_id else None
    if action != "abandon":
        raise CanvasGenerationValidationError("unknown resolution action is invalid")
    current = now or _utcnow()
    generation = _generation_for_item(db, item)
    transition_item(item.status, "cancelled")
    item.status = "cancelled"
    item.completed_at = current
    _refresh_generation(db, generation, now=current)
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=_latest_attempt(db, item.id),
        event_type="generation.item.unknown_abandoned",
    )
    return None


def canvas_generation_project_activity_guard(
    db: Session,
    project_id: str,
) -> list[dict[str, object]]:
    rows = db.execute(
        select(CanvasGeneration.id, CanvasGeneration.status)
        .where(
            CanvasGeneration.project_id == project_id,
            CanvasGeneration.status.in_(tuple(_ACTIVE_GENERATION_STATUSES)),
        )
        .order_by(CanvasGeneration.created_at, CanvasGeneration.id)
    ).all()
    return [
        {"kind": "canvas_generation", "generationId": row.id, "status": row.status}
        for row in rows
    ]


project_service.register_canvas_project_activity_guard(canvas_generation_project_activity_guard)


__all__ = [
    "CanvasGenerationActionConflict",
    "ItemRetryResult",
    "RecoverySummary",
    "canvas_generation_project_activity_guard",
    "recover_canvas_generation_work",
    "request_generation_cancel",
    "resolve_unknown_item",
    "retry_generation_item",
]
