"""PostgreSQL-backed integration jobs and connection/resource leases.

Every public mutation stages work in the caller's SQLAlchemy ``Session``.  No
function in this module commits or rolls back: transaction boundaries belong to
the scheduler, worker, callback, or management request that called it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import unicodedata
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from urllib.parse import unquote_plus

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from integration_models import (
    IntegrationConnection,
    IntegrationJob,
    IntegrationSyncCheckpoint,
)
from integrations.redaction import assert_payload_safe, normalize_payload_key
from integrations.types import (
    CheckpointStatus,
    JobStatus,
    JobType,
    ResourceType,
    utc_now,
)


MIN_RESOURCE_JITTER_SECONDS = 1
MAX_RESOURCE_JITTER_SECONDS = 5
MAX_CURSOR_METADATA_BYTES = 4096
MAX_CURSOR_DEPTH = 4
MAX_CURSOR_ITEMS = 64
MAX_CURSOR_STRING_LENGTH = 512
MAX_PLATFORM_CURSOR_LENGTH = 4096


class JobErrorCode(str, Enum):
    """Allowlisted, non-sensitive worker failure classifications."""

    AUTHORIZATION_REQUIRED = "authorization_required"
    CONNECTOR_UNAVAILABLE = "connector_unavailable"
    INTERNAL_ERROR = "internal_error"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    RESOURCE_LEASE_BUSY = "resource_lease_busy"
    TRANSIENT_PROVIDER_ERROR = "transient_provider_error"
    LEASE_EXPIRED = "lease_expired"
    MAX_ATTEMPTS_EXHAUSTED = "max_attempts_exhausted"
    PERMISSION_DENIED = "permission_denied"


class JobErrorSummary(str, Enum):
    """Closed diagnostic summaries safe for persistent operator display."""

    AUTHORIZATION_REFRESH_REQUIRED = "authorization refresh required"
    CONNECTOR_NOT_CONFIGURED = "connector is not configured"
    INTERNAL_WORKER_FAILURE = "internal worker failure"
    PROVIDER_RESPONSE_REJECTED = "provider response rejected"
    PROVIDER_THROTTLED = "provider rate limit reached"
    RESOURCE_LEASE_CONTENTION = "resource lease is busy"
    TRANSIENT_PROVIDER_FAILURE = "transient provider failure"
    LEASE_EXPIRED_RETRY_SCHEDULED = "expired lease scheduled for retry"
    FINAL_ATTEMPT_LEASE_EXPIRED = "final attempt lease expired"
    PROVIDER_PERMISSION_DENIED = "provider permission denied"


_ERROR_SUMMARY_BY_CODE = {
    JobErrorCode.AUTHORIZATION_REQUIRED: JobErrorSummary.AUTHORIZATION_REFRESH_REQUIRED,
    JobErrorCode.CONNECTOR_UNAVAILABLE: JobErrorSummary.CONNECTOR_NOT_CONFIGURED,
    JobErrorCode.INTERNAL_ERROR: JobErrorSummary.INTERNAL_WORKER_FAILURE,
    JobErrorCode.INVALID_PROVIDER_RESPONSE: JobErrorSummary.PROVIDER_RESPONSE_REJECTED,
    JobErrorCode.PROVIDER_RATE_LIMITED: JobErrorSummary.PROVIDER_THROTTLED,
    JobErrorCode.RESOURCE_LEASE_BUSY: JobErrorSummary.RESOURCE_LEASE_CONTENTION,
    JobErrorCode.TRANSIENT_PROVIDER_ERROR: JobErrorSummary.TRANSIENT_PROVIDER_FAILURE,
    JobErrorCode.LEASE_EXPIRED: JobErrorSummary.LEASE_EXPIRED_RETRY_SCHEDULED,
    JobErrorCode.MAX_ATTEMPTS_EXHAUSTED: JobErrorSummary.FINAL_ATTEMPT_LEASE_EXPIRED,
    JobErrorCode.PERMISSION_DENIED: JobErrorSummary.PROVIDER_PERMISSION_DENIED,
}


_SECRET_TEXT = re.compile(
    r"(?ix)"
    r"(?:"
    r"access[\s_-]*token|refresh[\s_-]*token|app[\s_-]*secret|"
    r"client[\s_-]*secret|authorization[\s_-]*code|"
    r"(?:x[\s_-]*)?api[\s_-]*key|proxy[\s_-]*authorization|"
    r"authorization|set[\s_-]*cookie|cookie|token|secret"
    r")"
    r"\s*[\"']?\s*[:=]"
    r"|\bbearer(?:\s|[\"'])+"
)
_EMAIL_TEXT = re.compile(
    r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?![\w.-])"
)
_MAINLAND_PHONE_TEXT = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PRC_ID_TEXT = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")
_CURSOR_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_SECRET_CURSOR_KEYS = frozenset(
    {
        "auth",
        "authorization",
        "proxyauthorization",
        "apikey",
        "xapikey",
        "credential",
        "credentials",
        "accesstoken",
        "refreshtoken",
        "appsecret",
        "clientsecret",
        "authorizationcode",
        "cookie",
        "setcookie",
    }
)


_PAYLOAD_FIELDS: dict[JobType, tuple[frozenset[str], frozenset[str]]] = {
    JobType.SYNC_RESOURCE: (
        frozenset(
            {
                "connection_id",
                "resource_type",
                "window_start",
                "window_end",
            }
        ),
        frozenset({"checkpoint_id", "cursor"}),
    ),
    JobType.REFRESH_AUTHORIZATION: (
        frozenset({"authorization_id"}),
        frozenset(),
    ),
    JobType.PROCESS_EVENT: (
        frozenset({"event_inbox_id", "connection_id"}),
        frozenset(),
    ),
    JobType.ARCHIVE_CLEANUP: (
        frozenset({"archive_manifest_id"}),
        frozenset(),
    ),
    JobType.EXPORT: (
        frozenset({"export_job_id"}),
        frozenset(),
    ),
    JobType.PURGE_CONNECTION: (
        frozenset({"connection_id"}),
        frozenset(),
    ),
}
_ID_PAYLOAD_FIELDS = frozenset(
    {
        "archive_manifest_id",
        "authorization_id",
        "checkpoint_id",
        "connection_id",
        "event_inbox_id",
        "export_job_id",
    }
)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _positive_duration(value: timedelta, *, field_name: str) -> timedelta:
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise ValueError(f"{field_name} must be a positive timedelta")
    if value > timedelta(hours=1):
        raise ValueError(f"{field_name} must not exceed one hour")
    return value


def _owner(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("owner must be a non-empty bounded identifier")
    return value


def _target_id(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("target_id must be a string or integer identifier")
    selected = str(value)
    if (
        not selected
        or selected != selected.strip()
        or len(selected) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in selected)
    ):
        raise ValueError("target_id must be a non-empty bounded identifier")
    return selected


def _validate_json_value(value: Any, *, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain a non-finite number")
        return value
    if isinstance(value, (list, tuple)):
        return [
            _validate_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        selected: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} must use string object keys")
            selected[key] = _validate_json_value(item, path=f"{path}.{key}")
        return selected
    raise ValueError(f"{path} contains a non-JSON value")


def _positive_payload_id(value: Any, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _iso_aware_utc(value: Any, *, field_name: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be an ISO timezone-aware timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be an ISO timezone-aware timestamp"
        ) from exc
    selected = _aware_utc(parsed, field_name=field_name)
    canonical = selected.isoformat().replace("+00:00", "Z")
    return canonical, selected


def _decoded_text(value: str) -> str:
    selected = unicodedata.normalize("NFKC", value)
    # Fully unwrap bounded, repeatedly URL-encoded content so nested query or
    # header credentials cannot evade the secret classifiers.
    for _ in range(MAX_CURSOR_STRING_LENGTH):
        decoded = unquote_plus(selected)
        if decoded == selected:
            break
        selected = decoded
    return unicodedata.normalize("NFKC", selected)


def _assert_cursor_string_safe(
    value: str,
    *,
    path: str,
    maximum: int = MAX_CURSOR_STRING_LENGTH,
) -> str:
    if (
        not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{path} contains an unsafe cursor string")
    decoded = _decoded_text(value)
    if any(
        pattern.search(decoded) is not None
        for pattern in (
            _SECRET_TEXT,
            _EMAIL_TEXT,
            _MAINLAND_PHONE_TEXT,
            _PRC_ID_TEXT,
        )
    ):
        raise ValueError(f"{path} contains sensitive cursor content")
    return value


def _cursor_metadata(value: Any, *, path: str = "$.cursor", depth: int = 0) -> Any:
    if depth > MAX_CURSOR_DEPTH:
        raise ValueError(f"{path} exceeds the cursor metadata depth limit")
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain a non-finite number")
        return value
    if isinstance(value, str):
        return _assert_cursor_string_safe(value, path=path)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_CURSOR_ITEMS:
            raise ValueError(f"{path} exceeds the cursor metadata item limit")
        return [
            _cursor_metadata(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if len(value) > MAX_CURSOR_ITEMS:
            raise ValueError(f"{path} exceeds the cursor metadata item limit")
        selected: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _CURSOR_KEY.fullmatch(key) is None:
                raise ValueError(f"{path} contains an invalid cursor metadata key")
            if normalize_payload_key(key) in _SECRET_CURSOR_KEYS:
                raise ValueError(f"{path} contains a secret-like cursor metadata key")
            selected[key] = _cursor_metadata(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        assert_payload_safe(selected)
        return selected
    raise ValueError(f"{path} contains a non-JSON cursor value")


def _validate_job_payload(
    job_type: JobType,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    selected = _validate_json_value(payload)
    assert_payload_safe(selected)
    required, optional = _PAYLOAD_FIELDS[job_type]
    keys = frozenset(selected)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise ValueError("payload fields do not match the job type schema")
    for field_name in keys & _ID_PAYLOAD_FIELDS:
        selected[field_name] = _positive_payload_id(
            selected[field_name],
            field_name=field_name,
        )
    if job_type is JobType.SYNC_RESOURCE:
        try:
            selected["resource_type"] = ResourceType(selected["resource_type"]).value
        except (TypeError, ValueError) as exc:
            raise ValueError("resource_type must be a ResourceType value") from exc
        start_iso, start = _iso_aware_utc(
            selected["window_start"],
            field_name="window_start",
        )
        end_iso, end = _iso_aware_utc(
            selected["window_end"],
            field_name="window_end",
        )
        if end <= start:
            raise ValueError("window_end must be after window_start")
        selected["window_start"] = start_iso
        selected["window_end"] = end_iso
        if "cursor" in selected:
            if not isinstance(selected["cursor"], Mapping):
                raise ValueError("cursor must be a metadata object")
            selected["cursor"] = _cursor_metadata(selected["cursor"])
            encoded = canonical_logical_request(selected["cursor"]).encode("utf-8")
            if len(encoded) > MAX_CURSOR_METADATA_BYTES:
                raise ValueError("cursor metadata exceeds the size limit")
    return selected


def canonical_logical_request(logical_request: Any) -> str:
    """Return stable sorted, compact JSON for a logical work request."""

    selected = _validate_json_value(logical_request)
    return json.dumps(
        selected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def make_dedupe_key(
    job_type: JobType,
    target_id: str | int,
    logical_request: Any,
) -> str:
    """Hash job type, target and canonical logical request per queue contract."""

    if not isinstance(job_type, JobType):
        raise ValueError("job_type must be a JobType")
    canonical = canonical_logical_request(logical_request)
    material = f"{job_type.value}\n{_target_id(target_id)}\n{canonical}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _manual_request(
    logical_request: Any,
    *,
    manual: bool,
    logical_request_id: str | None,
) -> Any:
    if type(manual) is not bool:
        raise ValueError("manual must be a boolean")
    if not manual:
        if logical_request_id is not None:
            raise ValueError("logical_request_id is only valid for a manual request")
        return {
            "namespace": "automatic",
            "logical_request": logical_request,
        }
    request_id = _target_id(logical_request_id) if logical_request_id is not None else None
    if request_id is None:
        raise ValueError("manual requests require logical_request_id")
    return {
        "namespace": "manual",
        "logical_request_id": request_id,
    }


def _job_by_id(db: Session, job_id: int) -> IntegrationJob:
    job = db.scalar(
        select(IntegrationJob)
        .where(IntegrationJob.id == job_id)
        .execution_options(populate_existing=True)
    )
    if job is None:  # pragma: no cover - protected by the just-returned identifier
        raise RuntimeError("Enqueued integration job disappeared")
    return job


def enqueue_job(
    db: Session,
    *,
    job_type: JobType,
    target_id: str | int,
    logical_request: Any,
    payload: Mapping[str, Any],
    available_at: datetime | None = None,
    priority: int = 0,
    max_attempts: int = 6,
    manual: bool = False,
    logical_request_id: str | None = None,
) -> IntegrationJob:
    """Stage one idempotent job without taking ownership of the transaction."""

    if not isinstance(job_type, JobType):
        raise ValueError("job_type must be a JobType")
    if type(priority) is not int or priority < 0:
        raise ValueError("priority must be a non-negative integer")
    if type(max_attempts) is not int or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    selected_payload = _validate_job_payload(job_type, payload)
    selected_logical_request = _manual_request(
        logical_request,
        manual=manual,
        logical_request_id=logical_request_id,
    )
    due_at = _aware_utc(
        available_at if available_at is not None else utc_now(),
        field_name="available_at",
    )
    dedupe_key = make_dedupe_key(
        job_type,
        target_id,
        selected_logical_request,
    )
    now = utc_now()
    insert_statement = postgres_insert(IntegrationJob).values(
        job_type=job_type,
        dedupe_key=dedupe_key,
        payload=selected_payload,
        priority=priority,
        status=JobStatus.QUEUED,
        available_at=due_at,
        attempts=0,
        max_attempts=max_attempts,
        created_at=now,
        updated_at=now,
    )
    statement = (
        insert_statement.on_conflict_do_update(
            constraint="uq_integration_jobs_dedupe_key",
            set_={
                "available_at": func.least(
                    IntegrationJob.available_at,
                    insert_statement.excluded.available_at,
                )
            },
            where=IntegrationJob.status.in_(
                (JobStatus.QUEUED, JobStatus.RETRY_WAIT)
            ),
        ).returning(IntegrationJob.id)
    )
    job_id = db.execute(statement).scalar_one_or_none()
    if job_id is None:
        job_id = db.scalar(
            select(IntegrationJob.id).where(IntegrationJob.dedupe_key == dedupe_key)
        )
    if job_id is None:  # pragma: no cover - unique conflict guarantees the row
        raise RuntimeError("Unable to resolve enqueued integration job")
    return _job_by_id(db, job_id)


def enqueue_refresh_authorization(
    db: Session,
    *,
    authorization_id: int,
    payload: Mapping[str, Any],
    available_at: datetime | None = None,
    logical_request: Mapping[str, Any] | None = None,
    priority: int = 100,
) -> IntegrationJob:
    """Enqueue refresh work keyed by authorization, never by a child connection."""

    if type(authorization_id) is not int or authorization_id <= 0:
        raise ValueError("authorization_id must be a positive integer")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    if payload.get("authorization_id") != authorization_id:
        raise ValueError("payload authorization_id must match the refresh target")
    return enqueue_job(
        db,
        job_type=JobType.REFRESH_AUTHORIZATION,
        target_id=authorization_id,
        logical_request={"namespace": "authorization_refresh"},
        payload=payload,
        available_at=available_at,
        priority=priority,
    )


def _prepare_claimable_jobs(db: Session, *, now: datetime) -> None:
    """Recover expired leases through valid states inside the claim transaction."""

    expired = and_(
        IntegrationJob.lease_expires_at.is_not(None),
        IntegrationJob.lease_expires_at <= now,
    )
    final_attempt = IntegrationJob.attempts >= IntegrationJob.max_attempts
    retryable_attempt = IntegrationJob.attempts < IntegrationJob.max_attempts
    monotonic_update = func.greatest(IntegrationJob.updated_at, now)

    # LEASED cannot transition directly to FAILED. Promote the exhausted lease
    # to RUNNING first, then finalize all exhausted RUNNING rows below.
    db.execute(
        update(IntegrationJob)
        .where(
            IntegrationJob.status == JobStatus.LEASED,
            expired,
            final_attempt,
        )
        .values(status=JobStatus.RUNNING, updated_at=monotonic_update)
    )
    db.execute(
        update(IntegrationJob)
        .where(
            IntegrationJob.status == JobStatus.RUNNING,
            expired,
            final_attempt,
        )
        .values(
            status=JobStatus.FAILED,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            last_error_code=JobErrorCode.MAX_ATTEMPTS_EXHAUSTED.value,
            last_error_summary=JobErrorSummary.FINAL_ATTEMPT_LEASE_EXPIRED.value,
            completed_at=now,
            updated_at=monotonic_update,
        )
    )
    retry_values = {
        "available_at": func.least(IntegrationJob.available_at, now),
        "lease_owner": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "last_error_code": JobErrorCode.LEASE_EXPIRED.value,
        "last_error_summary": JobErrorSummary.LEASE_EXPIRED_RETRY_SCHEDULED.value,
        "completed_at": None,
        "updated_at": monotonic_update,
    }
    db.execute(
        update(IntegrationJob)
        .where(
            IntegrationJob.status == JobStatus.LEASED,
            expired,
            retryable_attempt,
        )
        .values(status=JobStatus.QUEUED, **retry_values)
    )
    db.execute(
        update(IntegrationJob)
        .where(
            IntegrationJob.status == JobStatus.RUNNING,
            expired,
            retryable_attempt,
        )
        .values(status=JobStatus.RETRY_WAIT, **retry_values)
    )
    db.execute(
        update(IntegrationJob)
        .where(
            IntegrationJob.status == JobStatus.RETRY_WAIT,
            IntegrationJob.available_at <= now,
            retryable_attempt,
        )
        .values(
            status=JobStatus.QUEUED,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            updated_at=monotonic_update,
        )
    )


def claim_next_job(
    db: Session,
    *,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
) -> IntegrationJob | None:
    """Lock and lease the highest-priority due row using ``SKIP LOCKED``."""

    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    duration = _positive_duration(lease_duration, field_name="lease_duration")
    _prepare_claimable_jobs(db, now=selected_now)
    due = and_(
        IntegrationJob.status == JobStatus.QUEUED,
        IntegrationJob.available_at <= selected_now,
        IntegrationJob.attempts < IntegrationJob.max_attempts,
    )
    job = db.scalar(
        select(IntegrationJob)
        .where(due)
        .order_by(
            IntegrationJob.priority.desc(),
            IntegrationJob.available_at.asc(),
            IntegrationJob.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if job is None:
        return None
    job.status = JobStatus.LEASED
    job.lease_owner = selected_owner
    job.lease_expires_at = selected_now + duration
    job.heartbeat_at = selected_now
    job.updated_at = selected_now
    db.flush((job,))
    return job


def start_job(
    db: Session,
    *,
    job_id: int,
    owner: str,
    now: datetime,
) -> bool:
    """Start a live owned lease and consume exactly one attempt."""

    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    statement = (
        update(IntegrationJob)
        .where(
            IntegrationJob.id == job_id,
            IntegrationJob.status == JobStatus.LEASED,
            IntegrationJob.lease_owner == selected_owner,
            IntegrationJob.lease_expires_at > selected_now,
            IntegrationJob.attempts < IntegrationJob.max_attempts,
        )
        .values(
            status=JobStatus.RUNNING,
            attempts=IntegrationJob.attempts + 1,
            updated_at=selected_now,
        )
        .returning(IntegrationJob.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def heartbeat_job(
    db: Session,
    *,
    job_id: int,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
) -> bool:
    """Extend only a live job lease held by ``owner``."""

    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    duration = _positive_duration(lease_duration, field_name="lease_duration")
    statement = (
        update(IntegrationJob)
        .where(
            IntegrationJob.id == job_id,
            IntegrationJob.status.in_((JobStatus.LEASED, JobStatus.RUNNING)),
            IntegrationJob.lease_owner == selected_owner,
            IntegrationJob.lease_expires_at > selected_now,
            or_(
                IntegrationJob.heartbeat_at.is_(None),
                IntegrationJob.heartbeat_at <= selected_now,
            ),
            IntegrationJob.updated_at <= selected_now,
        )
        .values(
            heartbeat_at=func.greatest(
                IntegrationJob.heartbeat_at,
                selected_now,
            ),
            lease_expires_at=func.greatest(
                IntegrationJob.lease_expires_at,
                selected_now + duration,
            ),
            updated_at=func.greatest(IntegrationJob.updated_at, selected_now),
        )
        .returning(IntegrationJob.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def _checkpoint_by_id(db: Session, checkpoint_id: int) -> IntegrationSyncCheckpoint:
    checkpoint = db.scalar(
        select(IntegrationSyncCheckpoint)
        .where(IntegrationSyncCheckpoint.id == checkpoint_id)
        .execution_options(populate_existing=True)
    )
    if checkpoint is None:  # pragma: no cover - protected by RETURNING
        raise RuntimeError("Acquired sync checkpoint disappeared")
    return checkpoint


def acquire_checkpoint_lease(
    db: Session,
    *,
    connection_id: int,
    resource_type: ResourceType,
    window_start: datetime,
    window_end: datetime,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
) -> IntegrationSyncCheckpoint | None:
    """Acquire the unique connection/resource/window lease in this transaction."""

    if type(connection_id) is not int or connection_id <= 0:
        raise ValueError("connection_id must be a positive integer")
    if not isinstance(resource_type, ResourceType):
        raise ValueError("resource_type must be a ResourceType")
    selected_start = _aware_utc(window_start, field_name="window_start")
    selected_end = _aware_utc(window_end, field_name="window_end")
    if selected_end <= selected_start:
        raise ValueError("window_end must be after window_start")
    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    duration = _positive_duration(lease_duration, field_name="lease_duration")
    expires_at = selected_now + duration

    # The parent connection is the durable advisory row for this resource
    # namespace. Locking it makes the subsequent cross-window live-lease check
    # race-safe without weakening the existing per-window uniqueness contract.
    locked_connection_id = db.scalar(
        select(IntegrationConnection.id)
        .where(IntegrationConnection.id == connection_id)
        .with_for_update()
    )
    if locked_connection_id is None:
        raise ValueError("connection_id does not reference an integration connection")
    active_checkpoints = db.scalars(
        select(IntegrationSyncCheckpoint)
        .where(
            IntegrationSyncCheckpoint.connection_id == connection_id,
            IntegrationSyncCheckpoint.resource_type == resource_type,
            IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
            IntegrationSyncCheckpoint.lease_expires_at > selected_now,
        )
        .with_for_update()
    ).all()
    if active_checkpoints:
        if len(active_checkpoints) != 1:
            return None
        active = active_checkpoints[0]
        same_window_and_owner = (
            active.window_start == selected_start
            and active.window_end == selected_end
            and active.lease_owner == selected_owner
        )
        if not same_window_and_owner:
            return None

    inserted_id = db.execute(
        postgres_insert(IntegrationSyncCheckpoint)
        .values(
            connection_id=connection_id,
            resource_type=resource_type,
            window_start=selected_start,
            window_end=selected_end,
            status=CheckpointStatus.RUNNING,
            attempts=0,
            lease_owner=selected_owner,
            lease_expires_at=expires_at,
            heartbeat_at=selected_now,
            created_at=selected_now,
            updated_at=selected_now,
        )
        .on_conflict_do_nothing(
            constraint="uq_integration_sync_checkpoints_connection_resource_window"
        )
        .returning(IntegrationSyncCheckpoint.id)
    ).scalar_one_or_none()
    if inserted_id is not None:
        return _checkpoint_by_id(db, inserted_id)

    lease_available = or_(
        IntegrationSyncCheckpoint.lease_expires_at.is_(None),
        IntegrationSyncCheckpoint.lease_expires_at <= selected_now,
    )
    available_pending = and_(
        IntegrationSyncCheckpoint.status == CheckpointStatus.PENDING,
        lease_available,
    )
    available_retry = and_(
        IntegrationSyncCheckpoint.status == CheckpointStatus.RETRY_WAIT,
        IntegrationSyncCheckpoint.next_retry_at.is_not(None),
        IntegrationSyncCheckpoint.next_retry_at <= selected_now,
        lease_available,
    )
    same_owner = and_(
        IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
        IntegrationSyncCheckpoint.lease_owner == selected_owner,
        IntegrationSyncCheckpoint.lease_expires_at > selected_now,
    )
    abandoned = and_(
        IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
        or_(
            IntegrationSyncCheckpoint.lease_expires_at.is_(None),
            IntegrationSyncCheckpoint.lease_expires_at <= selected_now,
        ),
    )
    acquired_id = db.execute(
        update(IntegrationSyncCheckpoint)
        .where(
            IntegrationSyncCheckpoint.connection_id == connection_id,
            IntegrationSyncCheckpoint.resource_type == resource_type,
            IntegrationSyncCheckpoint.window_start == selected_start,
            IntegrationSyncCheckpoint.window_end == selected_end,
            or_(available_pending, available_retry, same_owner, abandoned),
        )
        .values(
            status=CheckpointStatus.RUNNING,
            lease_owner=selected_owner,
            lease_expires_at=func.greatest(
                IntegrationSyncCheckpoint.lease_expires_at,
                expires_at,
            ),
            heartbeat_at=func.greatest(
                IntegrationSyncCheckpoint.heartbeat_at,
                selected_now,
            ),
            next_retry_at=None,
            updated_at=func.greatest(
                IntegrationSyncCheckpoint.updated_at,
                selected_now,
            ),
        )
        .returning(IntegrationSyncCheckpoint.id)
    ).scalar_one_or_none()
    if acquired_id is None:
        return None
    return _checkpoint_by_id(db, acquired_id)


def heartbeat_checkpoint(
    db: Session,
    *,
    checkpoint_id: int,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
) -> bool:
    """Extend only a live checkpoint lease held by ``owner``."""

    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    duration = _positive_duration(lease_duration, field_name="lease_duration")
    statement = (
        update(IntegrationSyncCheckpoint)
        .where(
            IntegrationSyncCheckpoint.id == checkpoint_id,
            IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
            IntegrationSyncCheckpoint.lease_owner == selected_owner,
            IntegrationSyncCheckpoint.lease_expires_at > selected_now,
            or_(
                IntegrationSyncCheckpoint.heartbeat_at.is_(None),
                IntegrationSyncCheckpoint.heartbeat_at <= selected_now,
            ),
            IntegrationSyncCheckpoint.updated_at <= selected_now,
        )
        .values(
            heartbeat_at=func.greatest(
                IntegrationSyncCheckpoint.heartbeat_at,
                selected_now,
            ),
            lease_expires_at=func.greatest(
                IntegrationSyncCheckpoint.lease_expires_at,
                selected_now + duration,
            ),
            updated_at=func.greatest(
                IntegrationSyncCheckpoint.updated_at,
                selected_now,
            ),
        )
        .returning(IntegrationSyncCheckpoint.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def _owned_running_checkpoint(
    db: Session,
    *,
    checkpoint_id: int,
    owner: str,
    now: datetime,
) -> IntegrationSyncCheckpoint | None:
    if type(checkpoint_id) is not int or checkpoint_id <= 0:
        raise ValueError("checkpoint_id must be a positive integer")
    return db.scalar(
        select(IntegrationSyncCheckpoint)
        .where(
            IntegrationSyncCheckpoint.id == checkpoint_id,
            IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
            IntegrationSyncCheckpoint.lease_owner == owner,
            IntegrationSyncCheckpoint.lease_expires_at > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def advance_checkpoint(
    db: Session,
    *,
    checkpoint_id: int,
    owner: str,
    cursor: str | None,
    watermark: datetime | None,
    now: datetime,
) -> bool:
    """Stage a page cursor only while the caller owns the live checkpoint."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    if cursor is not None:
        if type(cursor) is not str:
            raise ValueError("cursor must be a string or None")
        selected_cursor = _assert_cursor_string_safe(
            cursor,
            path="checkpoint.cursor",
            maximum=MAX_PLATFORM_CURSOR_LENGTH,
        )
    else:
        selected_cursor = None
    selected_watermark = (
        _aware_utc(watermark, field_name="watermark")
        if watermark is not None
        else None
    )
    checkpoint = _owned_running_checkpoint(
        db,
        checkpoint_id=checkpoint_id,
        owner=selected_owner,
        now=selected_now,
    )
    if checkpoint is None:
        return False
    checkpoint.cursor = selected_cursor
    if selected_watermark is not None and (
        checkpoint.watermark_at is None
        or selected_watermark > checkpoint.watermark_at
    ):
        checkpoint.watermark_at = selected_watermark
    checkpoint.heartbeat_at = max(
        checkpoint.heartbeat_at or selected_now,
        selected_now,
    )
    checkpoint.updated_at = max(checkpoint.updated_at, selected_now)
    db.flush((checkpoint,))
    return True


