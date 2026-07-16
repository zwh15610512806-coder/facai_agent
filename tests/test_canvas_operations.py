import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import get_args
from uuid import uuid4

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch


OPERATION_TYPES = {"cutout", "compose", "export"}
OPERATION_STATUSES = {
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "interrupted",
}
OPERATION_COLUMNS = {
    "id",
    "project_id",
    "operation_type",
    "status",
    "attempt_count",
    "worker_id",
    "lease_expires_at",
    "heartbeat_at",
    "next_attempt_at",
    "cancel_requested_at",
    "input_asset_id",
    "output_asset_id",
    "request_snapshot_json",
    "processor_version",
    "idempotency_key",
    "safe_error_json",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
}


def _normalized_sql(value: str | None) -> str:
    return "".join((value or "").lower().split()).replace('"', "").replace("`", "")


class CanvasAssetOperationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-operations.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        import database

        self.database = database
        self.original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"

    def tearDown(self):
        self.database.engine, self.database.DATABASE_URL = self.original
        self.engine.dispose()
        self.tmp.cleanup()

    def test_literal_contract_and_exact_fresh_columns(self):
        import canvas_models

        self.assertEqual(OPERATION_TYPES, set(get_args(getattr(canvas_models, "OperationType", None))))
        self.assertEqual(
            OPERATION_STATUSES,
            set(get_args(getattr(canvas_models, "OperationStatus", None))),
        )

        self.database.init_db()
        schema = inspect(self.engine)
        self.assertIn("canvas_asset_operations", schema.get_table_names())
        self.assertEqual(
            OPERATION_COLUMNS,
            {column["name"] for column in schema.get_columns("canvas_asset_operations")},
        )

    def test_operation_checks_unique_key_indexes_and_delete_actions_are_exact(self):
        self.database.init_db()
        schema = inspect(self.engine)
        checks = {
            check["name"]: _normalized_sql(check.get("sqltext"))
            for check in schema.get_check_constraints("canvas_asset_operations")
        }
        expected_types = ",".join(f"'{value}'" for value in sorted(OPERATION_TYPES))
        expected_statuses = ",".join(f"'{value}'" for value in sorted(OPERATION_STATUSES))
        self.assertEqual(
            f"operation_typein({expected_types})",
            checks.get("ck_canvas_asset_operations_type"),
        )
        self.assertEqual(
            f"statusin({expected_statuses})",
            checks.get("ck_canvas_asset_operations_status"),
        )
        self.assertEqual(
            "attempt_count>=0",
            checks.get("ck_canvas_asset_operations_attempt_count"),
        )

        unique_columns = {
            tuple(constraint["column_names"])
            for constraint in schema.get_unique_constraints("canvas_asset_operations")
        }
        self.assertIn(("project_id", "operation_type", "idempotency_key"), unique_columns)

        indexes = {
            tuple(index["column_names"])
            for index in schema.get_indexes("canvas_asset_operations")
        }
        for expected in {
            ("status", "operation_type", "next_attempt_at", "created_at"),
            ("lease_expires_at",),
            ("project_id", "status"),
            ("input_asset_id",),
            ("output_asset_id",),
        }:
            self.assertIn(expected, indexes)

        foreign_keys = {
            tuple(foreign_key["constrained_columns"]): (
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                (foreign_key.get("options") or {}).get("ondelete"),
            )
            for foreign_key in schema.get_foreign_keys("canvas_asset_operations")
        }
        self.assertEqual(
            ("canvas_projects", ("id",), "CASCADE"),
            foreign_keys.get(("project_id",)),
        )
        for asset_column in ("input_asset_id", "output_asset_id"):
            self.assertEqual(
                ("canvas_assets", ("project_id", "id"), "RESTRICT"),
                foreign_keys.get(("project_id", asset_column)),
            )

    def test_database_rejects_invalid_operation_values_cross_project_assets_and_duplicates(self):
        self.database.init_db()
        project_a, project_b = str(uuid4()), str(uuid4())
        asset_a, asset_b = str(uuid4()), str(uuid4())
        with self.engine.begin() as connection:
            for project_id in (project_a, project_b):
                connection.execute(
                    text(
                        "INSERT INTO canvas_projects "
                        "(id, name, status, semantic_state, layout_state, schema_version, revision) "
                        "VALUES (:id, 'Operations', 'active', '{}', '{}', 1, 1)"
                    ),
                    {"id": project_id},
                )
            connection.execute(
                text(
                    "INSERT INTO canvas_assets "
                    "(id, project_id, asset_type, relative_path, original_filename, mime_type, "
                    "byte_count, width, height, sha256, transparency_status, metadata_json) "
                    "VALUES (:id, :project_id, 'source', 'source/a.png', 'a.png', 'image/png', "
                    "1, 1, 1, :sha256, 'unknown', '{}')"
                ),
                {
                    "id": asset_a,
                    "project_id": project_a,
                    "sha256": asset_a.replace("-", "").ljust(64, "0"),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO canvas_assets "
                    "(id, project_id, asset_type, relative_path, original_filename, mime_type, "
                    "byte_count, width, height, sha256, transparency_status, metadata_json) "
                    "VALUES (:id, :project_id, 'source', 'source/b.png', 'b.png', 'image/png', "
                    "1, 1, 1, :sha256, 'unknown', '{}')"
                ),
                {
                    "id": asset_b,
                    "project_id": project_b,
                    "sha256": asset_b.replace("-", "").ljust(64, "0"),
                },
            )

        def insert_operation(**overrides):
            values = {
                "id": str(uuid4()),
                "project_id": project_a,
                "operation_type": "cutout",
                "status": "queued",
                "attempt_count": 0,
                "input_asset_id": asset_a,
                "idempotency_key": "same-request",
            }
            values.update(overrides)
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO canvas_asset_operations "
                        "(id, project_id, operation_type, status, attempt_count, input_asset_id, "
                        "request_snapshot_json, idempotency_key) VALUES "
                        "(:id, :project_id, :operation_type, :status, :attempt_count, "
                        ":input_asset_id, '{}', :idempotency_key)"
                    ),
                    values,
                )

        insert_operation()
        insert_operation(
            id=str(uuid4()),
            operation_type="compose",
            idempotency_key="same-request",
        )
        insert_operation(
            id=str(uuid4()),
            project_id=project_b,
            input_asset_id=asset_b,
            operation_type="export",
            idempotency_key="same-request",
        )
        invalid_cases = (
            {"operation_type": "resize", "idempotency_key": "invalid-type"},
            {"status": "done", "idempotency_key": "invalid-status"},
            {"attempt_count": -1, "idempotency_key": "invalid-attempt"},
            {"project_id": project_b, "idempotency_key": "cross-project"},
            {"id": str(uuid4())},
        )
        for invalid in invalid_cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(IntegrityError):
                    insert_operation(**invalid)

    def test_operation_events_are_owner_validated_and_never_commit_the_caller(self):
        import canvas_models
        from services.canvas import events

        self.database.init_db()
        self.assertIs(
            getattr(canvas_models, "CanvasAssetOperation", None),
            events.SUBJECT_MODEL_REGISTRY["operation_id"],
        )
        self.assertIs(
            getattr(canvas_models, "CanvasGeneration", None),
            events.SUBJECT_MODEL_REGISTRY["generation_id"],
        )
        self.assertIs(
            getattr(canvas_models, "CanvasGenerationItem", None),
            events.SUBJECT_MODEL_REGISTRY["item_id"],
        )

        Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with Session() as db:
            project = canvas_models.CanvasProject(name="Operation event")
            db.add(project)
            db.flush()
            asset = canvas_models.CanvasAsset(
                project_id=project.id,
                asset_type="source",
                relative_path="source/event.png",
                original_filename="event.png",
                mime_type="image/png",
                byte_count=1,
                width=1,
                height=1,
                sha256="a" * 64,
            )
            db.add(asset)
            db.flush()
            operation = canvas_models.CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                input_asset_id=asset.id,
                idempotency_key="event-operation",
            )
            db.add(operation)
            db.flush()

            other_project = canvas_models.CanvasProject(name="Other operation owner")
            db.add(other_project)
            db.flush()
            other_asset = canvas_models.CanvasAsset(
                project_id=other_project.id,
                asset_type="source",
                relative_path="source/other.png",
                original_filename="other.png",
                mime_type="image/png",
                byte_count=1,
                width=1,
                height=1,
                sha256="b" * 64,
            )
            db.add(other_asset)
            db.flush()
            other_operation = canvas_models.CanvasAssetOperation(
                project_id=other_project.id,
                operation_type="cutout",
                input_asset_id=other_asset.id,
                idempotency_key="other-operation",
            )
            db.add(other_operation)
            db.flush()

            with patch.object(db, "commit") as commit_spy:
                canvas_event = events.append_canvas_event(
                    db,
                    project_id=project.id,
                    event_type="operation.queued",
                    operation_id=operation.id,
                    payload={"status": "queued"},
                )
                commit_spy.assert_not_called()

            self.assertIn(canvas_event, db.new)
            self.assertEqual(operation.id, canvas_event.operation_id)
            with self.assertRaises(events.CanvasEventValidationError):
                events.append_canvas_event(
                    db,
                    project_id=project.id,
                    event_type="operation.cross-project",
                    operation_id=other_operation.id,
                    payload={"status": "queued"},
                )

    def test_asset_references_restrict_delete_and_operation_events_set_null(self):
        self.database.init_db()
        project_id = str(uuid4())
        input_asset_id, output_asset_id, operation_id = (
            str(uuid4()),
            str(uuid4()),
            str(uuid4()),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO canvas_projects "
                    "(id, name, status, semantic_state, layout_state, schema_version, revision) "
                    "VALUES (:id, 'Delete behavior', 'active', '{}', '{}', 1, 1)"
                ),
                {"id": project_id},
            )
            for asset_id, asset_type in (
                (input_asset_id, "source"),
                (output_asset_id, "cutout"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO canvas_assets "
                        "(id, project_id, asset_type, relative_path, original_filename, "
                        "mime_type, byte_count, width, height, sha256, "
                        "transparency_status, metadata_json) VALUES "
                        "(:id, :project_id, :asset_type, :path, 'asset.png', "
                        "'image/png', 1, 1, 1, :sha256, 'unknown', '{}')"
                    ),
                    {
                        "id": asset_id,
                        "project_id": project_id,
                        "asset_type": asset_type,
                        "path": f"{asset_type}/{asset_id}.png",
                        "sha256": asset_id.replace("-", "").ljust(64, "0"),
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO canvas_asset_operations "
                    "(id, project_id, operation_type, status, attempt_count, "
                    "input_asset_id, output_asset_id, request_snapshot_json, "
                    "idempotency_key) VALUES "
                    "(:id, :project_id, 'cutout', 'succeeded', 1, :input_asset_id, "
                    ":output_asset_id, '{}', 'delete-behavior')"
                ),
                {
                    "id": operation_id,
                    "project_id": project_id,
                    "input_asset_id": input_asset_id,
                    "output_asset_id": output_asset_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO canvas_events "
                    "(project_id, event_type, operation_id, payload_json) "
                    "VALUES (:project_id, 'operation.succeeded', :operation_id, '{}')"
                ),
                {"project_id": project_id, "operation_id": operation_id},
            )

        for asset_id in (input_asset_id, output_asset_id):
            with self.subTest(asset_id=asset_id):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(
                            text("DELETE FROM canvas_assets WHERE id = :id"),
                            {"id": asset_id},
                        )

        with self.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM canvas_asset_operations WHERE id = :id"),
                {"id": operation_id},
            )
        with self.engine.connect() as connection:
            self.assertIsNone(
                connection.execute(
                    text(
                        "SELECT operation_id FROM canvas_events "
                        "WHERE event_type = 'operation.succeeded'"
                    )
                ).scalar_one()
            )


class CanvasOperationServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-operation-service.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )

        @event.listens_for(self.engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
            dbapi_connection.execute("PRAGMA journal_mode=WAL")
            dbapi_connection.execute("PRAGMA busy_timeout=5000")

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        try:
            database.init_db()
        finally:
            database.engine, database.DATABASE_URL = original

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    @staticmethod
    def _add_project_asset(db, *, name="Operations", project_id=None, asset_id=None):
        from canvas_models import CanvasAsset, CanvasProject

        project_id = project_id or str(uuid4())
        asset_id = asset_id or str(uuid4())
        project = CanvasProject(id=project_id, name=name)
        asset = CanvasAsset(
            id=asset_id,
            project_id=project_id,
            asset_type="source",
            relative_path=f"source/{asset_id}.png",
            original_filename="source.png",
            mime_type="image/png",
            byte_count=4,
            width=1,
            height=1,
            sha256=asset_id.replace("-", "").ljust(64, "0"),
        )
        db.add(project)
        db.flush()
        db.add(asset)
        db.commit()
        return project, asset

    @staticmethod
    def _add_asset(db, *, project_id, asset_type="cutout"):
        from canvas_models import CanvasAsset

        asset_id = str(uuid4())
        asset = CanvasAsset(
            id=asset_id,
            project_id=project_id,
            asset_type=asset_type,
            relative_path=f"{asset_type}/{asset_id}.png",
            original_filename=f"{asset_type}.png",
            mime_type="image/png",
            byte_count=4,
            width=1,
            height=1,
            sha256=asset_id.replace("-", "").ljust(64, "0"),
        )
        db.add(asset)
        db.flush()
        return asset

    def test_enqueue_is_savepoint_safe_fingerprinted_and_never_commits(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        with self.Session() as db:
            project, asset = self._add_project_asset(db)
            with (
                patch.object(db, "commit") as commit_spy,
                patch.object(db, "begin_nested", wraps=db.begin_nested) as savepoint_spy,
            ):
                created = operations.enqueue_asset_operation(
                    db,
                    project_id=project.id,
                    operation_type="cutout",
                    input_asset_id=asset.id,
                    idempotency_key="upload-cutout",
                    request_snapshot={"assetId": asset.id, "mode": "automatic"},
                )
                repeated = operations.enqueue_asset_operation(
                    db,
                    project_id=project.id,
                    operation_type="cutout",
                    input_asset_id=asset.id,
                    idempotency_key="upload-cutout",
                    request_snapshot={"mode": "automatic", "assetId": asset.id},
                )
                commit_spy.assert_not_called()
                self.assertEqual(1, savepoint_spy.call_count)

            self.assertEqual(created.id, repeated.id)
            db.flush()
            self.assertEqual(1, len(db.execute(select(CanvasAssetOperation)).scalars().all()))
            self.assertEqual(
                ["operation.queued"],
                [row.event_type for row in db.execute(select(CanvasEvent)).scalars().all()],
            )

            with self.assertRaises(operations.CanvasOperationIdempotencyConflict):
                operations.enqueue_asset_operation(
                    db,
                    project_id=project.id,
                    operation_type="cutout",
                    input_asset_id=asset.id,
                    idempotency_key="upload-cutout",
                    request_snapshot={"assetId": asset.id, "mode": "explicit"},
                )
            recursive_snapshot = {}
            recursive_snapshot["self"] = recursive_snapshot
            for invalid_snapshot in (
                recursive_snapshot,
                {"value": "x" * (operations.MAX_OPERATION_REQUEST_SNAPSHOT_BYTES + 1)},
            ):
                with self.subTest(invalid_snapshot_type=type(invalid_snapshot).__name__):
                    with self.assertRaises(ValueError):
                        operations.enqueue_asset_operation(
                            db,
                            project_id=project.id,
                            operation_type="cutout",
                            input_asset_id=asset.id,
                            idempotency_key=f"invalid-json-{uuid4()}",
                            request_snapshot=invalid_snapshot,
                        )
            compose = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="compose",
                input_asset_id=asset.id,
                idempotency_key="upload-cutout",
                request_snapshot={"assetId": asset.id},
            )
            self.assertNotEqual(created.id, compose.id)

            other_project, _ = self._add_project_asset(db, name="Other")
            with self.assertRaises(operations.CanvasOperationNotFound):
                operations.enqueue_asset_operation(
                    db,
                    project_id=other_project.id,
                    operation_type="cutout",
                    input_asset_id=asset.id,
                    idempotency_key="cross-project",
                    request_snapshot={},
                )

    def test_retry_is_idempotent_for_failed_and_interrupted_and_rolls_back_with_event(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        with self.Session() as db:
            project, asset = self._add_project_asset(db)
            operation = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="failed",
                attempt_count=2,
                worker_id="dead-worker",
                heartbeat_at=datetime(2026, 7, 14, 1, 0),
                lease_expires_at=datetime(2026, 7, 14, 1, 1),
                completed_at=datetime(2026, 7, 14, 1, 2),
                input_asset_id=asset.id,
                idempotency_key="failed-cutout",
                safe_error_json=json.dumps(
                    {
                        "code": "rembg_model_unavailable",
                        "message": "Model unavailable\nretry later",
                        "retryable": True,
                        "path": r"C:\\private\\model.onnx",
                        "traceback": "secret traceback",
                    }
                ),
            )
            db.add(operation)
            db.commit()
            operation_id = operation.id

            with patch.object(db, "commit") as commit_spy:
                retried = operations.retry_asset_operation(db, operation_id=operation_id)
                repeated = operations.retry_asset_operation(db, operation_id=operation_id)
                commit_spy.assert_not_called()
            self.assertEqual(operation_id, retried.id)
            self.assertEqual(operation_id, repeated.id)
            self.assertEqual("queued", retried.status)
            self.assertEqual(2, retried.attempt_count)
            self.assertIsNone(retried.worker_id)
            self.assertIsNone(retried.safe_error_json)
            self.assertIsNone(retried.completed_at)
            db.flush()
            events = db.execute(
                select(CanvasEvent).where(CanvasEvent.operation_id == operation_id)
            ).scalars().all()
            self.assertEqual(["operation.retried"], [row.event_type for row in events])
            db.rollback()

        with self.Session() as db:
            restored = db.get(CanvasAssetOperation, operation_id)
            self.assertEqual("failed", restored.status)
            self.assertEqual([], db.execute(select(CanvasEvent)).scalars().all())

    def test_retry_rejects_operations_owned_by_an_archived_project(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations, projects

        with self.Session() as db:
            project, asset = self._add_project_asset(db)
            operation = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="failed",
                attempt_count=1,
                input_asset_id=asset.id,
                idempotency_key="archived-failed-cutout",
            )
            db.add(operation)
            project.status = "archived"
            db.commit()

            with self.assertRaises(projects.CanvasProjectStatusConflict) as generic_error:
                operations.retry_asset_operation(db, operation_id=operation.id)
            self.assertEqual("archived", generic_error.exception.status)

            with self.assertRaises(projects.CanvasProjectStatusConflict) as cutout_error:
                operations.retry_cutout_for_asset(
                    db,
                    input_asset_id=asset.id,
                    client_request_id="archived-retry-click",
                )
            self.assertEqual("archived", cutout_error.exception.status)

            db.flush()
            self.assertEqual("failed", operation.status)
            self.assertEqual([], db.execute(select(CanvasEvent)).scalars().all())

    def test_cutout_retry_reuses_failures_and_explicit_success_request_ids(self):
        from canvas_models import CanvasAssetOperation
        from services.canvas import operations

        with self.Session() as db:
            project, source = self._add_project_asset(db)
            source.asset_type = "working"
            failed = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="interrupted",
                attempt_count=1,
                input_asset_id=source.id,
                idempotency_key="automatic-cutout",
            )
            db.add(failed)
            db.commit()

            retried = operations.retry_cutout_for_asset(
                db,
                input_asset_id=source.id,
                client_request_id="retry-click-1",
            )
            repeated = operations.retry_cutout_for_asset(
                db,
                input_asset_id=source.id,
                client_request_id="retry-click-1",
            )
            self.assertEqual(failed.id, retried.id)
            self.assertEqual(failed.id, repeated.id)
            with self.assertRaises(operations.CanvasOperationStatusConflict):
                operations.retry_cutout_for_asset(
                    db,
                    input_asset_id=source.id,
                    client_request_id="retry-click-2",
                )

            retried.status = "succeeded"
            retried.completed_at = datetime(2026, 7, 14, 2, 0)
            retried.output_asset_id = self._add_asset(db, project_id=project.id).id
            db.commit()
            old_output_id = retried.output_asset_id

            completed_retry_repeat = operations.retry_cutout_for_asset(
                db,
                input_asset_id=source.id,
                client_request_id="retry-click-1",
            )
            self.assertEqual(retried.id, completed_retry_repeat.id)

            explicit = operations.retry_cutout_for_asset(
                db,
                input_asset_id=source.id,
                client_request_id="explicit-recutout-1",
            )
            double_click = operations.retry_cutout_for_asset(
                db,
                input_asset_id=source.id,
                client_request_id="explicit-recutout-1",
            )
            self.assertEqual(explicit.id, double_click.id)
            self.assertNotEqual(retried.id, explicit.id)
            self.assertEqual("queued", explicit.status)
            self.assertEqual(
                operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
                explicit.processor_version,
            )
            explicit_snapshot = json.loads(explicit.request_snapshot_json)
            self.assertEqual(source.sha256, explicit_snapshot["inputSha256"])
            self.assertEqual(
                operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
                explicit_snapshot["processorVersion"],
            )
            self.assertEqual(old_output_id, retried.output_asset_id)
            with self.assertRaises(operations.CanvasOperationStatusConflict):
                operations.retry_cutout_for_asset(
                    db,
                    input_asset_id=source.id,
                    client_request_id="explicit-recutout-2",
                )

    def test_automatic_cutout_key_is_stable_and_lane_claim_is_atomic_and_transactional(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        now = datetime(2026, 7, 14, 3, 0)
        with self.Session() as db:
            project, source = self._add_project_asset(db)
            with self.assertRaises(operations.CanvasOperationStatusConflict) as invalid_input:
                operations.enqueue_automatic_cutout(
                    db,
                    project_id=project.id,
                    input_asset_id=source.id,
                )
            self.assertEqual("invalid_input", invalid_input.exception.status)
            source.asset_type = "working"
            db.flush()
            automatic = operations.enqueue_automatic_cutout(
                db,
                project_id=project.id,
                input_asset_id=source.id,
            )
            repeated = operations.enqueue_automatic_cutout(
                db,
                project_id=project.id,
                input_asset_id=source.id,
            )
            self.assertEqual(automatic.id, repeated.id)
            automatic_snapshot = json.loads(automatic.request_snapshot_json)
            self.assertIn(source.sha256, automatic.idempotency_key)
            self.assertIn(operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION, automatic.idempotency_key)
            self.assertEqual(source.sha256, automatic_snapshot["inputSha256"])
            self.assertEqual(
                operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
                automatic_snapshot["processorVersion"],
            )
            self.assertEqual(
                operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
                automatic.processor_version,
            )
            automatic.next_attempt_at = now - timedelta(seconds=1)
            compose = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="compose",
                input_asset_id=source.id,
                idempotency_key="compose-1",
                request_snapshot={"layout": "v1"},
            )
            compose.next_attempt_at = now - timedelta(seconds=1)

            archived_project, archived_source = self._add_project_asset(db, name="Archived")
            archived_project.status = "archived"
            archived_operation = CanvasAssetOperation(
                project_id=archived_project.id,
                operation_type="cutout",
                status="queued",
                input_asset_id=archived_source.id,
                idempotency_key="archived-cutout",
                next_attempt_at=now - timedelta(minutes=1),
            )
            db.add(archived_operation)
            db.commit()

        with self.Session() as db:
            with patch.object(db, "commit") as commit_spy:
                claimed = operations.claim_next_operation(
                    db,
                    worker_id="rembg-worker-1",
                    lane="rembg",
                    now=now,
                )
                commit_spy.assert_not_called()
            self.assertEqual(automatic.id, claimed.id)
            self.assertEqual("cutout", claimed.operation_type)
            self.assertEqual(1, claimed.attempt_count)
            self.assertEqual("rembg-worker-1", claimed.worker_id)
            db.flush()
            running = db.get(CanvasAssetOperation, automatic.id)
            self.assertEqual("running", running.status)
            self.assertEqual(
                ["operation.queued", "operation.running"],
                [
                    row.event_type
                    for row in db.execute(
                        select(CanvasEvent).where(CanvasEvent.operation_id == automatic.id)
                    ).scalars()
                ],
            )
            db.rollback()

        with self.Session() as db:
            self.assertEqual("queued", db.get(CanvasAssetOperation, automatic.id).status)
            self.assertEqual("queued", db.get(CanvasAssetOperation, archived_operation.id).status)
            self.assertEqual([], db.execute(select(CanvasEvent).where(
                CanvasEvent.event_type == "operation.running"
            )).scalars().all())
            local_claim = operations.claim_next_operation(
                db,
                worker_id="local-worker-1",
                lane="local",
                now=now,
            )
            self.assertEqual(compose.id, local_claim.id)
            with self.assertRaises(ValueError):
                operations.claim_next_operation(
                    db,
                    worker_id="worker",
                    lane="remote",
                    now=now,
                )

    def test_two_concurrent_rembg_claimants_cannot_claim_the_same_operation(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        now = datetime(2026, 7, 14, 4, 0)
        with self.Session() as db:
            project, working = self._add_project_asset(db)
            working.asset_type = "working"
            queued = operations.enqueue_automatic_cutout(
                db,
                project_id=project.id,
                input_asset_id=working.id,
            )
            queued.next_attempt_at = now
            db.commit()
            operation_id = queued.id

        barrier = threading.Barrier(2)

        def claim(worker_id):
            with self.Session() as db:
                barrier.wait(timeout=5)
                claimed = operations.claim_next_operation(
                    db,
                    worker_id=worker_id,
                    lane="rembg",
                    now=now,
                )
                db.commit()
                return None if claimed is None else claimed.id

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("concurrent-a", "concurrent-b")))

        self.assertEqual(1, results.count(operation_id), results)
        self.assertEqual(1, results.count(None), results)
        with self.Session() as db:
            restored = db.get(CanvasAssetOperation, operation_id)
            self.assertEqual("running", restored.status)
            self.assertEqual(1, restored.attempt_count)
            self.assertEqual(
                1,
                len(db.scalars(select(CanvasEvent).where(
                    CanvasEvent.operation_id == operation_id,
                    CanvasEvent.event_type == "operation.running",
                )).all()),
            )

    def test_expired_leases_requeue_only_the_requested_active_lane_without_committing(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        now = datetime(2026, 7, 14, 5, 0)
        with self.Session() as db:
            project, asset = self._add_project_asset(db)
            expired = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="running",
                attempt_count=1,
                worker_id="lost-worker",
                input_asset_id=asset.id,
                idempotency_key="expired-cutout",
                heartbeat_at=now - timedelta(minutes=10),
                lease_expires_at=now - timedelta(seconds=1),
            )
            future = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="running",
                attempt_count=1,
                worker_id="live-worker",
                input_asset_id=asset.id,
                idempotency_key="future-cutout",
                heartbeat_at=now,
                lease_expires_at=now + timedelta(minutes=5),
            )
            local = CanvasAssetOperation(
                project_id=project.id,
                operation_type="compose",
                status="running",
                attempt_count=1,
                worker_id="local-worker",
                input_asset_id=asset.id,
                idempotency_key="expired-compose",
                heartbeat_at=now - timedelta(minutes=10),
                lease_expires_at=now - timedelta(seconds=1),
            )
            db.add_all([expired, future, local])
            db.commit()

            with patch.object(db, "commit") as commit_spy:
                recovered = operations.recover_expired_operations(
                    db,
                    lane="rembg",
                    now=now,
                )
                commit_spy.assert_not_called()

            self.assertEqual(1, recovered)
            self.assertEqual("queued", expired.status)
            self.assertIsNone(expired.worker_id)
            self.assertIsNone(expired.lease_expires_at)
            self.assertEqual(1, expired.attempt_count)
            self.assertEqual("running", future.status)
            self.assertEqual("running", local.status)
            recovered_events = db.scalars(
                select(CanvasEvent).where(CanvasEvent.event_type == "operation.recovered")
            ).all()
            self.assertEqual([expired.id], [event.operation_id for event in recovered_events])

    def test_compositable_guard_prefers_cutout_and_requires_explicit_opaque_fallback(self):
        from canvas_models import CanvasAssetOperation
        from services.canvas import operations

        with self.Session() as db:
            project, working = self._add_project_asset(db)
            working.asset_type = "working"
            working.transparency_status = "opaque"
            queued = operations.enqueue_automatic_cutout(
                db,
                project_id=project.id,
                input_asset_id=working.id,
            )
            db.commit()

            with self.assertRaises(operations.CanvasProductAssetNotReady) as pending:
                operations.require_compositable_product_asset(
                    db,
                    project_id=project.id,
                    source_asset_id=working.id,
                )
            self.assertEqual("queued", pending.exception.status)
            self.assertEqual(
                working.id,
                operations.require_compositable_product_asset(
                    db,
                    project_id=project.id,
                    source_asset_id=working.id,
                    allow_opaque_fallback=True,
                ).id,
            )

            cutout = self._add_asset(db, project_id=project.id, asset_type="cutout")
            cutout.source_asset_id = working.id
            cutout.transparency_status = "transparent"
            queued.status = "succeeded"
            queued.output_asset_id = cutout.id
            db.commit()
            self.assertEqual(
                cutout.id,
                operations.require_compositable_product_asset(
                    db,
                    project_id=project.id,
                    source_asset_id=working.id,
                ).id,
            )

            transparent_project, transparent = self._add_project_asset(
                db,
                name="Transparent",
            )
            transparent.asset_type = "working"
            transparent.transparency_status = "transparent"
            db.commit()
            self.assertEqual(
                transparent.id,
                operations.require_compositable_product_asset(
                    db,
                    project_id=transparent_project.id,
                    source_asset_id=transparent.id,
                ).id,
            )

            other_project, _ = self._add_project_asset(db, name="Other")
            with self.assertRaises(operations.CanvasOperationNotFound):
                operations.require_compositable_product_asset(
                    db,
                    project_id=other_project.id,
                    source_asset_id=working.id,
                )

    def test_claim_token_heartbeats_and_terminal_updates_are_compare_and_swap_guarded(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        now = datetime(2026, 7, 14, 6, 0)
        with self.Session() as db:
            project, working = self._add_project_asset(db)
            queued = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="cutout",
                input_asset_id=working.id,
                idempotency_key="claim-token-cutout",
                request_snapshot={},
            )
            queued.next_attempt_at = now - timedelta(seconds=1)
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="owner-worker",
                lane="rembg",
                now=now,
            )
            db.commit()

            self.assertFalse(
                operations.heartbeat_claimed_operation(
                    db,
                    operation_id=claimed.id,
                    worker_id="wrong-worker",
                    attempt_count=claimed.attempt_count,
                    now=now + timedelta(seconds=30),
                )
            )
            output = self._add_asset(db, project_id=project.id, asset_type="cutout")
            output.source_asset_id = working.id
            output.transparency_status = "transparent"
            after_expiry = claimed.lease_expires_at + timedelta(microseconds=1)
            self.assertFalse(
                operations.heartbeat_claimed_operation(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    now=after_expiry,
                )
            )
            self.assertIsNone(
                operations.mark_claimed_operation_succeeded(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    output_asset_id=output.id,
                    now=after_expiry,
                )
            )
            self.assertFalse(
                operations.mark_claimed_operation_failed(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    safe_error={
                        "code": "expired_failure",
                        "message": "expired claims cannot publish failures",
                        "retryable": True,
                    },
                    now=after_expiry,
                )
            )
            self.assertTrue(
                operations.heartbeat_claimed_operation(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    now=now + timedelta(seconds=30),
                )
            )
            invalid_lineage = self._add_asset(
                db,
                project_id=project.id,
                asset_type="cutout",
            )
            with self.assertRaises(operations.CanvasOperationStatusConflict) as bad_lineage:
                operations.mark_claimed_operation_succeeded(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    output_asset_id=invalid_lineage.id,
                    now=now + timedelta(seconds=31),
                )
            self.assertEqual("invalid_output", bad_lineage.exception.status)
            with self.assertRaises(operations.CanvasOperationStatusConflict) as wrong_output:
                operations.mark_claimed_operation_succeeded(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    output_asset_id=working.id,
                    now=now + timedelta(seconds=31),
                )
            self.assertEqual("invalid_output", wrong_output.exception.status)
            self.assertIsNone(
                operations.mark_claimed_operation_succeeded(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count + 1,
                    output_asset_id=output.id,
                    now=now + timedelta(seconds=31),
                )
            )
            succeeded = operations.mark_claimed_operation_succeeded(
                db,
                operation_id=claimed.id,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
                output_asset_id=output.id,
                now=now + timedelta(seconds=31),
            )
            self.assertEqual("succeeded", succeeded.status)
            self.assertEqual(output.id, succeeded.output_asset_id)
            self.assertFalse(
                operations.mark_claimed_operation_failed(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    safe_error={
                        "code": "late_failure",
                        "message": "must not overwrite success",
                        "retryable": True,
                    },
                    now=now + timedelta(seconds=32),
                )
            )
            db.commit()

            restored = db.get(CanvasAssetOperation, claimed.id)
            self.assertEqual("succeeded", restored.status)
            event_types = [
                event.event_type
                for event in db.scalars(
                    select(CanvasEvent)
                    .where(CanvasEvent.operation_id == claimed.id)
                    .order_by(CanvasEvent.id)
                )
            ]
            self.assertEqual(
                ["operation.queued", "operation.running", "operation.succeeded"],
                event_types,
            )

    def test_unstarted_claim_can_be_released_for_the_next_worker_without_committing(self):
        from canvas_models import CanvasAssetOperation, CanvasEvent
        from services.canvas import operations

        now = datetime(2026, 7, 14, 6, 30)
        with self.Session() as db:
            project, working = self._add_project_asset(db)
            queued = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="cutout",
                input_asset_id=working.id,
                idempotency_key="release-unstarted-cutout",
                request_snapshot={},
            )
            queued.next_attempt_at = now
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="stopping-worker",
                lane="rembg",
                now=now,
            )
            db.commit()

            self.assertFalse(
                operations.release_claimed_operation(
                    db,
                    operation_id=claimed.id,
                    worker_id="wrong-worker",
                    attempt_count=claimed.attempt_count,
                    now=now + timedelta(seconds=1),
                )
            )
            with patch.object(db, "commit") as commit_spy:
                self.assertTrue(
                    operations.release_claimed_operation(
                        db,
                        operation_id=claimed.id,
                        worker_id=claimed.worker_id,
                        attempt_count=claimed.attempt_count,
                        now=now + timedelta(seconds=1),
                    )
                )
                commit_spy.assert_not_called()
            db.commit()

            restored = db.get(CanvasAssetOperation, claimed.id)
            self.assertEqual("queued", restored.status)
            self.assertIsNone(restored.worker_id)
            self.assertIsNone(restored.lease_expires_at)
            self.assertIsNone(restored.started_at)
            self.assertEqual(now + timedelta(seconds=1), restored.next_attempt_at)
            self.assertEqual(
                ["operation.queued", "operation.running", "operation.released"],
                [
                    event.event_type
                    for event in db.scalars(
                        select(CanvasEvent)
                        .where(CanvasEvent.operation_id == claimed.id)
                        .order_by(CanvasEvent.id)
                    )
                ],
            )


