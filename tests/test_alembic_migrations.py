import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


class AlembicMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "migration.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        import database

        self.database = database
        self.original_engine = database.engine
        self.original_url = database.DATABASE_URL
        self.original_session = database.SessionLocal
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        database.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def tearDown(self):
        self.database.engine = self.original_engine
        self.database.DATABASE_URL = self.original_url
        self.database.SessionLocal = self.original_session
        self.engine.dispose()
        self.tmp.cleanup()

    def test_new_database_reaches_single_declared_head_idempotently(self):
        application_logger = logging.getLogger("services.script_generator")
        application_logger.disabled = False
        self.database.init_db()
        self.database.init_db()

        tables = set(inspect(self.engine).get_table_names())
        with self.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

        self.assertEqual(revision, "20260720_0003")
        self.assertFalse(application_logger.disabled)
        self.assertGreaterEqual(
            tables,
            {"products", "creators", "audit_events", "durable_tasks"},
        )

    def test_unversioned_existing_database_is_adopted_without_data_loss(self):
        import creator_models  # noqa: F401
        import models  # noqa: F401

        self.database.Base.metadata.create_all(bind=self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO products (name, category, price, status, created_at) "
                    "VALUES ('legacy-product', 'legacy', 1, 'active', CURRENT_TIMESTAMP)"
                )
            )

        self.database.init_db()

        with self.engine.connect() as connection:
            name = connection.execute(text("SELECT name FROM products")).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        self.assertEqual(name, "legacy-product")
        self.assertEqual(revision, "20260720_0003")

    def test_current_database_does_not_run_legacy_startup_schema_mutators(self):
        self.database.init_db()

        with (
            patch.object(self.database.Base.metadata, "create_all") as create_all,
            patch.object(self.database, "_ensure_creator_indexes") as creator_indexes,
            patch.object(self.database, "_ensure_compatible_columns") as compatible_columns,
            patch.object(
                self.database,
                "_ensure_creator_integrity_triggers",
            ) as creator_triggers,
            patch.object(
                self.database,
                "_ensure_integration_connection_provider_unique",
            ) as integration_parent_key,
        ):
            self.database.init_db()

        create_all.assert_not_called()
        creator_indexes.assert_not_called()
        compatible_columns.assert_not_called()
        creator_triggers.assert_not_called()
        integration_parent_key.assert_not_called()

    def test_failed_upgrade_restores_pre_migration_database(self):
        self.database.init_db()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO products (name, category, price, status, created_at) "
                    "VALUES ('keep-me', 'legacy', 1, 'active', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(text("DELETE FROM alembic_version"))

        def destructive_failure(config, _target):
            connection = config.attributes["connection"]
            connection.execute(text("DELETE FROM products"))
            connection.commit()
            raise RuntimeError("simulated migration failure")

        with patch("alembic.command.upgrade", side_effect=destructive_failure):
            with self.assertRaisesRegex(RuntimeError, "simulated migration failure"):
                self.database._run_schema_migrations()

        with self.engine.connect() as connection:
            names = connection.execute(text("SELECT name FROM products")).scalars().all()
        self.assertEqual(names, ["keep-me"])

    def test_post_upgrade_drift_check_also_restores_pre_migration_database(self):
        self.database.init_db()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO products (name, category, price, status, created_at) "
                    "VALUES ('restore-after-drift', 'legacy', 1, 'active', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(text("DELETE FROM alembic_version"))

        with patch.object(self.database, "_schema_migration_required", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "schema drift detected after"):
                self.database._run_schema_migrations()

        with self.engine.connect() as connection:
            names = connection.execute(text("SELECT name FROM products")).scalars().all()
            revisions = connection.execute(text("SELECT version_num FROM alembic_version")).all()
        self.assertEqual(names, ["restore-after-drift"])
        self.assertEqual(revisions, [])


if __name__ == "__main__":
    unittest.main()
