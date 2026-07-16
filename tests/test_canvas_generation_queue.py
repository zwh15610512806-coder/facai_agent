"""State, lease, and execution contracts for the Canvas generation queue."""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


class GenerationStateMachineTests(unittest.TestCase):
    def test_only_documented_attempt_item_and_generation_transitions_are_legal(self):
        from services.canvas.generation.state import (
            InvalidGenerationTransition,
            transition_attempt,
            transition_generation,
            transition_item,
        )

        transition_attempt("queued", "submitting")
        transition_attempt("submitting", "polling")
        transition_attempt("submitting", "succeeded")
        transition_item("queued", "running")
        transition_item("running", "composing")
        transition_item("composing", "succeeded")
        transition_generation("queued", "running")
        transition_generation("running", "partially_failed")
        transition_generation("partially_failed", "running")
        for current, target, transition in (
            ("succeeded", "queued", transition_attempt),
            ("queued", "succeeded", transition_item),
            ("succeeded", "running", transition_generation),
        ):
            with self.subTest(current=current, target=target):
                with self.assertRaises(InvalidGenerationTransition):
                    transition(current, target)

    def test_generation_aggregation_distinguishes_all_terminal_outcomes_and_retry(self):
        from services.canvas.generation.state import aggregate_generation_status

        self.assertEqual("succeeded", aggregate_generation_status(["succeeded"], "running"))
        self.assertEqual("failed", aggregate_generation_status(["failed", "failed"], "running"))
        self.assertEqual("cancelled", aggregate_generation_status(["cancelled"], "cancel_requested"))
        self.assertEqual("unknown", aggregate_generation_status(["succeeded", "unknown"], "running"))
        self.assertEqual(
            "partially_failed",
            aggregate_generation_status(["succeeded", "failed"], "running"),
        )
        self.assertEqual(
            "running",
            aggregate_generation_status(["succeeded", "queued"], "partially_failed"),
        )


class GenerationQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'queue.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401
        from database import Base

        Base.metadata.create_all(self.engine)
        self.ids = self._seed_queue()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _seed_queue(self) -> dict[str, str]:
        from canvas_models import (
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
            CanvasProject,
            ImageModelProfile,
            ImageProviderConnection,
        )

        ids = {name: str(uuid4()) for name in ("project", "provider", "model", "generation", "item", "attempt")}
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
            "protocol": "sync",
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
            "modelId": "fake-sync",
            "displayName": "Fake Sync",
            "configVersion": 1,
            "capabilities": capabilities,
            "configuration": {},
        }
        with self.Session() as db:
            db.add(CanvasProject(id=ids["project"], name="Queue"))
            db.add(
                ImageProviderConnection(
                    id=ids["provider"], adapter_type="fake", name="Fake",
                    base_url="https://provider.invalid/generate", auth_type="bearer",
                )
            )
            db.add(
                ImageModelProfile(
                    id=ids["model"], provider_id=ids["provider"], model_id="fake-sync",
                    display_name="Fake Sync", capabilities_json=json.dumps(capabilities),
                )
            )
            db.add(
                CanvasGeneration(
                    id=ids["generation"], project_id=ids["project"], mode="complete_set",
                    project_revision=1, request_snapshot_json="{}", request_fingerprint="a" * 64,
                    idempotency_key="queue-generation-key-01", status="queued", total_items=1,
                    storage_reservation_bytes=1_000_000,
                    storage_reservation_remaining_bytes=1_000_000,
                )
            )
            db.add(
                CanvasGenerationItem(
                    id=ids["item"], generation_id=ids["generation"], ordinal=0,
                    output_type="main", board_id="board-1", node_id="node-1",
                    board_order_snapshot=0, provider_id=ids["provider"], provider_config_version=1,
                    model_profile_id=ids["model"], model_config_version=1,
                    provider_config_snapshot_json=json.dumps(provider_snapshot),
                    model_config_snapshot_json=json.dumps(model_snapshot), prompt="studio",
                    width=64, height=64, ratio="1:1", layout_hash="sha256:" + "b" * 64,
                    layout_snapshot_json=json.dumps({"version": 1}), attempt_count=1, status="queued",
                )
            )
            db.add(
                CanvasGenerationAttempt(
                    id=ids["attempt"], item_id=ids["item"], attempt_no=1,
                    provider_id=ids["provider"], provider_config_version=1,
                    model_profile_id=ids["model"], model_config_version=1,
                    provider_config_snapshot_json=json.dumps(provider_snapshot),
                    model_config_snapshot_json=json.dumps(model_snapshot), status="queued",
                    provider_result_stage="awaiting_provider", upstream_idempotency_key="upstream-key-1",
                )
            )
            db.commit()
        return ids

    def test_one_attempt_claim_has_unique_fencing_token_and_short_lease(self):
        from services.canvas.generation.worker import claim_next_attempt

        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            first = claim_next_attempt(db, worker_id="worker", now=now)
            db.commit()
        with self.Session() as db:
            second = claim_next_attempt(db, worker_id="worker", now=now)
            db.commit()
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertTrue(first.claim_token.startswith("worker:"))
        self.assertGreater(first.lease_expires_at, now)

    def test_stale_claim_cannot_heartbeat_after_reclaim_even_with_same_worker_name(self):
        from services.canvas.generation.worker import (
            claim_next_attempt,
            heartbeat_claimed_attempt,
            recover_expired_generation_claims,
        )

        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            first = claim_next_attempt(db, worker_id="worker", now=now)
            db.commit()
        later = first.lease_expires_at + timedelta(seconds=1)
        with self.Session() as db:
            recover_expired_generation_claims(db, now=later)
            db.commit()
        with self.Session() as db:
            second = claim_next_attempt(db, worker_id="worker", now=later)
            db.commit()
        self.assertNotEqual(first.claim_token, second.claim_token)
        with self.Session() as db:
            self.assertFalse(heartbeat_claimed_attempt(db, claim=first, now=later))
            self.assertTrue(heartbeat_claimed_attempt(db, claim=second, now=later))
            db.commit()

    @staticmethod
    def _png_bytes() -> bytes:
        from PIL import Image

        output = io.BytesIO()
        with Image.new("RGBA", (64, 64), (14, 116, 144, 255)) as image:
            image.save(output, format="PNG")
        return output.getvalue()

    def test_execution_uses_immutable_claim_and_only_sends_supported_upstream_key(self):
        from services.canvas.generation.worker import (
            claim_next_attempt,
            execute_claimed_attempt,
            prepare_claimed_attempt_for_execution,
        )
        from services.canvas.provider_schemas import (
            ControlledImageBytes,
            ProviderRuntime,
            ProviderSubmission,
        )
        from services.canvas.providers.registry import ProviderRegistry

        class FakeAdapter:
            adapter_type = "fake"

            def __init__(self) -> None:
                self.request = None

            def runtime_factory(self):
                return ProviderRuntime(api_key="", transport=object())

            def validate_request(self, request, capabilities):
                self.request = request

            async def submit(self, request, runtime):
                await asyncio.sleep(0)
                return ProviderSubmission(
                    status="completed",
                    request_id="fake-request",
                    image=ControlledImageBytes(self_png),
                )

            async def poll(self, submission, runtime):  # pragma: no cover - sync case
                raise AssertionError("sync fake must not poll")

            async def cancel(self, submission, runtime):  # pragma: no cover - protocol only
                raise AssertionError("sync fake must not cancel")

            async def recover_by_idempotency_key(self, upstream_key, runtime):  # pragma: no cover
                raise AssertionError("fake does not support recovery lookup")

        self_png = self._png_bytes()
        adapter = FakeAdapter()
        registry = ProviderRegistry()
        registry.register(adapter)
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            claim = claim_next_attempt(db, worker_id="worker", now=now)
            db.commit()
        with self.Session() as db:
            self.assertTrue(prepare_claimed_attempt_for_execution(db, claim=claim, now=now))
            db.commit()

        result = asyncio.run(execute_claimed_attempt(claim, registry=registry))

        self.assertEqual("completed", result.kind)
        self.assertIsNotNone(result.image)
        self.assertEqual("fake-request", result.provider_request_id)
        # The saved key exists, but this profile says it has no upstream
        # idempotency support, so the adapter never receives it.
        self.assertIsNone(adapter.request.upstream_idempotency_key)

    def test_verified_result_promotes_without_reading_the_live_output_board(self):
        from canvas_models import CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas import storage
        from services.canvas.composition import composition_layout_hash
        from services.canvas.composition_schema import CompositionLayout, DEFAULT_COMPOSITION_LAYOUT
        from services.canvas.generation.results import (
            materialize_provider_result,
            promote_materialized_provider_result,
            remove_verified_temporary_result,
        )
        from services.canvas.generation.worker import (
            claim_next_attempt,
            prepare_claimed_attempt_for_execution,
        )
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
        data_root = Path(self.tmp.name) / "canvas-data"
        now = datetime.now(UTC).replace(tzinfo=None)
        with patch.object(storage, "CANVAS_DATA_DIR", str(data_root)):
            with self.Session() as db:
                claim = claim_next_attempt(db, worker_id="worker", now=now)
                db.commit()
            with self.Session() as db:
                self.assertTrue(prepare_claimed_attempt_for_execution(db, claim=claim, now=now))
                db.commit()
            materialized = asyncio.run(
                materialize_provider_result(
                    project_id=claim.project_id,
                    attempt_id=claim.attempt_id,
                    image=ControlledImageBytes(self._png_bytes()),
                )
            )
            self.assertEqual("png", materialized.source_format)
            with self.Session() as db:
                operation = promote_materialized_provider_result(
                    db,
                    attempt_id=claim.attempt_id,
                    claim_token=claim.claim_token,
                    provider_request_id="fake-request",
                    external_task_id=None,
                    now=now,
                )
                db.commit()
            remove_verified_temporary_result(
                project_id=claim.project_id,
                attempt_id=claim.attempt_id,
            )
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, self.ids["attempt"])
            item = db.get(CanvasGenerationItem, self.ids["item"])
            self.assertEqual("succeeded", attempt.status)
            self.assertEqual("composing", attempt.provider_result_stage)
            self.assertEqual("composing", item.status)
            self.assertEqual(operation.id, attempt.compose_operation_id)
            self.assertIsNotNone(attempt.background_asset_id)
            self.assertIsNotNone(attempt.background_preview_asset_id)


if __name__ == "__main__":
    unittest.main()
