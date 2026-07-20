import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Enum, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import integration_models
from alembic import command
from database import Base
from tests.postgres_test_support import requires_disposable_postgres

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"
ALEMBIC_ENV = ROOT / "alembic" / "env.py"
BASELINE = ROOT / "alembic" / "versions" / "20260713_0001_postgres_baseline.py"
SYNC_REVISION = ROOT / "alembic" / "versions" / "20260713_0002_sync_and_commerce.py"
BASELINE_REVISION = "20260713_0001"
REVISION = "20260713_0002"

SYNC_CONTROL_TABLES = {
    integration_models.IntegrationArchiveManifest.__tablename__,
    integration_models.IntegrationExportJob.__tablename__,
    integration_models.IntegrationJob.__tablename__,
    integration_models.IntegrationSyncCheckpoint.__tablename__,
    integration_models.IntegrationSyncError.__tablename__,
    integration_models.IntegrationSyncRun.__tablename__,
    integration_models.IntegrationWorkerHeartbeat.__tablename__,
}
SYNC_AND_COMMERCE_TABLES = SYNC_CONTROL_TABLES | {
    name for name in Base.metadata.tables if name.startswith("commerce_")
}
BASELINE_TABLES = set(Base.metadata.tables) - SYNC_AND_COMMERCE_TABLES

EXPECTED_ENUM_CHECKS = {
    ("integration_app_configs", "provider"): (
        "ck_integration_app_configs_provider",
        ("qianchuan", "doudian", "taobao", "pdd"),
    ),
    ("integration_authorizations", "provider"): (
        "ck_integration_authorizations_provider",
        ("qianchuan", "doudian", "taobao", "pdd"),
    ),
    ("integration_authorizations", "status"): (
        "ck_integration_authorizations_status",
        ("active", "reauthorization_required", "revoked", "disabled"),
    ),
    ("integration_connections", "provider"): (
        "ck_integration_connections_provider",
        ("qianchuan", "doudian", "taobao", "pdd"),
    ),
    ("integration_connections", "connection_type"): (
        "ck_integration_connections_connection_type",
        ("shop", "ad_account"),
    ),
    ("integration_connections", "status"): (
        "ck_integration_connections_status",
        (
            "setup_required",
            "authorizing",
            "active",
            "permission_limited",
            "syncing",
            "degraded",
            "reauthorization_required",
            "disabled",
        ),
    ),
    ("integration_oauth_states", "provider"): (
        "ck_integration_oauth_states_provider",
        ("qianchuan", "doudian", "taobao", "pdd"),
    ),
    ("integration_security_audit", "provider"): (
        "ck_integration_security_audit_provider",
        ("qianchuan", "doudian", "taobao", "pdd"),
    ),
}

for table in Base.metadata.sorted_tables:
    for column in table.columns:
        if isinstance(column.type, Enum) and column.type.native_enum is False:
            EXPECTED_ENUM_CHECKS.setdefault(
                (table.name, column.name),
                (column.type.name, tuple(column.type.enums)),
            )


def _task_files_exist() -> None:
    missing = [
        path
        for path in (ALEMBIC_INI, ALEMBIC_ENV, BASELINE, SYNC_REVISION)
        if not path.is_file()
    ]
    if missing:
        raise AssertionError(
            "Alembic configuration does not exist: "
            + ", ".join(path.relative_to(ROOT).as_posix() for path in missing)
        )


def _guarded_url() -> str:
    from integrations.db_safety import assert_disposable_postgres

    return assert_disposable_postgres(
        url_env="FACAI_TEST_DATABASE_URL",
        acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
    )


