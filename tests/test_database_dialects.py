import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

import creator_models
import database


class DatabaseDialectTests(unittest.TestCase):
    def test_all_supported_database_engines_hide_bound_parameters(self):
        for url in (
            "sqlite:///:memory:",
            "sqlite+pysqlite:///:memory:",
            "postgresql+psycopg://u:p@127.0.0.1:55432/facai",
        ):
            with self.subTest(url=url):
                engine = database.create_database_engine(url)
                try:
                    self.assertTrue(engine.hide_parameters)
                finally:
                    engine.dispose()

    def test_sqlite_engine_keeps_thread_override(self):
        with patch("database.create_engine", wraps=database.create_engine) as create_engine:
            engine = database.create_database_engine("sqlite:///:memory:")
        try:
            self.assertEqual(
                create_engine.call_args.kwargs.get("connect_args"),
                {"check_same_thread": False},
            )
            self.assertEqual(engine.dialect.name, "sqlite")
            with engine.connect() as connection:
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(),
                    1,
                )
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
                    5000,
                )
        finally:
            engine.dispose()

    def test_driver_qualified_sqlite_engine_keeps_options_and_pragmas(self):
        with patch("database.create_engine", wraps=database.create_engine) as create_engine:
            engine = database.create_database_engine("sqlite+pysqlite:///:memory:")
        try:
            self.assertEqual(
                create_engine.call_args.kwargs.get("connect_args"),
                {"check_same_thread": False},
            )
            with engine.connect() as connection:
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(),
                    1,
                )
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
                    5000,
                )
        finally:
            engine.dispose()

    def test_driver_qualified_sqlite_parent_is_created_for_file_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "nested" / "facai.db"

            database._ensure_sqlite_parent(
                f"sqlite+pysqlite:///{database_path.as_posix()}"
            )

            self.assertTrue(database_path.parent.is_dir())

    def test_driver_qualified_sqlite_file_database_enables_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "facai.db"
            engine = database.create_database_engine(
                f"sqlite+pysqlite:///{database_path.as_posix()}"
            )
            try:
                with engine.connect() as connection:
                    journal_mode = connection.exec_driver_sql(
                        "PRAGMA journal_mode"
                    ).scalar_one()
                self.assertEqual(str(journal_mode).lower(), "wal")
            finally:
                engine.dispose()

    def test_postgres_engine_does_not_receive_sqlite_connect_args(self):
        with patch("database.create_engine") as create_engine:
            database.create_database_engine("postgresql+psycopg://u:p@db/facai")

        kwargs = create_engine.call_args.kwargs
        self.assertNotIn("connect_args", kwargs)
        self.assertTrue(kwargs["pool_pre_ping"])

    def test_sqlite_parent_is_created_for_file_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "nested" / "facai.db"

            database._ensure_sqlite_parent(f"sqlite:///{database_path.as_posix()}")

            self.assertTrue(database_path.parent.is_dir())

    def test_postgres_init_only_asserts_schema_revision(self):
        postgres_engine = Mock()
        postgres_engine.dialect.name = "postgresql"
        sqlite_helpers = (
            "_schema_migration_required",
            "_backup_sqlite_database",
            "_ensure_creator_indexes",
            "_ensure_compatible_columns",
            "_ensure_creator_integrity_triggers",
        )

        with patch.object(database, "engine", postgres_engine), \
             patch.object(database.Base.metadata, "create_all") as create_all, \
             patch.object(database, "assert_schema_current") as assert_current, \
             patch.object(database, sqlite_helpers[0]) as schema_required, \
             patch.object(database, sqlite_helpers[1]) as backup_database, \
             patch.object(database, sqlite_helpers[2]) as creator_indexes, \
             patch.object(database, sqlite_helpers[3]) as compatible_columns, \
             patch.object(database, sqlite_helpers[4]) as integrity_triggers:
            database.init_db()

        create_all.assert_not_called()
        schema_required.assert_not_called()
        backup_database.assert_not_called()
        creator_indexes.assert_not_called()
        compatible_columns.assert_not_called()
        integrity_triggers.assert_not_called()
        assert_current.assert_called_once_with(postgres_engine)

    def test_assert_schema_current_accepts_matching_revision(self):
        bind = database.create_database_engine("sqlite:///:memory:")
        try:
            with bind.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES ('20260713_0001')")
                )

            with patch("alembic.script.ScriptDirectory.from_config") as from_config:
                from_config.return_value.get_current_head.return_value = "20260713_0001"

                database.assert_schema_current(bind)

            from_config.assert_called_once()
        finally:
            bind.dispose()

    def test_assert_schema_current_rejects_mismatched_revision(self):
        bind = database.create_database_engine("sqlite:///:memory:")
        try:
            with bind.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES ('20260713_0000')")
                )

            with patch("alembic.script.ScriptDirectory.from_config") as from_config:
                from_config.return_value.get_current_head.return_value = "20260713_0001"

                with self.assertRaisesRegex(RuntimeError, "alembic upgrade head"):
                    database.assert_schema_current(bind)
        finally:
            bind.dispose()

    def test_assert_schema_current_fails_closed_without_migration_config(self):
        bind = Mock()
        with patch(
            "alembic.script.ScriptDirectory.from_config",
            side_effect=RuntimeError("missing script location"),
        ):
            with self.assertRaisesRegex(RuntimeError, "alembic upgrade head"):
                database.assert_schema_current(bind)

        bind.connect.assert_not_called()

    def test_creator_partial_unique_indexes_compile_with_postgres_predicates(self):
        indexes = {
            index.name: index
            for table in (
                creator_models.Creator.__table__,
                creator_models.CreatorCollaboration.__table__,
                creator_models.CreatorImportBatch.__table__,
            )
            for index in table.indexes
        }

        for name in (
            "uq_creators_platform_uid",
            "uq_creators_douyin_handle",
            "uq_creator_collaboration_external",
            "uq_creator_import_committed_file",
        ):
            with self.subTest(index=name):
                ddl = str(CreateIndex(indexes[name]).compile(dialect=postgresql.dialect()))
                self.assertIn(" WHERE ", ddl.upper())


if __name__ == "__main__":
    unittest.main()
