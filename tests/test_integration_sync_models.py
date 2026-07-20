import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, UniqueConstraint, inspect, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import database
from database import Base
from integration_models import (
    IntegrationArchiveManifest,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationExportJob,
    IntegrationJob,
    IntegrationSyncCheckpoint,
    IntegrationSyncError,
    IntegrationSyncRun,
    IntegrationWorkerHeartbeat,
)
from integrations.types import (
    AuthorizationStatus,
    CheckpointStatus,
    ConnectionStatus,
    ConnectionType,
    ExportStatus,
    JobStatus,
    JobType,
    Provider,
    ResourceType,
    SyncSource,
    SyncStatus,
)
from tests.postgres_test_support import requires_disposable_postgres
from tests.test_integration_models import _require_disposable_postgres_url

SYNC_MODELS = (
    IntegrationJob,
    IntegrationWorkerHeartbeat,
    IntegrationSyncCheckpoint,
    IntegrationSyncRun,
    IntegrationSyncError,
    IntegrationArchiveManifest,
    IntegrationExportJob,
)
SYNC_TABLES = tuple(model.__table__ for model in SYNC_MODELS)
DEPENDENCY_TABLES = (
    IntegrationAuthorization.__table__,
    IntegrationConnection.__table__,
)
ALL_TEST_TABLES = DEPENDENCY_TABLES + SYNC_TABLES

EXPECTED_UNIQUES = {
    "integration_jobs": {
        "uq_integration_jobs_dedupe_key": ("dedupe_key",),
    },
    "integration_worker_heartbeats": {
        "uq_integration_worker_heartbeats_worker_id": ("worker_id",),
    },
    "integration_sync_checkpoints": {
        "uq_integration_sync_checkpoints_connection_resource_window": (
            "connection_id",
            "resource_type",
            "window_start",
            "window_end",
        ),
    },
    "integration_export_jobs": {
        "uq_integration_export_jobs_public_id": ("public_id",),
    },
}

EXPECTED_FOREIGN_KEYS = {
    "integration_sync_checkpoints": {
        "fk_integration_sync_checkpoints_connection": (
            ("connection_id",),
            "integration_connections",
            ("id",),
            "CASCADE",
        ),
    },
    "integration_sync_runs": {
        "fk_integration_sync_runs_checkpoint": (
            ("checkpoint_id",),
            "integration_sync_checkpoints",
            ("id",),
            "CASCADE",
        ),
        "fk_integration_sync_runs_parent": (
            ("parent_run_id",),
            "integration_sync_runs",
            ("id",),
            "SET NULL",
        ),
    },
    "integration_sync_errors": {
        "fk_integration_sync_errors_run": (
            ("run_id",),
            "integration_sync_runs",
            ("id",),
            "CASCADE",
        ),
    },
    "integration_archive_manifests": {
        "fk_integration_archive_manifests_run": (
            ("run_id",),
            "integration_sync_runs",
            ("id",),
            "CASCADE",
        ),
        "fk_integration_archive_manifests_connection_provider": (
            ("connection_id", "provider"),
            "integration_connections",
            ("id", "provider"),
            "CASCADE",
        ),
    },
}

EXPECTED_ENUMS = {
    ("integration_jobs", "job_type"): JobType,
    ("integration_jobs", "status"): JobStatus,
    ("integration_sync_checkpoints", "resource_type"): ResourceType,
    ("integration_sync_checkpoints", "status"): CheckpointStatus,
    ("integration_sync_runs", "source"): SyncSource,
    ("integration_sync_runs", "status"): SyncStatus,
    ("integration_sync_runs", "resource_type"): ResourceType,
    ("integration_archive_manifests", "provider"): Provider,
    ("integration_archive_manifests", "resource_type"): ResourceType,
    ("integration_export_jobs", "resource_type"): ResourceType,
    ("integration_export_jobs", "status"): ExportStatus,
}