def _config_for(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _run_guarded_migration(operation, revision: str) -> None:
    url = _guarded_url()
    config = _config_for(url)
    with patch.dict(
        os.environ,
        {"FACAI_MIGRATION_DATABASE_URL": url},
        clear=False,
    ):
        operation(config, revision)


def _guarded_engine():
    url = _guarded_url()
    return create_engine(url, pool_pre_ping=True)


class AlembicSourceContractTests(unittest.TestCase):
    def test_class_cleanup_is_registered_before_destructive_setup(self):
        source = Path(__file__).read_text(encoding="utf-8")
        class_start = source.index("\nclass AlembicPostgresTests(unittest.TestCase):")
        setup_start = source.index("    def setUpClass(cls):", class_start)
        setup_end = source.index("    def _cleanup_database(cls):", setup_start)
        setup_source = source[setup_start:setup_end]

        self.assertLess(
            setup_source.index("addClassCleanup"),
            setup_source.index("_run_guarded_migration"),
        )

    def test_env_imports_every_model_before_target_metadata(self):
        _task_files_exist()
        source = ALEMBIC_ENV.read_text(encoding="utf-8")
        target_position = source.index("target_metadata = Base.metadata")

        for module_name in (
            "models",
            "creator_models",
            "integration_models",
            "commerce_models",
        ):
            with self.subTest(module=module_name):
                self.assertLess(
                    source.index(f"import {module_name}"),
                    target_position,
                )

    def test_env_requires_credentials_from_environment_and_compares_schema_details(self):
        _task_files_exist()
        source = ALEMBIC_ENV.read_text(encoding="utf-8")
        alembic_config = Config(str(ALEMBIC_INI))

        self.assertEqual(alembic_config.get_main_option("sqlalchemy.url"), "")
        self.assertIn("FACAI_MIGRATION_DATABASE_URL", source)
        self.assertIn("DATABASE_URL", source)
        self.assertIn("compare_type=True", source)
        self.assertIn("compare_server_default=True", source)
        self.assertIn("transaction_per_migration=True", source)
        self.assertIn("disable_existing_loggers=False", source)
        self.assertNotIn("postgresql+psycopg://", source)

    def test_baseline_is_explicit_and_does_not_import_application_models(self):
        _task_files_exist()
        source = BASELINE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_modules.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        application_modules = {
            "database",
            "models",
            "creator_models",
            "integration_models",
            "commerce_models",
        }
        calls = {
            f"{node.func.value.id}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        }

        self.assertTrue(application_modules.isdisjoint(imported_modules))
        self.assertIn("op.create_table", calls)
        self.assertIn("op.create_index", calls)
        self.assertNotIn("Base.metadata.create_all", source)
        self.assertNotIn("create_all(", source)

    def test_sync_revision_is_explicit_and_does_not_import_application_models(self):
        _task_files_exist()
        source = SYNC_REVISION.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_modules.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        application_modules = {
            "database",
            "models",
            "creator_models",
            "integration_models",
            "commerce_models",
        }
        calls = {
            f"{node.func.value.id}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        }

        self.assertTrue(application_modules.isdisjoint(imported_modules))
        self.assertIn("op.create_table", calls)
        self.assertIn("op.create_index", calls)
        self.assertNotIn("Base.metadata.create_all", source)
        self.assertNotIn("create_all(", source)
        self.assertIn("down_revision: Union[str, Sequence[str], None] = '20260713_0001'", source)


@requires_disposable_postgres
class AlembicPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _task_files_exist()
        cls.addClassCleanup(cls._cleanup_database)
        _run_guarded_migration(command.downgrade, "base")
        _run_guarded_migration(command.upgrade, "head")

    @classmethod
    def _cleanup_database(cls):
        _run_guarded_migration(command.downgrade, "base")
        cleanup_engine = _guarded_engine()
        try:
            with cleanup_engine.begin() as connection:
                tables = sorted(inspect(connection).get_table_names())
                unexpected = [
                    table for table in tables if table != "alembic_version"
                ]
                if unexpected:
                    raise AssertionError(
                        f"Alembic cleanup left unexpected tables behind: {unexpected}"
                    )
                if "alembic_version" in tables:
                    revision_count = connection.execute(
                        text("SELECT COUNT(*) FROM alembic_version")
                    ).scalar_one()
                    if revision_count:
                        raise AssertionError(
                            "Refusing to drop a non-empty alembic_version table"
                        )
                    connection.exec_driver_sql('DROP TABLE "alembic_version"')
        finally:
            cleanup_engine.dispose()

        verification_engine = _guarded_engine()
        try:
            remaining = sorted(inspect(verification_engine).get_table_names())
            if remaining:
                raise AssertionError(
                    f"Alembic cleanup left tables behind: {remaining}"
                )
        finally:
            verification_engine.dispose()

    def test_upgrade_downgrade_upgrade_round_trip(self):
        _run_guarded_migration(command.downgrade, "base")
        _run_guarded_migration(command.upgrade, "head")
        first_engine = _guarded_engine()
        try:
            with first_engine.connect() as connection:
                first_tables = set(inspect(connection).get_table_names())
                first_revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        finally:
            first_engine.dispose()

        self.assertEqual(first_revision, REVISION)
        self.assertEqual(first_tables - {"alembic_version"}, set(Base.metadata.tables))
        self.assertEqual(
            len(first_tables - {"alembic_version"}),
            len(Base.metadata.tables),
        )
        self.assertIn("products", first_tables)
        self.assertIn("creator_import_batches", first_tables)
        self.assertIn("integration_app_configs", first_tables)
        self.assertIn("integration_jobs", first_tables)
        self.assertIn("commerce_orders", first_tables)

        _run_guarded_migration(command.downgrade, "base")
        _run_guarded_migration(command.upgrade, "head")
        second_engine = _guarded_engine()
        try:
            with second_engine.connect() as connection:
                second_revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        finally:
            second_engine.dispose()

        self.assertEqual(second_revision, REVISION)
        script = ScriptDirectory.from_config(_config_for(_guarded_url()))
        self.assertEqual(script.get_current_head(), REVISION)

    def test_downgrade_to_baseline_removes_only_sync_and_commerce_tables(self):
        _run_guarded_migration(command.downgrade, BASELINE_REVISION)
        engine = _guarded_engine()
        try:
            with engine.connect() as connection:
                tables = set(inspect(connection).get_table_names())
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        finally:
            engine.dispose()

        self.assertEqual(revision, BASELINE_REVISION)
        self.assertEqual(tables - {"alembic_version"}, BASELINE_TABLES)
        self.assertIn("integration_connections", tables)
        self.assertIn("products", tables)
        self.assertNotIn("integration_jobs", tables)
        self.assertNotIn("commerce_orders", tables)

        _run_guarded_migration(command.upgrade, REVISION)

    def test_database_matches_complete_metadata(self):
        engine = _guarded_engine()
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection,
                    opts={
                        "compare_type": True,
                        "compare_server_default": True,
                    },
                )
                diff = compare_metadata(context, Base.metadata)
        finally:
            engine.dispose()

        self.assertEqual(diff, [])

    def test_every_fixed_enum_has_expected_named_check_constraint(self):
        model_enum_checks = {}
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if isinstance(column.type, Enum) and column.type.native_enum is False:
                    model_enum_checks[(table.name, column.name)] = (
                        column.type.name,
                        tuple(column.type.enums),
                    )

        self.assertEqual(model_enum_checks, EXPECTED_ENUM_CHECKS)
        engine = _guarded_engine()
        try:
            with engine.connect() as connection:
                inspector = inspect(connection)
                for (table_name, column_name), (constraint_name, values) in (
                    EXPECTED_ENUM_CHECKS.items()
                ):
                    with self.subTest(table=table_name, column=column_name):
                        constraints = {
                            item["name"]: item["sqltext"]
                            for item in inspector.get_check_constraints(table_name)
                        }
                        self.assertIn(constraint_name, constraints)
                        sqltext = constraints[constraint_name]
                        self.assertIn(column_name, sqltext)
                        for value in values:
                            self.assertIn(value, sqltext)
        finally:
            engine.dispose()

    def test_migrated_oauth_constraint_rejects_percent_encoded_return_path(self):
        engine = _guarded_engine()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with self.assertRaises(IntegrityError):
                        connection.execute(
                            text(
                                "INSERT INTO integration_oauth_states ("
                                "state_hash, provider, initiating_session_digest, "
                                "return_path, expires_at, created_at"
                                ") VALUES ("
                                ":state_hash, 'qianchuan', :session_digest, "
                                ":return_path, now(), now()"
                                ")"
                            ),
                            {
                                "state_hash": "a" * 64,
                                "session_digest": "b" * 64,
                                "return_path": "/app/api-connections/%2e%2e/admin",
                            },
                        )
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
