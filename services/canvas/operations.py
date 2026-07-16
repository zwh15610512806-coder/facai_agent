"""Transactional queue and retry contracts for local Product Canvas operations."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from canvas_models import CanvasAsset, CanvasAssetOperation, CanvasEvent, CanvasProject
from services.canvas.events import append_canvas_event
from services.canvas import projects as project_service


OperationLane = Literal["rembg", "local"]

OPERATION_TYPES = frozenset({"cutout", "compose", "export"})
RETRYABLE_OPERATION_STATUSES = frozenset({"failed", "interrupted"})
ACTIVE_OPERATION_STATUSES = frozenset({"queued", "running", "cancel_requested"})
OPERATION_LANE_TYPES: dict[OperationLane, tuple[str, ...]] = {
    "rembg": ("cutout",),
    "local": ("compose", "export"),
}
OPERATION_OUTPUT_ASSET_TYPES = {
    "cutout": "cutout",
    "compose": "composed",
    "export": "export",
}
OPERATION_LEASE_SECONDS = 300
MAX_OPERATION_REQUEST_SNAPSHOT_BYTES = 256 * 1024
AUTOMATIC_CUTOUT_PROCESSOR_VERSION = "rembg-isnet-general-use-mask-only-v1"


class CanvasOperationError(Exception):
    """Base class for safe operation-domain failures."""


class CanvasOperationNotFound(CanvasOperationError, LookupError):
    def __init__(self, resource_id: str):
        self.resource_id = resource_id
        super().__init__(f"canvas operation resource does not exist: {resource_id}")


class CanvasOperationIdempotencyConflict(CanvasOperationError):
    def __init__(self, *, project_id: str, operation_type: str, idempotency_key: str):
        self.project_id = project_id
        self.operation_type = operation_type
        self.idempotency_key = idempotency_key
        super().__init__("canvas operation idempotency key has a different request fingerprint")


class CanvasOperationStatusConflict(CanvasOperationError):
    def __init__(self, *, operation_id: str, status: str):
        self.operation_id = operation_id
        self.status = status
        super().__init__(f"canvas operation status does not allow this action: {status}")


class CanvasProductAssetNotReady(CanvasOperationError):
    def __init__(self, *, status: str):
        self.status = status
        super().__init__(f"canvas product asset is not compositable yet: {status}")


@dataclass(frozen=True)
class ClaimedOperation:
    id: str
    project_id: str
    operation_type: str
    status: str
    attempt_count: int
    worker_id: str
    input_asset_id: str
    output_asset_id: str | None
    request_snapshot: dict[str, Any]
    lease_expires_at: datetime


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _canonical_json_object(value: dict[str, Any], *, field_name: str) -> str:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object")
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        serialized_size = len(serialized.encode("utf-8"))
    except (OverflowError, RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite JSON") from exc
    if serialized_size > MAX_OPERATION_REQUEST_SNAPSHOT_BYTES:
        raise ValueError(
            f"{field_name} exceeds {MAX_OPERATION_REQUEST_SNAPSHOT_BYTES} UTF-8 bytes"
        )
    return serialized


def _load_json_object(value: str | None) -> dict[str, Any]:
    try:
        loaded = json.loads(value or "{}")
    except (RecursionError, TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _validate_operation_type(operation_type: str) -> str:
    if operation_type not in OPERATION_TYPES:
        raise ValueError("operation_type must be cutout, compose, or export")
    return operation_type


def _validate_bounded_text(value: str, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise ValueError(f"{field_name} must contain 1 to {max_length} characters")
    return normalized


def _request_fingerprint(
    *,
    project_id: str,
    operation_type: str,
    input_asset_id: str,
    request_snapshot_json: str,
) -> str:
    envelope = {
        "inputAssetId": input_asset_id,
        "operationType": operation_type,
        "projectId": project_id,
        "requestSnapshot": _load_json_object(request_snapshot_json),
    }
    canonical = _canonical_json_object(envelope, field_name="operation request")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _find_idempotent_operation(
    db: Session,
    *,
    project_id: str,
    operation_type: str,
    idempotency_key: str,
) -> CanvasAssetOperation | None:
    return db.execute(
        select(CanvasAssetOperation).where(
            CanvasAssetOperation.project_id == project_id,
            CanvasAssetOperation.operation_type == operation_type,
            CanvasAssetOperation.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()


def _return_idempotent_or_raise(
    operation: CanvasAssetOperation,
    *,
    expected_fingerprint: str,
) -> CanvasAssetOperation:
    actual_fingerprint = _request_fingerprint(
        project_id=operation.project_id,
        operation_type=operation.operation_type,
        input_asset_id=operation.input_asset_id,
        request_snapshot_json=operation.request_snapshot_json,
    )
    if actual_fingerprint != expected_fingerprint:
        raise CanvasOperationIdempotencyConflict(
            project_id=operation.project_id,
            operation_type=operation.operation_type,
            idempotency_key=operation.idempotency_key,
        )
    return operation


def _require_live_input_asset(
    db: Session,
    *,
    project_id: str,
    input_asset_id: str,
) -> CanvasAsset:
    project = _require_active_project(db, project_id=project_id)
    asset = db.execute(
        select(CanvasAsset).where(
            CanvasAsset.id == input_asset_id,
            CanvasAsset.project_id == project_id,
            CanvasAsset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if asset is None:
        raise CanvasOperationNotFound(input_asset_id)
    return asset


def _require_active_project(db: Session, *, project_id: str) -> CanvasProject:
    project = db.get(CanvasProject, project_id)
    if project is None:
        raise CanvasOperationNotFound(project_id)
    if project.status != "active":
        raise project_service.CanvasProjectStatusConflict(project.status)
    return project


def _require_cutout_input(asset: CanvasAsset) -> None:
    if asset.asset_type != "working" or asset.mime_type != "image/png":
        raise CanvasOperationStatusConflict(
            operation_id=asset.id,
            status="invalid_input",
        )


def enqueue_asset_operation(
    db: Session,
    *,
    project_id: str,
    operation_type: str,
    input_asset_id: str,
    idempotency_key: str,
    request_snapshot: dict,
) -> CanvasAssetOperation:
    """Enqueue one fingerprinted operation without committing the caller's transaction."""

    operation_type = _validate_operation_type(operation_type)
    idempotency_key = _validate_bounded_text(
        idempotency_key,
        field_name="idempotency_key",
        max_length=200,
    )
    request_snapshot_json = _canonical_json_object(
        request_snapshot,
        field_name="request_snapshot",
    )
    _require_live_input_asset(
        db,
        project_id=project_id,
        input_asset_id=input_asset_id,
    )
    expected_fingerprint = _request_fingerprint(
        project_id=project_id,
        operation_type=operation_type,
        input_asset_id=input_asset_id,
        request_snapshot_json=request_snapshot_json,
    )
    existing = _find_idempotent_operation(
        db,
        project_id=project_id,
        operation_type=operation_type,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return _return_idempotent_or_raise(
            existing,
            expected_fingerprint=expected_fingerprint,
        )

    operation = CanvasAssetOperation(
        id=str(uuid4()),
        project_id=project_id,
        operation_type=operation_type,
        status="queued",
        attempt_count=0,
        input_asset_id=input_asset_id,
        request_snapshot_json=request_snapshot_json,
        idempotency_key=idempotency_key,
    )
    try:
        with db.begin_nested():
            db.add(operation)
            db.flush([operation])
            canvas_event = append_canvas_event(
                db,
                project_id=project_id,
                operation_id=operation.id,
                event_type="operation.queued",
                payload={
                    "inputAssetId": input_asset_id,
                    "operationId": operation.id,
                    "operationType": operation_type,
                    "status": "queued",
                },
            )
            db.flush([canvas_event])
    except IntegrityError:
        winner = _find_idempotent_operation(
            db,
            project_id=project_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
        )
        if winner is None:
            raise
        return _return_idempotent_or_raise(
            winner,
            expected_fingerprint=expected_fingerprint,
        )
    return operation


def enqueue_automatic_cutout(
    db: Session,
    *,
    project_id: str,
    input_asset_id: str,
) -> CanvasAssetOperation:
    """Enqueue the one stable automatic cutout associated with a source asset."""

    asset = _require_live_input_asset(
        db,
        project_id=project_id,
        input_asset_id=input_asset_id,
    )
    _require_cutout_input(asset)
    operation = enqueue_asset_operation(
        db,
        project_id=project_id,
        operation_type="cutout",
        input_asset_id=input_asset_id,
        idempotency_key=(
            f"automatic-cutout:{input_asset_id}:{asset.sha256}:"
            f"{AUTOMATIC_CUTOUT_PROCESSOR_VERSION}"
        ),
        request_snapshot={
            "inputAssetId": input_asset_id,
            "inputSha256": asset.sha256,
            "mode": "automatic",
            "processorVersion": AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
        },
    )
    if operation.processor_version != AUTOMATIC_CUTOUT_PROCESSOR_VERSION:
        operation.processor_version = AUTOMATIC_CUTOUT_PROCESSOR_VERSION
        db.flush([operation])
    return operation


enqueue_automatic_cutout_operation = enqueue_automatic_cutout


def get_asset_operation(db: Session, *, operation_id: str) -> CanvasAssetOperation:
    operation = db.get(CanvasAssetOperation, operation_id)
    if operation is None:
        raise CanvasOperationNotFound(operation_id)
    return operation


get_operation = get_asset_operation


def list_project_operations(db: Session, *, project_id: str) -> list[CanvasAssetOperation]:
    if db.get(CanvasProject, project_id) is None:
        raise CanvasOperationNotFound(project_id)
    return list(
        db.execute(
            select(CanvasAssetOperation)
            .where(CanvasAssetOperation.project_id == project_id)
            .order_by(
                CanvasAssetOperation.created_at.desc(),
                CanvasAssetOperation.id.desc(),
            )
        ).scalars()
    )


list_operations = list_project_operations


def _retry_request_matches(
    db: Session,
    *,
    operation_id: str,
    client_request_fingerprint: str,
) -> bool:
    events = db.execute(
        select(CanvasEvent.payload_json)
        .where(
            CanvasEvent.operation_id == operation_id,
            CanvasEvent.event_type == "operation.retried",
        )
        .order_by(CanvasEvent.id.desc())
    ).scalars()
    return any(
        _load_json_object(payload_json).get("clientRequestFingerprint")
        == client_request_fingerprint
        for payload_json in events
    )


def _operation_for_retry_request(
    db: Session,
    *,
    project_id: str,
    input_asset_id: str,
    client_request_fingerprint: str,
) -> CanvasAssetOperation | None:
    rows = db.execute(
        select(CanvasAssetOperation, CanvasEvent.payload_json)
        .join(CanvasEvent, CanvasEvent.operation_id == CanvasAssetOperation.id)
        .where(
            CanvasAssetOperation.project_id == project_id,
            CanvasAssetOperation.operation_type == "cutout",
            CanvasAssetOperation.input_asset_id == input_asset_id,
            CanvasEvent.event_type == "operation.retried",
        )
        .order_by(CanvasEvent.id.desc())
    ).all()
    for operation, payload_json in rows:
        if (
            _load_json_object(payload_json).get("clientRequestFingerprint")
            == client_request_fingerprint
        ):
            return operation
    return None


def _retry_asset_operation(
    db: Session,
    *,
    operation_id: str,
    client_request_fingerprint: str | None = None,
) -> CanvasAssetOperation:
    operation = get_asset_operation(db, operation_id=operation_id)
    _require_active_project(db, project_id=operation.project_id)
    if operation.status == "queued":
        if client_request_fingerprint is not None and not _retry_request_matches(
            db,
            operation_id=operation.id,
            client_request_fingerprint=client_request_fingerprint,
        ):
            raise CanvasOperationStatusConflict(
                operation_id=operation.id,
                status=operation.status,
            )
        return operation
    if operation.status not in RETRYABLE_OPERATION_STATUSES:
        raise CanvasOperationStatusConflict(
            operation_id=operation.id,
            status=operation.status,
        )

    now = _utcnow()
    statement = (
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == operation.id,
            CanvasAssetOperation.status.in_(tuple(RETRYABLE_OPERATION_STATUSES)),
            CanvasAssetOperation.project_id.in_(
                select(CanvasProject.id).where(CanvasProject.status == "active")
            ),
        )
        .values(
            status="queued",
            worker_id=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_attempt_at=now,
            cancel_requested_at=None,
            output_asset_id=None,
            safe_error_json=None,
            started_at=None,
            completed_at=None,
            updated_at=now,
        )
        .returning(CanvasAssetOperation)
        .execution_options(synchronize_session="fetch")
    )
    retried = db.execute(statement).scalar_one_or_none()
    if retried is None:
        db.expire(operation)
        operation = get_asset_operation(db, operation_id=operation_id)
        if operation.status == "queued" and (
            client_request_fingerprint is None
            or _retry_request_matches(
                db,
                operation_id=operation.id,
                client_request_fingerprint=client_request_fingerprint,
            )
        ):
            return operation
        raise CanvasOperationStatusConflict(
            operation_id=operation.id,
            status=operation.status,
        )

    payload: dict[str, Any] = {
        "attemptCount": retried.attempt_count,
        "operationId": retried.id,
        "operationType": retried.operation_type,
        "status": "queued",
    }
    if client_request_fingerprint is not None:
        payload["clientRequestFingerprint"] = client_request_fingerprint
    canvas_event = append_canvas_event(
        db,
        project_id=retried.project_id,
        operation_id=retried.id,
        event_type="operation.retried",
        payload=payload,
    )
    db.flush([canvas_event])
    return retried


