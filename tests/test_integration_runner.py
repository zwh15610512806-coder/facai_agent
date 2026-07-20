from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import database
from commerce_models import CommerceOrder, CommerceProduct
from database import Base
from integration_models import (
    IntegrationArchiveManifest,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationJob,
    IntegrationSyncCheckpoint,
    IntegrationSyncError,
    IntegrationSyncRun,
)
from integrations.connections import (
    acquire_authorization_refresh_lease,
    replace_refreshed_authorization_tokens,
)
from integrations.connectors.base import (
    AuthenticationFailed,
    PermissionDenied,
    RateLimited,
    TransientPlatformError,
)
from integrations.crypto import (
    CredentialPurpose,
    decrypt_credential,
    encrypt_credential,
)
from integrations.sync.queue import JobErrorCode, JobErrorSummary
from integrations.sync.runner import (
    RunnerConfig,
    RunnerResult,
    _fail_run,
    _RunState,
    run_sync_pages,
)
from integrations.types import (
    AccountIdentity,
    AuthorizationStatus,
    CheckpointStatus,
    ConnectionContext,
    ConnectionStatus,
    ConnectionType,
    FetchPage,
    JobStatus,
    JobType,
    NormalizedRecord,
    OrderStatus,
    ProductStatus,
    Provider,
    ResourceType,
    RevokeResult,
    SyncSource,
    SyncStatus,
    TimeWindow,
    TokenBundle,
)
from tests.postgres_test_support import requires_disposable_postgres
from tests.test_integration_models import _require_disposable_postgres_url

UTC = UTC
NOW = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)
MASTER_KEY = b"r" * 32
QUARANTINE_KEY = b"runner-quarantine-key-material-32bytes"
OWNER = "runner-worker-1"


RUNNER_TABLES = (
    IntegrationSyncError.__table__,
    IntegrationArchiveManifest.__table__,
    CommerceOrder.__table__,
    CommerceProduct.__table__,
    IntegrationSyncRun.__table__,
    IntegrationSyncCheckpoint.__table__,
    IntegrationJob.__table__,
    IntegrationConnection.__table__,
    IntegrationAuthorization.__table__,
)


@dataclass(frozen=True, slots=True)
class SeededWork:
    authorization_id: int
    connection_ids: tuple[int, ...]
    checkpoint_id: int
    job_id: int
    resource: ResourceType

    @property
    def connection_id(self) -> int:
        return self.connection_ids[0]


class SimulatedProcessCrash(BaseException):
    pass


class FakeConnector:
    provider = Provider.DOUDIAN

    def __init__(
        self,
        outcomes,
        *,
        refreshed_tokens: TokenBundle | None = None,
        refresh_outcomes=(),
        refresh_safety_window: timedelta = timedelta(0),
        fetch_probe=None,
    ) -> None:
        self.outcomes = list(outcomes)
        self.refreshed_tokens = refreshed_tokens
        self.refresh_outcomes = list(refresh_outcomes)
        self.refresh_safety_window = refresh_safety_window
        self.fetch_probe = fetch_probe
        self.fetch_calls = 0
        self.refresh_calls = 0
        self.cursors: list[str | None] = []
        self.windows: list[TimeWindow | None] = []
        self.access_tokens: list[str] = []

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        return "https://provider.invalid/oauth"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
        raise NotImplementedError

    async def refresh_tokens(self, tokens: TokenBundle) -> TokenBundle:
        self.refresh_calls += 1
        if self.refresh_outcomes:
            outcome = self.refresh_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        if self.refreshed_tokens is None:
            raise AssertionError("refresh_tokens was not expected")
        return self.refreshed_tokens

    async def discover_accounts(
        self,
        tokens: TokenBundle,
    ) -> list[AccountIdentity]:
        raise NotImplementedError

    async def probe_capabilities(self, connection: ConnectionContext):
        raise NotImplementedError

    async def fetch_page(
        self,
        *,
        connection: ConnectionContext,
        resource: ResourceType,
        window: TimeWindow | None,
        cursor: str | None,
    ) -> FetchPage:
        self.fetch_calls += 1
        self.cursors.append(cursor)
        self.windows.append(window)
        self.access_tokens.append(connection.tokens.access_token)
        if self.fetch_probe is not None:
            self.fetch_probe(self.fetch_calls, cursor, window)
        if not self.outcomes:
            raise AssertionError("fake connector ran out of outcomes")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def revoke(self, connection: ConnectionContext) -> RevokeResult:
        raise NotImplementedError


