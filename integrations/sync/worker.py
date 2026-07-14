"""Independent PostgreSQL worker runtime for ecommerce integration jobs.

The module owns process lifecycle, queue leases and maintenance cadence.  It
does not contain provider behavior: until a verified connector runner is wired,
the default handler records a closed ``connector_unavailable`` outcome instead
of inventing platform data.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import re
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from database import assert_schema_current
from integration_models import (
    IntegrationArchiveManifest,
    IntegrationExportJob,
    IntegrationJob,
    IntegrationSecurityAudit,
    IntegrationSyncCheckpoint,
    IntegrationWorkerHeartbeat,
)
from integrations.crypto import derive_archive_page_key
from integrations.settings import IntegrationSettings
from integrations.sync.archive import (
    cleanup_expired_archives,
    scan_orphan_archives,
)
from integrations.sync.queue import (
    JobErrorCode,
    JobErrorSummary,
    acquire_checkpoint_for_job,
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_checkpoint,
    heartbeat_job,
    start_job,
)
from integrations.types import (
    CheckpointStatus,
    ExportStatus,
    JobStatus,
    JobType,
    ResourceType,
    utc_now,
)


UTC = timezone.utc
WORKER_ENABLED_ENV = "FACAI_INTEGRATION_WORKER_ENABLED"
DEFAULT_WORKER_CONCURRENCY = 4
WORKER_VERSION = "ecommerce-integration-worker-v1"
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")


class WorkerReadinessError(RuntimeError):
    """Stable startup failure that never includes configuration values."""


class ConnectorUnavailableError(RuntimeError):
    """Typed signal used while no verified provider connector is configured."""


class RetryableMaintenanceError(RuntimeError):
    """Closed signal for archive I/O that should retry without raw details."""


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    enabled: bool
    concurrency: int = DEFAULT_WORKER_CONCURRENCY
    heartbeat_interval: float = 10.0
    lease_duration: timedelta = timedelta(seconds=45)
    poll_interval: float = 1.0
    maintenance_interval: float = 60.0
    shutdown_timeout: float = 30.0
    stale_after: timedelta = timedelta(seconds=30)

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        if type(self.concurrency) is not int or not 1 <= self.concurrency <= 64:
            raise ValueError("concurrency must be an integer from 1 through 64")
        for field_name in (
            "heartbeat_interval",
            "poll_interval",
            "maintenance_interval",
            "shutdown_timeout",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field_name} must be a positive number")
            selected = float(value)
            if not math.isfinite(selected) or selected <= 0:
                raise ValueError(f"{field_name} must be a positive number")
            object.__setattr__(self, field_name, selected)
        for field_name in ("lease_duration", "stale_after"):
            value = getattr(self, field_name)
            if not isinstance(value, timedelta) or value <= timedelta(0):
                raise ValueError(f"{field_name} must be a positive duration")
        if self.lease_duration.total_seconds() <= self.heartbeat_interval:
            raise ValueError("lease_duration must exceed heartbeat_interval")


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: int
    job_type: JobType
    payload: Mapping[str, Any]
    attempts: int = 0
    max_attempts: int = 6


@dataclass(frozen=True, slots=True)
class ReleasedLeaseCount:
    jobs: int = 0
    checkpoints: int = 0


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    enabled: bool
    claimed_jobs: int = 0
    succeeded_jobs: int = 0
    failed_jobs: int = 0
    maintenance_errors: int = 0


JobHandler = Callable[[ClaimedJob], Awaitable[None]]
MaintenanceHook = Callable[[], Awaitable[None]]


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _worker_id(value: str) -> str:
    if not isinstance(value, str) or _WORKER_ID_RE.fullmatch(value) is None:
        raise ValueError("worker_id must be a bounded safe identifier")
    return value


def parse_worker_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Fail closed: the worker runs only for the exact value ``1``."""

    values = os.environ if environ is None else environ
    raw = values.get(WORKER_ENABLED_ENV)
    if raw is None:
        return False
    if raw == "0":
        return False
    if raw == "1":
        return True
    raise ValueError(f"{WORKER_ENABLED_ENV} must be exactly 0 or 1")