def retry_asset_operation(db: Session, *, operation_id: str) -> CanvasAssetOperation:
    """Requeue a failed/interrupted operation idempotently without committing."""

    return _retry_asset_operation(db, operation_id=operation_id)


def _explicit_cutout_key(input_asset_id: str, client_request_id: str) -> str:
    request_digest = hashlib.sha256(client_request_id.encode("utf-8")).hexdigest()[:32]
    return f"explicit-cutout:{input_asset_id}:{request_digest}"


def retry_cutout_for_asset(
    db: Session,
    *,
    input_asset_id: str,
    client_request_id: str,
) -> CanvasAssetOperation:
    """Retry the latest cutout or enqueue one explicit, idempotent re-cutout."""

    client_request_id = _validate_bounded_text(
        client_request_id,
        field_name="client_request_id",
        max_length=200,
    )
    source = db.execute(
        select(CanvasAsset).where(
            CanvasAsset.id == input_asset_id,
            CanvasAsset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if source is None:
        raise CanvasOperationNotFound(input_asset_id)
    _require_active_project(db, project_id=source.project_id)
    _require_cutout_input(source)

    explicit_key = _explicit_cutout_key(input_asset_id, client_request_id)
    explicit = _find_idempotent_operation(
        db,
        project_id=source.project_id,
        operation_type="cutout",
        idempotency_key=explicit_key,
    )
    request_fingerprint = hashlib.sha256(client_request_id.encode("utf-8")).hexdigest()
    if explicit is not None:
        if explicit.input_asset_id != input_asset_id:
            raise CanvasOperationIdempotencyConflict(
                project_id=source.project_id,
                operation_type="cutout",
                idempotency_key=explicit_key,
            )
        return explicit

    prior_request_operation = _operation_for_retry_request(
        db,
        project_id=source.project_id,
        input_asset_id=input_asset_id,
        client_request_fingerprint=request_fingerprint,
    )
    if prior_request_operation is not None:
        return prior_request_operation

    active = db.execute(
        select(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.project_id == source.project_id,
            CanvasAssetOperation.operation_type == "cutout",
            CanvasAssetOperation.input_asset_id == input_asset_id,
            CanvasAssetOperation.status.in_(tuple(ACTIVE_OPERATION_STATUSES)),
        )
        .order_by(
            CanvasAssetOperation.created_at.desc(),
            CanvasAssetOperation.updated_at.desc(),
            CanvasAssetOperation.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if active is not None:
        if _retry_request_matches(
            db,
            operation_id=active.id,
            client_request_fingerprint=request_fingerprint,
        ):
            return active
        raise CanvasOperationStatusConflict(
            operation_id=active.id,
            status=active.status,
        )

    latest = db.execute(
        select(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.project_id == source.project_id,
            CanvasAssetOperation.operation_type == "cutout",
            CanvasAssetOperation.input_asset_id == input_asset_id,
        )
        .order_by(
            CanvasAssetOperation.created_at.desc(),
            CanvasAssetOperation.updated_at.desc(),
            CanvasAssetOperation.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise CanvasOperationNotFound(input_asset_id)
    if latest.status in RETRYABLE_OPERATION_STATUSES:
        return _retry_asset_operation(
            db,
            operation_id=latest.id,
            client_request_fingerprint=request_fingerprint,
        )
    if latest.status != "succeeded":
        raise CanvasOperationStatusConflict(
            operation_id=latest.id,
            status=latest.status,
        )

    explicit_operation = enqueue_asset_operation(
        db,
        project_id=source.project_id,
        operation_type="cutout",
        input_asset_id=input_asset_id,
        idempotency_key=explicit_key,
        request_snapshot={
            "clientRequestId": client_request_id,
            "inputAssetId": input_asset_id,
            "inputSha256": source.sha256,
            "mode": "explicit",
            "previousOperationId": latest.id,
            "processorVersion": AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
        },
    )
    if explicit_operation.processor_version != AUTOMATIC_CUTOUT_PROCESSOR_VERSION:
        explicit_operation.processor_version = AUTOMATIC_CUTOUT_PROCESSOR_VERSION
        db.flush([explicit_operation])
    return explicit_operation


def claim_next_operation(
    db: Session,
    *,
    worker_id: str,
    lane: OperationLane,
    now: datetime,
) -> ClaimedOperation | None:
    """Atomically claim one due queued operation in a dedicated local lane."""

    worker_id = _validate_bounded_text(worker_id, field_name="worker_id", max_length=100)
    if lane not in OPERATION_LANE_TYPES:
        raise ValueError("lane must be rembg or local")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    lane_types = OPERATION_LANE_TYPES[lane]
    candidate_id = (
        select(CanvasAssetOperation.id)
        .join(CanvasProject, CanvasProject.id == CanvasAssetOperation.project_id)
        .where(
            CanvasProject.status == "active",
            CanvasAssetOperation.status == "queued",
            CanvasAssetOperation.operation_type.in_(lane_types),
            CanvasAssetOperation.next_attempt_at <= now,
        )
        .order_by(
            CanvasAssetOperation.next_attempt_at,
            CanvasAssetOperation.created_at,
            CanvasAssetOperation.id,
        )
        .limit(1)
        .scalar_subquery()
    )
    lease_expires_at = now + timedelta(seconds=OPERATION_LEASE_SECONDS)
    statement = (
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == candidate_id,
            CanvasAssetOperation.status == "queued",
            CanvasAssetOperation.operation_type.in_(lane_types),
            CanvasAssetOperation.next_attempt_at <= now,
            CanvasAssetOperation.project_id.in_(
                select(CanvasProject.id).where(CanvasProject.status == "active")
            ),
        )
        .values(
            status="running",
            attempt_count=CanvasAssetOperation.attempt_count + 1,
            worker_id=worker_id,
            lease_expires_at=lease_expires_at,
            heartbeat_at=now,
            started_at=now,
            updated_at=now,
        )
        .returning(CanvasAssetOperation)
        .execution_options(synchronize_session="fetch", populate_existing=True)
    )
    operation = db.execute(statement).scalar_one_or_none()
    if operation is None:
        return None
    canvas_event = append_canvas_event(
        db,
        project_id=operation.project_id,
        operation_id=operation.id,
        event_type="operation.running",
        payload={
            "attemptCount": operation.attempt_count,
            "operationId": operation.id,
            "operationType": operation.operation_type,
            "status": "running",
        },
    )
    db.flush([canvas_event])
    return ClaimedOperation(
        id=operation.id,
        project_id=operation.project_id,
        operation_type=operation.operation_type,
        status=operation.status,
        attempt_count=operation.attempt_count,
        worker_id=operation.worker_id,
        input_asset_id=operation.input_asset_id,
        output_asset_id=operation.output_asset_id,
        request_snapshot=_load_json_object(operation.request_snapshot_json),
        lease_expires_at=operation.lease_expires_at,
    )


def recover_expired_operations(
    db: Session,
    *,
    lane: OperationLane,
    now: datetime,
) -> int:
    """Atomically requeue expired running work in one lane without committing."""

    if lane not in OPERATION_LANE_TYPES:
        raise ValueError("lane must be rembg or local")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    lane_types = OPERATION_LANE_TYPES[lane]
    recovered = list(
        db.execute(
            update(CanvasAssetOperation)
            .where(
                CanvasAssetOperation.status == "running",
                CanvasAssetOperation.operation_type.in_(lane_types),
                CanvasAssetOperation.lease_expires_at.is_not(None),
                CanvasAssetOperation.lease_expires_at <= now,
                CanvasAssetOperation.project_id.in_(
                    select(CanvasProject.id).where(CanvasProject.status == "active")
                ),
            )
            .values(
                status="queued",
                worker_id=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_attempt_at=now,
                started_at=None,
                updated_at=now,
            )
            .returning(CanvasAssetOperation)
            .execution_options(synchronize_session="fetch")
        ).scalars()
    )
    for operation in recovered:
        event = append_canvas_event(
            db,
            project_id=operation.project_id,
            operation_id=operation.id,
            event_type="operation.recovered",
            payload={
                "attemptCount": operation.attempt_count,
                "operationId": operation.id,
                "operationType": operation.operation_type,
                "reason": "lease_expired",
                "status": "queued",
            },
        )
        db.flush([event])
    return len(recovered)


def heartbeat_claimed_operation(
    db: Session,
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
    now: datetime,
) -> bool:
    """Extend a lease only when the exact running claim token is still current."""

    worker_id = _validate_bounded_text(worker_id, field_name="worker_id", max_length=100)
    if type(attempt_count) is not int or attempt_count <= 0:
        raise ValueError("attempt_count must be a positive integer")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    result = db.execute(
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == operation_id,
            CanvasAssetOperation.status == "running",
            CanvasAssetOperation.worker_id == worker_id,
            CanvasAssetOperation.attempt_count == attempt_count,
            CanvasAssetOperation.lease_expires_at.is_not(None),
            CanvasAssetOperation.lease_expires_at > now,
        )
        .values(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=OPERATION_LEASE_SECONDS),
            updated_at=now,
        )
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1


def release_claimed_operation(
    db: Session,
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
    now: datetime,
) -> bool:
    """Requeue an unstarted claim when its worker begins shutting down."""

    worker_id = _validate_bounded_text(worker_id, field_name="worker_id", max_length=100)
    if type(attempt_count) is not int or attempt_count <= 0:
        raise ValueError("attempt_count must be a positive integer")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    released = db.execute(
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == operation_id,
            CanvasAssetOperation.status == "running",
            CanvasAssetOperation.worker_id == worker_id,
            CanvasAssetOperation.attempt_count == attempt_count,
            CanvasAssetOperation.lease_expires_at.is_not(None),
            CanvasAssetOperation.lease_expires_at > now,
        )
        .values(
            status="queued",
            worker_id=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_attempt_at=now,
            started_at=None,
            completed_at=None,
            updated_at=now,
        )
        .returning(CanvasAssetOperation)
        .execution_options(synchronize_session="fetch")
    ).scalar_one_or_none()
    if released is None:
        return False
    event = append_canvas_event(
        db,
        project_id=released.project_id,
        operation_id=released.id,
        event_type="operation.released",
        payload={
            "attemptCount": released.attempt_count,
            "operationId": released.id,
            "operationType": released.operation_type,
            "reason": "worker_stopping",
            "status": "queued",
        },
    )
    db.flush([event])
    return True


def _safe_error_json(value: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise TypeError("safe_error must be an object")
    code = _validate_bounded_text(
        value.get("code"),
        field_name="safe_error.code",
        max_length=100,
    )
    message = _validate_bounded_text(
        value.get("message"),
        field_name="safe_error.message",
        max_length=500,
    )
    retryable = value.get("retryable")
    if type(retryable) is not bool:
        raise TypeError("safe_error.retryable must be a boolean")
    normalized = {
        "code": code,
        "message": " ".join(message.split()),
        "retryable": retryable,
    }
    return _canonical_json_object(normalized, field_name="safe_error"), normalized


def mark_claimed_operation_succeeded(
    db: Session,
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
    output_asset_id: str,
    now: datetime,
) -> CanvasAssetOperation | None:
    """Complete the exact claim token and emit its event in the caller transaction."""

    worker_id = _validate_bounded_text(worker_id, field_name="worker_id", max_length=100)
    if type(attempt_count) is not int or attempt_count <= 0:
        raise ValueError("attempt_count must be a positive integer")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    operation = db.get(CanvasAssetOperation, operation_id)
    if operation is None:
        return None
    output = db.execute(
        select(CanvasAsset).where(
            CanvasAsset.id == output_asset_id,
            CanvasAsset.project_id == operation.project_id,
            CanvasAsset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if output is None:
        raise CanvasOperationNotFound(output_asset_id)
    if output.asset_type != OPERATION_OUTPUT_ASSET_TYPES.get(operation.operation_type):
        raise CanvasOperationStatusConflict(
            operation_id=operation_id,
            status="invalid_output",
        )
    if operation.operation_type == "cutout" and (
        output.source_asset_id != operation.input_asset_id
        or output.transparency_status != "transparent"
    ):
        raise CanvasOperationStatusConflict(
            operation_id=operation_id,
            status="invalid_output",
        )
    completed = db.execute(
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == operation_id,
            CanvasAssetOperation.status == "running",
            CanvasAssetOperation.worker_id == worker_id,
            CanvasAssetOperation.attempt_count == attempt_count,
            CanvasAssetOperation.lease_expires_at.is_not(None),
            CanvasAssetOperation.lease_expires_at > now,
        )
        .values(
            status="succeeded",
            output_asset_id=output_asset_id,
            lease_expires_at=None,
            heartbeat_at=now,
            safe_error_json=None,
            completed_at=now,
            updated_at=now,
        )
        .returning(CanvasAssetOperation)
        .execution_options(synchronize_session="fetch")
    ).scalar_one_or_none()
    if completed is None:
        return None
    event = append_canvas_event(
        db,
        project_id=completed.project_id,
        operation_id=completed.id,
        event_type="operation.succeeded",
        payload={
            "attemptCount": completed.attempt_count,
            "operationId": completed.id,
            "operationType": completed.operation_type,
            "outputAssetId": output_asset_id,
            "status": "succeeded",
        },
    )
    db.flush([event])
    return completed


def mark_claimed_operation_failed(
    db: Session,
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
    safe_error: dict[str, Any],
    now: datetime,
) -> bool:
    """Fail the exact claim token with a bounded public error summary."""

    worker_id = _validate_bounded_text(worker_id, field_name="worker_id", max_length=100)
    if type(attempt_count) is not int or attempt_count <= 0:
        raise ValueError("attempt_count must be a positive integer")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    safe_error_json, normalized_error = _safe_error_json(safe_error)
    failed = db.execute(
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == operation_id,
            CanvasAssetOperation.status == "running",
            CanvasAssetOperation.worker_id == worker_id,
            CanvasAssetOperation.attempt_count == attempt_count,
            CanvasAssetOperation.lease_expires_at.is_not(None),
            CanvasAssetOperation.lease_expires_at > now,
        )
        .values(
            status="failed",
            lease_expires_at=None,
            heartbeat_at=now,
            safe_error_json=safe_error_json,
            completed_at=now,
            updated_at=now,
        )
        .returning(CanvasAssetOperation)
        .execution_options(synchronize_session="fetch")
    ).scalar_one_or_none()
    if failed is None:
        return False
    event = append_canvas_event(
        db,
        project_id=failed.project_id,
        operation_id=failed.id,
        event_type="operation.failed",
        payload={
            "attemptCount": failed.attempt_count,
            "operationId": failed.id,
            "operationType": failed.operation_type,
            "safeError": normalized_error,
            "status": "failed",
        },
    )
    db.flush([event])
    return True


def mark_claimed_operation_interrupted(
    db: Session,
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
    now: datetime,
) -> bool:
    """Invalidate an unfinished claim so stale CPU work cannot later publish."""

    worker_id = _validate_bounded_text(worker_id, field_name="worker_id", max_length=100)
    if type(attempt_count) is not int or attempt_count <= 0:
        raise ValueError("attempt_count must be a positive integer")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    interrupted = db.execute(
        update(CanvasAssetOperation)
        .where(
            CanvasAssetOperation.id == operation_id,
            CanvasAssetOperation.status == "running",
            CanvasAssetOperation.worker_id == worker_id,
            CanvasAssetOperation.attempt_count == attempt_count,
        )
        .values(
            status="interrupted",
            worker_id=None,
            lease_expires_at=None,
            heartbeat_at=now,
            completed_at=now,
            updated_at=now,
        )
        .returning(CanvasAssetOperation)
        .execution_options(synchronize_session="fetch")
    ).scalar_one_or_none()
    if interrupted is None:
        return False
    event = append_canvas_event(
        db,
        project_id=interrupted.project_id,
        operation_id=interrupted.id,
        event_type="operation.interrupted",
        payload={
            "attemptCount": interrupted.attempt_count,
            "operationId": interrupted.id,
            "operationType": interrupted.operation_type,
            "status": "interrupted",
        },
    )
    db.flush([event])
    return True


def require_compositable_product_asset(
    db: Session,
    *,
    project_id: str,
    source_asset_id: str,
    allow_opaque_fallback: bool = False,
) -> CanvasAsset:
    """Resolve a ready transparent product render or an explicit opaque fallback."""

    if type(allow_opaque_fallback) is not bool:
        raise TypeError("allow_opaque_fallback must be a boolean")
    working = db.execute(
        select(CanvasAsset).where(
            CanvasAsset.id == source_asset_id,
            CanvasAsset.project_id == project_id,
            CanvasAsset.asset_type == "working",
            CanvasAsset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if working is None:
        raise CanvasOperationNotFound(source_asset_id)
    _require_active_project(db, project_id=project_id)

    if working.transparency_status == "transparent":
        return working

    ready = db.execute(
        select(CanvasAsset)
        .join(
            CanvasAssetOperation,
            CanvasAssetOperation.output_asset_id == CanvasAsset.id,
        )
        .where(
            CanvasAssetOperation.project_id == project_id,
            CanvasAssetOperation.operation_type == "cutout",
            CanvasAssetOperation.status == "succeeded",
            CanvasAssetOperation.input_asset_id == working.id,
            CanvasAsset.asset_type == "cutout",
            CanvasAsset.deleted_at.is_(None),
        )
        .order_by(
            CanvasAssetOperation.completed_at.desc(),
            CanvasAssetOperation.updated_at.desc(),
            CanvasAssetOperation.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if ready is not None:
        return ready
    if allow_opaque_fallback:
        return working

    latest_status = db.execute(
        select(CanvasAssetOperation.status)
        .where(
            CanvasAssetOperation.project_id == project_id,
            CanvasAssetOperation.operation_type == "cutout",
            CanvasAssetOperation.input_asset_id == working.id,
        )
        .order_by(
            CanvasAssetOperation.created_at.desc(),
            CanvasAssetOperation.updated_at.desc(),
            CanvasAssetOperation.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    raise CanvasProductAssetNotReady(
        status=latest_status or "cutout_required",
    )


def canvas_operation_project_activity_guard(
    db: Session,
    project_id: str,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            CanvasAssetOperation.id,
            CanvasAssetOperation.operation_type,
            CanvasAssetOperation.status,
        )
        .where(
            CanvasAssetOperation.project_id == project_id,
            CanvasAssetOperation.status.in_(tuple(ACTIVE_OPERATION_STATUSES)),
        )
        .order_by(CanvasAssetOperation.created_at, CanvasAssetOperation.id)
    ).all()
    return [
        {
            "kind": "canvas_asset_operation",
            "operationId": operation_id,
            "operationType": operation_type,
            "status": status,
        }
        for operation_id, operation_type, status in rows
    ]


project_service.register_canvas_project_activity_guard(
    canvas_operation_project_activity_guard
)


__all__ = [
    "ACTIVE_OPERATION_STATUSES",
    "AUTOMATIC_CUTOUT_PROCESSOR_VERSION",
    "CanvasOperationError",
    "CanvasOperationIdempotencyConflict",
    "CanvasOperationNotFound",
    "CanvasOperationStatusConflict",
    "CanvasProductAssetNotReady",
    "ClaimedOperation",
    "MAX_OPERATION_REQUEST_SNAPSHOT_BYTES",
    "OPERATION_LEASE_SECONDS",
    "canvas_operation_project_activity_guard",
    "claim_next_operation",
    "enqueue_asset_operation",
    "enqueue_automatic_cutout",
    "enqueue_automatic_cutout_operation",
    "get_asset_operation",
    "get_operation",
    "heartbeat_claimed_operation",
    "list_operations",
    "list_project_operations",
    "mark_claimed_operation_failed",
    "mark_claimed_operation_interrupted",
    "mark_claimed_operation_succeeded",
    "recover_expired_operations",
    "release_claimed_operation",
    "require_compositable_product_asset",
    "retry_asset_operation",
    "retry_cutout_for_asset",
]
