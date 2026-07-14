"""Resumable connector page execution with commit-safe cursors.

The runner performs provider I/O outside database transactions.  Each fetched
page receives its own archive context and database transaction so a cursor is
never durable before the archive manifest and normalized rows are durable.
"""

from __future__ import annotations

import asyncio
import math
import os
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from integration_models import (
    IntegrationArchiveManifest,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationJob,
    IntegrationSyncCheckpoint,
    IntegrationSyncRun,
)
from integrations.connections import (
    ConnectorOutputInvalid,
    acquire_authorization_refresh_lease,
    mark_authorization_reauthorization_required,
    mark_connection_permission_limited,
    release_authorization_refresh_lease,
    replace_refreshed_authorization_tokens,
)
from integrations.connectors.base import (
    AuthenticationFailed,
    EcommerceConnector,
    InvalidPlatformResponse,
    PermissionDenied,
    RateLimited,
    TransientPlatformError,
)
from integrations.crypto import (
    CredentialDecryptionError,
    CredentialPurpose,
    decrypt_credential,
)
from integrations.sync.archive import ArchivePage, archive_expires_at
from integrations.sync.queue import (
    JobErrorCode,
    JobErrorSummary,
    advance_checkpoint,
    complete_checkpoint,
    complete_job,
    fail_checkpoint,
    fail_job,
    heartbeat_checkpoint,
    heartbeat_job,
)
from integrations.sync.writer import write_records
from integrations.types import (
    AuthorizationStatus,
    CheckpointStatus,
    ConnectionContext,
    ConnectionStatus,
    FetchPage,
    JobStatus,
    JobType,
    Provider,
    ResourceType,
    SyncSource,
    SyncStatus,
    TimeWindow,
    TokenBundle,
    utc_now,
)


_SNAPSHOT_RESOURCES = frozenset(
    {
        ResourceType.SHOPS,
        ResourceType.PRODUCTS,
        ResourceType.SKUS,
        ResourceType.INVENTORY,
        ResourceType.AD_ACCOUNTS,
        ResourceType.AD_ENTITIES,
        ResourceType.AD_BALANCE_SNAPSHOTS,
    }
)
_MAX_FETCH_ATTEMPTS = 6
_MAX_LEASE_DURATION = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    archive_dir: os.PathLike[str] | str
    master_key: bytes
    quarantine_hmac_key: bytes
    lease_duration: timedelta = timedelta(minutes=20)
    refresh_lease_duration: timedelta = timedelta(minutes=5)
    max_fetch_attempts: int = _MAX_FETCH_ATTEMPTS

    def __post_init__(self) -> None:
        try:
            os.fspath(self.archive_dir)
        except TypeError:
            raise TypeError("archive_dir must be a filesystem path") from None
        if type(self.master_key) is not bytes or len(self.master_key) != 32:
            raise ValueError("master_key must contain exactly 32 bytes")
        if (
            type(self.quarantine_hmac_key) is not bytes
            or len(self.quarantine_hmac_key) < 32
        ):
            raise ValueError(
                "quarantine_hmac_key must contain at least 32 bytes"
            )
        for field_name in ("lease_duration", "refresh_lease_duration"):
            duration = getattr(self, field_name)
            if (
                not isinstance(duration, timedelta)
                or duration <= timedelta(0)
                or duration > _MAX_LEASE_DURATION
            ):
                raise ValueError(
                    f"{field_name} must be positive and at most one hour"
                )
        if (
            type(self.max_fetch_attempts) is not int
            or not 1 <= self.max_fetch_attempts <= _MAX_FETCH_ATTEMPTS
        ):
            raise ValueError("max_fetch_attempts must be from 1 through 6")


@dataclass(frozen=True, slots=True)
class RunnerResult:
    run_id: int
    status: SyncStatus
    pages_committed: int
    fetch_attempts: int
    records_read: int
    records_written: int
    records_skipped: int
    records_quarantined: int
    refreshed: bool


@dataclass(frozen=True, slots=True)
class _RunState:
    run_id: int
    connection_id: int
    authorization_id: int
    provider: Provider
    resource: ResourceType
    window_start: datetime
    window_end: datetime
    cursor: str | None
    page_number: int


@dataclass(frozen=True, slots=True)
class _RetriesExhausted(Exception):
    error: RateLimited | TransientPlatformError
    attempts: int