class SyncModelMetadataTests(unittest.TestCase):
    def test_all_sync_control_tables_are_registered(self):
        self.assertEqual(
            {table.name for table in SYNC_TABLES},
            {
                "integration_jobs",
                "integration_worker_heartbeats",
                "integration_sync_checkpoints",
                "integration_sync_runs",
                "integration_sync_errors",
                "integration_archive_manifests",
                "integration_export_jobs",
            },
        )

    def test_json_columns_compile_to_jsonb_on_postgresql(self):
        json_columns = {
            (table.name, column.name)
            for table in SYNC_TABLES
            for column in table.columns
            if column.name in {"payload", "cursor", "field_errors", "filters"}
        }
        self.assertEqual(
            json_columns,
            {
                ("integration_jobs", "payload"),
                ("integration_sync_checkpoints", "cursor"),
                ("integration_sync_errors", "field_errors"),
                ("integration_export_jobs", "filters"),
            },
        )
        for table_name, column_name in json_columns:
            column = Base.metadata.tables[table_name].c[column_name]
            with self.subTest(table=table_name, column=column_name):
                self.assertIsInstance(
                    column.type.dialect_impl(postgresql.dialect()),
                    JSONB,
                )

    def test_all_sync_timestamps_are_timezone_aware(self):
        for table in SYNC_TABLES:
            for column in table.columns:
                if isinstance(column.type, DateTime):
                    with self.subTest(table=table.name, column=column.name):
                        self.assertTrue(column.type.timezone)

    def test_queued_sync_run_has_a_created_time_before_it_has_a_start_time(self):
        table = IntegrationSyncRun.__table__
        self.assertIn("created_at", table.c)
        self.assertFalse(table.c.created_at.nullable)
        self.assertTrue(table.c.started_at.nullable)

    def test_named_uniques_match_the_idempotency_contract(self):
        actual = {}
        for table in SYNC_TABLES:
            named = {
                constraint.name: tuple(column.name for column in constraint.columns)
                for constraint in table.constraints
                if isinstance(constraint, UniqueConstraint)
                and constraint.name in EXPECTED_UNIQUES.get(table.name, {})
            }
            if named:
                actual[table.name] = named
        self.assertEqual(actual, EXPECTED_UNIQUES)

    def test_export_audit_and_retention_indexes_are_named(self):
        indexes = {
            index.name: tuple(column.name for column in index.columns)
            for index in IntegrationExportJob.__table__.indexes
        }
        self.assertEqual(
            indexes,
            {
                "ix_integration_export_jobs_requester_session_digest": (
                    "requester_session_digest",
                ),
                "ix_integration_export_jobs_status": ("status", "created_at"),
                "ix_integration_export_jobs_expires_at": ("expires_at",),
            },
        )

    def test_every_persisted_enum_has_an_exact_named_check(self):
        actual = {}
        for table in SYNC_TABLES:
            for column in table.columns:
                if isinstance(column.type, SqlEnum):
                    actual[(table.name, column.name)] = column.type.enum_class
                    self.assertEqual(
                        column.type.name,
                        f"ck_{table.name}_{column.name}",
                    )
                    self.assertFalse(column.type.native_enum)
                    self.assertTrue(column.type.create_constraint)
        self.assertEqual(actual, EXPECTED_ENUMS)


