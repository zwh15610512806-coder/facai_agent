"""Pure recurring-window calculation and idempotent scheduler enqueueing.

The scheduler deliberately knows nothing about provider endpoints.  It consumes
an already verified capability catalog, calculates UTC-exclusive work windows
from Asia/Shanghai business boundaries, and stages PostgreSQL queue rows in the
caller's transaction.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from types import MappingProxyType
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from integration_models import IntegrationJob, IntegrationSyncCheckpoint
from integrations.sync.queue import (
    enqueue_job,
    enqueue_refresh_authorization,
    make_dedupe_key,
)
from integrations.types import (
    CheckpointStatus,
    ConnectionStatus,
    JobStatus,
    JobType,
    ResourceType,
    TimeWindow,
    utc_now,
)


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")

_INTERVAL_RESOURCES = frozenset(
    {ResourceType.ORDERS, ResourceType.REFUNDS, ResourceType.SHIPMENTS}
)
_HOURLY_SNAPSHOTS = frozenset(
    {
        ResourceType.PRODUCTS,
        ResourceType.SKUS,
        ResourceType.INVENTORY,
        ResourceType.AD_ENTITIES,
        ResourceType.AD_BALANCE_SNAPSHOTS,
    }
)
_DAILY_SNAPSHOTS = frozenset({ResourceType.SHOPS, ResourceType.AD_ACCOUNTS})
_DAILY_METRICS = frozenset(
    {ResourceType.DAILY_METRICS, ResourceType.AD_DAILY_METRICS}
)
_DAILY_FINANCE = frozenset(
    {
        ResourceType.SETTLEMENTS,
        ResourceType.AD_FINANCE_TRANSACTIONS,
    }
)
_BACKFILL_RESOURCES = _INTERVAL_RESOURCES | _DAILY_METRICS | _DAILY_FINANCE
_SCHEDULABLE_STATUSES = frozenset(
    {ConnectionStatus.ACTIVE, ConnectionStatus.PERMISSION_LIMITED}
)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError):
        offset = None
    if offset is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _positive_id(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class CapabilityAssignment:
    """One exhaustive fetch-mode classification for a normalized resource."""

    resource: ResourceType
    mode: str
    verified: bool
    earliest_available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.resource, ResourceType):
            raise ValueError("resource must be a ResourceType")
        if type(self.verified) is not bool:
            raise ValueError("verified must be a boolean")
        if not isinstance(self.mode, str) or not self.mode:
            raise ValueError("mode must classify the resource")
        if self.mode not in {"direct", "unavailable"} and not self.mode.startswith(
            "emitted_by:"
        ):
            raise ValueError("mode must be direct, unavailable or emitted_by:<resource>")
        if self.earliest_available_at is not None:
            object.__setattr__(
                self,
                "earliest_available_at",
                _aware_utc(
                    self.earliest_available_at,
                    field_name="earliest_available_at",
                ),
            )


class CapabilityCatalog:
    """Validated exhaustive resource classification for one connection."""

    __slots__ = ("assignments", "direct_resources", "emitted_resources", "unavailable_resources")

    def __init__(self, assignments: tuple[CapabilityAssignment, ...]) -> None:
        if not isinstance(assignments, tuple):
            raise ValueError("assignments must be a tuple")
        selected: dict[ResourceType, CapabilityAssignment] = {}
        for assignment in assignments:
            if not isinstance(assignment, CapabilityAssignment):
                raise ValueError("assignments must contain CapabilityAssignment values")
            if assignment.resource in selected:
                raise ValueError("each resource must be classified exactly once")
            selected[assignment.resource] = assignment
        if set(selected) != set(ResourceType):
            raise ValueError("every ResourceType must be classified exactly once")

        parents: dict[ResourceType, ResourceType] = {}
        for resource, assignment in selected.items():
            if not assignment.mode.startswith("emitted_by:"):
                continue
            parent_value = assignment.mode.partition(":")[2]
            try:
                parent = ResourceType(parent_value)
            except ValueError as exc:
                raise ValueError("emitted_by parent must be a ResourceType") from exc
            if parent is resource:
                raise ValueError("a resource cannot emit itself")
            parents[resource] = parent

        # Follow every parent chain.  A repeated node means the graph is cyclic.
        for resource in parents:
            visited: set[ResourceType] = set()
            current = resource
            while current in parents:
                if current in visited:
                    raise ValueError("emitted_by classifications must be acyclic")
                visited.add(current)
                current = parents[current]

        order_items = selected[ResourceType.ORDER_ITEMS]
        if order_items.mode != "emitted_by:orders":
            raise ValueError("order_items must be emitted atomically by orders")

        self.assignments = MappingProxyType(selected)
        self.direct_resources = frozenset(
            resource
            for resource, assignment in selected.items()
            if assignment.mode == "direct"
        )
        self.emitted_resources = frozenset(parents)
        self.unavailable_resources = frozenset(
            resource
            for resource, assignment in selected.items()
            if assignment.mode == "unavailable"
        )

    def assignment(self, resource: ResourceType) -> CapabilityAssignment:
        if not isinstance(resource, ResourceType):
            raise ValueError("resource must be a ResourceType")
        return self.assignments[resource]


@dataclass(frozen=True, slots=True)
class ScheduledConnection:
    connection_id: int
    authorization_id: int
    status: ConnectionStatus
    backfill_from: datetime | None = None
    authorization_refresh_due: bool = False

    def __post_init__(self) -> None:
        _positive_id(self.connection_id, field_name="connection_id")
        _positive_id(self.authorization_id, field_name="authorization_id")
        if not isinstance(self.status, ConnectionStatus):
            raise ValueError("status must be a ConnectionStatus")
        if self.backfill_from is not None:
            object.__setattr__(
                self,
                "backfill_from",
                _aware_utc(self.backfill_from, field_name="backfill_from"),
            )
        if type(self.authorization_refresh_due) is not bool:
            raise ValueError("authorization_refresh_due must be a boolean")


@dataclass(frozen=True, slots=True)
class ScheduledUnit:
    job_type: JobType
    authorization_id: int | None = None
    connection_id: int | None = None
    resource_type: ResourceType | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    api_window: TimeWindow | None = None
    captured_at: datetime | None = None
    schedule_slot: datetime | None = None
    archive_manifest_id: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduleEnqueueResult:
    sync_units: int = 0
    refresh_units: int = 0
    archive_cleanup_units: int = 0


def _local_schedule_at(now: datetime, scheduled_time: time) -> datetime:
    local_now = now.astimezone(SHANGHAI)
    candidate = datetime.combine(local_now.date(), scheduled_time, tzinfo=SHANGHAI)
    if candidate > local_now:
        candidate -= timedelta(days=1)
    return candidate.astimezone(UTC)


def _local_day_windows(scheduled_at: datetime, *, days: int = 7) -> list[tuple[datetime, datetime]]:
    local_date = scheduled_at.astimezone(SHANGHAI).date()
    windows: list[tuple[datetime, datetime]] = []
    for days_ago in range(days, 0, -1):
        start_local = datetime.combine(
            local_date - timedelta(days=days_ago),
            time.min,
            tzinfo=SHANGHAI,
        )
        end_local = start_local + timedelta(days=1)
        windows.append((start_local.astimezone(UTC), end_local.astimezone(UTC)))
    return windows


def _split_backfill_by_local_day(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    if start >= end:
        return []
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        local_cursor = cursor.astimezone(SHANGHAI)
        next_midnight_local = datetime.combine(
            local_cursor.date() + timedelta(days=1),
            time.min,
            tzinfo=SHANGHAI,
        )
        boundary = min(end, next_midnight_local.astimezone(UTC))
        windows.append((cursor, boundary))
        cursor = boundary
    return windows


def _sync_unit(
    connection: ScheduledConnection,
    resource: ResourceType,
    start: datetime,
    end: datetime,
    *,
    api_window: bool,
    captured_at: datetime | None = None,
    schedule_slot: datetime,
) -> ScheduledUnit:
    selected_start = _aware_utc(start, field_name="window_start")
    selected_end = _aware_utc(end, field_name="window_end")
    if selected_end <= selected_start:
        raise ValueError("window_end must be after window_start")
    return ScheduledUnit(
        job_type=JobType.SYNC_RESOURCE,
        authorization_id=connection.authorization_id,
        connection_id=connection.connection_id,
        resource_type=resource,
        window_start=selected_start,
        window_end=selected_end,
        api_window=TimeWindow(selected_start, selected_end) if api_window else None,
        captured_at=captured_at,
        schedule_slot=_aware_utc(schedule_slot, field_name="schedule_slot"),
    )


def _recurring_units(
    now: datetime,
    connection: ScheduledConnection,
    resource: ResourceType,
) -> list[ScheduledUnit]:
    if resource in _INTERVAL_RESOURCES:
        minute = (now.minute // 15) * 15
        end = now.replace(minute=minute, second=0, microsecond=0)
        return [
            _sync_unit(
                connection,
                resource,
                start,
                boundary,
                api_window=True,
                schedule_slot=end,
            )
            for start, boundary in _split_backfill_by_local_day(
                end - timedelta(minutes=30),
                end,
            )
        ]
    if resource in _HOURLY_SNAPSHOTS:
        slot = now.replace(minute=0, second=0, microsecond=0)
        return [
            _sync_unit(
                connection,
                resource,
                slot,
                slot + timedelta(hours=1),
                api_window=False,
                captured_at=slot,
                schedule_slot=slot,
            )
        ]
    if resource in _DAILY_SNAPSHOTS:
        slot = _local_schedule_at(now, time(5, 30))
        return [
            _sync_unit(
                connection,
                resource,
                slot,
                slot + timedelta(days=1),
                api_window=False,
                captured_at=slot,
                schedule_slot=slot,
            )
        ]
    if resource in _DAILY_METRICS:
        slot = _local_schedule_at(now, time(6, 0))
        return [
            _sync_unit(
                connection,
                resource,
                start,
                end,
                api_window=True,
                schedule_slot=slot,
            )
            for start, end in _local_day_windows(slot)
        ]
    if resource in _DAILY_FINANCE:
        slot = _local_schedule_at(now, time(6, 30))
        return [
            _sync_unit(
                connection,
                resource,
                start,
                end,
                api_window=True,
                schedule_slot=slot,
            )
            for start, end in _local_day_windows(slot)
        ]
    raise ValueError(f"resource has no cadence: {resource.value}")


def _respect_earliest_available(
    units: list[ScheduledUnit],
    earliest_available_at: datetime | None,
) -> list[ScheduledUnit]:
    """Drop or clip only API time windows at the verified history boundary."""

    if earliest_available_at is None:
        return units
    boundary = _aware_utc(
        earliest_available_at,
        field_name="earliest_available_at",
    )
    selected: list[ScheduledUnit] = []
    for unit in units:
        if unit.api_window is None:
            selected.append(unit)
            continue
        end = _aware_utc(unit.api_window.end_at, field_name="api_window.end_at")
        start = max(
            _aware_utc(unit.api_window.start_at, field_name="api_window.start_at"),
            boundary,
        )
        if end <= start:
            continue
        selected.append(
            replace(
                unit,
                window_start=start,
                api_window=TimeWindow(start, end),
            )
        )
    return selected


def due_jobs(
    now: datetime,
    connections: list[ScheduledConnection] | tuple[ScheduledConnection, ...],
    capabilities: Mapping[int, CapabilityCatalog],
    *,
    expired_archive_manifest_ids: Collection[int] = (),
) -> list[ScheduledUnit]:
    """Calculate the latest idempotent units due at ``now`` without DB access."""

    selected_now = _aware_utc(now, field_name="now")
    if not isinstance(capabilities, Mapping):
        raise ValueError("capabilities must be a mapping")
    units: list[ScheduledUnit] = []
    refresh_authorizations: set[int] = set()

    for connection in connections:
        if not isinstance(connection, ScheduledConnection):
            raise ValueError("connections must contain ScheduledConnection values")
        if connection.authorization_refresh_due and connection.status is not ConnectionStatus.DISABLED:
            refresh_authorizations.add(connection.authorization_id)
        if connection.status not in _SCHEDULABLE_STATUSES:
            continue
        catalog = capabilities.get(connection.connection_id)
        if not isinstance(catalog, CapabilityCatalog):
            raise ValueError("every schedulable connection requires a capability catalog")

        for resource in sorted(catalog.direct_resources, key=lambda item: item.value):
            assignment = catalog.assignment(resource)
            if not assignment.verified:
                continue
            resource_units = _respect_earliest_available(
                _recurring_units(selected_now, connection, resource),
                assignment.earliest_available_at,
            )
            if connection.backfill_from is not None and resource in _BACKFILL_RESOURCES:
                backfill_start = connection.backfill_from
                if assignment.earliest_available_at is not None:
                    backfill_start = max(backfill_start, assignment.earliest_available_at)
                resource_units.extend(
                    _sync_unit(
                        connection,
                        resource,
                        start,
                        end,
                        api_window=True,
                        schedule_slot=connection.backfill_from,
                    )
                    for start, end in _split_backfill_by_local_day(
                        backfill_start,
                        selected_now,
                    )
                )

            unique: dict[tuple[datetime, datetime], ScheduledUnit] = {}
            for unit in resource_units:
                assert unit.window_start is not None and unit.window_end is not None
                unique[(unit.window_start, unit.window_end)] = unit
            units.extend(
                unique[key]
                for key in sorted(unique, key=lambda pair: (pair[0], pair[1]))
            )

    units.extend(
        ScheduledUnit(
            job_type=JobType.REFRESH_AUTHORIZATION,
            authorization_id=authorization_id,
        )
        for authorization_id in sorted(refresh_authorizations)
    )
    if isinstance(expired_archive_manifest_ids, (str, bytes, bytearray)):
        raise ValueError("expired archive manifest ids must be a collection")
    manifest_ids = {
        _positive_id(value, field_name="archive_manifest_id")
        for value in expired_archive_manifest_ids
    }
    units.extend(
        ScheduledUnit(
            job_type=JobType.ARCHIVE_CLEANUP,
            archive_manifest_id=manifest_id,
            schedule_slot=_local_schedule_at(selected_now, time(3, 0)),
        )
        for manifest_id in sorted(manifest_ids)
    )
    return units


def _iso_utc(value: datetime) -> str:
    return _aware_utc(value, field_name="timestamp").isoformat().replace("+00:00", "Z")


def _checkpoint(db: Session, unit: ScheduledUnit) -> IntegrationSyncCheckpoint:
    assert unit.connection_id is not None
    assert unit.resource_type is not None
    assert unit.window_start is not None
    assert unit.window_end is not None
    now = utc_now()
    checkpoint_id = db.execute(
        postgres_insert(IntegrationSyncCheckpoint)
        .values(
            connection_id=unit.connection_id,
            resource_type=unit.resource_type,
            window_start=unit.window_start,
            window_end=unit.window_end,
            status=CheckpointStatus.PENDING,
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            constraint="uq_integration_sync_checkpoints_connection_resource_window"
        )
        .returning(IntegrationSyncCheckpoint.id)
    ).scalar_one_or_none()
    statement = select(IntegrationSyncCheckpoint)
    if checkpoint_id is not None:
        statement = statement.where(IntegrationSyncCheckpoint.id == checkpoint_id)
    else:
        statement = statement.where(
            IntegrationSyncCheckpoint.connection_id == unit.connection_id,
            IntegrationSyncCheckpoint.resource_type == unit.resource_type,
            IntegrationSyncCheckpoint.window_start == unit.window_start,
            IntegrationSyncCheckpoint.window_end == unit.window_end,
        )
    checkpoint = db.scalar(statement.with_for_update())
    if checkpoint is None:  # pragma: no cover - conflict guarantees a row
        raise RuntimeError("unable to resolve scheduled sync checkpoint")
    return checkpoint


def _sync_logical_request(
    unit: ScheduledUnit,
    *,
    checkpoint_id: int,
) -> dict[str, object]:
    if unit.schedule_slot is None:
        raise ValueError("sync units require a schedule slot")
    assert unit.resource_type is not None
    assert unit.window_start is not None
    assert unit.window_end is not None
    return {
        "checkpoint_id": checkpoint_id,
        "resource_type": unit.resource_type.value,
        "schedule_slot": _iso_utc(unit.schedule_slot),
        "window_start": _iso_utc(unit.window_start),
        "window_end": _iso_utc(unit.window_end),
    }


def _job_dedupe_key(
    unit: ScheduledUnit,
    *,
    logical_request: Mapping[str, object],
    manual_logical_request_id: str | None = None,
) -> str:
    assert unit.connection_id is not None
    dedupe_request: Mapping[str, object]
    if manual_logical_request_id is None:
        dedupe_request = {
            "namespace": "automatic",
            "logical_request": logical_request,
        }
    else:
        dedupe_request = {
            "namespace": "manual",
            "logical_request_id": manual_logical_request_id,
        }
    return make_dedupe_key(
        JobType.SYNC_RESOURCE,
        unit.connection_id,
        dedupe_request,
    )


def _prepare_checkpoint_cycle(
    db: Session,
    *,
    unit: ScheduledUnit,
    checkpoint: IntegrationSyncCheckpoint,
    logical_request: Mapping[str, object],
    manual_logical_request_id: str | None = None,
) -> bool:
    """Return false while an older cycle still owns the reusable checkpoint."""

    current_key = _job_dedupe_key(
        unit,
        logical_request=logical_request,
        manual_logical_request_id=manual_logical_request_id,
    )
    if db.scalar(
        select(IntegrationJob.id).where(IntegrationJob.dedupe_key == current_key)
    ) is not None:
        return True

    active_statuses = (
        JobStatus.QUEUED,
        JobStatus.LEASED,
        JobStatus.RUNNING,
        JobStatus.RETRY_WAIT,
    )
    active_job_id = db.scalar(
        select(IntegrationJob.id)
        .where(
            IntegrationJob.status.in_(active_statuses),
            IntegrationJob.payload["checkpoint_id"].as_integer() == checkpoint.id,
        )
        .limit(1)
    )
    if active_job_id is not None or checkpoint.status is CheckpointStatus.RUNNING:
        return False

    if checkpoint.status is not CheckpointStatus.PENDING:
        checkpoint.status = CheckpointStatus.PENDING
        checkpoint.cursor = None
        checkpoint.watermark_at = None
        checkpoint.attempts = 0
        checkpoint.next_retry_at = None
        checkpoint.lease_owner = None
        checkpoint.lease_expires_at = None
        checkpoint.heartbeat_at = None
        checkpoint.updated_at = utc_now()
        db.flush((checkpoint,))
    return True


def enqueue_scheduled_units(
    db: Session,
    units: list[ScheduledUnit] | tuple[ScheduledUnit, ...],
    *,
    manual_request_id: str | None = None,
) -> ScheduleEnqueueResult:
    """Stage calculated units; the caller owns commit and rollback."""

    sync_count = 0
    refresh_count = 0
    archive_cleanup_count = 0
    if manual_request_id is not None and (
        not isinstance(manual_request_id, str)
        or not manual_request_id
        or manual_request_id != manual_request_id.strip()
        or len(manual_request_id) > 64
    ):
        raise ValueError("manual_request_id must be a bounded identifier")
    for unit in units:
        if not isinstance(unit, ScheduledUnit):
            raise ValueError("units must contain ScheduledUnit values")
        if unit.job_type is JobType.SYNC_RESOURCE:
            if (
                unit.connection_id is None
                or unit.resource_type is None
                or unit.window_start is None
                or unit.window_end is None
            ):
                raise ValueError("sync units require connection, resource and window")
            checkpoint = _checkpoint(db, unit)
            logical_request = _sync_logical_request(
                unit,
                checkpoint_id=checkpoint.id,
            )
            unit_manual_id = (
                f"{manual_request_id}:{unit.resource_type.value}:"
                f"{_iso_utc(unit.window_start)}:{_iso_utc(unit.window_end)}"
                if manual_request_id is not None
                else None
            )
            if not _prepare_checkpoint_cycle(
                db,
                unit=unit,
                checkpoint=checkpoint,
                logical_request=logical_request,
                manual_logical_request_id=unit_manual_id,
            ):
                sync_count += 1
                continue
            payload = {
                "connection_id": unit.connection_id,
                "resource_type": unit.resource_type.value,
                "window_start": _iso_utc(unit.window_start),
                "window_end": _iso_utc(unit.window_end),
                "checkpoint_id": checkpoint.id,
            }
            enqueue_job(
                db,
                job_type=JobType.SYNC_RESOURCE,
                target_id=unit.connection_id,
                logical_request=logical_request,
                payload=payload,
                manual=unit_manual_id is not None,
                logical_request_id=unit_manual_id,
            )
            sync_count += 1
        elif unit.job_type is JobType.REFRESH_AUTHORIZATION:
            if manual_request_id is not None:
                raise ValueError("manual requests may contain only sync units")
            if unit.authorization_id is None:
                raise ValueError("refresh units require an authorization")
            enqueue_refresh_authorization(
                db,
                authorization_id=unit.authorization_id,
                payload={"authorization_id": unit.authorization_id},
            )
            refresh_count += 1
        elif unit.job_type is JobType.ARCHIVE_CLEANUP:
            if manual_request_id is not None:
                raise ValueError("manual requests may contain only sync units")
            if unit.archive_manifest_id is None or unit.schedule_slot is None:
                raise ValueError("archive cleanup units require a manifest and slot")
            enqueue_job(
                db,
                job_type=JobType.ARCHIVE_CLEANUP,
                target_id=unit.archive_manifest_id,
                logical_request={
                    "archive_manifest_id": unit.archive_manifest_id,
                    "schedule_slot": _iso_utc(unit.schedule_slot),
                },
                payload={"archive_manifest_id": unit.archive_manifest_id},
                priority=10,
            )
            archive_cleanup_count += 1
        else:
            raise ValueError("scheduler unit uses an unsupported job type")
    return ScheduleEnqueueResult(
        sync_units=sync_count,
        refresh_units=refresh_count,
        archive_cleanup_units=archive_cleanup_count,
    )


__all__ = [
    "CapabilityAssignment",
    "CapabilityCatalog",
    "ScheduleEnqueueResult",
    "ScheduledConnection",
    "ScheduledUnit",
    "due_jobs",
    "enqueue_scheduled_units",
]
