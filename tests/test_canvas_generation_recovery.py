"""Recovery, cancellation, and retry contracts for durable Canvas generations."""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


class CanvasGenerationRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'recovery.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401
        from database import Base

        Base.metadata.create_all(self.engine)
        self.ids = self._seed_generation()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _seed_generation(self) -> dict[str, str]:
        from canvas_models import (
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
            CanvasProject,
            ImageModelProfile,
            ImageProviderConnection,
        )

        ids = {
            name: str(uuid4())
            for name in ("project", "provider", "model", "generation", "item", "attempt")
        }
        capabilities = {
            "text_to_image": True,
            "image_to_image": False,
            "mask_edit": False,
            "allowed_ratios": [],
            "allowed_sizes": [],
            "min_width": None,
            "max_width": None,
            "min_height": None,
            "max_height": None,
            "max_quantity": 1,
            "max_reference_images": 0,
            "reference_transfer": "none",
            "protocol": "async",
            "supports_cancel": False,
            "supports_idempotency": False,
            "supports_idempotency_lookup": False,
            "concurrency_limit": 1,
            "price_metadata": None,
        }
        provider_snapshot = {
            "id": ids["provider"],
            "adapterType": "fake",
            "name": "Fake",
            "baseUrl": "https://provider.invalid/generate",
            "authType": "bearer",
            "configVersion": 1,
            "concurrencyLimit": 1,
        }
        model_snapshot = {
            "id": ids["model"],
            "providerId": ids["provider"],
            "modelId": "fake-async",
            "displayName": "Fake Async",
            "configVersion": 1,
            "capabilities": capabilities,
            "configuration": {},
        }
        with self.Session() as db:
            db.add(CanvasProject(id=ids["project"], name="Recovery"))
            db.add(
                ImageProviderConnection(
                    id=ids["provider"],
                    adapter_type="fake",
                    name="Fake",
                    base_url="https://provider.invalid/generate",
                    auth_type="bearer",
                )
            )
            db.add(
                ImageModelProfile(
                    id=ids["model"],
                    provider_id=ids["provider"],
                    model_id="fake-async",
                    display_name="Fake Async",
                    capabilities_json=json.dumps(capabilities),
                )
            )
            db.add(
                CanvasGeneration(
                    id=ids["generation"],
                    project_id=ids["project"],
                    mode="complete_set",
                    project_revision=1,
                    request_snapshot_json="{}",
                    request_fingerprint="a" * 64,
                    idempotency_key="recovery-generation-key-01",
                    status="queued",
                    total_items=1,
                    storage_reservation_bytes=1_000_000_000,
                    storage_reservation_remaining_bytes=1_000_000_000,
                )
            )
            db.add(
                CanvasGenerationItem(
                    id=ids["item"],
                    generation_id=ids["generation"],
                    ordinal=0,
                    output_type="main",
                    board_id="board-1",
                    node_id="node-1",
                    board_order_snapshot=0,
                    provider_id=ids["provider"],
                    provider_config_version=1,
                    model_profile_id=ids["model"],
                    model_config_version=1,
                    provider_config_snapshot_json=json.dumps(provider_snapshot),
                    model_config_snapshot_json=json.dumps(model_snapshot),
                    prompt="studio",
                    width=64,
                    height=64,
                    ratio="1:1",
                    layout_hash="sha256:" + "b" * 64,
                    layout_snapshot_json=json.dumps({"version": 1}),
                    attempt_count=1,
                    status="queued",
                )
            )
            db.add(
                CanvasGenerationAttempt(
                    id=ids["attempt"],
                    item_id=ids["item"],
                    attempt_no=1,
                    provider_id=ids["provider"],
                    provider_config_version=1,
                    model_profile_id=ids["model"],
                    model_config_version=1,
                    provider_config_snapshot_json=json.dumps(provider_snapshot),
                    model_config_snapshot_json=json.dumps(model_snapshot),
                    status="queued",
                    provider_result_stage="awaiting_provider",
                    upstream_idempotency_key="upstream-key-1",
                    usage_json="{}",
                )
            )
            db.commit()
        return ids

    def _mark_attempt(self, *, status: str, item_status: str, generation_status: str) -> None:
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem

        with self.Session() as db:
            db.get(CanvasGenerationAttempt, self.ids["attempt"]).status = status
            db.get(CanvasGenerationItem, self.ids["item"]).status = item_status
            db.get(CanvasGeneration, self.ids["generation"]).status = generation_status
            db.commit()

    @staticmethod
    def _png_bytes() -> bytes:
        from PIL import Image

        output = io.BytesIO()
        with Image.new("RGBA", (64, 64), (14, 116, 144, 255)) as image:
            image.save(output, format="PNG")
        return output.getvalue()

    def test_recovery_leaves_queued_attempt_untouched(self):
        from canvas_models import CanvasGenerationAttempt
        from services.canvas.generation.recovery import recover_canvas_generation_work

        with self.Session() as db:
            summary = recover_canvas_generation_work(db, now=datetime.now(UTC).replace(tzinfo=None))
            db.commit()
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            self.assertEqual(1, summary.queued_untouched)
            self.assertEqual("queued", attempt.status)

    def test_recovery_resumes_saved_async_task_without_new_submission(self):
        from canvas_models import CanvasGenerationAttempt
        from services.canvas.generation.recovery import recover_canvas_generation_work

        self._mark_attempt(status="polling", item_status="running", generation_status="running")
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            attempt.external_task_id = "provider-task-1"
            summary = recover_canvas_generation_work(db, now=now)
            db.commit()
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            self.assertEqual(1, summary.polling_resumed)
            self.assertEqual("polling", attempt.status)
            self.assertEqual("provider-task-1", attempt.external_task_id)
            self.assertEqual(now, attempt.next_poll_at)

    def test_recovery_marks_uncertain_submission_unknown_without_resubmit(self):
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas.generation.recovery import recover_canvas_generation_work

        self._mark_attempt(status="submitting", item_status="running", generation_status="running")
        with self.Session() as db:
            summary = recover_canvas_generation_work(db, now=datetime.now(UTC).replace(tzinfo=None))
            db.commit()
        with self.Session() as db:
            self.assertEqual(1, summary.marked_unknown)
            self.assertEqual("unknown", db.get(CanvasGenerationAttempt, self.ids["attempt"]).status)
            self.assertEqual("unknown", db.get(CanvasGenerationItem, self.ids["item"]).status)
            self.assertEqual("unknown", db.get(CanvasGeneration, self.ids["generation"]).status)

    def test_recovery_promotes_verified_temp_locally_without_provider_submission(self):
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas import storage
        from services.canvas.composition import composition_layout_hash
        from services.canvas.composition_schema import CompositionLayout, DEFAULT_COMPOSITION_LAYOUT
        from services.canvas.generation.recovery import recover_canvas_generation_work
        from services.canvas.generation.results import materialize_provider_result
        from services.canvas.provider_schemas import ControlledImageBytes

        layout = CompositionLayout.model_validate(DEFAULT_COMPOSITION_LAYOUT)
        source_id, render_id, layer_id = (str(uuid4()) for _ in range(3))
        with self.Session() as db:
            item = db.get(CanvasGenerationItem, self.ids["item"])
            item.layout_hash = composition_layout_hash(layout)
            item.layout_snapshot_json = json.dumps(
                {
                    "version": 1,
                    "compositionGroupId": "group-1",
                    "composition": layout.model_dump(by_alias=True),
                    "layoutHash": item.layout_hash,
                    "productLayer": {
                        "id": layer_id,
                        "sourceAssetId": source_id,
                        "renderAssetId": render_id,
                        "allowOpaqueFallback": True,
                        "sourceAssetSha256": "a" * 64,
                        "renderAssetSha256": "b" * 64,
                        "sourceWidth": 64,
                        "sourceHeight": 64,
                        "renderWidth": 64,
                        "renderHeight": 64,
                        "transform": {"x": 0.5, "y": 0.9, "scale": 0.8, "rotation": 0},
                    },
                    "textSnapshots": [],
                    "outputBoard": {"id": item.board_id},
                    "outputNode": {"id": item.node_id},
                }
            )
            db.get(CanvasGenerationAttempt, self.ids["attempt"]).status = "submitting"
            item.status = "running"
            db.get(CanvasGeneration, self.ids["generation"]).status = "running"
            db.commit()

        data_root = Path(self.tmp.name) / "canvas-data"
        now = datetime.now(UTC).replace(tzinfo=None)
        with patch.object(storage, "CANVAS_DATA_DIR", str(data_root)):
            asyncio.run(
                materialize_provider_result(
                    project_id=self.ids["project"],
                    attempt_id=self.ids["attempt"],
                    image=ControlledImageBytes(self._png_bytes()),
                )
            )
            with self.Session() as db:
                summary = recover_canvas_generation_work(db, now=now)
                db.commit()
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            item = db.get(CanvasGenerationItem, self.ids["item"])
            self.assertEqual(1, summary.local_results_promoted)
            self.assertEqual("succeeded", attempt.status)
            self.assertEqual("composing", attempt.provider_result_stage)
            self.assertEqual("composing", item.status)
            self.assertIsNotNone(attempt.background_asset_id)
            self.assertIsNotNone(attempt.compose_operation_id)

    def test_completed_sync_result_is_promoted_after_local_cancel_request(self):
        from canvas_models import CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas import storage
        from services.canvas.composition import composition_layout_hash
        from services.canvas.composition_schema import CompositionLayout, DEFAULT_COMPOSITION_LAYOUT
        from services.canvas.generation.recovery import request_generation_cancel
        from services.canvas.generation.results import (
            materialize_provider_result,
            promote_materialized_provider_result,
        )
        from services.canvas.generation.worker import claim_next_attempt, prepare_claimed_attempt_for_execution
        from services.canvas.provider_schemas import ControlledImageBytes

        layout = CompositionLayout.model_validate(DEFAULT_COMPOSITION_LAYOUT)
        source_id, render_id, layer_id = (str(uuid4()) for _ in range(3))
        with self.Session() as db:
            item = db.get(CanvasGenerationItem, self.ids["item"])
            item.layout_hash = composition_layout_hash(layout)
            item.layout_snapshot_json = json.dumps(
                {
                    "version": 1,
                    "compositionGroupId": "group-1",
                    "composition": layout.model_dump(by_alias=True),
                    "layoutHash": item.layout_hash,
                    "productLayer": {
                        "id": layer_id,
                        "sourceAssetId": source_id,
                        "renderAssetId": render_id,
                        "allowOpaqueFallback": True,
                        "sourceAssetSha256": "a" * 64,
                        "renderAssetSha256": "b" * 64,
                        "sourceWidth": 64,
                        "sourceHeight": 64,
                        "renderWidth": 64,
                        "renderHeight": 64,
                        "transform": {"x": 0.5, "y": 0.9, "scale": 0.8, "rotation": 0},
                    },
                    "textSnapshots": [],
                    "outputBoard": {"id": item.board_id},
                    "outputNode": {"id": item.node_id},
                }
            )
            db.commit()
        now = datetime.now(UTC).replace(tzinfo=None)
        data_root = Path(self.tmp.name) / "canvas-data"
        with patch.object(storage, "CANVAS_DATA_DIR", str(data_root)):
            with self.Session() as db:
                claim = claim_next_attempt(db, worker_id="sync-cancel-test", now=now)
                db.commit()
            with self.Session() as db:
                self.assertTrue(prepare_claimed_attempt_for_execution(db, claim=claim, now=now))
                db.commit()
            with self.Session() as db:
                request_generation_cancel(db, generation_id=self.ids["generation"], now=now)
                db.commit()
            asyncio.run(
                materialize_provider_result(
                    project_id=self.ids["project"],
                    attempt_id=self.ids["attempt"],
                    image=ControlledImageBytes(self._png_bytes()),
                )
            )
            with self.Session() as db:
                promote_materialized_provider_result(
                    db,
                    attempt_id=self.ids["attempt"],
                    claim_token=claim.claim_token,
                    provider_request_id="sync-result",
                    external_task_id=None,
                    now=now,
                )
                db.commit()
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            item = db.get(CanvasGenerationItem, self.ids["item"])
            self.assertEqual("succeeded", attempt.status)
            self.assertEqual("composing", item.status)
            self.assertIsNotNone(attempt.compose_operation_id)

    def test_cancelling_queued_generation_preserves_history_and_cancels_local_work(self):
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas.generation.recovery import request_generation_cancel

        with self.Session() as db:
            request_generation_cancel(db, generation_id=self.ids["generation"])
            db.commit()
        with self.Session() as db:
            self.assertEqual("cancelled", db.get(CanvasGeneration, self.ids["generation"]).status)
            self.assertEqual("cancelled", db.get(CanvasGenerationItem, self.ids["item"]).status)
            self.assertEqual("cancelled", db.get(CanvasGenerationAttempt, self.ids["attempt"]).status)

    def test_non_cancellable_async_work_keeps_polling_after_local_cancel_request(self):
        from canvas_models import CanvasGenerationAttempt
        from services.canvas.generation.recovery import request_generation_cancel
        from services.canvas.generation.worker import claim_next_attempt

        self._mark_attempt(status="polling", item_status="running", generation_status="running")
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            db.get(CanvasGenerationAttempt, self.ids["attempt"]).external_task_id = "provider-task-1"
            request_generation_cancel(db, generation_id=self.ids["generation"], now=now)
            db.commit()
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            self.assertEqual("polling", attempt.status)
            self.assertEqual("provider_cancel_unsupported", attempt.normalized_error_code)
        with self.Session() as db:
            claim = claim_next_attempt(db, worker_id="recovery-test", now=now)
            db.commit()
        self.assertIsNotNone(claim)
        self.assertEqual("polling", claim.status)

    def test_cancel_capable_async_task_calls_provider_and_finishes_cancelled(self):
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas.generation.recovery import request_generation_cancel
        from services.canvas.generation.worker import (
            claim_next_attempt,
            execute_claimed_attempt,
            persist_attempt_execution_result,
            prepare_claimed_attempt_for_execution,
        )
        from services.canvas.provider_schemas import ProviderCancelResult, ProviderRuntime
        from services.canvas.providers.registry import ProviderRegistry

        self._mark_attempt(status="polling", item_status="running", generation_status="running")
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            item = db.get(CanvasGenerationItem, self.ids["item"])
            for record in (attempt, item):
                snapshot = json.loads(record.model_config_snapshot_json)
                snapshot["capabilities"]["supports_cancel"] = True
                record.model_config_snapshot_json = json.dumps(snapshot)
            attempt.external_task_id = "provider-task-1"
            request_generation_cancel(db, generation_id=self.ids["generation"], now=now)
            db.commit()

        class CancelAdapter:
            adapter_type = "fake"

            def __init__(self) -> None:
                self.cancelled_task_ids: list[str | None] = []

            def runtime_factory(self):
                return ProviderRuntime(api_key="", transport=object())

            def validate_request(self, request, capabilities):
                return None

            async def submit(self, request, runtime):  # pragma: no cover - must not submit
                raise AssertionError("cancel flow must not submit")

            async def poll(self, submission, runtime):  # pragma: no cover - cancellation wins
                raise AssertionError("cancelled task must not be polled first")

            async def cancel(self, submission, runtime):
                self.cancelled_task_ids.append(submission.external_task_id)
                return ProviderCancelResult(kind="cancelled")

            async def recover_by_idempotency_key(self, upstream_key, runtime):  # pragma: no cover
                raise AssertionError("cancel flow must not recover")

        adapter = CancelAdapter()
        registry = ProviderRegistry()
        registry.register(adapter)
        with self.Session() as db:
            claim = claim_next_attempt(db, worker_id="cancel-test", now=now)
            db.commit()
        self.assertIsNotNone(claim)
        with self.Session() as db:
            self.assertTrue(prepare_claimed_attempt_for_execution(db, claim=claim, now=now))
            db.commit()
        result = asyncio.run(execute_claimed_attempt(claim, registry=registry))
        self.assertEqual("cancelled", result.kind)
        self.assertEqual(["provider-task-1"], adapter.cancelled_task_ids)
        with self.Session() as db:
            self.assertTrue(persist_attempt_execution_result(db, claim=claim, result=result, now=now))
            db.commit()
        with self.Session() as db:
            self.assertEqual("cancelled", db.get(CanvasGenerationAttempt, self.ids["attempt"]).status)
            self.assertEqual("cancelled", db.get(CanvasGenerationItem, self.ids["item"]).status)
            generation = db.get(CanvasGeneration, self.ids["generation"])
            self.assertEqual("cancelled", generation.status)
            self.assertEqual(0, generation.storage_reservation_remaining_bytes)

    def test_unknown_retry_requires_restored_capacity_before_creating_attempt(self):
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas import storage
        from services.canvas.generation.recovery import resolve_unknown_item

        self._mark_attempt(status="unknown", item_status="unknown", generation_status="unknown")
        with self.Session() as db:
            generation = db.get(CanvasGeneration, self.ids["generation"])
            generation.storage_reservation_remaining_bytes = 0
            db.commit()

        with self.Session() as db, patch.object(
            storage,
            "assert_canvas_capacity",
            side_effect=storage.CanvasStorageError("canvas_storage_low_disk", "full"),
        ):
            with self.assertRaises(storage.CanvasStorageError):
                resolve_unknown_item(db, item_id=self.ids["item"], action="retry")
            db.rollback()

        with self.Session() as db:
            attempts = list(
                db.scalars(
                    select(CanvasGenerationAttempt)
                    .where(CanvasGenerationAttempt.item_id == self.ids["item"])
                    .order_by(CanvasGenerationAttempt.attempt_no)
                ).all()
            )
            item = db.get(CanvasGenerationItem, self.ids["item"])
            generation = db.get(CanvasGeneration, self.ids["generation"])
            self.assertEqual([1], [attempt.attempt_no for attempt in attempts])
            self.assertEqual("unknown", item.status)
            self.assertEqual("unknown", generation.status)
            self.assertEqual(0, generation.storage_reservation_remaining_bytes)

    def test_confirmed_unknown_retry_reopens_generation_and_keeps_prior_attempt_immutable(self):
        from canvas_models import CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas import storage
        from services.canvas.generation.recovery import resolve_unknown_item

        self._mark_attempt(status="unknown", item_status="unknown", generation_status="unknown")
        terminal_at = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            generation = db.get(CanvasGeneration, self.ids["generation"])
            generation.completed_at = terminal_at
            generation.storage_reservation_remaining_bytes = 0
            db.commit()

        with self.Session() as db, patch.object(storage, "assert_canvas_capacity") as capacity:
            retry = resolve_unknown_item(db, item_id=self.ids["item"], action="retry")
            db.commit()

        with self.Session() as db:
            attempts = list(
                db.scalars(
                    select(CanvasGenerationAttempt)
                    .where(CanvasGenerationAttempt.item_id == self.ids["item"])
                    .order_by(CanvasGenerationAttempt.attempt_no)
                ).all()
            )
            item = db.get(CanvasGenerationItem, self.ids["item"])
            generation = db.get(CanvasGeneration, self.ids["generation"])
            self.assertEqual([1, 2], [attempt.attempt_no for attempt in attempts])
            self.assertEqual("unknown", attempts[0].status)
            self.assertEqual(retry.id, attempts[1].id)
            self.assertEqual("queued", item.status)
            self.assertEqual("running", generation.status)
            self.assertIsNone(generation.completed_at)
            self.assertGreater(generation.storage_reservation_remaining_bytes, 0)
            capacity.assert_called_once()

    def test_retry_expands_legacy_reservation_ceiling_before_restoring_peak(self):
        from canvas_models import CanvasGeneration
        from services.canvas import storage
        from services.canvas.generation.recovery import resolve_unknown_item

        self._mark_attempt(status="unknown", item_status="unknown", generation_status="unknown")
        with self.Session() as db:
            generation = db.get(CanvasGeneration, self.ids["generation"])
            generation.storage_reservation_bytes = 1
            generation.storage_reservation_remaining_bytes = 0
            db.commit()
        with self.Session() as db, patch.object(storage, "assert_canvas_capacity"):
            resolve_unknown_item(db, item_id=self.ids["item"], action="retry")
            db.commit()
        with self.Session() as db:
            generation = db.get(CanvasGeneration, self.ids["generation"])
            self.assertGreater(generation.storage_reservation_remaining_bytes, 1)
            self.assertGreaterEqual(
                generation.storage_reservation_bytes,
                generation.storage_reservation_remaining_bytes,
            )

    def test_duplicate_paid_retry_reuses_the_already_restored_attempt_and_reservation(self):
        from canvas_models import CanvasGeneration
        from services.canvas import storage
        from services.canvas.generation.recovery import retry_generation_item

        self._mark_attempt(status="unknown", item_status="unknown", generation_status="unknown")
        with self.Session() as db:
            db.get(CanvasGeneration, self.ids["generation"]).storage_reservation_remaining_bytes = 0
            db.commit()
        with patch.object(storage, "assert_canvas_capacity") as capacity:
            with self.Session() as db:
                first = retry_generation_item(db, item_id=self.ids["item"])
                db.commit()
            with self.Session() as db:
                replay = retry_generation_item(db, item_id=self.ids["item"])
                db.commit()
        self.assertTrue(first.paid_retry)
        self.assertEqual(first, replay)
        capacity.assert_called_once()

    def _seed_failed_compose(self) -> str:
        from canvas_models import (
            CanvasAsset,
            CanvasAssetOperation,
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
        )

        asset_id, operation_id = str(uuid4()), str(uuid4())
        with self.Session() as db:
            generation = db.get(CanvasGeneration, self.ids["generation"])
            item = db.get(CanvasGenerationItem, self.ids["item"])
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            db.add(
                CanvasAsset(
                    id=asset_id,
                    project_id=self.ids["project"],
                    asset_type="generated_background",
                    relative_path=f"generated/{asset_id}.png",
                    original_filename="background.png",
                    mime_type="image/png",
                    byte_count=64,
                    width=64,
                    height=64,
                    sha256="c" * 64,
                    transparency_status="opaque",
                )
            )
            db.add(
                CanvasAssetOperation(
                    id=operation_id,
                    project_id=self.ids["project"],
                    operation_type="compose",
                    status="failed",
                    attempt_count=1,
                    input_asset_id=asset_id,
                    request_snapshot_json="{}",
                    idempotency_key=f"generation-compose:{attempt.id}",
                )
            )
            attempt.status = "succeeded"
            attempt.provider_result_stage = "composing"
            attempt.background_asset_id = asset_id
            attempt.compose_operation_id = operation_id
            item.status = "failed"
            generation.status = "failed"
            generation.completed_at = datetime.now(UTC).replace(tzinfo=None)
            generation.storage_reservation_remaining_bytes = 0
            db.commit()
        return operation_id

    def test_compose_retry_requires_capacity_without_requeueing_local_operation(self):
        from canvas_models import CanvasAssetOperation, CanvasGeneration, CanvasGenerationItem
        from services.canvas import storage
        from services.canvas.generation.recovery import retry_generation_item

        operation_id = self._seed_failed_compose()
        with self.Session() as db, patch.object(
            storage,
            "assert_canvas_capacity",
            side_effect=storage.CanvasStorageError("canvas_storage_low_disk", "full"),
        ):
            with self.assertRaises(storage.CanvasStorageError):
                retry_generation_item(db, item_id=self.ids["item"])
            db.rollback()

        with self.Session() as db:
            self.assertEqual("failed", db.get(CanvasAssetOperation, operation_id).status)
            self.assertEqual("failed", db.get(CanvasGenerationItem, self.ids["item"]).status)
            self.assertEqual("failed", db.get(CanvasGeneration, self.ids["generation"]).status)

    def test_compose_retry_requeues_only_local_operation_without_new_paid_attempt(self):
        from canvas_models import (
            CanvasAssetOperation,
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
        )
        from services.canvas import storage
        from services.canvas.generation.recovery import retry_generation_item

        operation_id = self._seed_failed_compose()
        with self.Session() as db, patch.object(storage, "assert_canvas_capacity") as capacity:
            result = retry_generation_item(db, item_id=self.ids["item"])
            db.commit()

        with self.Session() as db:
            attempts = list(
                db.scalars(
                    select(CanvasGenerationAttempt)
                    .where(CanvasGenerationAttempt.item_id == self.ids["item"])
                    .order_by(CanvasGenerationAttempt.attempt_no)
                ).all()
            )
            self.assertFalse(result.paid_retry)
            self.assertEqual(operation_id, result.compose_operation_id)
            self.assertEqual([1], [attempt.attempt_no for attempt in attempts])
            self.assertEqual("queued", db.get(CanvasAssetOperation, operation_id).status)
            self.assertEqual("composing", db.get(CanvasGenerationItem, self.ids["item"]).status)
            generation = db.get(CanvasGeneration, self.ids["generation"])
            self.assertEqual("running", generation.status)
            self.assertIsNone(generation.completed_at)
            capacity.assert_called_once()

    def test_duplicate_compose_retry_reuses_the_queued_local_operation_and_reservation(self):
        from services.canvas import storage
        from services.canvas.generation.recovery import retry_generation_item

        self._seed_failed_compose()
        with patch.object(storage, "assert_canvas_capacity") as capacity:
            with self.Session() as db:
                first = retry_generation_item(db, item_id=self.ids["item"])
                db.commit()
            with self.Session() as db:
                replay = retry_generation_item(db, item_id=self.ids["item"])
                db.commit()
        self.assertFalse(first.paid_retry)
        self.assertEqual(first, replay)
        capacity.assert_called_once()

    def test_cancel_queued_compose_completes_item_without_discarding_provider_attempt(self):
        from canvas_models import CanvasAssetOperation, CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas.generation.recovery import request_generation_cancel

        operation_id = self._seed_failed_compose()
        with self.Session() as db:
            db.get(CanvasAssetOperation, operation_id).status = "queued"
            db.get(CanvasGenerationItem, self.ids["item"]).status = "composing"
            db.get(CanvasGeneration, self.ids["generation"]).status = "running"
            db.commit()
        with self.Session() as db:
            request_generation_cancel(db, generation_id=self.ids["generation"])
            db.commit()
        with self.Session() as db:
            operation = db.get(CanvasAssetOperation, operation_id)
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            item = db.get(CanvasGenerationItem, self.ids["item"])
            generation = db.get(CanvasGeneration, self.ids["generation"])
            self.assertEqual("cancelled", operation.status)
            self.assertEqual("succeeded", attempt.status)
            self.assertEqual("cancelled", item.status)
            self.assertEqual("cancelled", generation.status)

    def test_paid_action_routes_protect_cancel_and_return_capacity_failure_without_retry_side_effect(self):
        import config
        from canvas_models import CanvasGeneration
        from database import get_db
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.canvas import router as canvas_router
        from services.canvas import storage

        token = "recovery-paid-access-token"
        app = FastAPI()
        app.include_router(canvas_router, prefix="/api/canvas")

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        with patch.object(config, "CANVAS_ACCESS_TOKEN", token, create=True):
            with TestClient(app) as client:
                locked = client.post(f"/api/canvas/generations/{self.ids['generation']}/cancel")
                self.assertEqual(401, locked.status_code, locked.text)
                self.assertEqual(
                    200,
                    client.post("/api/canvas/access/unlock", json={"token": token}).status_code,
                )
                cancelled = client.post(f"/api/canvas/generations/{self.ids['generation']}/cancel")
                self.assertEqual(200, cancelled.status_code, cancelled.text)
                self.assertEqual("cancelled", cancelled.json()["status"])

        self._mark_attempt(status="unknown", item_status="unknown", generation_status="unknown")
        with self.Session() as db:
            db.get(CanvasGeneration, self.ids["generation"]).storage_reservation_remaining_bytes = 0
            db.commit()
        with patch.object(config, "CANVAS_ACCESS_TOKEN", token, create=True), patch.object(
            storage,
            "assert_canvas_capacity",
            side_effect=storage.CanvasStorageError("canvas_storage_low_disk", "full"),
        ):
            with TestClient(app) as client:
                self.assertEqual(
                    200,
                    client.post("/api/canvas/access/unlock", json={"token": token}).status_code,
                )
                insufficient = client.post(
                    f"/api/canvas/generation-items/{self.ids['item']}/resolve-unknown",
                    json={"action": "retry"},
                )
                self.assertEqual(507, insufficient.status_code, insufficient.text)
                self.assertEqual("canvas_storage_low_disk", insufficient.json()["code"])
        with self.Session() as db:
            self.assertEqual("unknown", db.get(CanvasGeneration, self.ids["generation"]).status)


if __name__ == "__main__":
    unittest.main()