@requires_disposable_postgres
class PostgresSyncModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine)
        cls.addClassCleanup(cls._cleanup)
        cls._reset_schema()

    @classmethod
    def _cleanup(cls):
        Base.metadata.drop_all(cls.engine, tables=ALL_TEST_TABLES, checkfirst=True)
        cls.engine.dispose()

    @classmethod
    def _reset_schema(cls):
        Base.metadata.drop_all(cls.engine, tables=ALL_TEST_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=ALL_TEST_TABLES, checkfirst=False)

    def setUp(self):
        self._reset_schema()
        session = self.Session()
        try:
            authorization = IntegrationAuthorization(
                provider=Provider.QIANCHUAN,
                external_subject_id="subject-sync",
                scopes=["report.read"],
                access_token_ciphertext="opaque-ciphertext",
                access_token_tail="0000",
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=datetime.now(UTC),
            )
            session.add(authorization)
            session.flush()
            connection = IntegrationConnection(
                authorization_id=authorization.id,
                provider=Provider.QIANCHUAN,
                connection_type=ConnectionType.AD_ACCOUNT,
                external_account_id="account-sync",
                display_name="Sync test account",
                status=ConnectionStatus.ACTIVE,
                capability_report={},
            )
            session.add(connection)
            session.commit()
            self.connection_id = connection.id
        finally:
            session.close()

    @staticmethod
    def _now():
        return datetime.now(UTC).replace(microsecond=0)

    def _job_values(self, suffix: str):
        now = self._now()
        return {
            "job_type": JobType.SYNC_RESOURCE.value,
            "dedupe_key": (suffix * 64)[:64],
            "payload": {"connection_id": self.connection_id},
            "priority": 10,
            "status": JobStatus.QUEUED.value,
            "available_at": now,
            "attempts": 0,
            "max_attempts": 6,
            "created_at": now,
            "updated_at": now,
        }

    def _heartbeat_values(self, suffix: str):
        now = self._now()
        return {
            "worker_id": f"worker-{suffix}",
            "pid": 1234,
            "started_at": now,
            "last_seen_at": now,
            "active_job_count": 0,
            "version": "test",
        }

    def _checkpoint_values(self, suffix: str):
        start = self._now() + timedelta(days=ord(suffix[0]) % 10)
        return {
            "connection_id": self.connection_id,
            "resource_type": ResourceType.ORDERS.value,
            "window_start": start,
            "window_end": start + timedelta(hours=1),
            "cursor": None,
            "status": CheckpointStatus.PENDING.value,
            "attempts": 0,
            "created_at": self._now(),
            "updated_at": self._now(),
        }

    def _export_values(self, suffix: str):
        now = self._now()
        return {
            "public_id": f"00000000-0000-4000-8000-{ord(suffix[0]):012d}",
            "requester_session_digest": "e" * 64,
            "resource_type": ResourceType.ORDERS.value,
            "filters": {"connection_id": self.connection_id},
            "format": "csv",
            "status": ExportStatus.QUEUED.value,
            "row_count": 0,
            "created_at": now,
            "expires_at": now + timedelta(days=1),
        }

    def _insert_run_tree(self):
        checkpoint_values = self._checkpoint_values("r")
        with self.engine.begin() as connection:
            checkpoint_id = connection.execute(
                IntegrationSyncCheckpoint.__table__.insert()
                .values(**checkpoint_values)
                .returning(IntegrationSyncCheckpoint.id)
            ).scalar_one()
            run_id = connection.execute(
                IntegrationSyncRun.__table__.insert()
                .values(
                    checkpoint_id=checkpoint_id,
                    source=SyncSource.SCHEDULED.value,
                    status=SyncStatus.RUNNING.value,
                    resource_type=ResourceType.ORDERS.value,
                    window_start=checkpoint_values["window_start"],
                    window_end=checkpoint_values["window_end"],
                    progress=0,
                    records_read=0,
                    records_written=0,
                    records_skipped=0,
                    records_quarantined=0,
                    started_at=self._now(),
                )
                .returning(IntegrationSyncRun.id)
            ).scalar_one()
            error_id = connection.execute(
                IntegrationSyncError.__table__.insert()
                .values(
                    run_id=run_id,
                    external_key_hmac="f" * 64,
                    error_type="validation_error",
                    sanitized_summary="invalid field",
                    field_errors=[{"path": "status", "code": "enum"}],
                    retryable=False,
                    created_at=self._now(),
                )
                .returning(IntegrationSyncError.id)
            ).scalar_one()
            archive_id = connection.execute(
                IntegrationArchiveManifest.__table__.insert()
                .values(
                    run_id=run_id,
                    page_number=1,
                    provider=Provider.QIANCHUAN.value,
                    connection_id=self.connection_id,
                    resource_type=ResourceType.ORDERS.value,
                    window_start=checkpoint_values["window_start"],
                    window_end=checkpoint_values["window_end"],
                    relative_path="qianchuan/1/orders/2026/07/run-000001.jsonl.gz.aes",
                    sha256="a" * 64,
                    record_count=1,
                    created_at=self._now(),
                    expires_at=self._now() + timedelta(days=90),
                )
                .returning(IntegrationArchiveManifest.id)
            ).scalar_one()
        return checkpoint_id, run_id, error_id, archive_id

    def test_database_has_exact_named_unique_constraints(self):
        inspector = inspect(self.engine)
        for table_name, expected in EXPECTED_UNIQUES.items():
            actual = {
                item["name"]: tuple(item["column_names"])
                for item in inspector.get_unique_constraints(table_name)
                if item["name"] in expected
            }
            self.assertEqual(actual, expected, table_name)

    def test_each_idempotency_key_rejects_a_duplicate(self):
        cases = (
            (IntegrationJob.__table__, self._job_values("j")),
            (IntegrationWorkerHeartbeat.__table__, self._heartbeat_values("h")),
            (IntegrationSyncCheckpoint.__table__, self._checkpoint_values("c")),
            (IntegrationExportJob.__table__, self._export_values("x")),
        )
        for table, values in cases:
            with self.subTest(table=table.name):
                with self.engine.begin() as connection:
                    connection.execute(table.insert().values(**values))
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(table.insert().values(**values))

    def test_database_has_exact_named_foreign_keys_and_delete_actions(self):
        inspector = inspect(self.engine)
        for table_name, expected in EXPECTED_FOREIGN_KEYS.items():
            actual = {}
            for item in inspector.get_foreign_keys(table_name):
                if item["name"] not in expected:
                    continue
                actual[item["name"]] = (
                    tuple(item["constrained_columns"]),
                    item["referred_table"],
                    tuple(item["referred_columns"]),
                    (item.get("options") or {}).get("ondelete"),
                )
            self.assertEqual(actual, expected, table_name)

    def test_foreign_keys_reject_missing_parents(self):
        checkpoint = self._checkpoint_values("m")
        checkpoint["connection_id"] = 999999
        invalid_rows = (
            (IntegrationSyncCheckpoint.__table__, checkpoint),
            (
                IntegrationSyncRun.__table__,
                {
                    "checkpoint_id": 999999,
                    "source": SyncSource.MANUAL.value,
                    "status": SyncStatus.QUEUED.value,
                    "resource_type": ResourceType.ORDERS.value,
                    "window_start": self._now(),
                    "window_end": self._now() + timedelta(hours=1),
                    "progress": 0,
                    "records_read": 0,
                    "records_written": 0,
                    "records_skipped": 0,
                    "records_quarantined": 0,
                    "started_at": self._now(),
                },
            ),
            (
                IntegrationSyncError.__table__,
                {
                    "run_id": 999999,
                    "external_key_hmac": "a" * 64,
                    "error_type": "validation_error",
                    "field_errors": [],
                    "retryable": False,
                    "created_at": self._now(),
                },
            ),
        )
        for table, values in invalid_rows:
            with self.subTest(table=table.name), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(table.insert().values(**values))

    def test_parent_deletes_follow_the_declared_fk_policy(self):
        checkpoint_id, run_id, _, _ = self._insert_run_tree()
        with self.engine.begin() as connection:
            connection.execute(
                IntegrationSyncCheckpoint.__table__.delete().where(
                    IntegrationSyncCheckpoint.id == checkpoint_id
                )
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT count(*) FROM integration_sync_runs WHERE id=:id"),
                    {"id": run_id},
                ).scalar_one(),
                0,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT count(*) FROM integration_sync_errors")
                ).scalar_one(),
                0,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT count(*) FROM integration_archive_manifests")
                ).scalar_one(),
                0,
            )

    def test_database_enum_checks_exist_and_reject_invalid_raw_updates(self):
        job_id = None
        export_id = None
        with self.engine.begin() as connection:
            job_id = connection.execute(
                IntegrationJob.__table__.insert()
                .values(**self._job_values("q"))
                .returning(IntegrationJob.id)
            ).scalar_one()
            export_id = connection.execute(
                IntegrationExportJob.__table__.insert()
                .values(**self._export_values("q"))
                .returning(IntegrationExportJob.id)
            ).scalar_one()
        checkpoint_id, run_id, _, archive_id = self._insert_run_tree()

        ids = {
            "integration_jobs": job_id,
            "integration_sync_checkpoints": checkpoint_id,
            "integration_sync_runs": run_id,
            "integration_archive_manifests": archive_id,
            "integration_export_jobs": export_id,
        }
        inspector = inspect(self.engine)
        for (table_name, column_name), enum_type in EXPECTED_ENUMS.items():
            constraint_name = f"ck_{table_name}_{column_name}"
            constraints = {
                item["name"]: item["sqltext"]
                for item in inspector.get_check_constraints(table_name)
            }
            with self.subTest(table=table_name, column=column_name):
                self.assertIn(constraint_name, constraints)
                for member in enum_type:
                    self.assertIn(member.value, constraints[constraint_name])
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(
                            text(
                                f'UPDATE "{table_name}" '
                                f'SET "{column_name}" = :invalid WHERE id = :id'
                            ),
                            {"invalid": "x", "id": ids[table_name]},
                        )

    def test_postgresql_round_trips_timezone_aware_timestamps(self):
        with self.engine.begin() as connection:
            job_id = connection.execute(
                IntegrationJob.__table__.insert()
                .values(**self._job_values("t"))
                .returning(IntegrationJob.id)
            ).scalar_one()
            available_at = connection.execute(
                text("SELECT available_at FROM integration_jobs WHERE id=:id"),
                {"id": job_id},
            ).scalar_one()
        self.assertIsNotNone(available_at.tzinfo)
        self.assertIsNotNone(available_at.utcoffset())


if __name__ == "__main__":
    unittest.main()