def complete_checkpoint(
    db: Session,
    *,
    checkpoint_id: int,
    owner: str,
    now: datetime,
) -> bool:
    """Complete and release one live owned checkpoint."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    checkpoint = _owned_running_checkpoint(
        db,
        checkpoint_id=checkpoint_id,
        owner=selected_owner,
        now=selected_now,
    )
    if checkpoint is None:
        return False
    checkpoint.status = CheckpointStatus.COMPLETE
    checkpoint.next_retry_at = None
    checkpoint.lease_owner = None
    checkpoint.lease_expires_at = None
    checkpoint.heartbeat_at = None
    checkpoint.updated_at = max(checkpoint.updated_at, selected_now)
    db.flush((checkpoint,))
    return True


def fail_checkpoint(
    db: Session,
    *,
    checkpoint_id: int,
    owner: str,
    now: datetime,
) -> bool:
    """Fail and release one live owned checkpoint."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    checkpoint = _owned_running_checkpoint(
        db,
        checkpoint_id=checkpoint_id,
        owner=selected_owner,
        now=selected_now,
    )
    if checkpoint is None:
        return False
    checkpoint.status = CheckpointStatus.FAILED
    checkpoint.next_retry_at = None
    checkpoint.lease_owner = None
    checkpoint.lease_expires_at = None
    checkpoint.heartbeat_at = None
    checkpoint.updated_at = max(checkpoint.updated_at, selected_now)
    db.flush((checkpoint,))
    return True