class CanvasOperationApiTests(unittest.TestCase):
    setUp = CanvasOperationServiceTests.setUp
    tearDown = CanvasOperationServiceTests.tearDown
    _add_project_asset = staticmethod(CanvasOperationServiceTests._add_project_asset)

    def test_list_get_and_retry_api_use_safe_wire_contract_and_commit(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import database
        from canvas_models import CanvasAssetOperation
        from routers.canvas.operations import router

        with self.Session() as db:
            project, source = self._add_project_asset(db)
            operation = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="failed",
                attempt_count=1,
                input_asset_id=source.id,
                idempotency_key="api-retry",
                request_snapshot_json='{"mode":"automatic"}',
                safe_error_json=json.dumps(
                    {
                        "code": "rembg_model_unavailable",
                        "message": "Model unavailable\nretry later",
                        "retryable": True,
                        "path": r"C:\\private\\model.onnx",
                        "traceback": "secret traceback",
                    }
                ),
            )
            db.add(operation)
            db.commit()
            operation_id = operation.id

        app = FastAPI()
        app.include_router(router, prefix="/api/canvas")

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[database.get_db] = override_db
        with TestClient(app) as client:
            listed = client.get(f"/api/canvas/projects/{project.id}/operations")
            self.assertEqual(200, listed.status_code, listed.text)
            self.assertEqual(operation_id, listed.json()["operations"][0]["id"])
            self.assertEqual(
                {
                    "code": "rembg_model_unavailable",
                    "message": "Model unavailable retry later",
                    "retryable": True,
                },
                listed.json()["operations"][0]["safeError"],
            )
            self.assertNotIn("private", listed.text)
            self.assertNotIn("traceback", listed.text)

            fetched = client.get(f"/api/canvas/operations/{operation_id}")
            self.assertEqual(200, fetched.status_code, fetched.text)
            self.assertEqual("api-retry", fetched.json()["idempotencyKey"])

            retried = client.post(f"/api/canvas/operations/{operation_id}/retry")
            self.assertEqual(200, retried.status_code, retried.text)
            self.assertEqual("queued", retried.json()["status"])

            missing = client.get(f"/api/canvas/operations/{uuid4()}")
            self.assertEqual(404, missing.status_code)
            self.assertEqual("canvas_resource_not_found", missing.json()["code"])

        with self.Session() as db:
            self.assertEqual("queued", db.get(CanvasAssetOperation, operation_id).status)

    def test_compose_enqueue_http_is_revisioned_and_returns_the_operation_id(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import database
        from canvas_models import CanvasAssetOperation
        from routers.canvas.operations import router

        with self.Session() as db:
            project, source = self._add_project_asset(db)
        operation_id = str(uuid4())

        def fake_enqueue(db, **_kwargs):
            operation = CanvasAssetOperation(
                id=operation_id,
                project_id=project.id,
                operation_type="compose",
                status="queued",
                attempt_count=0,
                input_asset_id=source.id,
                request_snapshot_json='{"boardId":"board-main"}',
                processor_version="pillow-12.3.0-compose-v1",
                idempotency_key="compose-http",
            )
            db.add(operation)
            db.flush()
            return operation
        app = FastAPI()
        app.include_router(router, prefix="/api/canvas")

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[database.get_db] = override_db
        with patch(
            "routers.canvas.operations.compose_service.enqueue_compose_operation",
            side_effect=fake_enqueue,
        ) as enqueue, TestClient(app) as client:
            response = client.post(
                f"/api/canvas/projects/{project.id}/compose",
                json={
                    "revision": 7,
                    "boardId": "board-main",
                    "backgroundAssetId": source.id,
                    "idempotencyKey": "compose-http",
                },
            )
        self.assertEqual(202, response.status_code, response.text)
        self.assertEqual(operation_id, response.json()["id"])
        enqueue.assert_called_once()
        self.assertEqual(7, enqueue.call_args.kwargs["expected_revision"])
        self.assertEqual("board-main", enqueue.call_args.kwargs["board_id"])
        self.assertEqual(source.id, enqueue.call_args.kwargs["background_asset_id"])


if __name__ == "__main__":
    unittest.main()
