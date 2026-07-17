import asyncio
import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import database
from commerce_models import CommerceOrder
from database import Base
from integration_models import (
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationExportJob,
    IntegrationJob,
    IntegrationSyncCheckpoint,
    IntegrationWorkerHeartbeat,
)
from integrations.settings import IntegrationSettings
from integrations.purge import PurgeFileError
from integrations.sync.queue import enqueue_job
from integrations.sync.worker import (
    ClaimedJob,
    DEFAULT_WORKER_CONCURRENCY,
    ConnectorUnavailableError,
    IntegrationWorker,
    WorkerConfig,
    WorkerReadinessError,
    RetryableMaintenanceError,
    build_default_job_handler,
    default_job_handler,
    expire_export_maintenance,
    tick_scheduler_maintenance,
    parse_worker_enabled,
    release_worker_leases,
    stale_worker_ids,
    upsert_worker_heartbeat,
    validate_worker_readiness,
)
from integrations.types import ExportStatus, JobStatus, JobType, ResourceType, utc_now
from tests.test_integration_models import _require_disposable_postgres_url


UTC = timezone.utc
WORKER_TABLES = (
    IntegrationAuthorization.__table__,
    IntegrationConnection.__table__,
    CommerceOrder.__table__,
    IntegrationExportJob.__table__,
    IntegrationJob.__table__,
    IntegrationSyncCheckpoint.__table__,
    IntegrationWorkerHeartbeat.__table__,
)


def _ready_settings(archive_dir: Path, *, concurrency: int = 4) -> IntegrationSettings:
    return IntegrationSettings(
        master_key=b"m" * 32,
        internal_base_url="http://127.0.0.1:8765",
        public_base_url="https://callbacks.test.invalid",
        archive_dir=archive_dir,
        trusted_proxy_networks=(),
        worker_concurrency=concurrency,
        credential_ready=True,
        errors=(),
    )


