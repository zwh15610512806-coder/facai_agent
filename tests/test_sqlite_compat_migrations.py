import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


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

    @staticmethod
    def _connection_provider_unique_specs(engine) -> list[tuple[str, ...]]:
        inspector = inspect(engine)
        specs = [
            tuple(item.get("column_names") or ())
            for item in inspector.get_unique_constraints("integration_connections")
        ]
        specs.extend(
            tuple(item.get("column_names") or ())
            for item in inspector.get_indexes("integration_connections")
            if item.get("unique")
            and (item.get("dialect_options") or {}).get("sqlite_where") is None
        )
        return [spec for spec in specs if spec == ("id", "provider")]

    def _use_database_engine(self, database):
        self.engine.dispose()
        self.engine = database.create_database_engine(f"sqlite:///{self.db_path}")

    def _create_pre_0002_schema(self, database):
        import commerce_models  # noqa: F401
        import creator_models  # noqa: F401
        import integration_models
        import models  # noqa: F401

        new_table_names = {
            name for name in database.Base.metadata.tables if name.startswith("commerce_")
        } | {
            "integration_archive_manifests",
            "integration_export_jobs",
            "integration_jobs",
            "integration_sync_checkpoints",
            "integration_sync_errors",
            "integration_sync_runs",
            "integration_worker_heartbeats",
        }
        legacy_tables = [
            table
            for table in database.Base.metadata.sorted_tables
            if table.name not in new_table_names
            and table.name != "integration_connections"
        ]
        database.Base.metadata.create_all(self.engine, tables=legacy_tables)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE integration_connections ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "authorization_id INTEGER NOT NULL, "
                    "provider VARCHAR(10) NOT NULL, "
                    "connection_type VARCHAR(10) NOT NULL, "
                    "external_account_id VARCHAR(255) NOT NULL, "
                    "display_name VARCHAR(255) NOT NULL, "
                    "status VARCHAR(24) NOT NULL, "
                    "capability_report JSON NOT NULL, "
                    "earliest_available_date DATE, "
                    "last_successful_sync_at DATETIME, "
                    "disabled_at DATETIME, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL, "
                    "CONSTRAINT uq_integration_connections_provider_type_external_account "
                    "UNIQUE (provider, connection_type, external_account_id), "
                    "CONSTRAINT fk_integration_connections_authorization_provider "
                    "FOREIGN KEY (authorization_id, provider) "
                    "REFERENCES integration_authorizations (id, provider) "
                    "ON DELETE RESTRICT"
                    ")"
                )
            )
            authorization_id = connection.execute(
                integration_models.IntegrationAuthorization.__table__.insert()
                .values(
                    provider="doudian",
                    external_subject_id="legacy-subject",
                    scopes=["shop.read"],
                    access_token_ciphertext="opaque-ciphertext",
                    access_token_tail="0000",
                    status="active",
                    last_authorized_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                .returning(integration_models.IntegrationAuthorization.id)
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO integration_connections ("
                    "id, authorization_id, provider, connection_type, "
                    "external_account_id, display_name, status, capability_report, "
                    "created_at, updated_at"
                    ") VALUES ("
                    "1, :authorization_id, 'doudian', 'shop', "
                    "'legacy-shop', 'Legacy shop', 'active', '{}', "
                    ":created_at, :updated_at"
                    ")"
                ),
                {
                    "authorization_id": authorization_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    def test_pre_0002_sqlite_is_backed_up_and_repaired_before_child_tables(self):
        import commerce_models
        import database

        self._use_database_engine(database)
        original_engine = database.engine
        database.engine = self.engine
        try:
            self._create_pre_0002_schema(database)
            database._ensure_creator_integrity_triggers()
            self.assertEqual(self._connection_provider_unique_specs(self.engine), [])
            self.assertTrue(database._schema_migration_required())

            database.init_db()

            exact_specs = self._connection_provider_unique_specs(self.engine)
            self.assertEqual(exact_specs, [("id", "provider")])
            backups = sorted((self.db_path.parent / "backups").glob("*.db"))
            self.assertEqual(len(backups), 1)
            backup_engine = create_engine(f"sqlite:///{backups[0]}")
            try:
                self.assertEqual(
                    self._connection_provider_unique_specs(backup_engine),
                    [],
                )
            finally:
                backup_engine.dispose()

            now = datetime.now(timezone.utc)
            valid_values = {
                "connection_id": 1,
                "provider": "doudian",
                "external_shop_id": "shop-1",
                "name": "Legacy migrated shop",
                "normalized_status": "active",
                "raw_status": "OPEN",
                "platform_updated_at": now,
                "platform_metadata": {},
                "ingested_at": now,
                "updated_at": now,
            }
            with self.engine.begin() as connection:
                connection.execute(
                    commerce_models.CommerceShop.__table__.insert().values(**valid_values)
                )
            invalid_values = {
                **valid_values,
                "provider": "pdd",
                "external_shop_id": "shop-provider-mismatch",
            }
            with self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(
                        commerce_models.CommerceShop.__table__.insert().values(
                            **invalid_values
                        )
                    )

            database.init_db()
            self.assertEqual(
                self._connection_provider_unique_specs(self.engine),
                [("id", "provider")],
            )
            self.assertEqual(
                len(list((self.db_path.parent / "backups").glob("*.db"))),
                1,
            )
        finally:
            database.engine = original_engine

    def test_fresh_sqlite_gets_one_exact_parent_key_without_backup(self):
        import database

        self._use_database_engine(database)
        original_engine = database.engine
        database.engine = self.engine
        try:
            database.init_db()
            database.init_db()
            self.assertEqual(
                self._connection_provider_unique_specs(self.engine),
                [("id", "provider")],
            )
            self.assertFalse((self.db_path.parent / "backups").exists())
        finally:
            database.engine = original_engine

    def test_partial_parent_key_with_different_name_is_backed_up_and_repaired(self):
        import commerce_models
        import database

        self._use_database_engine(database)
        original_engine = database.engine
        database.engine = self.engine
        try:
            self._create_pre_0002_schema(database)
            database._ensure_creator_integrity_triggers()
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_partial_connections_id_provider "
                        "ON integration_connections (id, provider) "
                        "WHERE status = 'active'"
                    )
                )

            self.assertFalse(
                database._integration_connection_provider_unique_valid(
                    inspect(self.engine)
                )
            )
            self.assertTrue(database._schema_migration_required())

            database.init_db()

            self.assertEqual(
                self._connection_provider_unique_specs(self.engine),
                [("id", "provider")],
            )
            self.assertEqual(
                len(list((self.db_path.parent / "backups").glob("*.db"))),
                1,
            )
            now = datetime.now(timezone.utc)
            valid_values = {
                "connection_id": 1,
                "provider": "doudian",
                "external_shop_id": "partial-repaired-shop",
                "name": "Partial repaired shop",
                "normalized_status": "active",
                "raw_status": "OPEN",
                "platform_updated_at": now,
                "platform_metadata": {},
                "ingested_at": now,
                "updated_at": now,
            }
            with self.engine.begin() as connection:
                connection.execute(
                    commerce_models.CommerceShop.__table__.insert().values(
                        **valid_values
                    )
                )
            with self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(
                        commerce_models.CommerceShop.__table__.insert().values(
                            **{
                                **valid_values,
                                "provider": "pdd",
                                "external_shop_id": "partial-provider-mismatch",
                            }
                        )
                    )
        finally:
            database.engine = original_engine

    def test_partial_parent_key_using_reserved_name_backs_up_then_fails_closed(self):
        import database

        self._use_database_engine(database)
        original_engine = database.engine
        database.engine = self.engine
        try:
            self._create_pre_0002_schema(database)
            database._ensure_creator_integrity_triggers()
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_integration_connections_id_provider "
                        "ON integration_connections (id, provider) "
                        "WHERE status = 'active'"
                    )
                )

            self.assertFalse(
                database._integration_connection_provider_unique_valid(
                    inspect(self.engine)
                )
            )
            self.assertTrue(database._schema_migration_required())

            with self.assertRaisesRegex(RuntimeError, "incompatible definition"):
                database.init_db()

            backups = list((self.db_path.parent / "backups").glob("*.db"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(self._connection_provider_unique_specs(self.engine), [])
            self.assertNotIn("commerce_shops", inspect(self.engine).get_table_names())
            backup_engine = create_engine(f"sqlite:///{backups[0]}")
            try:
                reserved = {
                    item["name"]: item
                    for item in inspect(backup_engine).get_indexes(
                        "integration_connections"
                    )
                }["uq_integration_connections_id_provider"]
                self.assertIsNotNone(
                    (reserved.get("dialect_options") or {}).get("sqlite_where")
                )
            finally:
                backup_engine.dispose()
        finally:
            database.engine = original_engine

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