class RunnerLockOrderTests(unittest.TestCase):
    def test_reauthorization_failure_locks_authorization_before_connection(self):
        events: list[str] = []
        run = SimpleNamespace(
            status=SyncStatus.RUNNING,
            ended_at=None,
            failure_code=None,
            failure_summary=None,
        )
        connection = SimpleNamespace(
            status=ConnectionStatus.SYNCING,
            updated_at=NOW,
        )
        scalar_results = iter((run, connection))
        scalar_events = iter(("run", "connection"))
        db = Mock()

        def scalar(_statement):
            events.append(next(scalar_events))
            return next(scalar_results)

        db.scalar.side_effect = scalar
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(return_value=False)
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        state = _RunState(
            run_id=1,
            connection_id=2,
            authorization_id=3,
            provider=Provider.DOUDIAN,
            resource=ResourceType.ORDERS,
            window_start=NOW - timedelta(days=1),
            window_end=NOW,
            cursor=None,
            page_number=0,
        )

        def mark_authorization(*_args, **_kwargs):
            events.append("authorization")
            return 1

        with (
            patch(
                "integrations.sync.runner.mark_authorization_reauthorization_required",
                side_effect=mark_authorization,
            ),
            patch("integrations.sync.runner.fail_checkpoint", return_value=True),
            patch("integrations.sync.runner.fail_job", return_value=True),
            patch(
                "integrations.sync.runner._result",
                return_value="failure-result",
            ),
        ):
            result = _fail_run(
                session_factory,
                state=state,
                job_id=4,
                checkpoint_id=5,
                owner=OWNER,
                now=NOW,
                error_code=JobErrorCode.AUTHORIZATION_REQUIRED,
                error_summary=JobErrorSummary.AUTHORIZATION_REFRESH_REQUIRED,
                pages_committed=0,
                fetch_attempts=1,
                refreshed=True,
                reauthorization_required=True,
            )

        self.assertEqual(result, "failure-result")
        self.assertEqual(events, ["authorization", "run", "connection"])


