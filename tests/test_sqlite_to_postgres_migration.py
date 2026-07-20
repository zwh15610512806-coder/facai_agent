"""Contract tests for the verified SQLite-to-PostgreSQL migration."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import (
    JSON,
    Column,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from database import Base
from integrations.db_safety import assert_disposable_postgres
from integrations.migration import (
    LEGACY_COLUMN_ADAPTERS,
    BackupReport,
    LegacyColumnAdapter,
    MigrationError,
    MigrationReport,
    SnapshotEvidence,
    TableMigrationReport,
    backup_sqlite_source,
    migrate_sqlite_to_postgres,
)
from tests.postgres_test_support import requires_disposable_postgres

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"
OPTIONAL_INTEGRATION_TABLES = {
    "commerce_ad_accounts",
    "commerce_ad_balance_snapshots",
    "commerce_ad_daily_metrics",
    "commerce_ad_entities",
    "commerce_ad_finance_transactions",
    "commerce_daily_metrics",
    "commerce_event_inbox",
    "commerce_inventory_snapshots",
    "commerce_order_items",
    "commerce_orders",
    "commerce_product_links",
    "commerce_products",
    "commerce_refunds",
    "commerce_settlements",
    "commerce_shipments",
    "commerce_shops",
    "commerce_skus",
    "integration_app_configs",
    "integration_archive_manifests",
    "integration_authorizations",
    "integration_connections",
    "integration_export_jobs",
    "integration_jobs",
    "integration_login_throttles",
    "integration_oauth_states",
    "integration_security_audit",
    "integration_sync_checkpoints",
    "integration_sync_errors",
    "integration_sync_runs",
    "integration_worker_heartbeats",
}
LEGACY_TABLES = tuple(
    table
    for table in Base.metadata.sorted_tables
    if table.name not in OPTIONAL_INTEGRATION_TABLES
)


def _guarded_url() -> str:
    return assert_disposable_postgres(
        url_env="FACAI_TEST_DATABASE_URL",
        acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
    )


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _run_guarded_alembic(operation, revision: str) -> None:
    url = _guarded_url()
    with patch.dict(os.environ, {"FACAI_MIGRATION_DATABASE_URL": url}, clear=False):
        operation(_alembic_config(url), revision)


def _create_legacy_fixture(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        Base.metadata.create_all(engine, tables=list(LEGACY_TABLES))
    finally:
        engine.dispose()


def _source_execute(path: Path, *statements: tuple[str, tuple[object, ...]]) -> None:
    with closing(sqlite3.connect(path)) as connection:
        for sql, parameters in statements:
            connection.execute(sql, parameters)
        connection.commit()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sqlite_logical_sha(path: Path) -> str:
    with closing(
        sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    ) as connection:
        dump = "\n".join(connection.iterdump())
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def _sqlite_table_fingerprint(path: Path, table_name: str) -> str:
    quoted = table_name.replace('"', '""')
    with closing(sqlite3.connect(path)) as connection:
        schema_rows = connection.execute(
            f'PRAGMA table_info("{quoted}")'
        ).fetchall()
    signature = "\n".join(
        "|".join("" if value is None else str(value) for value in row)
        for row in schema_rows
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def _snapshot_evidence(path: Path, *, retained: bool = False) -> SnapshotEvidence:
    resolved = path.resolve()
    size = resolved.stat().st_size
    digest = _file_sha(resolved)
    return SnapshotEvidence(
        source_path=resolved,
        source_size=size,
        source_sha256=digest,
        source_database_sha256=digest,
        source_wal_path=None,
        source_wal_size=0,
        source_wal_sha256=None,
        source_integrity_check="ok",
        source_page_count=1,
        snapshot_path=resolved if retained else None,
        snapshot_size=size,
        snapshot_sha256=digest,
        snapshot_integrity_check="ok",
        snapshot_page_count=1,
        retained=retained,
        ok=True,
    )


class MigrationReportContractTests(unittest.TestCase):
    def test_report_dataclasses_are_exact_frozen_slot_contracts(self) -> None:
        self.assertEqual(
            [field.name for field in fields(TableMigrationReport)],
            [
                "table",
                "source_rows",
                "target_rows",
                "orphan_foreign_keys",
                "duplicate_unique_keys",
                "json_errors",
                "synthesized_columns",
            ],
        )
        self.assertEqual(
            [field.name for field in fields(SnapshotEvidence)],
            [
                "source_path",
                "source_size",
                "source_sha256",
                "source_database_sha256",
                "source_wal_path",
                "source_wal_size",
                "source_wal_sha256",
                "source_integrity_check",
                "source_page_count",
                "snapshot_path",
                "snapshot_size",
                "snapshot_sha256",
                "snapshot_integrity_check",
                "snapshot_page_count",
                "retained",
                "ok",
            ],
        )
        self.assertEqual(
            [field.name for field in fields(MigrationReport)],
            [
                "source_path",
                "source_sha256",
                "backup_path",
                "backup_sha256",
                "applied",
                "tables",
                "amount_totals",
                "ok",
                "snapshot",
                "warnings",
            ],
        )
        report = TableMigrationReport("products", 0, 0, (), (), (), {})
        self.assertFalse(hasattr(report, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            report.source_rows = 1  # type: ignore[misc]

    def test_snapshot_evidence_rejects_impossible_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "evidence.db"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY)")
                connection.commit()
            ephemeral = _snapshot_evidence(source)
            with self.assertRaisesRegex(ValueError, "retained"):
                replace(ephemeral, retained=True)
            with self.assertRaisesRegex(ValueError, "ephemeral"):
                replace(
                    ephemeral,
                    snapshot_path=source.resolve(),
                    retained=False,
                )


class SQLiteBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source = Path(self.temp_dir.name) / "source.db"

    def _create_source(self) -> None:
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO evidence(value) VALUES ('迁移证据')")
            connection.commit()

    def test_missing_and_non_sqlite_sources_are_rejected(self) -> None:
        with self.assertRaises(MigrationError):
            backup_sqlite_source(self.source)

        self.source.write_text("not sqlite", encoding="utf-8")
        with self.assertRaises(MigrationError):
            backup_sqlite_source(self.source)

    def test_backup_uses_sqlite_backup_api_and_preserves_source_bytes(self) -> None:
        self._create_source()
        source_before = self.source.read_bytes()
        source_sha = hashlib.sha256(source_before).hexdigest()

        report = backup_sqlite_source(self.source)

        self.assertIsInstance(report, BackupReport)
        self.assertTrue(report.ok)
        self.assertEqual(report.source_path, self.source.resolve())
        self.assertEqual(report.source_sha256, source_sha)
        self.assertEqual(report.source_size, len(source_before))
        self.assertEqual(report.source_integrity_check, "ok")
        self.assertEqual(report.backup_integrity_check, "ok")
        self.assertEqual(report.source_page_count, report.backup_page_count)
        self.assertEqual(report.backup_size, report.backup_path.stat().st_size)
        self.assertEqual(
            report.backup_sha256,
            hashlib.sha256(report.backup_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertEqual(report.backup_path.parent, self.source.parent / "backups")
        self.assertRegex(
            report.backup_path.name,
            r"^source_pre_postgres_\d{8}T\d{6}\d{6}Z\.db$",
        )
        with closing(sqlite3.connect(report.backup_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM evidence").fetchone()[0],
                "迁移证据",
            )

    def test_backup_fingerprints_committed_wal_state_not_only_main_file(self) -> None:
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
            writer.execute("INSERT INTO evidence(value) VALUES ('first')")
            writer.commit()

            first_main_sha = _file_sha(self.source)
            first = backup_sqlite_source(self.source)
            writer.execute("INSERT INTO evidence(value) VALUES ('second')")
            writer.commit()
            second_main_sha = _file_sha(self.source)
            second = backup_sqlite_source(self.source)

        self.assertEqual(first_main_sha, second_main_sha)
        self.assertEqual(first.source_database_sha256, second.source_database_sha256)
        self.assertNotEqual(first.source_wal_sha256, second.source_wal_sha256)
        self.assertNotEqual(first.source_sha256, second.source_sha256)
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)

    def test_apply_source_guard_is_query_only_while_holding_write_lock(self) -> None:
        import integrations.migration as migration

        self._create_source()
        guard = migration._lock_sqlite_source(self.source.resolve())
        try:
            self.assertTrue(guard.in_transaction)
            self.assertEqual(guard.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError) as raised:
                guard.execute("INSERT INTO evidence(value) VALUES ('forbidden')")
            self.assertEqual(raised.exception.sqlite_errorcode, sqlite3.SQLITE_READONLY)
        finally:
            guard.rollback()
            guard.close()

    def test_apply_guard_does_not_count_empty_lock_wal_as_committed_state(self) -> None:
        import integrations.migration as migration

        self._create_source()
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        before = migration._sqlite_state(self.source)

        guard = migration._lock_sqlite_source(self.source.resolve())
        try:
            self.assertEqual(migration._sqlite_state(self.source), before)
        finally:
            guard.rollback()
            guard.close()

        self.assertEqual(migration._sqlite_state(self.source), before)


class MigrationDiagnosticPrivacyTests(unittest.TestCase):
    def test_source_and_target_fk_diagnostics_share_redacted_fingerprint(self) -> None:
        import integrations.migration as migration

        sensitive_authorization_id = 987_654_321
        rows_by_table = {
            table.name: [] for table in Base.metadata.sorted_tables
        }
        rows_by_table["integration_connections"] = [
            {
                "id": 1,
                "authorization_id": sensitive_authorization_id,
                "provider": "pdd",
            }
        ]
        source_states = migration._new_states()
        migration._validate_source_foreign_keys(rows_by_table, source_states)
        source_errors = source_states[
            "integration_connections"
        ].orphan_foreign_keys

        authorization = Base.metadata.tables["integration_authorizations"]
        connection_table = Base.metadata.tables["integration_connections"]
        target_engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(
                target_engine,
                tables=[authorization, connection_table],
            )
            with target_engine.begin() as target:
                target.execute(
                    connection_table.insert(),
                    {
                        "id": 1,
                        "authorization_id": sensitive_authorization_id,
                        "provider": "pdd",
                        "connection_type": "shop",
                        "external_account_id": "sensitive-account",
                        "display_name": "sensitive-display-name",
                        "status": "active",
                        "capability_report": {},
                    },
                )
                target_state = migration._TableState(connection_table)
                migration._validate_target_foreign_keys(
                    target,
                    connection_table,
                    target_state,
                )
        finally:
            target_engine.dispose()

        self.assertEqual(len(source_errors), 1)
        self.assertEqual(source_errors, target_state.orphan_foreign_keys)
        diagnostic = source_errors[0]
        self.assertIn("orphan_count=1", diagnostic)
        self.assertRegex(diagnostic, r"key_sha256=[0-9a-f]{64}")
        self.assertNotIn(str(sensitive_authorization_id), diagnostic)
        self.assertNotIn("sensitive", diagnostic)


class MigrationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source = Path(self.temp_dir.name) / "迁移证据.db"
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY)")
            connection.commit()

    def test_backup_only_never_reads_target_environment_or_opens_postgres(self) -> None:
        import scripts.migrate_sqlite_to_postgres as cli

        stdout = io.StringIO()
        with patch.object(
            cli,
            "_read_target_environment",
            side_effect=AssertionError("backup-only read a target environment"),
        ), patch.object(cli, "migrate_sqlite_to_postgres") as migrate, redirect_stdout(
            stdout
        ):
            exit_code = cli.main(["--source", str(self.source), "--backup-only"])

        self.assertEqual(exit_code, 0)
        migrate.assert_not_called()
        output = stdout.getvalue()
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        self.assertIn("迁移证据", output)
        self.assertNotIn("\\u8fc1", output)

    def test_documented_script_invocation_imports_from_repository_root(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "migrate_sqlite_to_postgres.py"),
                "--source",
                str(self.source),
                "--backup-only",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])

    def test_dry_run_requires_environment_variable_name_and_never_prints_url(self) -> None:
        import scripts.migrate_sqlite_to_postgres as cli

        stdout = io.StringIO()
        with patch.object(cli, "migrate_sqlite_to_postgres") as migrate, redirect_stdout(
            stdout
        ):
            exit_code = cli.main(
                [
                    "--source",
                    str(self.source),
                    "--target-env",
                    "postgresql+psycopg://user:secret@127.0.0.1/db",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 1)
        migrate.assert_not_called()
        self.assertNotIn("secret", stdout.getvalue())
        self.assertNotIn("postgresql", stdout.getvalue())

    def test_cli_resolves_named_target_and_exit_code_follows_report_ok(self) -> None:
        import scripts.migrate_sqlite_to_postgres as cli

        credential_url = (
            "postgresql+psycopg://operator:do-not-print@127.0.0.1:55432/"
            "facai_ecommerce_test"
        )
        successful = MigrationReport(
            source_path=self.source.resolve(),
            source_sha256=_file_sha(self.source),
            backup_path=None,
            backup_sha256=None,
            applied=False,
            tables=(),
            amount_totals={},
            ok=True,
            snapshot=_snapshot_evidence(self.source),
        )
        stdout = io.StringIO()
        with patch.dict(os.environ, {"SAFE_TARGET": credential_url}, clear=True), patch.object(
            cli,
            "migrate_sqlite_to_postgres",
            return_value=successful,
        ) as migrate, redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--source",
                    str(self.source),
                    "--target-env",
                    "SAFE_TARGET",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 0)
        migrate.assert_called_once_with(
            source=self.source,
            target_url=credential_url,
            apply=False,
        )
        self.assertTrue(json.loads(stdout.getvalue())["ok"])
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["snapshot"]["retained"])
        self.assertIsNone(payload["snapshot"]["snapshot_path"])
        self.assertEqual(
            set(payload["snapshot"]),
            {field.name for field in fields(SnapshotEvidence)},
        )
        self.assertNotIn("do-not-print", stdout.getvalue())
        self.assertNotIn("postgresql", stdout.getvalue())

    def test_target_json_primary_key_is_redacted_in_cli_json(self) -> None:
        import integrations.migration as migration
        import scripts.migrate_sqlite_to_postgres as cli

        sensitive_primary_key = "customer-token-DO-NOT-PRINT"
        metadata = MetaData()
        diagnostic_table = Table(
            "diagnostic_json",
            metadata,
            Column("id", String, primary_key=True),
            Column("payload", JSON, nullable=False),
        )
        engine = create_engine("sqlite://")
        try:
            metadata.create_all(engine)
            with engine.begin() as connection:
                driver_connection = connection.connection.driver_connection
                driver_connection.create_function("json_typeof", 1, lambda _value: None)
                connection.execute(
                    diagnostic_table.insert(),
                    {"id": sensitive_primary_key, "payload": {"safe": True}},
                )
                state = migration._TableState(diagnostic_table)
                migration._validate_target_json(connection, diagnostic_table, state)
        finally:
            engine.dispose()

        table_report = state.report()
        self.assertEqual(len(table_report.json_errors), 1)
        library_diagnostic = table_report.json_errors[0]
        self.assertNotIn(sensitive_primary_key, library_diagnostic)
        self.assertIn("error_count=1", library_diagnostic)
        self.assertRegex(library_diagnostic, r"key_sha256=[0-9a-f]{64}")

        report = MigrationReport(
            source_path=self.source.resolve(),
            source_sha256=_file_sha(self.source),
            backup_path=None,
            backup_sha256=None,
            applied=False,
            tables=(table_report,),
            amount_totals={},
            ok=False,
            snapshot=_snapshot_evidence(self.source),
        )
        stdout = io.StringIO()
        with patch.dict(
            os.environ,
            {"SAFE_TARGET": "postgresql://redacted"},
            clear=True,
        ), patch.object(
            cli,
            "migrate_sqlite_to_postgres",
            return_value=report,
        ), redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--source",
                    str(self.source),
                    "--target-env",
                    "SAFE_TARGET",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertNotIn(sensitive_primary_key, output)
        self.assertIn("error_count=1", output)
        self.assertRegex(output, r"key_sha256=[0-9a-f]{64}")

    def test_backup_only_rejects_target_env_and_does_not_edit_configuration(self) -> None:
        import scripts.migrate_sqlite_to_postgres as cli

        env_path = ROOT / ".env"
        env_before = env_path.read_bytes() if env_path.exists() else None
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--source",
                    str(self.source),
                    "--target-env",
                    "SHOULD_NOT_BE_USED",
                    "--backup-only",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            env_path.read_bytes() if env_path.exists() else None,
            env_before,
        )


class PostgresCutoverRunbookTests(unittest.TestCase):
    def test_runbook_documents_evidence_gates_and_point_of_no_return(self) -> None:
        runbook = ROOT / "docs" / "runbooks" / "postgres-cutover.md"
        content = runbook.read_text(encoding="utf-8").lower()

        for required in (
            "preflight",
            "stop writes",
            "--backup-only",
            "sha-256",
            "alembic upgrade head",
            "--dry-run",
            "--apply",
            "row counts",
            "amount totals",
            "foreign keys",
            "json",
            "read-only",
            "smoke tests",
            "point of no return",
            "zero writes",
            "pitr",
            "forward fix",
            "never copy postgresql changes back into sqlite",
            "does not perform the cutover",
            "`source_sha256` is the composite",
            "`source_database_sha256`",
            "`source_wal_sha256`",
            "sequence changes are nontransactional",
            "sequence-stage failure",
            "reprovision",
        ):
            with self.subTest(required=required):
                self.assertIn(required, content)


@requires_disposable_postgres
class SQLiteToPostgresMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.addClassCleanup(cls._cleanup_target_schema)
        _run_guarded_alembic(command.downgrade, "base")
        _run_guarded_alembic(command.upgrade, "head")

    @classmethod
    def _cleanup_target_schema(cls) -> None:
        _run_guarded_alembic(command.downgrade, "base")
        url = _guarded_url()
        engine = create_engine(url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                tables = set(inspect(connection).get_table_names())
                if "alembic_version" in tables:
                    count = connection.execute(
                        text("SELECT COUNT(*) FROM alembic_version")
                    ).scalar_one()
                    if count:
                        raise AssertionError("alembic_version was not emptied")
                    connection.exec_driver_sql('DROP TABLE "alembic_version"')
        finally:
            engine.dispose()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source = Path(self.temp_dir.name) / "legacy.db"
        _create_legacy_fixture(self.source)
        self._empty_target()

    def tearDown(self) -> None:
        self._empty_target()
        self._assert_target_empty()

    def _target_engine(self):
        return create_engine(_guarded_url(), pool_pre_ping=True)

    def _empty_target(self) -> None:
        engine = self._target_engine()
        try:
            with engine.begin() as connection:
                for table in reversed(Base.metadata.sorted_tables):
                    connection.execute(table.delete())
        finally:
            engine.dispose()

    def _assert_target_empty(self) -> None:
        engine = self._target_engine()
        try:
            with engine.connect() as connection:
                counts = {
                    table.name: connection.execute(
                        select(func.count()).select_from(table)
                    ).scalar_one()
                    for table in Base.metadata.sorted_tables
                }
        finally:
            engine.dispose()
        self.assertEqual({name: count for name, count in counts.items() if count}, {})

    def _migrate(self, *, apply: bool) -> MigrationReport:
        target_url = _guarded_url()
        return migrate_sqlite_to_postgres(
            source=self.source,
            target_url=target_url,
            apply=apply,
        )

    def _insert_product(self, product_id: int = 1) -> None:
        _source_execute(
            self.source,
            (
                "INSERT INTO products(id, name, category, price, status) "
                "VALUES (?, '迁移蛋糕', '蛋糕', 19.9, 'active')",
                (product_id,),
            ),
        )

    def test_dry_run_copies_all_legacy_tables_in_transaction_then_rolls_back(self) -> None:
        import integrations.migration as migration

        self._insert_product()
        _source_execute(
            self.source,
            (
                "INSERT INTO qianchuan_import_batches"
                "(id, filename, file_sha256, row_count, imported_count, skipped_count) "
                "VALUES (1, 'report.xlsx', ?, 1, 1, 0)",
                ("a" * 64,),
            ),
            (
                "INSERT INTO qianchuan_material_performance"
                "(id, batch_id, material_id, material_name, transaction_amount, "
                "user_pay_amount, spend, raw_data) "
                "VALUES (1, 1, 'm-1', '素材', 10.25, 9.75, 2.5, ?)",
                ('{"nested":[1,true,"值"]}',),
            ),
        )

        source_before = self.source.read_bytes()
        snapshots: list[tuple[Path, int, str]] = []
        original_load = migration._load_source_rows

        def capture_snapshot(snapshot_path: Path):
            snapshots.append(
                (
                    snapshot_path,
                    snapshot_path.stat().st_size,
                    _file_sha(snapshot_path),
                )
            )
            return original_load(snapshot_path)

        with patch.object(
            migration,
            "_load_source_rows",
            side_effect=capture_snapshot,
        ):
            report = self._migrate(apply=False)

        self.assertTrue(report.ok)
        self.assertFalse(report.applied)
        self.assertIsNone(report.backup_path)
        self.assertIsNone(report.backup_sha256)
        self.assertEqual(report.source_sha256, hashlib.sha256(source_before).hexdigest())
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertEqual(len(snapshots), 1)
        snapshot_path, snapshot_size, snapshot_sha256 = snapshots[0]
        self.assertNotEqual(snapshot_path.resolve(), self.source.resolve())
        self.assertFalse(snapshot_path.exists())
        self.assertFalse(report.snapshot.retained)
        self.assertIsNone(report.snapshot.snapshot_path)
        self.assertEqual(report.snapshot.source_path, self.source.resolve())
        self.assertEqual(report.snapshot.source_size, len(source_before))
        self.assertEqual(report.snapshot.source_database_sha256, _file_sha(self.source))
        self.assertIsNone(report.snapshot.source_wal_path)
        self.assertEqual(report.snapshot.source_wal_size, 0)
        self.assertIsNone(report.snapshot.source_wal_sha256)
        self.assertEqual(report.snapshot.source_integrity_check, "ok")
        self.assertEqual(report.snapshot.snapshot_integrity_check, "ok")
        self.assertEqual(
            report.snapshot.source_page_count,
            report.snapshot.snapshot_page_count,
        )
        self.assertEqual(report.snapshot.snapshot_size, snapshot_size)
        self.assertEqual(report.snapshot.snapshot_sha256, snapshot_sha256)
        self.assertTrue(report.snapshot.ok)
        self.assertEqual(len(report.tables), len(Base.metadata.tables))
        by_table = {item.table: item for item in report.tables}
        self.assertEqual(by_table["products"].source_rows, 1)
        self.assertEqual(by_table["products"].target_rows, 1)
        for table_name in OPTIONAL_INTEGRATION_TABLES:
            self.assertEqual(
                (by_table[table_name].source_rows, by_table[table_name].target_rows),
                (0, 0),
            )
        self.assertEqual(
            report.amount_totals,
            {
                "creator_collaborations.actual_paid_cents": "0",
                "qianchuan_material_performance.spend": "2.5",
                "qianchuan_material_performance.transaction_amount": "10.25",
                "qianchuan_material_performance.user_pay_amount": "9.75",
            },
        )
        self._assert_target_empty()

    def test_target_must_be_at_head_and_empty_before_copy(self) -> None:
        self._insert_product()
        engine = self._target_engine()
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE alembic_version SET version_num = 'wrong-revision'")
                )
            try:
                with self.assertRaisesRegex(MigrationError, "Alembic head"):
                    self._migrate(apply=False)
            finally:
                current_head = ScriptDirectory.from_config(
                    _alembic_config(_guarded_url())
                ).get_current_head()
                self.assertIsNotNone(current_head)
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "UPDATE alembic_version "
                            "SET version_num = :current_head"
                        ),
                        {"current_head": current_head},
                    )

            with engine.begin() as connection:
                connection.execute(
                    Base.metadata.tables["products"].insert(),
                    {"name": "existing", "category": "guard", "price": 1.0},
                )
            with self.assertRaisesRegex(MigrationError, "not empty"):
                self._migrate(apply=False)
        finally:
            engine.dispose()

    def test_apply_creates_fresh_backup_commits_and_advances_integer_sequence(self) -> None:
        self._insert_product(product_id=41)
        source_sha = _file_sha(self.source)

        report = self._migrate(apply=True)

        self.assertTrue(report.ok)
        self.assertTrue(report.applied)
        self.assertEqual(report.source_sha256, source_sha)
        self.assertIsNotNone(report.backup_path)
        self.assertTrue(report.backup_path.is_file())
        self.assertEqual(report.backup_sha256, _file_sha(report.backup_path))
        self.assertTrue(report.snapshot.retained)
        self.assertEqual(report.snapshot.snapshot_path, report.backup_path)
        self.assertEqual(report.snapshot.snapshot_size, report.backup_path.stat().st_size)
        self.assertEqual(report.snapshot.snapshot_sha256, report.backup_sha256)
        self.assertTrue(report.snapshot.snapshot_path.is_file())
        self.assertTrue(report.snapshot.ok)
        engine = self._target_engine()
        try:
            with engine.begin() as connection:
                migrated_ids = connection.execute(
                    select(Base.metadata.tables["products"].c.id)
                ).scalars().all()
                next_id = connection.execute(
                    Base.metadata.tables["products"]
                    .insert()
                    .values(name="next", category="sequence", price=1.0)
                    .returning(Base.metadata.tables["products"].c.id)
                ).scalar_one()
        finally:
            engine.dispose()
        self.assertEqual(migrated_ids, [41])
        self.assertEqual(next_id, 42)

    def test_sequence_stage_failure_warns_about_nontransactional_side_effects(self) -> None:
        import integrations.migration as migration
        import scripts.migrate_sqlite_to_postgres as cli

        self._insert_product(product_id=41)
        exception_sentinel = "sequence-secret-DO-NOT-PRINT"

        def change_sequence_then_fail(connection):
            sequence = connection.execute(
                select(func.pg_get_serial_sequence("products", "id"))
            ).scalar_one()
            connection.execute(
                text(
                    "SELECT setval(CAST(:sequence AS regclass), "
                    ":value, :is_called)"
                ),
                {"sequence": sequence, "value": 999, "is_called": True},
            )
            raise SQLAlchemyError(exception_sentinel)

        with patch.object(
            migration,
            "_advance_integer_sequences",
            side_effect=change_sequence_then_fail,
        ):
            report = self._migrate(apply=True)

        self.assertFalse(report.ok)
        self.assertFalse(report.applied)
        self.assertTrue(report.snapshot.retained)
        self.assertEqual(len(report.warnings), 1)
        warning = report.warnings[0].lower()
        self.assertIn("sequence", warning)
        self.assertIn("nontransactional", warning)
        self.assertIn("reprovision", warning)
        payload = json.dumps(cli._json_value(report), ensure_ascii=False)
        self.assertIn("sequence-stage failure", payload.lower())
        self.assertNotIn(exception_sentinel, payload)
        self._assert_target_empty()

    def test_json_sql_null_and_json_literal_null_remain_distinct(self) -> None:
        _source_execute(
            self.source,
            (
                "INSERT INTO products"
                "(id, name, category, price, status, pending_fields) "
                "VALUES (1, 'sql-null', 'test', 1.0, 'active', NULL)",
                (),
            ),
            (
                "INSERT INTO products"
                "(id, name, category, price, status, pending_fields) "
                "VALUES (2, 'json-null', 'test', 2.0, 'active', 'null')",
                (),
            ),
        )

        report = self._migrate(apply=True)

        self.assertTrue(report.ok)
        engine = self._target_engine()
        try:
            with engine.connect() as connection:
                null_evidence = connection.execute(
                    text(
                        "SELECT id, pending_fields IS NULL AS sql_null, "
                        "json_typeof(pending_fields) AS json_kind "
                        "FROM products ORDER BY id"
                    )
                ).all()
        finally:
            engine.dispose()
        self.assertEqual(
            null_evidence,
            [(1, True, None), (2, False, "null")],
        )

    def test_broken_json_and_orphan_fk_return_failed_report_and_empty_target(self) -> None:
        cases = (
            (
                (
                    "INSERT INTO script_templates"
                    "(id, name, video_type, structure) VALUES (1, 'bad', 'talk', ?)",
                    ("{broken",),
                ),
                "script_templates",
                "json_errors",
            ),
            (
                (
                    "INSERT INTO generated_scripts"
                    "(id, product_id, script_content) VALUES (1, 999, 'orphan')",
                    (),
                ),
                "generated_scripts",
                "orphan_foreign_keys",
            ),
        )
        for statement, table_name, error_field in cases:
            with self.subTest(error=error_field):
                self._empty_target()
                self.source.unlink()
                _create_legacy_fixture(self.source)
                _source_execute(self.source, statement)

                report = self._migrate(apply=True)

                self.assertFalse(report.ok)
                self.assertFalse(report.applied)
                self.assertIsNotNone(report.backup_path)
                self.assertTrue(report.snapshot.retained)
                self.assertEqual(report.snapshot.snapshot_path, report.backup_path)
                self.assertTrue(report.snapshot.snapshot_path.is_file())
                table_report = {item.table: item for item in report.tables}[table_name]
                self.assertTrue(getattr(table_report, error_field))
                self._assert_target_empty()

    def test_apply_blocks_writer_after_lock_through_postgres_commit(self) -> None:
        import integrations.migration as migration

        wal_keeper = sqlite3.connect(self.source)
        self.addCleanup(wal_keeper.close)
        wal_keeper.execute("PRAGMA journal_mode=WAL")
        wal_keeper.execute("PRAGMA wal_autocheckpoint=0")
        wal_keeper.execute(
            "INSERT INTO products(id, name, category, price, status) "
            "VALUES (1, 'verified-snapshot', 'test', 1.0, 'active')"
        )
        wal_keeper.commit()
        wal_path = Path(f"{self.source}-wal")
        source_state_before = migration._sqlite_state(self.source)
        source_main_before = self.source.read_bytes()
        source_wal_before = wal_path.read_bytes()
        source_logical_before = _sqlite_logical_sha(self.source)
        writer_error_codes: list[int | None] = []
        original_advance = migration._advance_integer_sequences

        def attempt_write_before_postgres_commit(connection):
            contender = sqlite3.connect(self.source, timeout=0)
            try:
                contender.execute("PRAGMA busy_timeout=0")
                contender.execute(
                    "INSERT INTO products(id, name, category, price, status) "
                    "VALUES (2, 'late-writer', 'test', 2.0, 'active')"
                )
                contender.commit()
            except sqlite3.OperationalError as exc:
                writer_error_codes.append(exc.sqlite_errorcode)
                contender.rollback()
            else:
                writer_error_codes.append(None)
            finally:
                contender.close()
            original_advance(connection)

        with patch.object(
            migration,
            "_advance_integer_sequences",
            side_effect=attempt_write_before_postgres_commit,
        ):
            report = self._migrate(apply=True)

        self.assertTrue(report.ok)
        self.assertTrue(report.applied)
        self.assertEqual(writer_error_codes, [sqlite3.SQLITE_BUSY])
        self.assertEqual(migration._sqlite_state(self.source), source_state_before)
        self.assertEqual(self.source.read_bytes(), source_main_before)
        self.assertEqual(wal_path.read_bytes(), source_wal_before)
        self.assertEqual(_sqlite_logical_sha(self.source), source_logical_before)
        self.assertIsNotNone(report.backup_path)
        self.assertEqual(
            report.source_sha256,
            source_state_before.sha256,
        )

        with closing(sqlite3.connect(self.source, timeout=0)) as after_release:
            after_release.execute(
                "INSERT INTO products(id, name, category, price, status) "
                "VALUES (2, 'after-release', 'test', 2.0, 'active')"
            )
            after_release.commit()

    def test_apply_aborts_when_writer_commits_before_source_lock(self) -> None:
        import integrations.migration as migration

        self._insert_product(product_id=1)
        original_lock = migration._lock_sqlite_source
        committed_state: list[object] = []

        def commit_before_lock(source_path: Path):
            _source_execute(
                source_path,
                (
                    "INSERT INTO products(id, name, category, price, status) "
                    "VALUES (2, 'before-lock', 'test', 2.0, 'active')",
                    (),
                ),
            )
            committed_state.append(migration._sqlite_state(source_path))
            return original_lock(source_path)

        with patch.object(
            migration,
            "_lock_sqlite_source",
            side_effect=commit_before_lock,
        ):
            report = self._migrate(apply=True)

        self.assertFalse(report.ok)
        self.assertFalse(report.applied)
        self.assertEqual(len(committed_state), 1)
        self.assertNotEqual(report.source_sha256, committed_state[0].sha256)
        self.assertTrue(
            any(
                "source" in error.lower()
                and "changed" in error.lower()
                and "lock" in error.lower()
                for table in report.tables
                for error in table.json_errors
            )
        )
        self._assert_target_empty()

    def test_unregistered_missing_or_unknown_columns_fail_closed_without_source_mutation(self) -> None:
        _source_execute(
            self.source,
            ("ALTER TABLE products DROP COLUMN status", ()),
            ("ALTER TABLE products ADD COLUMN future_payload TEXT", ()),
            (
                "INSERT INTO products(id, name, category, price, future_payload) "
                "VALUES (1, 'drift', 'test', 1.0, 'must-not-drop')",
                (),
            ),
        )
        before = self.source.read_bytes()

        report = self._migrate(apply=False)

        self.assertFalse(report.ok)
        product_report = {item.table: item for item in report.tables}["products"]
        self.assertTrue(any("missing current column" in error for error in product_report.json_errors))
        self.assertTrue(any("unknown source column" in error for error in product_report.json_errors))
        self.assertEqual(self.source.read_bytes(), before)
        self._assert_target_empty()

    def test_registered_deterministic_adapter_is_counted_and_keeps_source_hash(self) -> None:
        _source_execute(
            self.source,
            ("ALTER TABLE products DROP COLUMN status", ()),
            (
                "INSERT INTO products(id, name, category, price) "
                "VALUES (1, 'legacy', 'test', 1.0)",
                (),
            ),
        )
        before_sha = _file_sha(self.source)
        adapter = LegacyColumnAdapter(
            description="Historical fixtures predate products.status",
            source_schema_sha256=_sqlite_table_fingerprint(self.source, "products"),
            derive=lambda row: "active" if row["price"] is not None else None,
        )

        with patch.dict(
            LEGACY_COLUMN_ADAPTERS,
            {("products", "status"): adapter},
            clear=False,
        ):
            report = self._migrate(apply=False)

        self.assertTrue(report.ok)
        product_report = {item.table: item for item in report.tables}["products"]
        self.assertEqual(product_report.synthesized_columns, {"status": 1})
        self.assertEqual(report.source_sha256, before_sha)
        self.assertEqual(_file_sha(self.source), before_sha)
        self._assert_target_empty()

    def test_production_adapter_registry_is_minimal_and_schema_fingerprinted(self) -> None:
        self.assertEqual(
            set(LEGACY_COLUMN_ADAPTERS),
            {("viral_scripts", "is_high_conversion")},
        )
        self.assertEqual(
            LEGACY_COLUMN_ADAPTERS[
                ("viral_scripts", "is_high_conversion")
            ].derive({}),
            0,
        )
        _source_execute(
            self.source,
            ("ALTER TABLE viral_scripts DROP COLUMN is_high_conversion", ()),
            (
                "INSERT INTO viral_scripts(id, title, script_content) "
                "VALUES (1, 'historical', 'adapter evidence')",
                (),
            ),
        )
        self.assertEqual(
            _sqlite_table_fingerprint(self.source, "viral_scripts"),
            "4ece88ef1e2ecae46534018097bcd4ffe3397f3a55dd4dc3827d2d3891abeab0",
        )
        before_sha = _file_sha(self.source)

        report = self._migrate(apply=False)

        self.assertTrue(report.ok)
        table_report = {item.table: item for item in report.tables}["viral_scripts"]
        self.assertEqual(
            table_report.synthesized_columns,
            {"is_high_conversion": 1},
        )
        self.assertEqual(report.source_sha256, before_sha)
        self.assertEqual(_file_sha(self.source), before_sha)
        self._assert_target_empty()

    def test_adapter_rejects_same_missing_column_on_unapproved_schema_fingerprint(self) -> None:
        _source_execute(
            self.source,
            ("ALTER TABLE viral_scripts DROP COLUMN is_high_conversion", ()),
            (
                "INSERT INTO viral_scripts(id, title, script_content) "
                "VALUES (1, 'unapproved', 'must fail closed')",
                (),
            ),
        )
        before_sha = _file_sha(self.source)
        mismatched = LegacyColumnAdapter(
            description="deliberately wrong schema approval",
            source_schema_sha256="0" * 64,
            derive=lambda _row: 0,
        )

        with patch.dict(
            LEGACY_COLUMN_ADAPTERS,
            {("viral_scripts", "is_high_conversion"): mismatched},
            clear=False,
        ):
            report = self._migrate(apply=False)

        self.assertFalse(report.ok)
        table_report = {item.table: item for item in report.tables}["viral_scripts"]
        self.assertTrue(
            any("fingerprint" in error.lower() for error in table_report.json_errors)
        )
        self.assertEqual(_file_sha(self.source), before_sha)
        self._assert_target_empty()

    def test_nullable_partial_unique_allows_nulls_and_rejects_duplicate_values(
        self,
    ) -> None:
        insert_creator = (
            "INSERT INTO creators("
            "id, platform, platform_uid, platform_uid_normalized, "
            "douyin_handle, douyin_handle_normalized, nickname, stage, tags, "
            "created_at, updated_at"
            ") VALUES (?, 'douyin', ?, ?, ?, ?, ?, 'lead', '[]', "
            "'2026-07-13 00:00:00', '2026-07-13 00:00:00')"
        )
        _source_execute(
            self.source,
            (insert_creator, (1, None, None, "h1", "h1", "null-one")),
            (insert_creator, (2, None, None, "h2", "h2", "null-two")),
        )

        null_report = self._migrate(apply=False)

        self.assertTrue(null_report.ok)
        null_table_report = {item.table: item for item in null_report.tables}[
            "creators"
        ]
        self.assertFalse(
            any(
                "uq_creators_platform_uid" in duplicate
                for duplicate in null_table_report.duplicate_unique_keys
            )
        )
        self._assert_target_empty()

        sensitive_uid = "sensitive-platform-uid"
        _source_execute(
            self.source,
            ("DROP INDEX uq_creators_platform_uid", ()),
            (
                insert_creator,
                (3, sensitive_uid, sensitive_uid, "h3", "h3", "duplicate-one"),
            ),
            (
                insert_creator,
                (4, sensitive_uid, sensitive_uid, "h4", "h4", "duplicate-two"),
            ),
        )

        duplicate_report = self._migrate(apply=False)

        self.assertFalse(duplicate_report.ok)
        duplicate_table_report = {
            item.table: item for item in duplicate_report.tables
        }["creators"]
        duplicate = next(
            duplicate
            for duplicate in duplicate_table_report.duplicate_unique_keys
            if "uq_creators_platform_uid" in duplicate
        )
        self.assertIn("duplicate_count=2", duplicate)
        self.assertRegex(duplicate, r"key_sha256=[0-9a-f]{64}")
        self.assertNotIn(sensitive_uid, duplicate)
        self._assert_target_empty()

    def test_duplicate_partial_unique_key_is_reported_with_null_semantics(self) -> None:
        _source_execute(
            self.source,
            ("DROP INDEX uq_creator_import_committed_file", ()),
            (
                "INSERT INTO creator_import_batches"
                "(id, token, kind, source_type, filename, file_sha256, status, "
                "mapping, errors, row_count, imported_count, updated_count, "
                "skipped_count, error_count, created_at) "
                "VALUES (1, 't1', 'creator', 'xlsx', 'a.xlsx', ?, 'committed', "
                "'{}', '[]', 1, 1, 0, 0, 0, '2026-07-13 00:00:00')",
                ("b" * 64,),
            ),
            (
                "INSERT INTO creator_import_batches"
                "(id, token, kind, source_type, filename, file_sha256, status, "
                "mapping, errors, row_count, imported_count, updated_count, "
                "skipped_count, error_count, created_at) "
                "VALUES (2, 't2', 'creator', 'xlsx', 'b.xlsx', ?, 'committed', "
                "'{}', '[]', 1, 1, 0, 0, 0, '2026-07-13 00:00:00')",
                ("b" * 64,),
            ),
        )

        report = self._migrate(apply=False)

        self.assertFalse(report.ok)
        table_report = {item.table: item for item in report.tables}[
            "creator_import_batches"
        ]
        duplicate = next(
            duplicate
            for duplicate in table_report.duplicate_unique_keys
            if "uq_creator_import_committed_file" in duplicate
        )
        self.assertIn("duplicate_count=2", duplicate)
        self.assertRegex(duplicate, r"key_sha256=[0-9a-f]{64}")
        self.assertNotIn("b" * 64, duplicate)
        self._assert_target_empty()


if __name__ == "__main__":
    unittest.main()