def _jitter_seconds(value: int | None) -> int:
    if value is None:
        return MIN_RESOURCE_JITTER_SECONDS + secrets.randbelow(
            MAX_RESOURCE_JITTER_SECONDS - MIN_RESOURCE_JITTER_SECONDS + 1
        )
    if type(value) is not int or not (
        MIN_RESOURCE_JITTER_SECONDS <= value <= MAX_RESOURCE_JITTER_SECONDS
    ):
        raise ValueError(
            "jitter_seconds must be an integer between "
            f"{MIN_RESOURCE_JITTER_SECONDS} and {MAX_RESOURCE_JITTER_SECONDS}"
        )
    return value


def acquire_checkpoint_for_job(
    db: Session,
    *,
    job_id: int,
    connection_id: int,
    resource_type: ResourceType,
    window_start: datetime,
    window_end: datetime,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
    jitter_seconds: int | None = None,
) -> IntegrationSyncCheckpoint | None:
    """Start an owned job only after its resource lease is acquired.

    Contention returns the job to ``queued`` with bounded jitter and leaves its
    attempt counter unchanged.
    """

    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    job = db.scalar(
        select(IntegrationJob)
        .where(
            IntegrationJob.id == job_id,
            IntegrationJob.status == JobStatus.LEASED,
            IntegrationJob.lease_owner == selected_owner,
            IntegrationJob.lease_expires_at > selected_now,
            IntegrationJob.attempts < IntegrationJob.max_attempts,
        )
        .with_for_update()
    )
    if job is None:
        return None
    checkpoint = acquire_checkpoint_lease(
        db,
        connection_id=connection_id,
        resource_type=resource_type,
        window_start=window_start,
        window_end=window_end,
        owner=selected_owner,
        now=selected_now,
        lease_duration=lease_duration,
    )
    if checkpoint is None:
        job.status = JobStatus.QUEUED
        job.available_at = selected_now + timedelta(seconds=_jitter_seconds(jitter_seconds))
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.updated_at = selected_now
        db.flush((job,))
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.updated_at = selected_now
    db.flush((job,))
    return checkpoint