@requires_disposable_postgres
class IntegrationRunnerTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.addClassCleanup(cls._cleanup)
        cls._reset_schema()

    @classmethod
    def _cleanup(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=RUNNER_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    @classmethod
    def _reset_schema(cls):
        Base.metadata.drop_all(cls.engine, tables=RUNNER_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=RUNNER_TABLES, checkfirst=False)

    def setUp(self):
        self._reset_schema()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self._job_sequence = 0

    def _seed_work(
        self,
        *,
        resource: ResourceType = ResourceType.ORDERS,
        access_expires_at: datetime | None = NOW + timedelta(hours=1),
        child_connections: int = 1,
        now: datetime = NOW,
    ) -> SeededWork:
        with self.Session.begin() as db:
            authorization = IntegrationAuthorization(
                provider=Provider.DOUDIAN,
                external_subject_id="runner-subject",
                scopes=["orders.read", "products.read"],
                access_token_ciphertext=encrypt_credential(
                    "old-access-token-1111",
                    master_key=MASTER_KEY,
                    purpose=CredentialPurpose.ACCESS_TOKEN,
                ),
                access_token_tail="1111",
                refresh_token_ciphertext=encrypt_credential(
                    "old-refresh-token-2222",
                    master_key=MASTER_KEY,
                    purpose=CredentialPurpose.REFRESH_TOKEN,
                ),
                refresh_token_tail="2222",
                access_expires_at=access_expires_at,
                refresh_expires_at=NOW + timedelta(days=10),
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
            db.add(authorization)
            db.flush()
            connections = []
            for index in range(child_connections):
                connection = IntegrationConnection(
                    authorization_id=authorization.id,
                    provider=Provider.DOUDIAN,
                    connection_type=ConnectionType.SHOP,
                    external_account_id=f"runner-shop-{index + 1}",
                    display_name=f"Runner Shop {index + 1}",
                    status=ConnectionStatus.ACTIVE,
                    capability_report={
                        "resources": {
                            resource.value: {
                                "available": True,
                                "reason": "verified",
                            }
                        }
                    },
                    created_at=NOW,
                    updated_at=NOW,
                )
                db.add(connection)
                db.flush()
                connections.append(connection)
            checkpoint = IntegrationSyncCheckpoint(
                connection_id=connections[0].id,
                resource_type=resource,
                window_start=NOW - timedelta(days=1),
                window_end=NOW,
                status=CheckpointStatus.RUNNING,
                attempts=0,
                lease_owner=OWNER,
                lease_expires_at=now + timedelta(hours=1),
                heartbeat_at=now,
                created_at=NOW,
                updated_at=now,
            )
            db.add(checkpoint)
            db.flush()
            job = self._new_running_job(
                db,
                connection_id=connections[0].id,
                checkpoint_id=checkpoint.id,
                resource=resource,
                now=now,
            )
            return SeededWork(
                authorization_id=authorization.id,
                connection_ids=tuple(item.id for item in connections),
                checkpoint_id=checkpoint.id,
                job_id=job.id,
                resource=resource,
            )

    def _new_running_job(
        self,
        db,
        *,
        connection_id: int,
        checkpoint_id: int,
        resource: ResourceType,
        now: datetime,
    ) -> IntegrationJob:
        self._job_sequence += 1
        job = IntegrationJob(
            job_type=JobType.SYNC_RESOURCE,
            dedupe_key=hashlib.sha256(
                f"runner-job-{self._job_sequence}".encode("ascii")
            ).hexdigest(),
            payload={
                "connection_id": connection_id,
                "checkpoint_id": checkpoint_id,
                "resource_type": resource.value,
                "window_start": (NOW - timedelta(days=1)).isoformat(),
                "window_end": NOW.isoformat(),
            },
            priority=0,
            status=JobStatus.RUNNING,
            available_at=now,
            attempts=1,
            max_attempts=6,
            lease_owner=OWNER,
            lease_expires_at=now + timedelta(hours=1),
            heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()
        return job

    def _order_record(
        self,
        external_id: str,
        *,
        payload_external_id: object | None = None,
        platform_updated_at: datetime = NOW,
    ) -> NormalizedRecord:
        return NormalizedRecord(
            resource=ResourceType.ORDERS,
            external_id=external_id,
            platform_updated_at=platform_updated_at,
            payload={
                "external_order_id": (
                    external_id
                    if payload_external_id is None
                    else payload_external_id
                ),
                "external_shop_id": "runner-shop-1",
                "normalized_status": OrderStatus.PAID.value,
                "raw_status": "WAIT_SEND",
                "buyer_digest": "a" * 64,
                "province": "Zhejiang",
                "city": "Hangzhou",
                "currency": "CNY",
                "order_amount": "100.00",
                "paid_amount": "90.00",
                "discount_amount": "10.00",
                "shipping_amount": "0.00",
                "created_at": NOW - timedelta(hours=2),
                "paid_at": NOW - timedelta(hours=1),
                "shipped_at": None,
                "completed_at": None,
            },
            sanitized_source_payload={
                "source_code": "safe",
                "order_id": external_id,
            },
        )

    def _product_record(self, external_id: str) -> NormalizedRecord:
        return NormalizedRecord(
            resource=ResourceType.PRODUCTS,
            external_id=external_id,
            platform_updated_at=NOW,
            payload={
                "external_product_id": external_id,
                "external_shop_id": "runner-shop-1",
                "title": "Runner product",
                "normalized_status": ProductStatus.ON_SALE.value,
                "raw_status": "SELLING",
                "category": "cake",
                "price": "19.90",
                "currency": "CNY",
            },
            sanitized_source_payload={
                "source_code": "safe",
                "product_id": external_id,
            },
        )

    def _page(
        self,
        *records: NormalizedRecord,
        next_cursor: str | None = None,
        has_more: bool = False,
        watermark: datetime | None = NOW,
    ) -> FetchPage:
        return FetchPage(
            items=tuple(records),
            next_cursor=next_cursor,
            has_more=has_more,
            request_id="runner-request-1",
            rate_limit_hint=None,
            watermark=watermark,
        )

    async def _run(
        self,
        seeded: SeededWork,
        connector: FakeConnector,
        *,
        now: datetime = NOW,
        source: SyncSource = SyncSource.SCHEDULED,
        sleep=None,
        uniform=None,
        job_id: int | None = None,
    ) -> RunnerResult:
        async def no_sleep(_seconds: float) -> None:
            return None

        return await run_sync_pages(
            self.Session,
            connector=connector,
            job_id=seeded.job_id if job_id is None else job_id,
            checkpoint_id=seeded.checkpoint_id,
            owner=OWNER,
            source=source,
            config=RunnerConfig(
                archive_dir=Path(self.temp_dir.name),
                master_key=MASTER_KEY,
                quarantine_hmac_key=QUARANTINE_KEY,
                lease_duration=timedelta(minutes=20),
                refresh_lease_duration=timedelta(minutes=5),
                max_fetch_attempts=6,
            ),
            clock=lambda: now,
            sleep=no_sleep if sleep is None else sleep,
            uniform=(lambda _start, end: end) if uniform is None else uniform,
        )

    async def test_two_pages_commit_independently_and_finish_successfully(self):
        seeded = self._seed_work()
        first_watermark = NOW - timedelta(minutes=1)
        observed_first_commit = []

        def probe(call_number, cursor, window):
            if call_number != 2:
                return
            with self.Session() as db:
                checkpoint = db.get(
                    IntegrationSyncCheckpoint,
                    seeded.checkpoint_id,
                )
                observed_first_commit.append(
                    (
                        cursor,
                        checkpoint.cursor,
                        checkpoint.watermark_at,
                        db.scalar(
                            select(func.count()).select_from(
                                IntegrationArchiveManifest
                            )
                        ),
                        db.scalar(
                            select(func.count()).select_from(CommerceOrder)
                        ),
                    )
                )

        connector = FakeConnector(
            (
                self._page(
                    self._order_record("order-page-1"),
                    next_cursor="cursor-page-2",
                    has_more=True,
                    watermark=first_watermark,
                ),
                self._page(
                    self._order_record("order-page-2"),
                    watermark=NOW,
                ),
            ),
            fetch_probe=probe,
        )
        result = await self._run(seeded, connector)

        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(result.pages_committed, 2)
        self.assertEqual(result.records_written, 2)
        self.assertEqual(
            observed_first_commit,
            [("cursor-page-2", "cursor-page-2", first_watermark, 1, 1)],
        )
        self.assertTrue(all(isinstance(item, TimeWindow) for item in connector.windows))
        with self.Session() as db:
            run = db.get(IntegrationSyncRun, result.run_id)
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            job = db.get(IntegrationJob, seeded.job_id)
            self.assertEqual(run.status, SyncStatus.SUCCEEDED)
            self.assertEqual(run.progress, 1)
            self.assertEqual(run.records_read, 2)
            self.assertEqual(checkpoint.status, CheckpointStatus.COMPLETE)
            self.assertIsNone(checkpoint.cursor)
            self.assertEqual(checkpoint.watermark_at, NOW)
            self.assertIsNone(checkpoint.lease_owner)
            self.assertEqual(job.status, JobStatus.SUCCEEDED)
            manifests = db.scalars(
                select(IntegrationArchiveManifest).order_by(
                    IntegrationArchiveManifest.page_number
                )
            ).all()
            self.assertEqual([item.page_number for item in manifests], [0, 1])
            self.assertEqual([item.record_count for item in manifests], [1, 1])
        archived_files = list(Path(self.temp_dir.name).rglob("*.jsonl.gz.aes"))
        self.assertEqual(len(archived_files), 2)

    async def test_crash_before_commit_preserves_cursor_and_refetches_page(self):
        seeded = self._seed_work()
        first_connector = FakeConnector(
            (self._page(self._order_record("order-crash")),)
        )
        with patch(
            "integrations.sync.runner._commit_page",
            side_effect=SimulatedProcessCrash,
        ):
            with self.assertRaises(SimulatedProcessCrash):
                await self._run(seeded, first_connector)

        with self.Session() as db:
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            run = db.scalar(select(IntegrationSyncRun))
            self.assertIsNone(checkpoint.cursor)
            self.assertIsNone(checkpoint.watermark_at)
            self.assertEqual(run.status, SyncStatus.RUNNING)
            self.assertEqual(run.records_read, 0)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(CommerceOrder)),
                0,
            )
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(IntegrationArchiveManifest)
                ),
                0,
            )
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.aes")), [])

        retry_connector = FakeConnector(
            (self._page(self._order_record("order-crash")),)
        )
        result = await self._run(seeded, retry_connector)
        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(retry_connector.cursors, [None])
        with self.Session() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(CommerceOrder)),
                1,
            )

    async def test_rate_limit_honors_later_retry_after(self):
        seeded = self._seed_work()
        delays = []

        async def sleep(seconds):
            delays.append(seconds)

        connector = FakeConnector(
            (
                RateLimited(status_code=429, retry_after_seconds=37),
                self._page(self._order_record("order-rate-limit")),
            )
        )
        result = await self._run(seeded, connector, sleep=sleep)
        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(connector.fetch_calls, 2)
        self.assertEqual(delays, [37])

    async def test_network_and_5xx_use_bounded_full_jitter(self):
        seeded = self._seed_work()
        delays = []

        async def sleep(seconds):
            delays.append(seconds)

        connector = FakeConnector(
            (
                TransientPlatformError(status_code=None),
                TransientPlatformError(status_code=503),
                self._page(self._order_record("order-transient")),
            )
        )
        result = await self._run(seeded, connector, sleep=sleep)
        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(connector.fetch_calls, 3)
        self.assertEqual(delays, [5, 10])
        self.assertTrue(all(delay <= 900 for delay in delays))

    async def test_transient_failures_stop_after_six_and_degrade_connection(self):
        seeded = self._seed_work()
        delays = []

        async def sleep(seconds):
            delays.append(seconds)

        connector = FakeConnector(
            tuple(TransientPlatformError(status_code=503) for _ in range(6))
        )
        result = await self._run(seeded, connector, sleep=sleep)
        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertEqual(connector.fetch_calls, 6)
        self.assertEqual(delays, [5, 10, 20, 40, 80])
        with self.Session() as db:
            run = db.get(IntegrationSyncRun, result.run_id)
            job = db.get(IntegrationJob, seeded.job_id)
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            connection = db.get(IntegrationConnection, seeded.connection_id)
            self.assertEqual(run.status, SyncStatus.FAILED)
            self.assertEqual(
                run.failure_code,
                JobErrorCode.TRANSIENT_PROVIDER_ERROR.value,
            )
            self.assertEqual(job.status, JobStatus.FAILED)
            self.assertEqual(
                job.last_error_summary,
                JobErrorSummary.TRANSIENT_PROVIDER_FAILURE.value,
            )
            self.assertEqual(checkpoint.status, CheckpointStatus.FAILED)
            self.assertEqual(connection.status, ConnectionStatus.DEGRADED)

    async def test_401_refreshes_once_and_atomically_rotates_all_token_fields(self):
        seeded = self._seed_work()
        refreshed = TokenBundle(
            access_token="rotated-access-token-3333",
            refresh_token="rotated-refresh-token-4444",
            access_expires_at=NOW + timedelta(hours=2),
            refresh_expires_at=NOW + timedelta(days=20),
            scopes=("orders.read", "products.read"),
            external_subject_id="runner-subject",
        )
        connector = FakeConnector(
            (
                AuthenticationFailed(status_code=401),
                self._page(self._order_record("order-refreshed")),
            ),
            refreshed_tokens=refreshed,
        )
        with self.assertNoLogs("integrations.sync.runner", level="DEBUG"):
            result = await self._run(seeded, connector)

        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(connector.fetch_calls, 2)
        self.assertEqual(connector.refresh_calls, 1)
        self.assertEqual(
            connector.access_tokens,
            ["old-access-token-1111", "rotated-access-token-3333"],
        )
        with self.Session() as db:
            authorization = db.get(
                IntegrationAuthorization,
                seeded.authorization_id,
            )
            job = db.get(IntegrationJob, seeded.job_id)
            self.assertEqual(authorization.access_token_tail, "3333")
            self.assertEqual(authorization.refresh_token_tail, "4444")
            self.assertEqual(authorization.access_expires_at, refreshed.access_expires_at)
            self.assertEqual(
                authorization.refresh_expires_at,
                refreshed.refresh_expires_at,
            )
            self.assertIsNone(authorization.refresh_lease_owner)
            self.assertIsNone(authorization.refresh_lease_expires_at)
            self.assertEqual(
                decrypt_credential(
                    authorization.access_token_ciphertext,
                    master_key=MASTER_KEY,
                    purpose=CredentialPurpose.ACCESS_TOKEN,
                ),
                refreshed.access_token,
            )
            self.assertEqual(
                decrypt_credential(
                    authorization.refresh_token_ciphertext,
                    master_key=MASTER_KEY,
                    purpose=CredentialPurpose.REFRESH_TOKEN,
                ),
                refreshed.refresh_token,
            )
            rendered_payload = json.dumps(job.payload)
            for secret in (
                refreshed.access_token,
                refreshed.refresh_token,
                "old-access-token-1111",
                "old-refresh-token-2222",
            ):
                self.assertNotIn(secret, rendered_payload)

    async def test_connector_refresh_safety_window_triggers_proactive_refresh(self):
        seeded = self._seed_work(
            access_expires_at=NOW + timedelta(seconds=30)
        )
        refreshed = TokenBundle(
            access_token="proactive-access-5555",
            refresh_token="proactive-refresh-6666",
            access_expires_at=NOW + timedelta(hours=3),
            refresh_expires_at=None,
            scopes=("orders.read",),
            external_subject_id="runner-subject",
        )
        connector = FakeConnector(
            (self._page(self._order_record("order-proactive")),),
            refreshed_tokens=refreshed,
            refresh_safety_window=timedelta(minutes=2),
        )
        result = await self._run(seeded, connector)
        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(connector.refresh_calls, 1)
        self.assertEqual(connector.access_tokens, [refreshed.access_token])

    async def test_refresh_network_and_5xx_use_same_bounded_full_jitter(self):
        seeded = self._seed_work()
        delays = []

        async def sleep(seconds):
            delays.append(seconds)

        refreshed = TokenBundle(
            access_token="retry-refresh-access-7777",
            refresh_token="retry-refresh-token-8888",
            access_expires_at=NOW + timedelta(hours=2),
            refresh_expires_at=NOW + timedelta(days=2),
            scopes=("orders.read",),
            external_subject_id="runner-subject",
        )
        connector = FakeConnector(
            (
                AuthenticationFailed(status_code=401),
                self._page(self._order_record("order-refresh-retry")),
            ),
            refresh_outcomes=(
                TransientPlatformError(status_code=None),
                TransientPlatformError(status_code=503),
                refreshed,
            ),
        )

        result = await self._run(seeded, connector, sleep=sleep)

        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(connector.refresh_calls, 3)
        self.assertEqual(delays, [5, 10])
        self.assertEqual(connector.access_tokens[-1], refreshed.access_token)

    async def test_refresh_transient_failures_stop_after_six_and_release_lease(self):
        seeded = self._seed_work(access_expires_at=NOW)
        delays = []

        async def sleep(seconds):
            delays.append(seconds)

        connector = FakeConnector(
            (),
            refresh_outcomes=tuple(
                TransientPlatformError(status_code=503) for _ in range(6)
            ),
        )

        result = await self._run(seeded, connector, sleep=sleep)

        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertEqual(connector.refresh_calls, 6)
        self.assertEqual(delays, [5, 10, 20, 40, 80])
        with self.Session() as db:
            authorization = db.get(
                IntegrationAuthorization,
                seeded.authorization_id,
            )
            connection = db.get(IntegrationConnection, seeded.connection_id)
            job = db.get(IntegrationJob, seeded.job_id)
            self.assertIsNone(authorization.refresh_lease_owner)
            self.assertIsNone(authorization.refresh_lease_expires_at)
            self.assertEqual(connection.status, ConnectionStatus.DEGRADED)
            self.assertEqual(job.status, JobStatus.FAILED)
            self.assertEqual(
                job.last_error_code,
                JobErrorCode.TRANSIENT_PROVIDER_ERROR.value,
            )

    async def test_second_auth_failure_clears_tokens_and_marks_all_children(self):
        seeded = self._seed_work(child_connections=2)
        refreshed = TokenBundle(
            access_token="rejected-access-7777",
            refresh_token="rejected-refresh-8888",
            access_expires_at=NOW + timedelta(hours=1),
            refresh_expires_at=NOW + timedelta(days=1),
            scopes=("orders.read",),
            external_subject_id="runner-subject",
        )
        connector = FakeConnector(
            (
                AuthenticationFailed(status_code=401),
                AuthenticationFailed(status_code=401),
            ),
            refreshed_tokens=refreshed,
        )
        result = await self._run(seeded, connector)
        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertEqual(connector.refresh_calls, 1)
        self.assertEqual(connector.fetch_calls, 2)
        with self.Session() as db:
            authorization = db.get(
                IntegrationAuthorization,
                seeded.authorization_id,
            )
            connections = db.scalars(
                select(IntegrationConnection).order_by(IntegrationConnection.id)
            ).all()
            job = db.get(IntegrationJob, seeded.job_id)
            self.assertEqual(
                authorization.status,
                AuthorizationStatus.REAUTHORIZATION_REQUIRED,
            )
            self.assertEqual(authorization.access_token_ciphertext, "")
            self.assertEqual(authorization.access_token_tail, "")
            self.assertIsNone(authorization.refresh_token_ciphertext)
            self.assertIsNone(authorization.refresh_token_tail)
            self.assertIsNone(authorization.access_expires_at)
            self.assertIsNone(authorization.refresh_expires_at)
            self.assertTrue(
                all(
                    item.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
                    for item in connections
                )
            )
            self.assertEqual(
                job.last_error_code,
                JobErrorCode.AUTHORIZATION_REQUIRED.value,
            )

    def test_authorization_refresh_lease_is_shared_by_all_child_connections(self):
        seeded = self._seed_work(child_connections=2)
        barrier = Barrier(2)

        def acquire(index):
            with self.Session.begin() as db:
                barrier.wait(timeout=10)
                return acquire_authorization_refresh_lease(
                    db,
                    authorization_id=seeded.authorization_id,
                    owner=f"refresh-worker-{index}",
                    now=NOW,
                    lease_duration=timedelta(minutes=5),
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            acquired = list(executor.map(acquire, (1, 2)))
        self.assertEqual(sum(acquired), 1)

    def test_stale_refresh_generation_cannot_take_a_new_lease(self):
        seeded = self._seed_work(child_connections=2)
        refreshed = TokenBundle(
            access_token="generation-access-9999",
            refresh_token="generation-refresh-0000",
            access_expires_at=NOW + timedelta(hours=2),
            refresh_expires_at=NOW + timedelta(days=2),
            scopes=("orders.read",),
            external_subject_id="runner-subject",
        )
        with self.Session.begin() as db:
            self.assertTrue(
                acquire_authorization_refresh_lease(
                    db,
                    authorization_id=seeded.authorization_id,
                    owner="generation-winner",
                    now=NOW,
                    lease_duration=timedelta(minutes=5),
                    expected_last_refreshed_at=None,
                )
            )
        with self.Session.begin() as db:
            self.assertTrue(
                replace_refreshed_authorization_tokens(
                    db,
                    authorization_id=seeded.authorization_id,
                    owner="generation-winner",
                    tokens=refreshed,
                    master_key=MASTER_KEY,
                    now=NOW + timedelta(seconds=1),
                )
            )
        with self.Session.begin() as db:
            self.assertFalse(
                acquire_authorization_refresh_lease(
                    db,
                    authorization_id=seeded.authorization_id,
                    owner="generation-loser",
                    now=NOW + timedelta(seconds=2),
                    lease_duration=timedelta(minutes=5),
                    expected_last_refreshed_at=None,
                )
            )

    async def test_permission_denial_is_not_retried_and_records_safe_reason(self):
        seeded = self._seed_work()
        delays = []

        async def sleep(seconds):
            delays.append(seconds)

        connector = FakeConnector((PermissionDenied(status_code=403),))
        result = await self._run(seeded, connector, sleep=sleep)
        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertEqual(connector.fetch_calls, 1)
        self.assertEqual(delays, [])
        with self.Session() as db:
            connection = db.get(IntegrationConnection, seeded.connection_id)
            authorization = db.get(
                IntegrationAuthorization,
                seeded.authorization_id,
            )
            job = db.get(IntegrationJob, seeded.job_id)
            self.assertEqual(
                connection.status,
                ConnectionStatus.PERMISSION_LIMITED,
            )
            self.assertEqual(
                connection.capability_report["resources"]["orders"],
                {"available": False, "reason": "permission_denied"},
            )
            self.assertEqual(authorization.status, AuthorizationStatus.ACTIVE)
            self.assertEqual(
                job.last_error_code,
                JobErrorCode.PERMISSION_DENIED.value,
            )

    async def test_invalid_sibling_yields_partial_success_and_keeps_valid_row(self):
        seeded = self._seed_work()
        invalid = self._order_record(
            "invalid-order",
            payload_external_id=123,
        )
        valid = self._order_record("valid-order")
        connector = FakeConnector((self._page(invalid, valid),))
        result = await self._run(seeded, connector)
        self.assertEqual(result.status, SyncStatus.PARTIAL_SUCCESS)
        self.assertEqual(result.records_written, 1)
        self.assertEqual(result.records_quarantined, 1)
        with self.Session() as db:
            run = db.get(IntegrationSyncRun, result.run_id)
            job = db.get(IntegrationJob, seeded.job_id)
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            manifest = db.scalar(select(IntegrationArchiveManifest))
            self.assertEqual(run.status, SyncStatus.PARTIAL_SUCCESS)
            self.assertEqual(job.status, JobStatus.SUCCEEDED)
            self.assertEqual(checkpoint.status, CheckpointStatus.COMPLETE)
            self.assertEqual(manifest.record_count, 2)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(CommerceOrder)),
                1,
            )
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(IntegrationSyncError)
                ),
                1,
            )

    async def test_snapshot_cycle_keeps_logical_window_but_fetches_with_none(self):
        seeded = self._seed_work(resource=ResourceType.PRODUCTS)
        connector = FakeConnector(
            (self._page(self._product_record("product-snapshot")),)
        )
        result = await self._run(seeded, connector)
        self.assertEqual(result.status, SyncStatus.SUCCEEDED)
        self.assertEqual(connector.windows, [None])
        with self.Session() as db:
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            self.assertEqual(checkpoint.window_start, NOW - timedelta(days=1))
            self.assertEqual(checkpoint.window_end, NOW)

    async def test_scheduler_correction_cycle_creates_a_new_run_for_same_checkpoint(self):
        seeded = self._seed_work()
        first = await self._run(
            seeded,
            FakeConnector((self._page(self._order_record("order-cycle-1")),)),
        )
        second_now = NOW + timedelta(minutes=2)
        with self.Session.begin() as db:
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            checkpoint.status = CheckpointStatus.RUNNING
            checkpoint.cursor = None
            checkpoint.watermark_at = None
            checkpoint.lease_owner = OWNER
            checkpoint.lease_expires_at = second_now + timedelta(hours=1)
            checkpoint.heartbeat_at = second_now
            checkpoint.updated_at = second_now
            second_job = self._new_running_job(
                db,
                connection_id=seeded.connection_id,
                checkpoint_id=seeded.checkpoint_id,
                resource=seeded.resource,
                now=second_now,
            )

        second = await self._run(
            seeded,
            FakeConnector((self._page(self._order_record("order-cycle-2")),)),
            now=second_now,
            job_id=second_job.id,
        )
        self.assertNotEqual(first.run_id, second.run_id)
        with self.Session() as db:
            runs = db.scalars(
                select(IntegrationSyncRun).order_by(IntegrationSyncRun.id)
            ).all()
            manifests = db.scalars(
                select(IntegrationArchiveManifest).order_by(
                    IntegrationArchiveManifest.run_id
                )
            ).all()
            self.assertEqual(len(runs), 2)
            self.assertTrue(all(item.parent_run_id is None for item in runs))
            self.assertEqual([item.page_number for item in manifests], [0, 0])

    async def test_manual_retry_creates_child_run_linked_to_failed_run(self):
        seeded = self._seed_work()
        failed = await self._run(
            seeded,
            FakeConnector(
                tuple(TransientPlatformError(status_code=503) for _ in range(6))
            ),
        )
        retry_now = NOW + timedelta(minutes=2)
        with self.Session.begin() as db:
            checkpoint = db.get(IntegrationSyncCheckpoint, seeded.checkpoint_id)
            checkpoint.status = CheckpointStatus.RUNNING
            checkpoint.lease_owner = OWNER
            checkpoint.lease_expires_at = retry_now + timedelta(hours=1)
            checkpoint.heartbeat_at = retry_now
            checkpoint.updated_at = retry_now
            retry_job = self._new_running_job(
                db,
                connection_id=seeded.connection_id,
                checkpoint_id=seeded.checkpoint_id,
                resource=seeded.resource,
                now=retry_now,
            )
        succeeded = await self._run(
            seeded,
            FakeConnector((self._page(self._order_record("order-manual-retry")),)),
            now=retry_now,
            source=SyncSource.MANUAL,
            job_id=retry_job.id,
        )
        with self.Session() as db:
            child = db.get(IntegrationSyncRun, succeeded.run_id)
            self.assertEqual(child.parent_run_id, failed.run_id)
            self.assertEqual(child.source, SyncSource.MANUAL)
            self.assertEqual(child.status, SyncStatus.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