def _load_worker_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "integration_worker.py"
    spec = importlib.util.spec_from_file_location("integration_worker_script_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkerConfigurationTests(unittest.TestCase):
    def test_worker_is_disabled_by_default_and_ambiguous_values_fail_closed(self):
        self.assertFalse(parse_worker_enabled({}))
        self.assertFalse(parse_worker_enabled({"FACAI_INTEGRATION_WORKER_ENABLED": "0"}))
        self.assertTrue(parse_worker_enabled({"FACAI_INTEGRATION_WORKER_ENABLED": "1"}))
        for value in ("", "true", "01", " 1", "1 ", "yes"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_worker_enabled({"FACAI_INTEGRATION_WORKER_ENABLED": value})

    def test_worker_defaults_match_the_operational_contract(self):
        config = WorkerConfig(enabled=True)

        self.assertEqual(DEFAULT_WORKER_CONCURRENCY, 4)
        self.assertEqual(config.concurrency, 4)
        self.assertEqual(config.heartbeat_interval, 10.0)
        self.assertEqual(config.shutdown_timeout, 30.0)

    def test_readiness_requires_credentials_postgres_schema_and_writable_archive(self):
        postgres_engine = database.create_database_engine(
            _require_disposable_postgres_url()
        )
        sqlite_engine = database.create_database_engine("sqlite:///:memory:")
        self.addCleanup(postgres_engine.dispose)
        self.addCleanup(sqlite_engine.dispose)
        schema_validator = Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = Path(temp_dir) / "archive"
            ready = _ready_settings(archive_dir)
            validate_worker_readiness(
                postgres_engine,
                ready,
                schema_validator=schema_validator,
            )

            self.assertTrue(archive_dir.is_dir())
            self.assertEqual(list(archive_dir.iterdir()), [])
            schema_validator.assert_called_once_with(postgres_engine)

            with self.assertRaisesRegex(WorkerReadinessError, "PostgreSQL"):
                validate_worker_readiness(
                    sqlite_engine,
                    ready,
                    schema_validator=schema_validator,
                )

            incomplete = IntegrationSettings(
                master_key=None,
                internal_base_url=None,
                public_base_url=None,
                archive_dir=None,
                trusted_proxy_networks=(),
                worker_concurrency=4,
                credential_ready=False,
                errors=("FACAI_INTEGRATIONS_MASTER_KEY",),
            )
            with self.assertRaisesRegex(WorkerReadinessError, "security") as failure:
                validate_worker_readiness(
                    postgres_engine,
                    incomplete,
                    schema_validator=schema_validator,
                )
            self.assertNotIn("m" * 32, str(failure.exception))

    def test_default_handler_reports_typed_unavailable_without_fabricating_data(self):
        async def exercise():
            with self.assertRaises(ConnectorUnavailableError):
                await default_job_handler(
                    Mock(id=1, job_type=JobType.SYNC_RESOURCE, payload={})
                )

        asyncio.run(exercise())

    def test_scheduler_tick_queries_expired_manifests_and_delegates_dedupe(self):
        scalar_result = Mock()
        scalar_result.all.return_value = [91, 92]
        db = Mock()
        db.scalars.return_value = scalar_result
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(return_value=False)
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        now = datetime(2026, 7, 13, 2, 0, tzinfo=UTC)

        with (
            patch("integrations.sync.scheduler.due_jobs", return_value=[]) as due_jobs,
            patch("integrations.sync.scheduler.enqueue_scheduled_units") as enqueue,
        ):
            count = tick_scheduler_maintenance(session_factory, now=now)

        self.assertEqual(count, 0)
        self.assertEqual(due_jobs.call_args.args[:3], (now, (), {}))
        self.assertEqual(
            due_jobs.call_args.kwargs["expired_archive_manifest_ids"],
            [91, 92],
        )
        enqueue.assert_called_once_with(db, [])

    def test_local_export_and_archive_cleanup_are_real_but_connectors_remain_unavailable(self):
        db = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(return_value=False)
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        handler = build_default_job_handler(
            session_factory,
            archive_dir=Path(tempfile.gettempdir()) / "worker-archive-test",
        )
        cleanup_job = ClaimedJob(
            id=1,
            job_type=JobType.ARCHIVE_CLEANUP,
            payload={"archive_manifest_id": 91},
        )
        sync_job = ClaimedJob(
            id=2,
            job_type=JobType.SYNC_RESOURCE,
            payload={},
        )
        export_job = ClaimedJob(
            id=3,
            job_type=JobType.EXPORT,
            payload={"export_job_id": 27},
        )
        purge_job = ClaimedJob(
            id=4,
            job_type=JobType.PURGE_CONNECTION,
            payload={"connection_id": 19},
        )
        terminal_purge_job = ClaimedJob(
            id=4,
            job_type=JobType.PURGE_CONNECTION,
            payload={"connection_id": 19},
            attempts=5,
            max_attempts=6,
        )

        async def exercise():
            with patch(
                "integrations.sync.worker.cleanup_expired_archives",
                return_value=Mock(retry_count=0),
            ) as cleanup:
                await handler(cleanup_job)
            self.assertEqual(cleanup.call_args.kwargs["archive_dir"], Path(tempfile.gettempdir()) / "worker-archive-test")
            with self.assertRaises(ConnectorUnavailableError):
                await handler(sync_job)
            with (
                patch(
                    "integrations.sync.worker.cleanup_expired_archives",
                    return_value=Mock(retry_count=1),
                ),
                self.assertRaises(RetryableMaintenanceError),
            ):
                await handler(cleanup_job)
            with patch(
                "integrations.exports.generate_export_job",
                return_value=Mock(status=ExportStatus.READY),
            ) as generate_export:
                await handler(export_job)
            self.assertEqual(generate_export.call_args.kwargs["export_job_id"], 27)
            with (
                patch(
                    "integrations.exports.generate_export_job",
                    return_value=Mock(status=ExportStatus.FAILED),
                ),
                self.assertRaises(RetryableMaintenanceError),
            ):
                await handler(export_job)
            with patch(
                "integrations.purge.purge_connection_data",
                return_value=Mock(connection_deleted=True),
            ) as purge_connection:
                await handler(purge_job)
            self.assertEqual(
                purge_connection.call_args.kwargs,
                {
                    "connection_id": 19,
                    "archive_dir": Path(tempfile.gettempdir())
                    / "worker-archive-test",
                    "current_job_id": 4,
                },
            )
            with (
                patch(
                    "integrations.purge.purge_connection_data",
                    side_effect=PurgeFileError("test closed failure"),
                ),
                self.assertRaises(RetryableMaintenanceError),
            ):
                await handler(purge_job)
            with (
                patch(
                    "integrations.purge.purge_connection_data",
                    side_effect=RuntimeError("database deadlock detail"),
                ),
                self.assertRaisesRegex(
                    RetryableMaintenanceError,
                    "connection purge requires retry",
                ) as retry,
            ):
                await handler(purge_job)
            self.assertNotIn("deadlock", str(retry.exception))
            with (
                patch(
                    "integrations.purge.purge_connection_data",
                    side_effect=RuntimeError("database commit detail"),
                ),
                self.assertRaisesRegex(RuntimeError, "connection purge failed") as final,
            ):
                await handler(terminal_purge_job)
            self.assertNotIn("commit detail", str(final.exception))

        asyncio.run(exercise())

    def test_export_retry_stays_nonterminal_until_the_queue_final_attempt(self):
        db = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(return_value=False)
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        handler = build_default_job_handler(
            session_factory,
            archive_dir=Path(tempfile.gettempdir()) / "worker-export-retry-test",
        )
        retry_job = ClaimedJob(
            id=10,
            job_type=JobType.EXPORT,
            payload={"export_job_id": 30},
            attempts=0,
            max_attempts=2,
        )
        final_job = ClaimedJob(
            id=10,
            job_type=JobType.EXPORT,
            payload={"export_job_id": 30},
            attempts=1,
            max_attempts=2,
        )

        async def exercise():
            with patch(
                "integrations.exports.generate_export_job",
                return_value=Mock(status=ExportStatus.RUNNING, relative_file_path=None),
            ) as generate:
                with self.assertRaises(RetryableMaintenanceError):
                    await handler(retry_job)
                self.assertFalse(generate.call_args.kwargs["terminal_failure"])
            with patch(
                "integrations.exports.generate_export_job",
                return_value=Mock(status=ExportStatus.FAILED, relative_file_path=None),
            ) as generate:
                with self.assertRaisesRegex(RuntimeError, "export generation failed"):
                    await handler(final_job)
                self.assertTrue(generate.call_args.kwargs["terminal_failure"])

        asyncio.run(exercise())

    def test_ready_export_commit_failure_never_deletes_an_existing_artifact(self):
        db = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(side_effect=RuntimeError("commit failed"))
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        verification_db = Mock()
        verification_db.scalar.return_value = None
        verification_context = Mock()
        verification_context.__enter__ = Mock(return_value=verification_db)
        verification_context.__exit__ = Mock(return_value=False)
        session_factory.return_value = verification_context

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = Path(temp_dir)
            export_dir = archive_dir / "exports"
            export_dir.mkdir()
            relative_path = f"exports/{uuid4()}.csv"
            existing_file = archive_dir / relative_path
            existing_file.write_text("valid export", encoding="utf-8")
            handler = build_default_job_handler(
                session_factory,
                archive_dir=archive_dir,
            )
            job = ClaimedJob(
                id=20,
                job_type=JobType.EXPORT,
                payload={"export_job_id": 40},
            )

            async def exercise():
                with (
                    patch(
                        "integrations.exports.generate_export_job",
                        return_value=Mock(
                            status=ExportStatus.READY,
                            relative_file_path=relative_path,
                        ),
                    ),
                    self.assertRaisesRegex(
                        RetryableMaintenanceError,
                        "export generation requires retry",
                    ),
                ):
                    await handler(job)

            asyncio.run(exercise())
            self.assertTrue(existing_file.is_file())

    def test_new_export_commit_failure_removes_only_the_new_artifact(self):
        db = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(side_effect=RuntimeError("commit failed"))
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        verification_db = Mock()
        verification_db.scalar.return_value = None
        verification_context = Mock()
        verification_context.__enter__ = Mock(return_value=verification_db)
        verification_context.__exit__ = Mock(return_value=False)
        session_factory.return_value = verification_context

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = Path(temp_dir)
            export_dir = archive_dir / "exports"
            export_dir.mkdir()
            relative_path = f"exports/{uuid4()}.csv"
            new_file = archive_dir / relative_path
            handler = build_default_job_handler(
                session_factory,
                archive_dir=archive_dir,
            )
            job = ClaimedJob(
                id=21,
                job_type=JobType.EXPORT,
                payload={"export_job_id": 41},
            )

            def publish(*_args, **kwargs):
                new_file.write_text("new export", encoding="utf-8")
                kwargs["publication"].relative_path = relative_path
                return Mock(
                    status=ExportStatus.READY,
                    relative_file_path=relative_path,
                )

            async def exercise():
                with (
                    patch(
                        "integrations.exports.generate_export_job",
                        side_effect=publish,
                    ),
                    self.assertRaisesRegex(
                        RetryableMaintenanceError,
                        "export generation requires retry",
                    ),
                ):
                    await handler(job)

            asyncio.run(exercise())
            self.assertFalse(new_file.exists())

    def test_terminal_export_commit_failure_closes_a_non_ready_export_job(self):
        generation_db = Mock()
        generation_transaction = Mock()
        generation_transaction.__enter__ = Mock(return_value=generation_db)
        generation_transaction.__exit__ = Mock(
            side_effect=RuntimeError("commit failed")
        )
        recovery_db = Mock()
        export_job = SimpleNamespace(
            status=ExportStatus.RUNNING,
            error_code=None,
            error_summary=None,
            completed_at=None,
        )
        recovery_db.scalar.return_value = export_job
        recovery_transaction = Mock()
        recovery_transaction.__enter__ = Mock(return_value=recovery_db)
        recovery_transaction.__exit__ = Mock(return_value=False)
        session_factory = Mock()
        session_factory.begin.side_effect = (
            generation_transaction,
            recovery_transaction,
        )
        handler = build_default_job_handler(
            session_factory,
            archive_dir=Path(tempfile.gettempdir()) / "worker-export-terminal-test",
        )
        job = ClaimedJob(
            id=22,
            job_type=JobType.EXPORT,
            payload={"export_job_id": 42},
            attempts=1,
            max_attempts=2,
        )

        async def exercise():
            with (
                patch(
                    "integrations.exports.generate_export_job",
                    return_value=Mock(
                        status=ExportStatus.RUNNING,
                        relative_file_path=None,
                    ),
                ),
                self.assertRaisesRegex(RuntimeError, "export generation failed"),
            ):
                await handler(job)

        asyncio.run(exercise())
        self.assertIs(export_job.status, ExportStatus.FAILED)
        self.assertEqual(export_job.error_code, "export_generation_failed")
        self.assertEqual(
            export_job.error_summary,
            "integration export generation failed",
        )
        self.assertIsNotNone(export_job.completed_at)

    def test_ambiguous_commit_keeps_a_new_artifact_when_postgres_reports_ready(self):
        generation_db = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=generation_db)
        transaction.__exit__ = Mock(side_effect=RuntimeError("commit outcome unknown"))
        session_factory = Mock()
        session_factory.begin.return_value = transaction

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = Path(temp_dir)
            export_dir = archive_dir / "exports"
            export_dir.mkdir()
            relative_path = f"exports/{uuid4()}.csv"
            artifact = archive_dir / relative_path
            verification_db = Mock()
            verification_db.scalar.return_value = SimpleNamespace(
                status=ExportStatus.READY,
                relative_file_path=relative_path,
            )
            verification_context = Mock()
            verification_context.__enter__ = Mock(return_value=verification_db)
            verification_context.__exit__ = Mock(return_value=False)
            session_factory.return_value = verification_context
            handler = build_default_job_handler(
                session_factory,
                archive_dir=archive_dir,
            )
            job = ClaimedJob(
                id=23,
                job_type=JobType.EXPORT,
                payload={"export_job_id": 43},
            )

            def publish(*_args, **kwargs):
                artifact.write_text("committed export", encoding="utf-8")
                kwargs["publication"].relative_path = relative_path
                return Mock(
                    status=ExportStatus.READY,
                    relative_file_path=relative_path,
                )

            async def exercise():
                with (
                    patch(
                        "integrations.exports.generate_export_job",
                        side_effect=publish,
                    ),
                    self.assertRaises(RetryableMaintenanceError),
                ):
                    await handler(job)

            asyncio.run(exercise())
            self.assertTrue(artifact.is_file())

    def test_expired_export_files_are_maintained_without_fake_success(self):
        db = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=db)
        transaction.__exit__ = Mock(return_value=False)
        session_factory = Mock()
        session_factory.begin.return_value = transaction
        archive_dir = Path(tempfile.gettempdir()) / "worker-export-expiry-test"
        now = datetime(2026, 7, 13, 2, 0, tzinfo=UTC)

        with patch(
            "integrations.exports.expire_export_files",
            return_value=(2, 0),
        ) as expire:
            expired = expire_export_maintenance(
                session_factory,
                archive_dir=archive_dir,
                now=now,
            )

        self.assertEqual(expired, 2)
        expire.assert_called_once_with(
            db,
            archive_dir=archive_dir,
            now=now,
        )
        with (
            patch(
                "integrations.exports.expire_export_files",
                return_value=(0, 1),
            ),
            self.assertRaises(RetryableMaintenanceError),
        ):
            expire_export_maintenance(
                session_factory,
                archive_dir=archive_dir,
                now=now,
            )


