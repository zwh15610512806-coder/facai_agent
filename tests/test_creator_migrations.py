import inspect
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect as sa_inspect, text


class CreatorMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "creator-migration.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}", connect_args={"check_same_thread": False}
        )

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _swap_database(self):
        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        return database, original

    def _restore_database(self, database, original):
        database.engine, database.DATABASE_URL = original

    def test_missing_creator_tables_trigger_schema_migration(self):
        database, original = self._swap_database()
        try:
            with self.engine.begin() as connection:
                for table in (
                    "vector_sync_jobs",
                    "job_runs",
                    "product_rag_feedbacks",
                    "vector_index_versions",
                ):
                    connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"))

            self.assertTrue(database._schema_migration_required())
        finally:
            self._restore_database(database, original)

    def test_init_db_registers_creator_models_and_is_idempotent(self):
        database, original = self._swap_database()
        try:
            database.init_db()
            database.init_db()
            table_names = set(sa_inspect(self.engine).get_table_names())
            with self.engine.connect() as connection:
                trigger_names = {
                    row[0]
                    for row in connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='trigger'")
                    )
                }
            migration_required = database._schema_migration_required()
        finally:
            self._restore_database(database, original)

        self.assertIn("creator_sample_orders", table_names)
        self.assertIn("creator_import_batches", table_names)
        self.assertIn("import creator_models", inspect.getsource(database.init_db))
        self.assertGreaterEqual(
            trigger_names,
            {
                "trg_creators_validate_insert",
                "trg_creators_validate_update",
                "trg_creator_followups_validate_insert",
                "trg_creator_followups_validate_update",
                "trg_creator_collaborations_validate_insert",
                "trg_creator_collaborations_validate_update",
                "trg_creator_sample_orders_validate_insert",
                "trg_creator_sample_orders_validate_update",
            },
        )
        self.assertFalse(migration_required)

    def test_existing_creator_import_table_gets_unique_index_and_duplicate_repair(self):
        import creator_models  # noqa: F401
        import models  # noqa: F401
        from database import Base

        Base.metadata.create_all(bind=self.engine)
        with self.engine.begin() as connection:
            connection.execute(text("DROP INDEX uq_creator_import_committed_file"))
            for token in ("old-a", "old-b"):
                connection.execute(
                    text(
                        "INSERT INTO creator_import_batches "
                        "(token, kind, source_type, filename, file_sha256, status, mapping, errors, "
                        "row_count, imported_count, updated_count, skipped_count, error_count) "
                        "VALUES (:token, 'creators', 'test', 'old.xlsx', 'same-sha', 'committed', "
                        "'{}', '[]', 1, 1, 0, 0, 0)"
                    ),
                    {"token": token},
                )

        database, original = self._swap_database()
        try:
            self.assertTrue(database._schema_migration_required())
            database.init_db()
            indexes = {item["name"]: item for item in sa_inspect(self.engine).get_indexes("creator_import_batches")}
            with self.engine.connect() as connection:
                statuses = connection.execute(
                    text("SELECT status FROM creator_import_batches ORDER BY id")
                ).scalars().all()
        finally:
            self._restore_database(database, original)

        self.assertTrue(indexes["uq_creator_import_committed_file"]["unique"])
        self.assertEqual(["committed", "duplicate"], statuses)

    def test_named_nonunique_import_index_is_rebuilt_with_correct_definition(self):
        import creator_models  # noqa: F401
        import models  # noqa: F401
        from database import Base

        Base.metadata.create_all(bind=self.engine)
        with self.engine.begin() as connection:
            connection.execute(text("DROP INDEX uq_creator_import_committed_file"))
            connection.execute(
                text(
                    "CREATE INDEX uq_creator_import_committed_file "
                    "ON creator_import_batches (kind, file_sha256)"
                )
            )
        database, original = self._swap_database()
        try:
            self.assertTrue(database._schema_migration_required())
            database.init_db()
            index = next(
                item
                for item in sa_inspect(self.engine).get_indexes("creator_import_batches")
                if item["name"] == "uq_creator_import_committed_file"
            )
        finally:
            self._restore_database(database, original)

        self.assertTrue(index["unique"])
        self.assertEqual(["kind", "file_sha256"], index["column_names"])

    def test_missing_integrity_trigger_requires_and_repairs_migration(self):
        database, original = self._swap_database()
        try:
            database.init_db()
            with self.engine.begin() as connection:
                connection.execute(text("DROP TRIGGER trg_creators_validate_update"))
            self.assertTrue(database._schema_migration_required())

            database.init_db()
            with self.engine.connect() as connection:
                trigger_exists = connection.execute(
                    text(
                        "SELECT COUNT(*) FROM sqlite_master "
                        "WHERE type='trigger' AND name='trg_creators_validate_update'"
                    )
                ).scalar_one()
            migration_required_after_repair = database._schema_migration_required()
        finally:
            self._restore_database(database, original)

        self.assertEqual(1, trigger_exists)
        self.assertFalse(migration_required_after_repair)

    def test_wrong_named_integrity_trigger_is_rebuilt(self):
        database, original = self._swap_database()
        try:
            database.init_db()
            with self.engine.begin() as connection:
                connection.execute(text("DROP TRIGGER trg_creators_validate_update"))
                connection.execute(
                    text(
                        "CREATE TRIGGER trg_creators_validate_update "
                        "BEFORE UPDATE OF stage ON creators BEGIN SELECT 1; END"
                    )
                )
            self.assertTrue(database._schema_migration_required())

            database.init_db()
            migration_required_after_repair = database._schema_migration_required()
        finally:
            self._restore_database(database, original)

        self.assertFalse(migration_required_after_repair)

    def test_relative_sqlite_path_uses_process_working_directory(self):
        import database

        original_engine = database.engine
        original_url = database.DATABASE_URL
        original_cwd = Path.cwd()
        relative_engine = None
        try:
            os.chdir(self.tmp.name)
            relative_engine = create_engine(
                "sqlite:///relative-active.db", connect_args={"check_same_thread": False}
            )
            with relative_engine.begin() as connection:
                connection.execute(text("CREATE TABLE marker (id INTEGER PRIMARY KEY)"))
            database.engine = relative_engine
            database.DATABASE_URL = "sqlite:///relative-active.db"

            self.assertEqual(
                (Path(self.tmp.name) / "relative-active.db").resolve(),
                database._sqlite_database_path(),
            )
            backup_path = database._backup_sqlite_database()
            self.assertIsNotNone(backup_path)
            self.assertEqual((Path(self.tmp.name) / "backups").resolve(), backup_path.parent)
            backup_engine = create_engine(f"sqlite:///{backup_path.as_posix()}")
            try:
                with backup_engine.connect() as connection:
                    self.assertEqual(0, connection.execute(text("SELECT COUNT(*) FROM marker")).scalar_one())
            finally:
                backup_engine.dispose()
        finally:
            database.engine = original_engine
            database.DATABASE_URL = original_url
            if relative_engine is not None:
                relative_engine.dispose()
            os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
