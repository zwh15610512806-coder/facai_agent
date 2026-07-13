import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text


class SQLiteCompatibilityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "legacy.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}", connect_args={"check_same_thread": False})

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _column_names(self, table_name: str) -> set[str]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {row["name"] for row in rows}

    def test_legacy_sqlite_tables_get_current_high_risk_columns_idempotently(self):
        import database

        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, category VARCHAR(100) NOT NULL, price FLOAT NOT NULL)"))
            connection.execute(text("CREATE TABLE viral_scripts (id INTEGER PRIMARY KEY, title VARCHAR(300) NOT NULL, script_content TEXT NOT NULL)"))
            connection.execute(text("CREATE TABLE generated_scripts (id INTEGER PRIMARY KEY, script_content TEXT NOT NULL)"))
            connection.execute(text("CREATE TABLE reference_scripts (id INTEGER PRIMARY KEY, script_content TEXT NOT NULL)"))
            connection.execute(text("CREATE TABLE ai_interface_settings (id INTEGER PRIMARY KEY, interface_key VARCHAR(100) NOT NULL)"))
            connection.execute(text("INSERT INTO ai_interface_settings (interface_key) VALUES ('legacy_chat')"))

        original_engine = database.engine
        database.engine = self.engine
        try:
            database._ensure_compatible_columns()
            database._ensure_compatible_columns()
        finally:
            database.engine = original_engine

        self.assertGreaterEqual(
            self._column_names("viral_scripts"),
            {"is_high_conversion"},
        )
        self.assertGreaterEqual(
            self._column_names("generated_scripts"),
            {
                "ai_model",
                "is_high_conversion",
                "source_script_id",
                "source_script_source",
                "source_script_title",
                "source_script_content",
            },
        )
        self.assertGreaterEqual(
            self._column_names("reference_scripts"),
            {"is_high_conversion", "embedding_id"},
        )
        self.assertGreaterEqual(
            self._column_names("products"),
            {"pending_fields"},
        )
        self.assertGreaterEqual(
            self._column_names("ai_interface_settings"),
            {"provider", "model", "max_tokens", "api_key_secret", "base_url_override", "updated_at"},
        )

        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT provider, model, max_tokens FROM ai_interface_settings WHERE interface_key = 'legacy_chat'")
            ).mappings().one()

        self.assertTrue(row["provider"])
        self.assertTrue(row["model"])
        self.assertGreater(row["max_tokens"], 0)

    def test_legacy_qianchuan_tables_get_current_metric_columns(self):
        import database

        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE qianchuan_import_batches ("
                "id INTEGER PRIMARY KEY, filename VARCHAR(500) NOT NULL, "
                "file_sha256 VARCHAR(64) NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE qianchuan_material_performance ("
                "id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, "
                "material_id VARCHAR(100) NOT NULL, material_name VARCHAR(500) NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE qianchuan_script_bindings ("
                "id INTEGER PRIMARY KEY, script_id INTEGER NOT NULL, "
                "material_id VARCHAR(100) NOT NULL, material_name VARCHAR(500) NOT NULL)"
            ))

        original_engine = database.engine
        database.engine = self.engine
        try:
            database._ensure_compatible_columns()
            database._ensure_compatible_columns()
        finally:
            database.engine = original_engine

        self.assertGreaterEqual(
            self._column_names("qianchuan_import_batches"),
            {"row_count", "imported_count", "skipped_count", "amount_field", "created_at"},
        )
        self.assertGreaterEqual(
            self._column_names("qianchuan_material_performance"),
            {
                "material_evaluation",
                "material_duration",
                "material_created_time",
                "material_source",
                "tags",
                "amount_field",
                "transaction_amount",
                "order_count",
                "user_pay_amount",
                "roi",
                "impressions",
                "ctr",
                "spend",
                "clicks",
                "cvr",
                "play_3s_rate",
                "play_10s_rate",
                "avg_watch_seconds",
                "completion_rate",
                "plan_count",
                "product_count",
                "raw_data",
                "created_at",
            },
        )
        self.assertIn("created_at", self._column_names("qianchuan_script_bindings"))


if __name__ == "__main__":
    unittest.main()