class WorkerCliTests(unittest.TestCase):
    def test_disabled_cli_exits_without_touching_database_readiness(self):
        script = _load_worker_script()

        with (
            patch.object(script, "parse_worker_enabled", return_value=False),
            patch.object(script, "validate_worker_readiness") as readiness,
        ):
            result = script.main(["--once"])

        self.assertEqual(result, 0)
        readiness.assert_not_called()

    def test_enabled_once_installs_signal_handlers_and_drains_exactly_one_cycle(self):
        script = _load_worker_script()
        fake_worker = Mock()
        fake_worker.run = AsyncMock(
            return_value=Mock(
                claimed_jobs=0,
                succeeded_jobs=0,
                failed_jobs=0,
                maintenance_errors=0,
            )
        )
        settings = _ready_settings(Path(tempfile.gettempdir()) / "worker-cli-test")

        with (
            patch.object(script, "parse_worker_enabled", return_value=True),
            patch.object(script, "load_integration_settings", return_value=settings),
            patch.object(script, "validate_worker_readiness") as readiness,
            patch.object(
                script,
                "IntegrationWorker",
                return_value=fake_worker,
            ) as worker_type,
            patch.object(script, "install_signal_handlers") as install_signals,
            patch.object(script, "tick_scheduler_maintenance", return_value=0) as tick,
            patch.object(script, "expire_export_maintenance", return_value=0) as expire,
            patch.object(script, "scan_orphan_maintenance", return_value=0) as orphans,
        ):
            result = script.main(["--once"])
            asyncio.run(worker_type.call_args.kwargs["scheduler_tick"]())
            asyncio.run(worker_type.call_args.kwargs["orphan_cleanup"]())

        self.assertEqual(result, 0)
        readiness.assert_called_once()
        install_signals.assert_called_once_with(fake_worker)
        fake_worker.run.assert_awaited_once_with(once=True)
        tick.assert_called_once_with(database.SessionLocal)
        expire.assert_called_once_with(
            database.SessionLocal,
            archive_dir=settings.archive_dir,
        )
        orphans.assert_called_once_with(
            database.SessionLocal,
            archive_dir=settings.archive_dir,
        )

    def test_cli_never_logs_raw_worker_exceptions(self):
        script = _load_worker_script()
        fake_worker = Mock()
        fake_worker.run = AsyncMock(
            side_effect=RuntimeError("access_token=test-worker-secret")
        )
        settings = _ready_settings(Path(tempfile.gettempdir()) / "worker-cli-test")

        with (
            patch.object(script, "parse_worker_enabled", return_value=True),
            patch.object(script, "load_integration_settings", return_value=settings),
            patch.object(script, "validate_worker_readiness"),
            patch.object(script, "IntegrationWorker", return_value=fake_worker),
            patch.object(script, "install_signal_handlers"),
            self.assertLogs("facai.integration.worker", level="ERROR") as captured,
        ):
            result = script.main(["--once"])

        rendered = "\n".join(captured.output)
        self.assertEqual(result, 1)
        self.assertIn("code=internal_error", rendered)
        self.assertNotIn("test-worker-secret", rendered)


class WorkerDatabaseTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.addClassCleanup(cls._cleanup)
        cls._reset()

    @classmethod
    def _reset(cls):
        Base.metadata.drop_all(cls.engine, tables=WORKER_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=WORKER_TABLES, checkfirst=False)

    @classmethod
    def _cleanup(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=WORKER_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    def setUp(self):
        self._reset()

    def _enqueue_exports(self, count: int) -> list[int]:
        identifiers = []
        with self.Session.begin() as db:
            for index in range(1, count + 1):
                job = enqueue_job(
                    db,
                    job_type=JobType.EXPORT,
                    target_id=index,
                    logical_request={"export_job_id": index},
                    payload={"export_job_id": index},
                )
                identifiers.append(job.id)
        return identifiers

    async def test_heartbeat_upserts_and_stale_detection_uses_last_seen(self):
        started_at = datetime(2026, 7, 13, 2, 0, tzinfo=UTC)
        with self.Session.begin() as db:
            first = upsert_worker_heartbeat(
                db,
                worker_id="worker-a",
                pid=os.getpid(),
                active_job_count=0,
                now=started_at,
            )
        with self.Session.begin() as db:
            second = upsert_worker_heartbeat(
                db,
                worker_id="worker-a",
                pid=os.getpid(),
                active_job_count=2,
                now=started_at + timedelta(seconds=10),
            )
        with self.Session() as db:
            rows = db.scalars(select(IntegrationWorkerHeartbeat)).all()
            stale_before = stale_worker_ids(
                db,
                now=started_at + timedelta(seconds=39),
                stale_after=timedelta(seconds=30),
            )
            stale_after = stale_worker_ids(
                db,
                now=started_at + timedelta(seconds=41),
                stale_after=timedelta(seconds=30),
            )

        self.assertEqual(first, second)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].active_job_count, 2)
        self.assertEqual(rows[0].started_at, started_at)
        self.assertEqual(rows[0].last_seen_at, started_at + timedelta(seconds=10))
        self.assertEqual(stale_before, ())
        self.assertEqual(stale_after, ("worker-a",))

    async def test_run_once_ticks_maintenance_and_isolates_job_exceptions(self):
        job_ids = self._enqueue_exports(2)
        scheduler_ticks = []
        orphan_scans = []

        async def scheduler_tick():
            scheduler_ticks.append("tick")

        async def orphan_cleanup():
            orphan_scans.append("scan")

        async def handler(job):
            if job.payload["export_job_id"] == 1:
                raise RuntimeError("raw secret-like exception must not persist")

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(enabled=True, concurrency=2),
            job_handler=handler,
            scheduler_tick=scheduler_tick,
            orphan_cleanup=orphan_cleanup,
            worker_id="worker-isolation",
            pid=os.getpid(),
        )

        result = await worker.run(once=True)

        with self.Session() as db:
            jobs = db.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.id.in_(job_ids))
                .order_by(IntegrationJob.id)
            ).all()
            heartbeat = db.scalar(
                select(IntegrationWorkerHeartbeat).where(
                    IntegrationWorkerHeartbeat.worker_id == "worker-isolation"
                )
            )

        self.assertEqual(scheduler_ticks, ["tick"])
        self.assertEqual(orphan_scans, ["scan"])
        self.assertEqual(result.claimed_jobs, 2)
        self.assertEqual(result.succeeded_jobs, 1)
        self.assertEqual(result.failed_jobs, 1)
        self.assertEqual([job.status for job in jobs], [JobStatus.FAILED, JobStatus.SUCCEEDED])
        self.assertEqual(jobs[0].last_error_code, "internal_error")
        self.assertEqual(jobs[0].last_error_summary, "internal worker failure")
        self.assertNotIn("raw secret", jobs[0].last_error_summary)
        self.assertEqual(heartbeat.active_job_count, 0)

    async def test_real_export_job_generates_local_csv_without_a_connector(self):
        now = utc_now()
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = Path(temp_dir)
            with self.Session.begin() as db:
                export_job = IntegrationExportJob(
                    requester_session_digest="e" * 64,
                    resource_type=ResourceType.ORDERS,
                    filters={},
                    format="csv",
                    status=ExportStatus.QUEUED,
                    row_count=0,
                    created_at=now,
                    expires_at=now + timedelta(days=1),
                )
                db.add(export_job)
                db.flush((export_job,))
                queue_job = enqueue_job(
                    db,
                    job_type=JobType.EXPORT,
                    target_id=export_job.id,
                    logical_request={"export_job_id": export_job.id},
                    payload={"export_job_id": export_job.id},
                )
                export_job_id = export_job.id
                queue_job_id = queue_job.id

            worker = IntegrationWorker(
                session_factory=self.Session,
                config=WorkerConfig(enabled=True),
                job_handler=build_default_job_handler(
                    self.Session,
                    archive_dir=archive_dir,
                ),
                worker_id="worker-real-export",
                pid=os.getpid(),
            )

            result = await worker.run(once=True)

            with self.Session() as db:
                stored_export = db.get(IntegrationExportJob, export_job_id)
                stored_queue_job = db.get(IntegrationJob, queue_job_id)

            self.assertEqual(result.succeeded_jobs, 1)
            self.assertEqual(stored_queue_job.status, JobStatus.SUCCEEDED)
            self.assertEqual(stored_export.status, ExportStatus.READY)
            self.assertEqual(stored_export.row_count, 0)
            output = archive_dir / stored_export.relative_file_path
            self.assertTrue(output.is_file())
            self.assertIn("平台订单号", output.read_text(encoding="utf-8-sig"))

    async def test_running_job_lease_is_renewed_until_handler_completes(self):
        job_id = self._enqueue_exports(1)[0]

        async def slow_handler(_job):
            await asyncio.sleep(0.35)

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                concurrency=1,
                heartbeat_interval=0.03,
                lease_duration=timedelta(seconds=0.15),
            ),
            job_handler=slow_handler,
            worker_id="worker-renewal",
            pid=os.getpid(),
        )

        await worker.run(once=True)

        with self.Session() as db:
            job = db.get(IntegrationJob, job_id)
            self.assertEqual(job.status, JobStatus.SUCCEEDED)
            self.assertIsNone(job.lease_owner)
            self.assertIsNone(job.lease_expires_at)
            self.assertGreaterEqual(job.attempts, 1)

    async def test_once_never_runs_more_than_the_configured_concurrency(self):
        job_ids = self._enqueue_exports(6)
        active = 0
        maximum_active = 0
        lock = asyncio.Lock()

        async def measured_handler(_job):
            nonlocal active, maximum_active
            async with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(enabled=True, concurrency=4),
            job_handler=measured_handler,
            worker_id="worker-concurrency",
            pid=os.getpid(),
        )

        result = await worker.run(once=True)

        with self.Session() as db:
            jobs = db.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.id.in_(job_ids))
                .order_by(IntegrationJob.id)
            ).all()
        self.assertEqual(maximum_active, 4)
        self.assertEqual(result.claimed_jobs, 4)
        self.assertEqual(
            [job.status for job in jobs].count(JobStatus.SUCCEEDED),
            4,
        )
        self.assertEqual(
            [job.status for job in jobs].count(JobStatus.QUEUED),
            2,
        )

    async def test_shutdown_timeout_also_cancels_a_stuck_maintenance_tick(self):
        maintenance_started = asyncio.Event()

        async def stuck_maintenance():
            maintenance_started.set()
            await asyncio.Event().wait()

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                poll_interval=0.01,
                shutdown_timeout=0.05,
            ),
            scheduler_tick=stuck_maintenance,
            worker_id="worker-maintenance-shutdown",
            pid=os.getpid(),
        )

        task = asyncio.create_task(worker.run())
        await asyncio.wait_for(maintenance_started.wait(), timeout=1)
        worker.request_stop()
        result = await asyncio.wait_for(task, timeout=1)

        self.assertTrue(result.enabled)

    async def test_shutdown_uses_one_budget_for_jobs_and_maintenance(self):
        self._enqueue_exports(1)
        job_started = asyncio.Event()
        maintenance_started = asyncio.Event()

        async def stuck_job(_job):
            job_started.set()
            await asyncio.Event().wait()

        async def stuck_maintenance():
            maintenance_started.set()
            await asyncio.Event().wait()

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                concurrency=1,
                poll_interval=0.01,
                shutdown_timeout=0.08,
            ),
            job_handler=stuck_job,
            scheduler_tick=stuck_maintenance,
            worker_id="worker-single-shutdown-budget",
            pid=os.getpid(),
        )

        task = asyncio.create_task(worker.run())
        await asyncio.wait_for(job_started.wait(), timeout=1)
        await asyncio.wait_for(maintenance_started.wait(), timeout=1)
        started_at = asyncio.get_running_loop().time()
        worker.request_stop()
        await asyncio.wait_for(task, timeout=1)
        elapsed = asyncio.get_running_loop().time() - started_at

        self.assertLess(elapsed, 0.13)

    async def test_heartbeat_failure_stops_claiming_and_still_releases_owned_work(self):
        job_id = self._enqueue_exports(1)[0]
        handler_started = asyncio.Event()

        async def blocking_handler(_job):
            handler_started.set()
            await asyncio.Event().wait()

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                concurrency=1,
                poll_interval=0.01,
                heartbeat_interval=0.02,
                lease_duration=timedelta(seconds=1),
                shutdown_timeout=0.05,
            ),
            job_handler=blocking_handler,
            worker_id="worker-heartbeat-failure",
            pid=os.getpid(),
        )
        real_heartbeat = worker._write_heartbeat
        calls = 0

        def fail_after_startup():
            nonlocal calls
            calls += 1
            if calls == 1:
                real_heartbeat()
                return
            raise RuntimeError("access_token=test-heartbeat-secret")

        with patch.object(worker, "_write_heartbeat", side_effect=fail_after_startup):
            task = asyncio.create_task(worker.run())
            await asyncio.wait_for(handler_started.wait(), timeout=1)
            result = await asyncio.wait_for(task, timeout=1)

        with self.Session() as db:
            job = db.get(IntegrationJob, job_id)

        self.assertTrue(result.enabled)
        self.assertEqual(job.status, JobStatus.RETRY_WAIT)
        self.assertIsNone(job.lease_owner)
        self.assertIsNone(job.lease_expires_at)

    async def test_job_renewal_failure_cannot_leave_active_heartbeat_count_stuck(self):
        job_id = self._enqueue_exports(1)[0]

        async def slow_handler(_job):
            await asyncio.sleep(0.08)

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                concurrency=1,
                heartbeat_interval=0.02,
                lease_duration=timedelta(seconds=1),
            ),
            job_handler=slow_handler,
            worker_id="worker-renewal-failure",
            pid=os.getpid(),
        )

        with patch(
            "integrations.sync.worker.heartbeat_job",
            side_effect=RuntimeError("access_token=test-renewal-secret"),
        ):
            result = await worker.run(once=True)

        with self.Session() as db:
            job = db.get(IntegrationJob, job_id)
            heartbeat = db.scalar(
                select(IntegrationWorkerHeartbeat).where(
                    IntegrationWorkerHeartbeat.worker_id
                    == "worker-renewal-failure"
                )
            )

        self.assertEqual(result.succeeded_jobs, 1)
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(heartbeat.active_job_count, 0)

    async def test_internal_task_exception_is_consumed_without_asyncio_raw_logging(self):
        job_id = self._enqueue_exports(1)[0]
        crashed = asyncio.Event()
        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                concurrency=1,
                poll_interval=0.01,
                shutdown_timeout=0.05,
            ),
            worker_id="worker-task-exception",
            pid=os.getpid(),
        )

        async def crash_task(_job):
            crashed.set()
            raise RuntimeError("access_token=test-task-secret")

        worker._process_job = crash_task
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        contexts = []
        loop.set_exception_handler(lambda _loop, context: contexts.append(context))
        try:
            task = asyncio.create_task(worker.run())
            await asyncio.wait_for(crashed.wait(), timeout=1)
            await asyncio.sleep(0.05)
            worker.request_stop()
            await asyncio.wait_for(task, timeout=1)
            await asyncio.sleep(0)
        finally:
            loop.set_exception_handler(previous_handler)

        with self.Session() as db:
            job = db.get(IntegrationJob, job_id)
        rendered = "\n".join(
            str(context.get("exception", "")) + str(context.get("message", ""))
            for context in contexts
        )
        self.assertNotIn("test-task-secret", rendered)
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertIsNone(job.lease_owner)

    async def test_stop_ceases_claiming_and_timed_out_work_releases_only_owned_leases(self):
        job_ids = self._enqueue_exports(2)
        started = asyncio.Event()

        async def blocking_handler(_job):
            started.set()
            await asyncio.Event().wait()

        worker = IntegrationWorker(
            session_factory=self.Session,
            config=WorkerConfig(
                enabled=True,
                concurrency=1,
                poll_interval=0.01,
                heartbeat_interval=0.02,
                lease_duration=timedelta(seconds=1),
                shutdown_timeout=0.05,
            ),
            job_handler=blocking_handler,
            worker_id="worker-shutdown",
            pid=os.getpid(),
        )

        task = asyncio.create_task(worker.run())
        await asyncio.wait_for(started.wait(), timeout=2)
        worker.request_stop()
        await asyncio.wait_for(task, timeout=2)

        with self.Session() as db:
            jobs = db.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.id.in_(job_ids))
                .order_by(IntegrationJob.id)
            ).all()

        self.assertEqual(jobs[0].status, JobStatus.RETRY_WAIT)
        self.assertEqual(jobs[0].attempts, 1)
        self.assertIsNone(jobs[0].lease_owner)
        self.assertIsNone(jobs[0].lease_expires_at)
        self.assertEqual(jobs[1].status, JobStatus.QUEUED)
        self.assertEqual(jobs[1].attempts, 0)

    async def test_release_worker_leases_never_touches_another_owner(self):
        job_ids = self._enqueue_exports(2)
        now = datetime.now(UTC)
        with self.Session.begin() as db:
            jobs = db.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.id.in_(job_ids))
                .order_by(IntegrationJob.id)
                .with_for_update()
            ).all()
            for owner, job in zip(("worker-a", "worker-b"), jobs):
                job.status = JobStatus.RUNNING
                job.attempts = 1
                job.lease_owner = owner
                job.lease_expires_at = now + timedelta(minutes=1)
                job.heartbeat_at = now
            released = release_worker_leases(db, owner="worker-a", now=now)

        with self.Session() as db:
            jobs = db.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.id.in_(job_ids))
                .order_by(IntegrationJob.id)
            ).all()

        self.assertEqual(released.jobs, 1)
        self.assertEqual(jobs[0].status, JobStatus.RETRY_WAIT)
        self.assertIsNone(jobs[0].lease_owner)
        self.assertEqual(jobs[1].status, JobStatus.RUNNING)
        self.assertEqual(jobs[1].lease_owner, "worker-b")


if __name__ == "__main__":
    unittest.main()