def _aware_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError):
        offset = None
    if offset is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _positive_id(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _owner(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("owner must be a non-empty bounded identifier")
    return value


def _commit_page(db: Session) -> None:
    """Small fault-injection seam around the irreversible page commit."""

    db.commit()


def _api_window(state: _RunState) -> TimeWindow | None:
    if state.resource in _SNAPSHOT_RESOURCES:
        return None
    return TimeWindow(state.window_start, state.window_end)


def _refresh_safety_window(
    connector: EcommerceConnector,
    tokens: TokenBundle,
) -> timedelta:
    reported: Any = getattr(connector, "refresh_safety_window", timedelta(0))
    if callable(reported):
        reported = reported(tokens)
    if (
        not isinstance(reported, timedelta)
        or reported < timedelta(0)
        or reported > timedelta(hours=24)
    ):
        raise InvalidPlatformResponse()
    return reported


def _token_refresh_due(
    connector: EcommerceConnector,
    tokens: TokenBundle,
    *,
    now: datetime,
) -> bool:
    if tokens.access_expires_at is None:
        return False
    expires_at = _aware_utc(
        tokens.access_expires_at,
        field_name="access_expires_at",
    )
    return expires_at <= now + _refresh_safety_window(connector, tokens)


def _load_connection_context(
    session_factory: Callable[[], Session],
    *,
    state: _RunState,
    master_key: bytes,
) -> ConnectionContext:
    with session_factory() as db:
        connection = db.get(IntegrationConnection, state.connection_id)
        authorization = db.get(
            IntegrationAuthorization,
            state.authorization_id,
        )
        if (
            connection is None
            or authorization is None
            or connection.authorization_id != authorization.id
            or connection.provider is not state.provider
            or authorization.provider is not state.provider
            or authorization.status is not AuthorizationStatus.ACTIVE
            or not authorization.access_token_ciphertext
        ):
            raise AuthenticationFailed()
        try:
            access_token = decrypt_credential(
                authorization.access_token_ciphertext,
                master_key=master_key,
                purpose=CredentialPurpose.ACCESS_TOKEN,
            )
            refresh_token = (
                decrypt_credential(
                    authorization.refresh_token_ciphertext,
                    master_key=master_key,
                    purpose=CredentialPurpose.REFRESH_TOKEN,
                )
                if authorization.refresh_token_ciphertext is not None
                else None
            )
        except CredentialDecryptionError:
            raise AuthenticationFailed() from None
        scopes = authorization.scopes
        if not isinstance(scopes, list) or any(
            type(scope) is not str for scope in scopes
        ):
            raise AuthenticationFailed()
        tokens = TokenBundle(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=authorization.access_expires_at,
            refresh_expires_at=authorization.refresh_expires_at,
            scopes=tuple(scopes),
            external_subject_id=authorization.external_subject_id,
        )
        return ConnectionContext(
            connection_id=connection.id,
            authorization_id=authorization.id,
            provider=connection.provider,
            connection_type=connection.connection_type,
            external_account_id=connection.external_account_id,
            tokens=tokens,
        )


def _start_or_resume_run(
    session_factory: Callable[[], Session],
    *,
    connector: EcommerceConnector,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    source: SyncSource,
    now: datetime,
) -> _RunState:
    with session_factory.begin() as db:
        job = db.scalar(
            select(IntegrationJob)
            .where(
                IntegrationJob.id == job_id,
                IntegrationJob.job_type == JobType.SYNC_RESOURCE,
                IntegrationJob.status == JobStatus.RUNNING,
                IntegrationJob.lease_owner == owner,
                IntegrationJob.lease_expires_at > now,
            )
            .with_for_update()
        )
        checkpoint = db.scalar(
            select(IntegrationSyncCheckpoint)
            .where(
                IntegrationSyncCheckpoint.id == checkpoint_id,
                IntegrationSyncCheckpoint.status == CheckpointStatus.RUNNING,
                IntegrationSyncCheckpoint.lease_owner == owner,
                IntegrationSyncCheckpoint.lease_expires_at > now,
            )
            .with_for_update()
        )
        if job is None or checkpoint is None:
            raise RuntimeError("sync work lease is not live")
        payload = job.payload if isinstance(job.payload, dict) else {}
        if (
            payload.get("checkpoint_id") != checkpoint.id
            or payload.get("connection_id") != checkpoint.connection_id
            or payload.get("resource_type") != checkpoint.resource_type.value
        ):
            raise RuntimeError("sync job payload does not match its checkpoint")
        connection = db.scalar(
            select(IntegrationConnection)
            .where(IntegrationConnection.id == checkpoint.connection_id)
            .with_for_update()
        )
        if connection is None:
            raise RuntimeError("sync checkpoint connection is missing")
        authorization = db.get(
            IntegrationAuthorization,
            connection.authorization_id,
        )
        if (
            authorization is None
            or authorization.provider is not connection.provider
            or connector.provider is not connection.provider
        ):
            raise RuntimeError("connector provider does not match the connection")
        if authorization.status is not AuthorizationStatus.ACTIVE:
            raise AuthenticationFailed()
        if connection.status in (
            ConnectionStatus.REAUTHORIZATION_REQUIRED,
            ConnectionStatus.DISABLED,
            ConnectionStatus.SETUP_REQUIRED,
            ConnectionStatus.AUTHORIZING,
        ):
            raise RuntimeError("connection is not runnable")

        latest = db.scalar(
            select(IntegrationSyncRun)
            .where(IntegrationSyncRun.checkpoint_id == checkpoint.id)
            .order_by(IntegrationSyncRun.id.desc())
            .with_for_update()
            .limit(1)
        )
        resumable = (
            latest is not None
            and latest.status
            in (
                SyncStatus.RUNNING,
                SyncStatus.PARTIAL_SUCCESS,
                SyncStatus.RETRY_WAIT,
            )
        )
        if resumable:
            run = latest
            if run.status is SyncStatus.RETRY_WAIT:
                run.status = SyncStatus.RUNNING
                run.ended_at = None
                run.failure_code = None
                run.failure_summary = None
        else:
            parent_run_id = (
                latest.id
                if latest is not None
                and latest.status is SyncStatus.FAILED
                and source in (SyncSource.MANUAL, SyncSource.RETRY)
                else None
            )
            run = IntegrationSyncRun(
                checkpoint_id=checkpoint.id,
                parent_run_id=parent_run_id,
                source=source,
                status=SyncStatus.RUNNING,
                resource_type=checkpoint.resource_type,
                window_start=checkpoint.window_start,
                window_end=checkpoint.window_end,
                progress=0,
                records_read=0,
                records_written=0,
                records_skipped=0,
                records_quarantined=0,
                created_at=now,
                started_at=now,
            )
            db.add(run)
            db.flush()
        checkpoint.attempts += 1
        checkpoint.updated_at = max(checkpoint.updated_at, now)
        if connection.status is ConnectionStatus.ACTIVE:
            connection.status = ConnectionStatus.SYNCING
            connection.updated_at = max(connection.updated_at, now)
        page_number = db.scalar(
            select(func.max(IntegrationArchiveManifest.page_number)).where(
                IntegrationArchiveManifest.run_id == run.id
            )
        )
        cursor = checkpoint.cursor
        if cursor is not None and type(cursor) is not str:
            raise RuntimeError("checkpoint cursor is invalid")
        return _RunState(
            run_id=run.id,
            connection_id=connection.id,
            authorization_id=authorization.id,
            provider=connection.provider,
            resource=checkpoint.resource_type,
            window_start=checkpoint.window_start,
            window_end=checkpoint.window_end,
            cursor=cursor,
            page_number=0 if page_number is None else page_number + 1,
        )


def _heartbeat(
    session_factory: Callable[[], Session],
    *,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
) -> None:
    with session_factory.begin() as db:
        job_live = heartbeat_job(
            db,
            job_id=job_id,
            owner=owner,
            now=now,
            lease_duration=lease_duration,
        )
        checkpoint_live = heartbeat_checkpoint(
            db,
            checkpoint_id=checkpoint_id,
            owner=owner,
            now=now,
            lease_duration=lease_duration,
        )
        if not job_live or not checkpoint_live:
            raise RuntimeError("sync work lease was lost")


def _jitter_delay(
    attempt: int,
    *,
    uniform: Callable[[float, float], float],
    retry_after_seconds: float | None,
) -> float:
    upper = min(900.0, (2**attempt) * 5.0)
    selected = uniform(0.0, upper)
    if (
        isinstance(selected, bool)
        or not isinstance(selected, (int, float))
        or not math.isfinite(selected)
        or not 0 <= selected <= upper
    ):
        raise ValueError("uniform returned an invalid full-jitter value")
    delay = float(selected)
    if retry_after_seconds is not None:
        if (
            isinstance(retry_after_seconds, bool)
            or not isinstance(retry_after_seconds, (int, float))
            or not math.isfinite(retry_after_seconds)
            or retry_after_seconds < 0
        ):
            raise InvalidPlatformResponse()
        delay = max(delay, float(retry_after_seconds))
    return delay


async def _fetch_with_retry(
    session_factory: Callable[[], Session],
    *,
    connector: EcommerceConnector,
    connection: ConnectionContext,
    state: _RunState,
    cursor: str | None,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    config: RunnerConfig,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[None]],
    uniform: Callable[[float, float], float],
) -> tuple[FetchPage, int]:
    for attempt in range(config.max_fetch_attempts):
        try:
            page = await connector.fetch_page(
                connection=connection,
                resource=state.resource,
                window=_api_window(state),
                cursor=cursor,
            )
            if not isinstance(page, FetchPage):
                raise InvalidPlatformResponse()
            if any(item.resource is not state.resource for item in page.items):
                raise InvalidPlatformResponse()
            if page.has_more and page.next_cursor == cursor:
                raise InvalidPlatformResponse()
            return page, attempt + 1
        except (AuthenticationFailed, PermissionDenied, InvalidPlatformResponse):
            raise
        except (RateLimited, TransientPlatformError) as error:
            if attempt + 1 >= config.max_fetch_attempts:
                raise _RetriesExhausted(error, attempt + 1) from None
            now = _aware_utc(clock(), field_name="clock")
            _heartbeat(
                session_factory,
                job_id=job_id,
                checkpoint_id=checkpoint_id,
                owner=owner,
                now=now,
                lease_duration=config.lease_duration,
            )
            delay = _jitter_delay(
                attempt,
                uniform=uniform,
                retry_after_seconds=(
                    error.retry_after_seconds
                    if isinstance(error, RateLimited)
                    else None
                ),
            )
            await sleep(delay)
    raise RuntimeError("unreachable fetch retry state")


async def _refresh_connection_context(
    session_factory: Callable[[], Session],
    *,
    connector: EcommerceConnector,
    state: _RunState,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    config: RunnerConfig,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[None]],
    uniform: Callable[[float, float], float],
) -> ConnectionContext:
    lease_acquired = False
    baseline_refreshed_at: datetime | None = None
    with session_factory() as db:
        authorization = db.get(IntegrationAuthorization, state.authorization_id)
        if authorization is None:
            raise AuthenticationFailed()
        baseline_refreshed_at = authorization.last_refreshed_at

    for attempt in range(config.max_fetch_attempts):
        now = _aware_utc(clock(), field_name="clock")
        with session_factory.begin() as db:
            lease_acquired = acquire_authorization_refresh_lease(
                db,
                authorization_id=state.authorization_id,
                owner=owner,
                now=now,
                lease_duration=config.refresh_lease_duration,
                expected_last_refreshed_at=baseline_refreshed_at,
            )
        if lease_acquired:
            break
        with session_factory() as db:
            authorization = db.get(
                IntegrationAuthorization,
                state.authorization_id,
            )
            if (
                authorization is None
                or authorization.status
                is AuthorizationStatus.REAUTHORIZATION_REQUIRED
            ):
                raise AuthenticationFailed()
            if authorization.last_refreshed_at != baseline_refreshed_at:
                return _load_connection_context(
                    session_factory,
                    state=state,
                    master_key=config.master_key,
                )
        if attempt + 1 >= config.max_fetch_attempts:
            raise TransientPlatformError()
        await sleep(_jitter_delay(attempt, uniform=uniform, retry_after_seconds=None))

    try:
        current = _load_connection_context(
            session_factory,
            state=state,
            master_key=config.master_key,
        )
        for attempt in range(config.max_fetch_attempts):
            try:
                refreshed = await connector.refresh_tokens(current.tokens)
                break
            except (
                AuthenticationFailed,
                PermissionDenied,
                InvalidPlatformResponse,
            ):
                raise
            except (RateLimited, TransientPlatformError) as error:
                if attempt + 1 >= config.max_fetch_attempts:
                    raise _RetriesExhausted(error, attempt + 1) from None
                now = _aware_utc(clock(), field_name="clock")
                _heartbeat(
                    session_factory,
                    job_id=job_id,
                    checkpoint_id=checkpoint_id,
                    owner=owner,
                    now=now,
                    lease_duration=config.lease_duration,
                )
                await sleep(
                    _jitter_delay(
                        attempt,
                        uniform=uniform,
                        retry_after_seconds=(
                            error.retry_after_seconds
                            if isinstance(error, RateLimited)
                            else None
                        ),
                    )
                )
        else:
            raise RuntimeError("unreachable refresh retry state")
        now = _aware_utc(clock(), field_name="clock")
        with session_factory.begin() as db:
            replaced = replace_refreshed_authorization_tokens(
                db,
                authorization_id=state.authorization_id,
                owner=owner,
                tokens=refreshed,
                master_key=config.master_key,
                now=now,
            )
            if not replaced:
                raise InvalidPlatformResponse()
        return _load_connection_context(
            session_factory,
            state=state,
            master_key=config.master_key,
        )
    except ConnectorOutputInvalid:
        raise InvalidPlatformResponse() from None
    finally:
        if lease_acquired:
            now = _aware_utc(clock(), field_name="clock")
            with session_factory.begin() as db:
                release_authorization_refresh_lease(
                    db,
                    authorization_id=state.authorization_id,
                    owner=owner,
                    now=now,
                )


