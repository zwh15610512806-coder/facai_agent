import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable


GENERATION_TABLES = {
    "image_provider_connections",
    "image_model_profiles",
    "canvas_generations",
    "canvas_generation_items",
    "canvas_generation_item_inputs",
    "canvas_generation_attempts",
}


class CanvasGenerationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-generation-models.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        self._foreign_key_listener = _enable_foreign_keys

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _swap_database(self):
        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        return database, original

    @staticmethod
    def _restore_database(database, original):
        database.engine, database.DATABASE_URL = original

    def test_init_db_creates_durable_generation_catalog_and_history_idempotently(self):
        database, original = self._swap_database()
        try:
            database.init_db()
            database.init_db()
            schema = inspect(self.engine)
            self.assertGreaterEqual(set(schema.get_table_names()), GENERATION_TABLES)

            expected_uniques = {
                "image_model_profiles": {("provider_id", "model_id")},
                "canvas_generations": {("project_id", "idempotency_key")},
                "canvas_generation_items": {
                    ("generation_id", "ordinal"),
                    ("generation_id", "board_id"),
                },
                "canvas_generation_item_inputs": {
                    ("item_id", "input_role", "ordinal")
                },
                "canvas_generation_attempts": {
                    ("item_id", "attempt_no"),
                    ("compose_operation_id",),
                },
            }
            for table_name, expected in expected_uniques.items():
                actual = {
                    tuple(constraint.get("column_names") or ())
                    for constraint in schema.get_unique_constraints(table_name)
                }
                self.assertEqual(expected, actual, table_name)

            expected_indexes = {
                "image_provider_connections": {
                    ("enabled", "name"),
                    ("adapter_type",),
                },
                "image_model_profiles": {
                    ("provider_id", "enabled"),
                },
                "canvas_generations": {
                    ("status", "created_at"),
                    ("lease_expires_at",),
                    ("project_id", "status"),
                },
                "canvas_generation_items": {
                    ("generation_id", "status"),
                    ("model_profile_id",),
                    ("latest_background_asset_id",),
                    ("latest_composed_asset_id",),
                },
                "canvas_generation_item_inputs": {("asset_id",)},
                "canvas_generation_attempts": {
                    ("status", "next_poll_at", "created_at"),
                    ("lease_expires_at",),
                    ("provider_id", "model_profile_id", "status"),
                    ("background_asset_id",),
                    ("composed_asset_id",),
                },
            }
            for table_name, required in expected_indexes.items():
                actual = {
                    tuple(index.get("column_names") or ())
                    for index in schema.get_indexes(table_name)
                }
                self.assertGreaterEqual(actual, required, table_name)

            provider_fks = schema.get_foreign_keys("image_model_profiles")
            self.assertEqual(
                [("provider_id", "image_provider_connections", "RESTRICT")],
                [
                    (
                        tuple(fk["constrained_columns"])[0],
                        fk["referred_table"],
                        fk["options"].get("ondelete"),
                    )
                    for fk in provider_fks
                ],
            )
            event_fks = {
                tuple(fk["constrained_columns"]): (
                    fk["referred_table"],
                    fk["options"].get("ondelete"),
                )
                for fk in schema.get_foreign_keys("canvas_events")
            }
            self.assertEqual(
                ("canvas_generations", "SET NULL"),
                event_fks[("generation_id",)],
            )
            self.assertEqual(
                ("canvas_generation_items", "SET NULL"),
                event_fks[("item_id",)],
            )
            self.assertEqual(
                ("canvas_asset_operations", "SET NULL"),
                event_fks[("operation_id",)],
            )
            self.assertFalse(database._schema_migration_required())
        finally:
            self._restore_database(database, original)

    def test_generation_schema_has_separate_immutable_result_stage_assets(self):
        database, original = self._swap_database()
        try:
            database.init_db()
            schema = inspect(self.engine)
            attempt_columns = {
                column["name"]
                for column in schema.get_columns("canvas_generation_attempts")
            }
            self.assertGreaterEqual(
                attempt_columns,
                {
                    "provider_result_stage",
                    "provider_accepted_at",
                    "provider_request_id",
                    "external_task_id",
                    "upstream_idempotency_key",
                    "last_polled_at",
                    "cancel_requested_at",
                    "background_asset_id",
                    "background_preview_asset_id",
                    "composed_asset_id",
                    "composed_preview_asset_id",
                    "compose_operation_id",
                    "provider_config_snapshot_json",
                    "model_config_snapshot_json",
                    "usage_json",
                    "normalized_error_code",
                    "safe_error_summary",
                    "safe_upstream_error_code",
                },
            )
            self.assertNotIn("output_asset_id", attempt_columns)

            attempt_fks = {
                tuple(fk["constrained_columns"]): (
                    fk["referred_table"],
                    fk["options"].get("ondelete"),
                )
                for fk in schema.get_foreign_keys("canvas_generation_attempts")
            }
            for column_name in (
                "background_asset_id",
                "background_preview_asset_id",
                "composed_asset_id",
                "composed_preview_asset_id",
            ):
                self.assertEqual(
                    ("canvas_assets", "RESTRICT"),
                    attempt_fks[(column_name,)],
                )
            input_fks = {
                tuple(fk["constrained_columns"]): (
                    fk["referred_table"],
                    fk["options"].get("ondelete"),
                )
                for fk in schema.get_foreign_keys("canvas_generation_item_inputs")
            }
            self.assertEqual(
                ("canvas_assets", "RESTRICT"),
                input_fks[("asset_id",)],
            )

            generation_columns = {
                column["name"] for column in schema.get_columns("canvas_generations")
            }
            self.assertGreaterEqual(
                generation_columns,
                {
                    "project_revision",
                    "request_snapshot_json",
                    "request_fingerprint",
                    "idempotency_key",
                    "storage_reservation_bytes",
                    "storage_reservation_remaining_bytes",
                    "safe_storage_block_reason",
                    "storage_blocked_at",
                    "cancel_requested_at",
                    "lease_expires_at",
                    "heartbeat_at",
                },
            )

            item_columns = {
                column["name"] for column in schema.get_columns("canvas_generation_items")
            }
            self.assertGreaterEqual(
                item_columns,
                {
                    "sku_id_snapshot",
                    "sku_name_snapshot",
                    "board_id",
                    "node_id",
                    "board_order_snapshot",
                    "provider_id",
                    "provider_config_version",
                    "model_profile_id",
                    "model_config_version",
                    "provider_config_snapshot_json",
                    "model_config_snapshot_json",
                    "layout_hash",
                    "layout_snapshot_json",
                    "latest_background_asset_id",
                    "latest_composed_asset_id",
                    "safe_current_error_code",
                    "safe_current_error_summary",
                },
            )
            self.assertNotIn("selected_result_asset_id", item_columns)
        finally:
            self._restore_database(database, original)

    def test_init_db_upgrades_legacy_layout_hash_width_without_data_loss(self):
        import canvas_models

        database, original = self._swap_database()
        try:
            database.init_db()
            table = canvas_models.CanvasGenerationItem.__table__
            legacy_ddl = str(CreateTable(table).compile(self.engine)).strip()
            legacy_ddl = legacy_ddl.replace(
                "CREATE TABLE canvas_generation_items",
                "CREATE TABLE canvas_generation_items_legacy",
                1,
            ).replace("layout_hash VARCHAR(71)", "layout_hash VARCHAR(64)", 1)
            with self.engine.connect() as connection:
                connection.commit()
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                database._drop_canvas_generation_integrity_triggers(connection)
                connection.exec_driver_sql("DROP TABLE canvas_generation_items")
                connection.exec_driver_sql(legacy_ddl)
                connection.exec_driver_sql(
                    "ALTER TABLE canvas_generation_items_legacy "
                    "RENAME TO canvas_generation_items"
                )
                connection.commit()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
            legacy_type = next(
                column["type"]
                for column in inspect(self.engine).get_columns("canvas_generation_items")
                if column["name"] == "layout_hash"
            )
            self.assertEqual("VARCHAR(64)", str(legacy_type).upper())

            database.init_db()

            upgraded_type = next(
                column["type"]
                for column in inspect(self.engine).get_columns("canvas_generation_items")
                if column["name"] == "layout_hash"
            )
            self.assertEqual("VARCHAR(71)", str(upgraded_type).upper())
            self.assertFalse(database._schema_migration_required())
        finally:
            self._restore_database(database, original)

    def _seed_generation_graph(self):
        database, original = self._swap_database()
        database.init_db()
        ids = {
            name: f"{ordinal:08x}-0000-4000-8000-{ordinal:012x}"
            for ordinal, name in enumerate(
                (
                    "project_a",
                    "project_b",
                    "provider_a",
                    "provider_b",
                    "model_a",
                    "model_b",
                    "asset_a",
                    "asset_b",
                    "operation_a",
                    "operation_b",
                    "generation",
                    "item",
                    "attempt",
                    "input",
                ),
                start=1,
            )
        }
        with self.engine.begin() as connection:
            for project_name in ("project_a", "project_b"):
                connection.execute(
                    text(
                        "INSERT INTO canvas_projects "
                        "(id, name, status, semantic_state, layout_state, schema_version, revision) "
                        "VALUES (:id, :name, 'active', '{}', '{}', 1, 1)"
                    ),
                    {"id": ids[project_name], "name": project_name},
                )
            for suffix in ("a", "b"):
                connection.execute(
                    text(
                        "INSERT INTO image_provider_connections "
                        "(id, adapter_type, name, base_url, auth_type) VALUES "
                        "(:id, 'fake', :name, 'https://provider.invalid', 'bearer')"
                    ),
                    {"id": ids[f"provider_{suffix}"], "name": f"Provider {suffix}"},
                )
                connection.execute(
                    text(
                        "INSERT INTO image_model_profiles "
                        "(id, provider_id, model_id, display_name) VALUES "
                        "(:id, :provider_id, :model_id, :display_name)"
                    ),
                    {
                        "id": ids[f"model_{suffix}"],
                        "provider_id": ids[f"provider_{suffix}"],
                        "model_id": f"model-{suffix}",
                        "display_name": f"Model {suffix}",
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO canvas_assets "
                        "(id, project_id, asset_type, relative_path, original_filename, "
                        "mime_type, byte_count, width, height, sha256, transparency_status, "
                        "metadata_json) VALUES "
                        "(:id, :project_id, 'source', :path, 'asset.png', 'image/png', "
                        "1, 1, 1, :sha256, 'unknown', '{}')"
                    ),
                    {
                        "id": ids[f"asset_{suffix}"],
                        "project_id": ids[f"project_{suffix}"],
                        "path": f"source/{suffix}.png",
                        "sha256": suffix * 64,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO canvas_asset_operations "
                        "(id, project_id, operation_type, input_asset_id, idempotency_key) "
                        "VALUES (:id, :project_id, 'compose', :asset_id, :key)"
                    ),
                    {
                        "id": ids[f"operation_{suffix}"],
                        "project_id": ids[f"project_{suffix}"],
                        "asset_id": ids[f"asset_{suffix}"],
                        "key": f"compose-{suffix}",
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO canvas_generations "
                    "(id, project_id, mode, project_revision, request_snapshot_json, "
                    "request_fingerprint, idempotency_key) VALUES "
                    "(:id, :project_id, 'complete_set', 1, '{}', :fingerprint, 'seed')"
                ),
                {
                    "id": ids["generation"],
                    "project_id": ids["project_a"],
                    "fingerprint": "f" * 64,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO canvas_generation_items "
                    "(id, generation_id, ordinal, output_type, board_id, node_id, "
                    "board_order_snapshot, provider_id, provider_config_version, "
                    "model_profile_id, model_config_version, provider_config_snapshot_json, "
                    "model_config_snapshot_json, prompt, width, height, ratio, layout_hash, "
                    "layout_snapshot_json, latest_background_asset_id, "
                    "latest_composed_asset_id) VALUES "
                    "(:id, :generation_id, 0, 'main', 'board', 'node', 0, :provider_id, 1, "
                    ":model_id, 1, '{}', '{}', 'background', 1024, 1024, '1:1', "
                    ":layout_hash, '{}', :asset_id, :asset_id)"
                ),
                {
                    "id": ids["item"],
                    "generation_id": ids["generation"],
                    "provider_id": ids["provider_a"],
                    "model_id": ids["model_a"],
                    "layout_hash": "sha256:" + "a" * 64,
                    "asset_id": ids["asset_a"],
                },
            )
            connection.execute(
                text(
                    "INSERT INTO canvas_generation_item_inputs "
                    "(id, item_id, asset_id, input_role, ordinal, asset_sha256) VALUES "
                    "(:id, :item_id, :asset_id, 'main_product', 0, :sha256)"
                ),
                {
                    "id": ids["input"],
                    "item_id": ids["item"],
                    "asset_id": ids["asset_a"],
                    "sha256": "a" * 64,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO canvas_generation_attempts "
                    "(id, item_id, attempt_no, provider_id, provider_config_version, "
                    "model_profile_id, model_config_version, provider_config_snapshot_json, "
                    "model_config_snapshot_json, upstream_idempotency_key, background_asset_id, "
                    "background_preview_asset_id, composed_asset_id, composed_preview_asset_id, "
                    "compose_operation_id) VALUES "
                    "(:id, :item_id, 1, :provider_id, 1, :model_id, 1, '{}', '{}', 'upstream', "
                    ":asset_id, :asset_id, :asset_id, :asset_id, :operation_id)"
                ),
                {
                    "id": ids["attempt"],
                    "item_id": ids["item"],
                    "provider_id": ids["provider_a"],
                    "model_id": ids["model_a"],
                    "asset_id": ids["asset_a"],
                    "operation_id": ids["operation_a"],
                },
            )
        return database, original, ids

    def test_raw_writes_reject_cross_project_generation_relations_and_model_mismatch(self):
        database, original, ids = self._seed_generation_graph()
        mutations = [
            (
                "UPDATE canvas_generation_items SET latest_background_asset_id=:bad "
                "WHERE id=:id",
                {"bad": ids["asset_b"], "id": ids["item"]},
            ),
            (
                "UPDATE canvas_generation_items SET latest_composed_asset_id=:bad WHERE id=:id",
                {"bad": ids["asset_b"], "id": ids["item"]},
            ),
            (
                "INSERT INTO canvas_generation_item_inputs "
                "(id, item_id, asset_id, input_role, ordinal, asset_sha256) VALUES "
                "('cross-input', :id, :bad, 'angle_reference', 0, :sha256)",
                {"id": ids["item"], "bad": ids["asset_b"], "sha256": "b" * 64},
            ),
        ]
        for column_name in (
            "background_asset_id",
            "background_preview_asset_id",
            "composed_asset_id",
            "composed_preview_asset_id",
        ):
            mutations.append(
                (
                    f"UPDATE canvas_generation_attempts SET {column_name}=:bad WHERE id=:id",
                    {"bad": ids["asset_b"], "id": ids["attempt"]},
                )
            )
        mutations.extend(
            [
                (
                    "UPDATE canvas_generation_attempts SET compose_operation_id=:bad WHERE id=:id",
                    {"bad": ids["operation_b"], "id": ids["attempt"]},
                ),
                (
                    "UPDATE canvas_generation_items SET model_profile_id=:bad WHERE id=:id",
                    {"bad": ids["model_b"], "id": ids["item"]},
                ),
                (
                    "UPDATE canvas_generation_attempts SET model_profile_id=:bad WHERE id=:id",
                    {"bad": ids["model_b"], "id": ids["attempt"]},
                ),
                (
                    "UPDATE image_model_profiles SET provider_id=:bad WHERE id=:id",
                    {"bad": ids["provider_b"], "id": ids["model_a"]},
                ),
            ]
        )
        try:
            for sql, parameters in mutations:
                with self.subTest(sql=sql):
                    with self.assertRaises(IntegrityError):
                        with self.engine.begin() as connection:
                            connection.execute(text(sql), parameters)
        finally:
            self._restore_database(database, original)

    def test_item_cannot_move_away_from_existing_input_and_attempt_assets(self):
        attempt_relations = (
            "background_asset_id",
            "background_preview_asset_id",
            "composed_asset_id",
            "composed_preview_asset_id",
            "compose_operation_id",
        )
        database, original, ids = self._seed_generation_graph()
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO canvas_generations "
                        "(id, project_id, mode, project_revision, "
                        "request_snapshot_json, request_fingerprint, "
                        "idempotency_key) VALUES "
                        "('generation-b', :project_id, 'complete_set', 1, '{}', "
                        ":fingerprint, 'move-target')"
                    ),
                    {"project_id": ids["project_b"], "fingerprint": "g" * 64},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_items SET "
                        "latest_background_asset_id=NULL, "
                        "latest_composed_asset_id=NULL WHERE id=:item_id"
                    ),
                    {"item_id": ids["item"]},
                )

            for relation in ("input", *attempt_relations):
                with self.subTest(relation=relation):
                    with self.engine.begin() as connection:
                        connection.execute(
                            text(
                                "DELETE FROM canvas_generation_item_inputs "
                                "WHERE item_id=:item_id"
                            ),
                            {"item_id": ids["item"]},
                        )
                        if relation == "input":
                            connection.execute(
                                text(
                                    "INSERT INTO canvas_generation_item_inputs "
                                    "(id, item_id, asset_id, input_role, ordinal, "
                                    "asset_sha256) VALUES "
                                    "('move-input', :item_id, :asset_id, "
                                    "'main_product', 0, :sha256)"
                                ),
                                {
                                    "item_id": ids["item"],
                                    "asset_id": ids["asset_a"],
                                    "sha256": "a" * 64,
                                },
                            )
                        assignments = {
                            column_name: None for column_name in attempt_relations
                        }
                        if relation in attempt_relations:
                            assignments[relation] = (
                                ids["operation_a"]
                                if relation == "compose_operation_id"
                                else ids["asset_a"]
                            )
                        connection.execute(
                            text(
                                "UPDATE canvas_generation_attempts SET "
                                "background_asset_id=:background_asset_id, "
                                "background_preview_asset_id=:background_preview_asset_id, "
                                "composed_asset_id=:composed_asset_id, "
                                "composed_preview_asset_id=:composed_preview_asset_id, "
                                "compose_operation_id=:compose_operation_id "
                                "WHERE item_id=:item_id"
                            ),
                            {**assignments, "item_id": ids["item"]},
                        )

                    with self.assertRaises(IntegrityError):
                        with self.engine.begin() as connection:
                            connection.execute(
                                text(
                                    "UPDATE canvas_generation_items "
                                    "SET generation_id='generation-b' WHERE id=:item_id"
                                ),
                                {"item_id": ids["item"]},
                            )
        finally:
            self._restore_database(database, original)

    def test_item_can_move_when_existing_children_have_no_project_bound_relations(self):
        database, original, ids = self._seed_generation_graph()
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO canvas_generations "
                        "(id, project_id, mode, project_revision, request_snapshot_json, "
                        "request_fingerprint, idempotency_key) VALUES "
                        "('generation-b', :project_id, 'complete_set', 1, '{}', "
                        ":fingerprint, 'move-target')"
                    ),
                    {"project_id": ids["project_b"], "fingerprint": "g" * 64},
                )
                connection.execute(
                    text(
                        "DELETE FROM canvas_generation_item_inputs WHERE item_id=:item_id"
                    ),
                    {"item_id": ids["item"]},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_attempts SET background_asset_id=NULL, "
                        "background_preview_asset_id=NULL, composed_asset_id=NULL, "
                        "composed_preview_asset_id=NULL, compose_operation_id=NULL "
                        "WHERE item_id=:item_id"
                    ),
                    {"item_id": ids["item"]},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_items SET latest_background_asset_id=NULL, "
                        "latest_composed_asset_id=NULL, generation_id='generation-b' "
                        "WHERE id=:item_id"
                    ),
                    {"item_id": ids["item"]},
                )
                moved_generation_id = connection.execute(
                    text(
                        "SELECT generation_id FROM canvas_generation_items WHERE id=:item_id"
                    ),
                    {"item_id": ids["item"]},
                ).scalar_one()
            self.assertEqual("generation-b", moved_generation_id)
        finally:
            self._restore_database(database, original)

    def test_raw_reverse_writes_cannot_invalidate_generation_project_relations(self):
        database, original, ids = self._seed_generation_graph()
        try:
            with self.engine.begin() as connection:
                for suffix in ("item", "input", "attempt"):
                    connection.execute(
                        text(
                            "INSERT INTO canvas_assets "
                            "(id, project_id, asset_type, relative_path, original_filename, "
                            "mime_type, byte_count, width, height, sha256, transparency_status, "
                            "metadata_json) VALUES "
                            "(:id, :project_id, 'source', :path, :filename, 'image/png', "
                            "1, 1, 1, :sha256, 'unknown', '{}')"
                        ),
                        {
                            "id": f"reverse-{suffix}-asset",
                            "project_id": ids["project_a"],
                            "path": f"source/reverse-{suffix}.png",
                            "filename": f"reverse-{suffix}.png",
                            "sha256": "c" * 64,
                        },
                    )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_items "
                        "SET latest_background_asset_id='reverse-item-asset' WHERE id=:item_id"
                    ),
                    {"item_id": ids["item"]},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_item_inputs "
                        "SET asset_id='reverse-input-asset' WHERE id=:input_id"
                    ),
                    {"input_id": ids["input"]},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_attempts "
                        "SET background_asset_id='reverse-attempt-asset' WHERE id=:attempt_id"
                    ),
                    {"attempt_id": ids["attempt"]},
                )

            mutations = [
                (
                    "UPDATE canvas_generations SET project_id=:bad WHERE id=:id",
                    {"bad": ids["project_b"], "id": ids["generation"]},
                ),
                (
                    "UPDATE canvas_assets SET project_id=:bad, "
                    "relative_path='source/reverse-item-moved.png' "
                    "WHERE id='reverse-item-asset'",
                    {"bad": ids["project_b"]},
                ),
                (
                    "UPDATE canvas_assets SET project_id=:bad, "
                    "relative_path='source/reverse-input-moved.png' "
                    "WHERE id='reverse-input-asset'",
                    {"bad": ids["project_b"]},
                ),
                (
                    "UPDATE canvas_assets SET project_id=:bad, "
                    "relative_path='source/reverse-attempt-moved.png' "
                    "WHERE id='reverse-attempt-asset'",
                    {"bad": ids["project_b"]},
                ),
                (
                    "UPDATE canvas_asset_operations SET project_id=:bad, input_asset_id=:asset "
                    "WHERE id=:id",
                    {
                        "bad": ids["project_b"],
                        "asset": ids["asset_b"],
                        "id": ids["operation_a"],
                    },
                ),
            ]
            for sql, parameters in mutations:
                with self.subTest(sql=sql):
                    with self.assertRaises(IntegrityError):
                        with self.engine.begin() as connection:
                            connection.execute(text(sql), parameters)
        finally:
            self._restore_database(database, original)

    def test_asset_reference_collection_fails_safe_for_preexisting_cross_project_link(self):
        database, original, ids = self._seed_generation_graph()
        try:
            with self.engine.begin() as connection:
                trigger_names = connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='trigger' "
                        "AND name LIKE 'trg_canvas_generation_%_integrity_%'"
                    )
                ).scalars().all()
                for trigger_name in trigger_names:
                    connection.exec_driver_sql(f'DROP TRIGGER "{trigger_name}"')
                connection.execute(
                    text(
                        "UPDATE canvas_generation_items SET latest_background_asset_id=:asset_id "
                        "WHERE id=:item_id"
                    ),
                    {"asset_id": ids["asset_b"], "item_id": ids["item"]},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_item_inputs SET asset_id=:asset_id "
                        "WHERE id=:input_id"
                    ),
                    {"asset_id": ids["asset_b"], "input_id": ids["input"]},
                )
                connection.execute(
                    text(
                        "UPDATE canvas_generation_attempts SET background_asset_id=:asset_id, "
                        "background_preview_asset_id=:asset_id, composed_asset_id=:asset_id, "
                        "composed_preview_asset_id=:asset_id WHERE id=:attempt_id"
                    ),
                    {"asset_id": ids["asset_b"], "attempt_id": ids["attempt"]},
                )
            from services.canvas.assets import collect_generation_asset_references

            Session = sessionmaker(bind=self.engine)
            with Session() as db:
                self.assertEqual(
                    {
                        "generationItemBackground",
                        "generationInput",
                        "generationAttemptBackground",
                        "generationAttemptBackgroundPreview",
                        "generationAttemptComposed",
                        "generationAttemptComposedPreview",
                    },
                    collect_generation_asset_references(
                        db,
                        project_id=ids["project_b"],
                        asset_id=ids["asset_b"],
                    ),
                )
        finally:
            self._restore_database(database, original)

    def test_attempt_preview_asset_foreign_keys_are_indexed(self):
        database, original = self._swap_database()
        try:
            database.init_db()
            indexes = {
                tuple(index.get("column_names") or ())
                for index in inspect(self.engine).get_indexes("canvas_generation_attempts")
            }
            self.assertIn(("background_preview_asset_id",), indexes)
            self.assertIn(("composed_preview_asset_id",), indexes)
        finally:
            self._restore_database(database, original)


if __name__ == "__main__":
    unittest.main()