def _terminal_job_update(
    db: Session,
    *,
    job_id: int,
    owner: str,
    live_at: datetime,
    values: Mapping[str, Any],
) -> bool:
    statement = (
        update(IntegrationJob)
        .where(
            IntegrationJob.id == job_id,
            IntegrationJob.status == JobStatus.RUNNING,
            IntegrationJob.lease_owner == owner,
            IntegrationJob.lease_expires_at > live_at,
            or_(
                IntegrationJob.heartbeat_at.is_(None),
                IntegrationJob.heartbeat_at <= live_at,
            ),
            IntegrationJob.updated_at <= live_at,
        )
        .values(
            **values,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
        )
        .returning(IntegrationJob.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def complete_job(
    db: Session,
    *,
    job_id: int,
    owner: str,
    now: datetime,
) -> bool:
    """Complete only a running job owned by the caller and clear its lease."""

    selected_owner = _owner(owner)
    selected_now = _aware_utc(now, field_name="now")
    return _terminal_job_update(
        db,
        job_id=job_id,
        owner=selected_owner,
        live_at=selected_now,
        values={
            "status": JobStatus.SUCCEEDED,
            "completed_at": selected_now,
            "last_error_code": None,
            "last_error_summary": None,
            "updated_at": selected_now,
        },
    )


def fail_job(
    db: Session,
    *,
    job_id: int,
    owner: str,
    error_code: JobErrorCode,
    error_summary: JobErrorSummary,
    retryable: bool,
    now: datetime,
    retry_delay: timedelta = timedelta(minutes=1),
) -> bool:
    """Persist only an allowlisted typed failure and release the owned lease."""

    selected_owner = _owner(owner)
    if not isinstance(error_code, JobErrorCode):
        raise ValueError("error_code must be a JobErrorCode")
    if not isinstance(error_summary, JobErrorSummary):
        raise ValueError("error_summary must be a JobErrorSummary")
    if _ERROR_SUMMARY_BY_CODE[error_code] is not error_summary:
        raise ValueError("error code and summary are not an allowlisted pair")
    if type(retryable) is not bool:
        raise ValueError("retryable must be a boolean")
    selected_now = _aware_utc(now, field_name="now")
    selected_delay = _positive_duration(retry_delay, field_name="retry_delay")
    job = db.scalar(
        select(IntegrationJob)
        .where(
            IntegrationJob.id == job_id,
            IntegrationJob.status == JobStatus.RUNNING,
            IntegrationJob.lease_owner == selected_owner,
            IntegrationJob.lease_expires_at > selected_now,
            or_(
                IntegrationJob.heartbeat_at.is_(None),
                IntegrationJob.heartbeat_at <= selected_now,
            ),
            IntegrationJob.updated_at <= selected_now,
        )
        .with_for_update()
    )
    if job is None:
        return False
    should_retry = retryable and job.attempts < job.max_attempts
    job.status = JobStatus.RETRY_WAIT if should_retry else JobStatus.FAILED
    job.available_at = selected_now + selected_delay
    job.last_error_code = error_code.value
    job.last_error_summary = error_summary.value
    job.completed_at = None if should_retry else selected_now
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    job.updated_at = selected_now
    db.flush((job,))
    return True


__all__ = [
    "JobErrorCode",
    "JobErrorSummary",
    "acquire_checkpoint_for_job",
    "acquire_checkpoint_lease",
    "advance_checkpoint",
    "canonical_logical_request",
    "claim_next_job",
    "complete_checkpoint",
    "complete_job",
    "enqueue_job",
    "enqueue_refresh_authorization",
    "fail_job",
    "fail_checkpoint",
    "heartbeat_checkpoint",
    "heartbeat_job",
    "make_dedupe_key",
    "start_job",
]