def _complete_page(
    session_factory: Callable[[], Session],
    *,
    state: _RunState,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    page: FetchPage,
    page_number: int,
    config: RunnerConfig,
    now: datetime,
) -> None:
    with ArchivePage(
        archive_dir=config.archive_dir,
        master_key=config.master_key,
        provider=state.provider,
        connection_id=state.connection_id,
        resource=state.resource,
        run_id=state.run_id,
        page_number=page_number,
        created_at=now,
        records=page.items,
    ) as archive:
        db = session_factory()
        try:
            write_records(
                db,
                run_id=state.run_id,
                records=page.items,
                quarantine_hmac_key=config.quarantine_hmac_key,
                now=now,
            )
            db.add(
                IntegrationArchiveManifest(
                    run_id=state.run_id,
                    page_number=page_number,
                    provider=state.provider,
                    connection_id=state.connection_id,
                    resource_type=state.resource,
                    window_start=state.window_start,
                    window_end=state.window_end,
                    relative_path=archive.relative_path,
                    sha256=archive.sha256,
                    record_count=archive.record_count,
                    created_at=now,
                    expires_at=archive_expires_at(now),
                )
            )
            if not advance_checkpoint(
                db,
                checkpoint_id=checkpoint_id,
                owner=owner,
                cursor=page.next_cursor,
                watermark=page.watermark,
                now=now,
            ):
                raise RuntimeError("sync checkpoint lease was lost")
            if not page.has_more:
                run = db.scalar(
                    select(IntegrationSyncRun)
                    .where(IntegrationSyncRun.id == state.run_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                connection = db.scalar(
                    select(IntegrationConnection)
                    .where(IntegrationConnection.id == state.connection_id)
                    .with_for_update()
                )
                if run is None or connection is None:
                    raise RuntimeError("sync completion state is missing")
                if run.status is SyncStatus.RUNNING:
                    run.status = SyncStatus.SUCCEEDED
                elif run.status is not SyncStatus.PARTIAL_SUCCESS:
                    raise RuntimeError("sync run is not completable")
                run.progress = 1
                run.ended_at = now
                run.failure_code = None
                run.failure_summary = None
                if not complete_checkpoint(
                    db,
                    checkpoint_id=checkpoint_id,
                    owner=owner,
                    now=now,
                ):
                    raise RuntimeError("sync checkpoint could not be completed")
                if not complete_job(
                    db,
                    job_id=job_id,
                    owner=owner,
                    now=now,
                ):
                    raise RuntimeError("sync job could not be completed")
                connection.last_successful_sync_at = now
                if connection.status in (
                    ConnectionStatus.SYNCING,
                    ConnectionStatus.DEGRADED,
                ):
                    connection.status = ConnectionStatus.ACTIVE
                connection.updated_at = max(connection.updated_at, now)
            _commit_page(db)
            archive.retain()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def _result(
    session_factory: Callable[[], Session],
    *,
    run_id: int,
    pages_committed: int,
    fetch_attempts: int,
    refreshed: bool,
) -> RunnerResult:
    with session_factory() as db:
        run = db.get(IntegrationSyncRun, run_id)
        if run is None:
            raise RuntimeError("sync run disappeared")
        return RunnerResult(
            run_id=run.id,
            status=run.status,
            pages_committed=pages_committed,
            fetch_attempts=fetch_attempts,
            records_read=run.records_read,
            records_written=run.records_written,
            records_skipped=run.records_skipped,
            records_quarantined=run.records_quarantined,
            refreshed=refreshed,
        )


def _fail_run(
    session_factory: Callable[[], Session],
    *,
    state: _RunState,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    now: datetime,
    error_code: JobErrorCode,
    error_summary: JobErrorSummary,
    pages_committed: int,
    fetch_attempts: int,
    refreshed: bool,
    degrade: bool = False,
    permission_limited: bool = False,
    reauthorization_required: bool = False,
) -> RunnerResult:
    with session_factory.begin() as db:
        if reauthorization_required:
            mark_authorization_reauthorization_required(
                db,
                authorization_id=state.authorization_id,
                now=now,
            )
        run = db.scalar(
            select(IntegrationSyncRun)
            .where(IntegrationSyncRun.id == state.run_id)
            .with_for_update()
        )
        connection = db.scalar(
            select(IntegrationConnection)
            .where(IntegrationConnection.id == state.connection_id)
            .with_for_update()
        )
        if run is None or connection is None:
            raise RuntimeError("sync failure state is missing")
        run.status = SyncStatus.FAILED
        run.ended_at = now
        run.failure_code = error_code.value
        run.failure_summary = error_summary.value
        if reauthorization_required:
            pass
        elif permission_limited:
            if not mark_connection_permission_limited(
                db,
                connection_id=state.connection_id,
                resource=state.resource,
                now=now,
            ):
                raise RuntimeError("connection permission state is missing")
        elif degrade:
            connection.status = ConnectionStatus.DEGRADED
            connection.updated_at = max(connection.updated_at, now)
        elif connection.status is ConnectionStatus.SYNCING:
            connection.status = ConnectionStatus.ACTIVE
            connection.updated_at = max(connection.updated_at, now)
        if not fail_checkpoint(
            db,
            checkpoint_id=checkpoint_id,
            owner=owner,
            now=now,
        ):
            raise RuntimeError("sync checkpoint could not be failed")
        if not fail_job(
            db,
            job_id=job_id,
            owner=owner,
            error_code=error_code,
            error_summary=error_summary,
            retryable=False,
            now=now,
        ):
            raise RuntimeError("sync job could not be failed")
    return _result(
        session_factory,
        run_id=state.run_id,
        pages_committed=pages_committed,
        fetch_attempts=fetch_attempts,
        refreshed=refreshed,
    )


async def run_sync_pages(
    session_factory: Callable[[], Session],
    *,
    connector: EcommerceConnector,
    job_id: int,
    checkpoint_id: int,
    owner: str,
    source: SyncSource,
    config: RunnerConfig,
    clock: Callable[[], datetime] = utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    uniform: Callable[[float, float], float] = random.uniform,
) -> RunnerResult:
    """Fetch and commit all pages for one already-leased sync job."""

    if not callable(session_factory):
        raise TypeError("session_factory must be callable")
    if not isinstance(connector, EcommerceConnector):
        raise TypeError("connector must implement EcommerceConnector")
    selected_job_id = _positive_id(job_id, field_name="job_id")
    selected_checkpoint_id = _positive_id(
        checkpoint_id,
        field_name="checkpoint_id",
    )
    selected_owner = _owner(owner)
    if not isinstance(source, SyncSource):
        raise ValueError("source must be a SyncSource")
    if not isinstance(config, RunnerConfig):
        raise TypeError("config must be a RunnerConfig")
    if not callable(clock) or not callable(sleep) or not callable(uniform):
        raise TypeError("runner dependencies must be callable")
    now = _aware_utc(clock(), field_name="clock")
    state = _start_or_resume_run(
        session_factory,
        connector=connector,
        job_id=selected_job_id,
        checkpoint_id=selected_checkpoint_id,
        owner=selected_owner,
        source=source,
        now=now,
    )
    pages_committed = 0
    fetch_attempts = 0
    refreshed = False

    try:
        connection = _load_connection_context(
            session_factory,
            state=state,
            master_key=config.master_key,
        )
        if _token_refresh_due(connector, connection.tokens, now=now):
            connection = await _refresh_connection_context(
                session_factory,
                connector=connector,
                state=state,
                job_id=selected_job_id,
                checkpoint_id=selected_checkpoint_id,
                owner=selected_owner,
                config=config,
                clock=clock,
                sleep=sleep,
                uniform=uniform,
            )
            refreshed = True
    except AuthenticationFailed:
        return _fail_run(
            session_factory,
            state=state,
            job_id=selected_job_id,
            checkpoint_id=selected_checkpoint_id,
            owner=selected_owner,
            now=_aware_utc(clock(), field_name="clock"),
            error_code=JobErrorCode.AUTHORIZATION_REQUIRED,
            error_summary=JobErrorSummary.AUTHORIZATION_REFRESH_REQUIRED,
            pages_committed=pages_committed,
            fetch_attempts=fetch_attempts,
            refreshed=refreshed,
            reauthorization_required=True,
        )
    except InvalidPlatformResponse:
        return _fail_run(
            session_factory,
            state=state,
            job_id=selected_job_id,
            checkpoint_id=selected_checkpoint_id,
            owner=selected_owner,
            now=_aware_utc(clock(), field_name="clock"),
            error_code=JobErrorCode.INVALID_PROVIDER_RESPONSE,
            error_summary=JobErrorSummary.PROVIDER_RESPONSE_REJECTED,
            pages_committed=pages_committed,
            fetch_attempts=fetch_attempts,
            refreshed=refreshed,
        )
    except PermissionDenied:
        return _fail_run(
            session_factory,
            state=state,
            job_id=selected_job_id,
            checkpoint_id=selected_checkpoint_id,
            owner=selected_owner,
            now=_aware_utc(clock(), field_name="clock"),
            error_code=JobErrorCode.PERMISSION_DENIED,
            error_summary=JobErrorSummary.PROVIDER_PERMISSION_DENIED,
            pages_committed=pages_committed,
            fetch_attempts=fetch_attempts,
            refreshed=refreshed,
            permission_limited=True,
        )
    except _RetriesExhausted as exhausted:
        rate_limited = isinstance(exhausted.error, RateLimited)
        return _fail_run(
            session_factory,
            state=state,
            job_id=selected_job_id,
            checkpoint_id=selected_checkpoint_id,
            owner=selected_owner,
            now=_aware_utc(clock(), field_name="clock"),
            error_code=(
                JobErrorCode.PROVIDER_RATE_LIMITED
                if rate_limited
                else JobErrorCode.TRANSIENT_PROVIDER_ERROR
            ),
            error_summary=(
                JobErrorSummary.PROVIDER_THROTTLED
                if rate_limited
                else JobErrorSummary.TRANSIENT_PROVIDER_FAILURE
            ),
            pages_committed=pages_committed,
            fetch_attempts=fetch_attempts,
            refreshed=refreshed,
            degrade=True,
        )

    cursor = state.cursor
    page_number = state.page_number
    while True:
        try:
            page, attempts = await _fetch_with_retry(
                session_factory,
                connector=connector,
                connection=connection,
                state=state,
                cursor=cursor,
                job_id=selected_job_id,
                checkpoint_id=selected_checkpoint_id,
                owner=selected_owner,
                config=config,
                clock=clock,
                sleep=sleep,
                uniform=uniform,
            )
            fetch_attempts += attempts
        except AuthenticationFailed:
            fetch_attempts += 1
            if refreshed:
                return _fail_run(
                    session_factory,
                    state=state,
                    job_id=selected_job_id,
                    checkpoint_id=selected_checkpoint_id,
                    owner=selected_owner,
                    now=_aware_utc(clock(), field_name="clock"),
                    error_code=JobErrorCode.AUTHORIZATION_REQUIRED,
                    error_summary=JobErrorSummary.AUTHORIZATION_REFRESH_REQUIRED,
                    pages_committed=pages_committed,
                    fetch_attempts=fetch_attempts,
                    refreshed=refreshed,
                    reauthorization_required=True,
                )
            try:
                connection = await _refresh_connection_context(
                    session_factory,
                    connector=connector,
                    state=state,
                    job_id=selected_job_id,
                    checkpoint_id=selected_checkpoint_id,
                    owner=selected_owner,
                    config=config,
                    clock=clock,
                    sleep=sleep,
                    uniform=uniform,
                )
            except AuthenticationFailed:
                return _fail_run(
                    session_factory,
                    state=state,
                    job_id=selected_job_id,
                    checkpoint_id=selected_checkpoint_id,
                    owner=selected_owner,
                    now=_aware_utc(clock(), field_name="clock"),
                    error_code=JobErrorCode.AUTHORIZATION_REQUIRED,
                    error_summary=JobErrorSummary.AUTHORIZATION_REFRESH_REQUIRED,
                    pages_committed=pages_committed,
                    fetch_attempts=fetch_attempts,
                    refreshed=True,
                    reauthorization_required=True,
                )
            except PermissionDenied:
                return _fail_run(
                    session_factory,
                    state=state,
                    job_id=selected_job_id,
                    checkpoint_id=selected_checkpoint_id,
                    owner=selected_owner,
                    now=_aware_utc(clock(), field_name="clock"),
                    error_code=JobErrorCode.PERMISSION_DENIED,
                    error_summary=JobErrorSummary.PROVIDER_PERMISSION_DENIED,
                    pages_committed=pages_committed,
                    fetch_attempts=fetch_attempts,
                    refreshed=refreshed,
                    permission_limited=True,
                )
            except InvalidPlatformResponse:
                return _fail_run(
                    session_factory,
                    state=state,
                    job_id=selected_job_id,
                    checkpoint_id=selected_checkpoint_id,
                    owner=selected_owner,
                    now=_aware_utc(clock(), field_name="clock"),
                    error_code=JobErrorCode.INVALID_PROVIDER_RESPONSE,
                    error_summary=JobErrorSummary.PROVIDER_RESPONSE_REJECTED,
                    pages_committed=pages_committed,
                    fetch_attempts=fetch_attempts,
                    refreshed=refreshed,
                )
            except _RetriesExhausted as exhausted:
                rate_limited = isinstance(exhausted.error, RateLimited)
                return _fail_run(
                    session_factory,
                    state=state,
                    job_id=selected_job_id,
                    checkpoint_id=selected_checkpoint_id,
                    owner=selected_owner,
                    now=_aware_utc(clock(), field_name="clock"),
                    error_code=(
                        JobErrorCode.PROVIDER_RATE_LIMITED
                        if rate_limited
                        else JobErrorCode.TRANSIENT_PROVIDER_ERROR
                    ),
                    error_summary=(
                        JobErrorSummary.PROVIDER_THROTTLED
                        if rate_limited
                        else JobErrorSummary.TRANSIENT_PROVIDER_FAILURE
                    ),
                    pages_committed=pages_committed,
                    fetch_attempts=fetch_attempts,
                    refreshed=refreshed,
                    degrade=True,
                )
            refreshed = True
            continue
        except PermissionDenied:
            fetch_attempts += 1
            return _fail_run(
                session_factory,
                state=state,
                job_id=selected_job_id,
                checkpoint_id=selected_checkpoint_id,
                owner=selected_owner,
                now=_aware_utc(clock(), field_name="clock"),
                error_code=JobErrorCode.PERMISSION_DENIED,
                error_summary=JobErrorSummary.PROVIDER_PERMISSION_DENIED,
                pages_committed=pages_committed,
                fetch_attempts=fetch_attempts,
                refreshed=refreshed,
                permission_limited=True,
            )
        except InvalidPlatformResponse:
            fetch_attempts += 1
            return _fail_run(
                session_factory,
                state=state,
                job_id=selected_job_id,
                checkpoint_id=selected_checkpoint_id,
                owner=selected_owner,
                now=_aware_utc(clock(), field_name="clock"),
                error_code=JobErrorCode.INVALID_PROVIDER_RESPONSE,
                error_summary=JobErrorSummary.PROVIDER_RESPONSE_REJECTED,
                pages_committed=pages_committed,
                fetch_attempts=fetch_attempts,
                refreshed=refreshed,
            )
        except _RetriesExhausted as exhausted:
            fetch_attempts += exhausted.attempts
            rate_limited = isinstance(exhausted.error, RateLimited)
            return _fail_run(
                session_factory,
                state=state,
                job_id=selected_job_id,
                checkpoint_id=selected_checkpoint_id,
                owner=selected_owner,
                now=_aware_utc(clock(), field_name="clock"),
                error_code=(
                    JobErrorCode.PROVIDER_RATE_LIMITED
                    if rate_limited
                    else JobErrorCode.TRANSIENT_PROVIDER_ERROR
                ),
                error_summary=(
                    JobErrorSummary.PROVIDER_THROTTLED
                    if rate_limited
                    else JobErrorSummary.TRANSIENT_PROVIDER_FAILURE
                ),
                pages_committed=pages_committed,
                fetch_attempts=fetch_attempts,
                refreshed=refreshed,
                degrade=True,
            )

        committed_at = _aware_utc(clock(), field_name="clock")
        _complete_page(
            session_factory,
            state=state,
            job_id=selected_job_id,
            checkpoint_id=selected_checkpoint_id,
            owner=selected_owner,
            page=page,
            page_number=page_number,
            config=config,
            now=committed_at,
        )
        pages_committed += 1
        if not page.has_more:
            return _result(
                session_factory,
                run_id=state.run_id,
                pages_committed=pages_committed,
                fetch_attempts=fetch_attempts,
                refreshed=refreshed,
            )
        cursor = page.next_cursor
        page_number += 1
        _heartbeat(
            session_factory,
            job_id=selected_job_id,
            checkpoint_id=selected_checkpoint_id,
            owner=selected_owner,
            now=_aware_utc(clock(), field_name="clock"),
            lease_duration=config.lease_duration,
        )


__all__ = ["RunnerConfig", "RunnerResult", "run_sync_pages"]