def validate_worker_readiness(
    engine: Engine,
    settings: IntegrationSettings,
    *,
    schema_validator: Callable[[Engine], None] = assert_schema_current,
) -> None:
    """Validate storage, migrations, key derivation and archive writability."""

    if engine.dialect.name != "postgresql":
        raise WorkerReadinessError("Integration worker requires PostgreSQL")
    if (
        not isinstance(settings, IntegrationSettings)
        or not settings.credential_ready
    ):
        raise WorkerReadinessError("Integration worker security configuration is incomplete")
    if settings.master_key is None or settings.archive_dir is None:
        raise WorkerReadinessError("Integration worker security configuration is incomplete")
    try:
        schema_validator(engine)
    except Exception as exc:
        raise WorkerReadinessError("Integration worker Alembic schema is not current") from exc
    try:
        derive_archive_page_key(settings.master_key)
        archive_dir = Path(settings.archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        if not archive_dir.is_dir():
            raise OSError
        descriptor, probe_name = tempfile.mkstemp(
            prefix=".worker-readiness-",
            suffix=".tmp",
            dir=archive_dir,
        )
        os.close(descriptor)
        Path(probe_name).unlink()
    except Exception as exc:
        raise WorkerReadinessError("Integration worker archive storage is not writable") from exc


def upsert_worker_heartbeat(
    db: Session,
    *,
    worker_id: str,
    pid: int,
    active_job_count: int,
    now: datetime,
    version: str = WORKER_VERSION,
) -> int:
    selected_worker_id = _worker_id(worker_id)
    if type(pid) is not int or pid <= 0:
        raise ValueError("pid must be a positive integer")
    if type(active_job_count) is not int or active_job_count < 0:
        raise ValueError("active_job_count must be a non-negative integer")
    if not isinstance(version, str) or not version or len(version) > 100:
        raise ValueError("version must be a bounded non-empty string")
    selected_now = _aware_utc(now, field_name="now")
    inserted = postgres_insert(IntegrationWorkerHeartbeat).values(
        worker_id=selected_worker_id,
        pid=pid,
        started_at=selected_now,
        last_seen_at=selected_now,
        active_job_count=active_job_count,
        version=version,
    )
    heartbeat_id = db.execute(
        inserted.on_conflict_do_update(
            constraint="uq_integration_worker_heartbeats_worker_id",
            set_={
                "pid": inserted.excluded.pid,
                "last_seen_at": inserted.excluded.last_seen_at,
                "active_job_count": inserted.excluded.active_job_count,
                "version": inserted.excluded.version,
            },
            where=(
                IntegrationWorkerHeartbeat.last_seen_at
                <= inserted.excluded.last_seen_at
            ),
        ).returning(IntegrationWorkerHeartbeat.id)
    ).scalar_one_or_none()
    if heartbeat_id is None:
        heartbeat_id = db.scalar(
            select(IntegrationWorkerHeartbeat.id).where(
                IntegrationWorkerHeartbeat.worker_id == selected_worker_id
            )
        )
    if heartbeat_id is None:  # pragma: no cover - unique conflict guarantees a row
        raise RuntimeError("Unable to resolve integration worker heartbeat")
    return heartbeat_id


def stale_worker_ids(
    db: Session,
    *,
    now: datetime,
    stale_after: timedelta = timedelta(seconds=30),
) -> tuple[str, ...]:
    selected_now = _aware_utc(now, field_name="now")
    if not isinstance(stale_after, timedelta) or stale_after <= timedelta(0):
        raise ValueError("stale_after must be a positive duration")
    return tuple(
        db.scalars(
            select(IntegrationWorkerHeartbeat.worker_id)
            .where(
                IntegrationWorkerHeartbeat.last_seen_at
                < selected_now - stale_after
            )
            .order_by(IntegrationWorkerHeartbeat.worker_id)
        ).all()
    )


def release_worker_leases(
    db: Session,
    *,
    owner: str,
    now: datetime,
) -> ReleasedLeaseCount:
    """Return only this worker's live work to retryable states."""

    selected_owner = _worker_id(owner)
    selected_now = _aware_utc(now, field_name="now")
    jobs = db.scalars(
        select(IntegrationJob)
        .where(
            IntegrationJob.lease_owner == selected_owner,
            IntegrationJob.status.in_((JobStatus.LEASED, JobStatus.RUNNING)),
        )
        .with_for_update()
    ).all()
    for job in jobs:
        if job.status is JobStatus.LEASED:
            job.status = JobStatus.QUEUED
        elif job.attempts < job.max_attempts:
            job.status = JobStatus.RETRY_WAIT
            job.last_error_code = JobErrorCode.LEASE_EXPIRED.value
            job.last_error_summary = JobErrorSummary.LEASE_EXPIRED_RETRY_SCHEDULED.value
        else:
            job.status = JobStatus.FAILED
            job.completed_at = selected_now
            job.last_error_code = JobErrorCode.MAX_ATTEMPTS_EXHAUSTED.value
            job.last_error_summary = JobErrorSummary.FINAL_ATTEMPT_LEASE_EXPIRED.value
        job.available_at = selected_now
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.updated_at = selected_now

    checkpoints = db.scalars(
        select(IntegrationSyncCheckpoint)
        .where(
            IntegrationSyncCheckpoint.lease_owner == selected_owner,
            IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
        )
        .with_for_update()
    ).all()
    for checkpoint in checkpoints:
        checkpoint.status = CheckpointStatus.RETRY_WAIT
        checkpoint.next_retry_at = selected_now
        checkpoint.lease_owner = None
        checkpoint.lease_expires_at = None
        checkpoint.heartbeat_at = None
        checkpoint.updated_at = selected_now
    db.flush((*jobs, *checkpoints))
    return ReleasedLeaseCount(jobs=len(jobs), checkpoints=len(checkpoints))


async def default_job_handler(_job: ClaimedJob) -> None:
    """Honest default while the four provider adapters remain unverified."""

    raise ConnectorUnavailableError("connector is not configured")


def build_default_job_handler(
    session_factory: sessionmaker,
    *,
    archive_dir: Path,
) -> JobHandler:
    """Handle internal archive retention and reject unconfigured providers."""

    if not callable(session_factory):
        raise TypeError("session_factory must be callable")
    selected_archive_dir = Path(archive_dir).resolve(strict=False)
    cleanup_lock = asyncio.Lock()

    def cleanup_archives() -> bool:
        retry_codes: list[str] = []
        with session_factory.begin() as db:
            def audit_missing(manifest_id, code) -> None:
                db.add(
                    IntegrationSecurityAudit(
                        event_type="archive_retention",
                        outcome="missing",
                        target_type="archive_manifest",
                        target_id=str(manifest_id),
                        summary_code=code.value,
                        details={},
                    )
                )

            def enqueue_retry(_manifest_id, code) -> None:
                retry_codes.append(code.value)

            result = cleanup_expired_archives(
                db,
                archive_dir=selected_archive_dir,
                now=utc_now(),
                audit_missing=audit_missing,
                enqueue_retry=enqueue_retry,
            )
        return bool(result.retry_count or retry_codes)

    def generate_export(
        export_job_id: int,
        terminal_failure: bool,
    ) -> ExportStatus:
        from integrations.exports import (
            ExportPublicationTracker,
            generate_export_job,
            resolve_export_path,
        )

        publication = ExportPublicationTracker()
        try:
            with session_factory.begin() as db:
                export_job = generate_export_job(
                    db,
                    export_job_id=export_job_id,
                    archive_dir=selected_archive_dir,
                    now=utc_now(),
                    terminal_failure=terminal_failure,
                    publication=publication,
                )
                status = export_job.status
        except Exception:
            if publication.relative_path is not None:
                delete_uncommitted = False
                try:
                    with session_factory() as verification_db:
                        persisted = verification_db.scalar(
                            select(IntegrationExportJob).where(
                                IntegrationExportJob.id == export_job_id
                            )
                        )
                    delete_uncommitted = not (
                        persisted is not None
                        and persisted.status is ExportStatus.READY
                        and persisted.relative_file_path
                        == publication.relative_path
                    )
                except Exception:
                    # An ambiguous commit must never destroy a possibly READY file.
                    delete_uncommitted = False
                if delete_uncommitted:
                    try:
                        resolve_export_path(
                            archive_dir=selected_archive_dir,
                            relative_path=publication.relative_path,
                        ).unlink(missing_ok=True)
                    except (OSError, ValueError):
                        pass
            raise
        return status

    def mark_export_terminal_failure(export_job_id: int) -> None:
        selected_now = utc_now()
        with session_factory.begin() as db:
            export_job = db.scalar(
                select(IntegrationExportJob)
                .where(IntegrationExportJob.id == export_job_id)
                .with_for_update()
            )
            if export_job is None or export_job.status in {
                ExportStatus.READY,
                ExportStatus.EXPIRED,
            }:
                return
            export_job.status = ExportStatus.FAILED
            export_job.error_code = "export_generation_failed"
            export_job.error_summary = "integration export generation failed"
            export_job.completed_at = selected_now

    def purge_connection(connection_id: int, current_job_id: int) -> bool:
        from integrations.purge import PurgeFileError, purge_connection_data

        try:
            with session_factory.begin() as db:
                purge_connection_data(
                    db,
                    connection_id=connection_id,
                    archive_dir=selected_archive_dir,
                    current_job_id=current_job_id,
                )
        except PurgeFileError:
            return False
        return True

    async def handle(job: ClaimedJob) -> None:
        if job.job_type is JobType.EXPORT:
            export_job_id = job.payload.get("export_job_id")
            if type(export_job_id) is not int or export_job_id <= 0:
                raise RetryableMaintenanceError("export payload is invalid")
            terminal_failure = job.attempts + 1 >= job.max_attempts
            try:
                status = await asyncio.to_thread(
                    generate_export,
                    export_job_id,
                    terminal_failure,
                )
            except Exception:
                if terminal_failure:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(
                            mark_export_terminal_failure,
                            export_job_id,
                        )
                    raise RuntimeError("export generation failed") from None
                raise RetryableMaintenanceError(
                    "export generation requires retry"
                ) from None
            if status in {ExportStatus.RUNNING, ExportStatus.FAILED}:
                if terminal_failure:
                    raise RuntimeError("export generation failed")
                raise RetryableMaintenanceError("export generation requires retry")
            return
        if job.job_type is JobType.PURGE_CONNECTION:
            connection_id = job.payload.get("connection_id")
            if type(connection_id) is not int or connection_id <= 0:
                raise RetryableMaintenanceError("purge payload is invalid")
            terminal_failure = job.attempts + 1 >= job.max_attempts
            try:
                succeeded = await asyncio.to_thread(
                    purge_connection,
                    connection_id,
                    job.id,
                )
            except Exception:
                if terminal_failure:
                    raise RuntimeError("connection purge failed") from None
                raise RetryableMaintenanceError(
                    "connection purge requires retry"
                ) from None
            if not succeeded:
                if terminal_failure:
                    raise RuntimeError("connection purge failed")
                raise RetryableMaintenanceError("connection purge requires retry")
            return
        if job.job_type is not JobType.ARCHIVE_CLEANUP:
            await default_job_handler(job)
            return
        manifest_id = job.payload.get("archive_manifest_id")
        if type(manifest_id) is not int or manifest_id <= 0:
            raise RetryableMaintenanceError("archive cleanup payload is invalid")
        async with cleanup_lock:
            should_retry = await asyncio.to_thread(cleanup_archives)
        if should_retry:
            raise RetryableMaintenanceError("archive cleanup requires retry")

    return handle


def _parse_payload_time(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical UTC timestamp") from exc
    return _aware_utc(parsed, field_name=field_name)


class IntegrationWorker:
    """Bounded asynchronous executor over the durable PostgreSQL queue."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        config: WorkerConfig,
        job_handler: JobHandler = default_job_handler,
        scheduler_tick: MaintenanceHook | None = None,
        orphan_cleanup: MaintenanceHook | None = None,
        worker_id: str | None = None,
        pid: int | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if not isinstance(config, WorkerConfig):
            raise TypeError("config must be WorkerConfig")
        if not callable(job_handler):
            raise TypeError("job_handler must be callable")
        if scheduler_tick is not None and not callable(scheduler_tick):
            raise TypeError("scheduler_tick must be callable")
        if orphan_cleanup is not None and not callable(orphan_cleanup):
            raise TypeError("orphan_cleanup must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.session_factory = session_factory
        self.config = config
        self.job_handler = job_handler
        self.scheduler_tick = scheduler_tick
        self.orphan_cleanup = orphan_cleanup
        self.worker_id = _worker_id(
            worker_id or f"worker-{uuid.uuid4().hex}"
        )
        self.pid = os.getpid() if pid is None else pid
        if type(self.pid) is not int or self.pid <= 0:
            raise ValueError("pid must be a positive integer")
        self.clock = clock
        self._stop = asyncio.Event()
        self._active_job_ids: set[int] = set()
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._claimed_jobs = 0
        self._succeeded_jobs = 0
        self._failed_jobs = 0
        self._maintenance_errors = 0

    def request_stop(self) -> None:
        self._stop.set()

    def _write_heartbeat(self) -> None:
        with self.session_factory.begin() as db:
            upsert_worker_heartbeat(
                db,
                worker_id=self.worker_id,
                pid=self.pid,
                active_job_count=len(self._active_job_ids),
                now=self.clock(),
            )

    def _claim_one(self) -> ClaimedJob | None:
        with self.session_factory.begin() as db:
            job = claim_next_job(
                db,
                owner=self.worker_id,
                now=self.clock(),
                lease_duration=self.config.lease_duration,
            )
            if job is None:
                return None
            claimed = ClaimedJob(
                id=job.id,
                job_type=job.job_type,
                payload=dict(job.payload),
                attempts=job.attempts,
                max_attempts=job.max_attempts,
            )
        self._claimed_jobs += 1
        return claimed

    def _start_claimed_job(self, job: ClaimedJob) -> bool:
        with self.session_factory.begin() as db:
            if job.job_type is JobType.SYNC_RESOURCE:
                try:
                    resource = ResourceType(job.payload["resource_type"])
                    connection_id = int(job.payload["connection_id"])
                    checkpoint_id = int(job.payload["checkpoint_id"])
                    window_start = _parse_payload_time(
                        job.payload["window_start"], field_name="window_start"
                    )
                    window_end = _parse_payload_time(
                        job.payload["window_end"], field_name="window_end"
                    )
                except (KeyError, TypeError, ValueError):
                    return False
                checkpoint = acquire_checkpoint_for_job(
                    db,
                    job_id=job.id,
                    connection_id=connection_id,
                    resource_type=resource,
                    window_start=window_start,
                    window_end=window_end,
                    owner=self.worker_id,
                    now=self.clock(),
                    lease_duration=self.config.lease_duration,
                )
                return checkpoint is not None and checkpoint.id == checkpoint_id
            return start_job(
                db,
                job_id=job.id,
                owner=self.worker_id,
                now=self.clock(),
            )

    async def _renew_lease(self, job: ClaimedJob) -> None:
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            now = self.clock()
            with self.session_factory.begin() as db:
                renewed = heartbeat_job(
                    db,
                    job_id=job.id,
                    owner=self.worker_id,
                    now=now,
                    lease_duration=self.config.lease_duration,
                )
                if renewed and job.job_type is JobType.SYNC_RESOURCE:
                    checkpoint_id = job.payload.get("checkpoint_id")
                    if type(checkpoint_id) is int and checkpoint_id > 0:
                        heartbeat_checkpoint(
                            db,
                            checkpoint_id=checkpoint_id,
                            owner=self.worker_id,
                            now=now,
                            lease_duration=self.config.lease_duration,
                        )
            if not renewed:
                return

    def _finish_success(self, job: ClaimedJob) -> None:
        with self.session_factory.begin() as db:
            if complete_job(
                db,
                job_id=job.id,
                owner=self.worker_id,
                now=self.clock(),
            ):
                self._succeeded_jobs += 1

    def _finish_failure(
        self,
        job: ClaimedJob,
        *,
        unavailable: bool,
        retryable: bool = False,
    ) -> None:
        code = (
            JobErrorCode.CONNECTOR_UNAVAILABLE
            if unavailable
            else JobErrorCode.INTERNAL_ERROR
        )
        summary = (
            JobErrorSummary.CONNECTOR_NOT_CONFIGURED
            if unavailable
            else JobErrorSummary.INTERNAL_WORKER_FAILURE
        )
        with self.session_factory.begin() as db:
            if fail_job(
                db,
                job_id=job.id,
                owner=self.worker_id,
                error_code=code,
                error_summary=summary,
                retryable=retryable,
                now=self.clock(),
            ):
                self._failed_jobs += 1

    async def _process_job(self, job: ClaimedJob) -> None:
        async with self._semaphore:
            if not self._start_claimed_job(job):
                return
            self._active_job_ids.add(job.id)
            renewal = asyncio.create_task(self._renew_lease(job))
            try:
                try:
                    await self.job_handler(job)
                except ConnectorUnavailableError:
                    self._finish_failure(job, unavailable=True)
                except RetryableMaintenanceError:
                    self._finish_failure(
                        job,
                        unavailable=False,
                        retryable=True,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._finish_failure(job, unavailable=False)
                else:
                    self._finish_success(job)
            finally:
                renewal.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await renewal
                self._active_job_ids.discard(job.id)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            self._write_heartbeat()

    async def _maintenance_once(self) -> None:
        hooks: Sequence[MaintenanceHook] = tuple(
            hook
            for hook in (self.scheduler_tick, self.orphan_cleanup)
            if hook is not None
        )
        if not hooks:
            return
        outcomes = await asyncio.gather(
            *(hook() for hook in hooks),
            return_exceptions=True,
        )
        self._maintenance_errors += sum(
            isinstance(outcome, BaseException) for outcome in outcomes
        )

    async def _maintenance_loop(self) -> None:
        while not self._stop.is_set():
            await self._maintenance_once()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.config.maintenance_interval
                )
            except asyncio.TimeoutError:
                continue

    async def _drain_tasks(
        self,
        tasks: set[asyncio.Task[None]],
        *,
        deadline: float,
    ) -> None:
        if not tasks:
            return
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        done, pending = await asyncio.wait(
            tasks,
            timeout=remaining,
        )
        for task in done:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                task.result()
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def run(self, *, once: bool = False) -> WorkerRunResult:
        if not self.config.enabled:
            return WorkerRunResult(enabled=False)

        self._write_heartbeat()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        maintenance_task = asyncio.create_task(
            self._maintenance_once() if once else self._maintenance_loop()
        )
        tasks: set[asyncio.Task[None]] = set()
        try:
            while not self._stop.is_set():
                if heartbeat_task.done():
                    self._stop.set()
                    break
                completed_tasks = {task for task in tasks if task.done()}
                for completed in completed_tasks:
                    try:
                        completed.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        self._stop.set()
                tasks.difference_update(completed_tasks)
                if self._stop.is_set():
                    break
                while len(tasks) < self.config.concurrency and not self._stop.is_set():
                    claimed = self._claim_one()
                    if claimed is None:
                        break
                    tasks.add(asyncio.create_task(self._process_job(claimed)))
                if once:
                    break
                await asyncio.sleep(self.config.poll_interval)
            shutdown_deadline = (
                asyncio.get_running_loop().time() + self.config.shutdown_timeout
            )
            await self._drain_tasks(tasks, deadline=shutdown_deadline)
            remaining = max(
                0.0,
                shutdown_deadline - asyncio.get_running_loop().time(),
            )
            done_maintenance, pending_maintenance = await asyncio.wait(
                {maintenance_task},
                timeout=remaining,
            )
            for completed in done_maintenance:
                try:
                    completed.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    self._maintenance_errors += 1
            for pending in pending_maintenance:
                pending.cancel()
            if pending_maintenance:
                await asyncio.gather(
                    *pending_maintenance,
                    return_exceptions=True,
                )
        finally:
            self._stop.set()
            maintenance_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await maintenance_task
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await heartbeat_task
            with self.session_factory.begin() as db:
                release_worker_leases(db, owner=self.worker_id, now=self.clock())
            with contextlib.suppress(Exception):
                self._write_heartbeat()

        return WorkerRunResult(
            enabled=True,
            claimed_jobs=self._claimed_jobs,
            succeeded_jobs=self._succeeded_jobs,
            failed_jobs=self._failed_jobs,
            maintenance_errors=self._maintenance_errors,
        )


def tick_scheduler_maintenance(
    session_factory: sessionmaker,
    *,
    now: datetime | None = None,
) -> int:
    """Enqueue only evidence-backed maintenance while connectors are pending."""

    from integrations.sync.scheduler import due_jobs, enqueue_scheduled_units

    selected_now = _aware_utc(now or utc_now(), field_name="now")
    with session_factory.begin() as db:
        expired_manifest_ids = db.scalars(
            select(IntegrationArchiveManifest.id)
            .where(
                IntegrationArchiveManifest.expires_at < selected_now,
                IntegrationArchiveManifest.deleted_at.is_(None),
            )
            .order_by(IntegrationArchiveManifest.id)
        ).all()
        units = due_jobs(
            selected_now,
            (),
            {},
            expired_archive_manifest_ids=expired_manifest_ids,
        )
        enqueue_scheduled_units(db, units)
    return len(units)


def expire_export_maintenance(
    session_factory: sessionmaker,
    *,
    archive_dir: Path,
    now: datetime | None = None,
) -> int:
    """Delete expired local export files and retry any closed I/O failures."""

    from integrations.exports import expire_export_files

    selected_now = _aware_utc(now or utc_now(), field_name="now")
    selected_archive_dir = Path(archive_dir).resolve(strict=False)
    with session_factory.begin() as db:
        expired_count, retry_count = expire_export_files(
            db,
            archive_dir=selected_archive_dir,
            now=selected_now,
        )
    if retry_count:
        raise RetryableMaintenanceError("export expiration requires retry")
    return expired_count


def scan_orphan_maintenance(
    session_factory: sessionmaker,
    *,
    archive_dir: Path,
    now: datetime | None = None,
) -> int:
    selected_now = _aware_utc(now or utc_now(), field_name="now")
    from integrations.exports import scan_orphan_exports

    with session_factory() as db:
        known_paths = tuple(
            db.scalars(
                select(IntegrationArchiveManifest.relative_path).order_by(
                    IntegrationArchiveManifest.id
                )
            ).all()
        )
        known_export_paths = tuple(
            path
            for path in db.scalars(
                select(IntegrationExportJob.relative_file_path)
                .where(IntegrationExportJob.relative_file_path.is_not(None))
                .order_by(IntegrationExportJob.id)
            ).all()
            if isinstance(path, str)
        )
    result = scan_orphan_archives(
        archive_dir=archive_dir,
        manifest_relative_paths=known_paths,
        now=selected_now,
    )
    export_result = scan_orphan_exports(
        archive_dir=archive_dir,
        known_relative_paths=known_export_paths,
        now=selected_now,
    )
    if export_result.failure_count:
        raise RetryableMaintenanceError("export orphan cleanup requires retry")
    return len(result.deleted_paths) + len(export_result.deleted_paths)


__all__ = [
    "ClaimedJob",
    "ConnectorUnavailableError",
    "DEFAULT_WORKER_CONCURRENCY",
    "IntegrationWorker",
    "ReleasedLeaseCount",
    "RetryableMaintenanceError",
    "WORKER_ENABLED_ENV",
    "WORKER_VERSION",
    "WorkerConfig",
    "WorkerReadinessError",
    "WorkerRunResult",
    "default_job_handler",
    "build_default_job_handler",
    "parse_worker_enabled",
    "release_worker_leases",
    "scan_orphan_maintenance",
    "stale_worker_ids",
    "tick_scheduler_maintenance",
    "upsert_worker_heartbeat",
    "validate_worker_readiness",
]
