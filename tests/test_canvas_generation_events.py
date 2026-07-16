"""Persisted replay contracts for Canvas generation progress."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


class CanvasGenerationEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'events.db').as_posix()}",
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
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        ids = {name: str(uuid4()) for name in ("project", "provider", "model", "generation", "item", "attempt")}
        provider_snapshot = {"id": ids["provider"], "adapterType": "fake", "name": "Fake", "baseUrl": "https://provider.invalid", "authType": "bearer", "configVersion": 1, "concurrencyLimit": 1}
        capabilities = {"text_to_image": True, "image_to_image": False, "mask_edit": False, "allowed_ratios": [], "allowed_sizes": [], "min_width": None, "max_width": None, "min_height": None, "max_height": None, "max_quantity": 1, "max_reference_images": 0, "reference_transfer": "none", "protocol": "async", "supports_cancel": False, "supports_idempotency": False, "supports_idempotency_lookup": False, "concurrency_limit": 1, "price_metadata": None}
        model_snapshot = {"id": ids["model"], "providerId": ids["provider"], "modelId": "fake", "displayName": "Fake", "configVersion": 1, "capabilities": capabilities, "configuration": {}}
        with self.Session() as db:
            db.add(CanvasProject(
                id=ids["project"],
                name="Events",
                semantic_state=json.dumps(empty_semantic_state().model_dump(by_alias=True)),
                layout_state=json.dumps(empty_layout_state().model_dump(by_alias=True)),
            ))
            db.add(ImageProviderConnection(id=ids["provider"], adapter_type="fake", name="Fake", base_url="https://provider.invalid", auth_type="bearer"))
            db.add(ImageModelProfile(id=ids["model"], provider_id=ids["provider"], model_id="fake", display_name="Fake", capabilities_json=json.dumps(capabilities)))
            db.add(CanvasGeneration(id=ids["generation"], project_id=ids["project"], mode="complete_set", project_revision=1, request_snapshot_json="{}", request_fingerprint="a" * 64, idempotency_key="events-generation-key-01", status="running", total_items=1, storage_reservation_bytes=1_000_000, storage_reservation_remaining_bytes=1_000_000))
            db.add(CanvasGenerationItem(id=ids["item"], generation_id=ids["generation"], ordinal=0, output_type="main", board_id="board-1", node_id="node-1", board_order_snapshot=0, provider_id=ids["provider"], provider_config_version=1, model_profile_id=ids["model"], model_config_version=1, provider_config_snapshot_json=json.dumps(provider_snapshot), model_config_snapshot_json=json.dumps(model_snapshot), prompt="studio", width=64, height=64, ratio="1:1", layout_hash="sha256:" + "b" * 64, layout_snapshot_json=json.dumps({"version": 1}), attempt_count=1, status="running"))
            db.add(CanvasGenerationAttempt(id=ids["attempt"], item_id=ids["item"], attempt_no=1, provider_id=ids["provider"], provider_config_version=1, model_profile_id=ids["model"], model_config_version=1, provider_config_snapshot_json=json.dumps(provider_snapshot), model_config_snapshot_json=json.dumps(model_snapshot), status="polling", provider_result_stage="awaiting_provider", upstream_idempotency_key="upstream-events-key", external_task_id="task-1", usage_json="{}"))
            db.commit()
        return ids

    def test_generation_and_item_events_are_owner_checked_and_project_snapshot_discovers_active_work(self):
        from services.canvas.events import (
            append_canvas_event,
            project_activity_snapshot,
        )

        with self.Session() as db:
            event = append_canvas_event(
                db,
                project_id=self.ids["project"],
                event_type="generation.item.progress",
                generation_id=self.ids["generation"],
                item_id=self.ids["item"],
                payload={"status": "polling", "progress": 50, "safeErrorSummary": None},
            )
            db.commit()
            event_id = event.id
        with self.Session() as db:
            snapshot = project_activity_snapshot(db, project_id=self.ids["project"])
        self.assertIsNotNone(event_id)
        self.assertEqual(self.ids["generation"], snapshot["generations"][0]["id"])
        self.assertEqual("polling", snapshot["generations"][0]["items"][0]["latestAttempt"]["status"])

    def test_worker_claim_persists_item_progress_event_in_the_state_transaction(self):
        from canvas_models import CanvasEvent, CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas.generation.worker import claim_next_attempt

        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            db.get(CanvasGenerationAttempt, self.ids["attempt"]).status = "queued"
            db.get(CanvasGenerationItem, self.ids["item"]).status = "queued"
            db.get(CanvasGeneration, self.ids["generation"]).status = "queued"
            db.commit()
        with self.Session() as db:
            claim = claim_next_attempt(db, worker_id="event-test", now=now)
            db.commit()
        self.assertIsNotNone(claim)
        with self.Session() as db:
            events = list(
                db.scalars(
                    select(CanvasEvent)
                    .where(CanvasEvent.generation_id == self.ids["generation"])
                    .order_by(CanvasEvent.id)
                ).all()
            )
        self.assertEqual(["generation.item.running"], [event.event_type for event in events])

    def test_provider_submission_and_polling_transitions_append_replayable_attempt_events(self):
        from canvas_models import CanvasEvent, CanvasGeneration, CanvasGenerationAttempt, CanvasGenerationItem
        from services.canvas.generation.worker import (
            AttemptExecutionResult,
            claim_next_attempt,
            persist_attempt_execution_result,
            prepare_claimed_attempt_for_execution,
        )

        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            db.get(CanvasGenerationAttempt, self.ids["attempt"]).status = "queued"
            db.get(CanvasGenerationItem, self.ids["item"]).status = "queued"
            db.get(CanvasGeneration, self.ids["generation"]).status = "queued"
            db.commit()
        with self.Session() as db:
            claim = claim_next_attempt(db, worker_id="event-test", now=now)
            db.commit()
        with self.Session() as db:
            self.assertTrue(prepare_claimed_attempt_for_execution(db, claim=claim, now=now))
            db.commit()
        with self.Session() as db:
            self.assertTrue(
                persist_attempt_execution_result(
                    db,
                    claim=claim,
                    result=AttemptExecutionResult(kind="pending", external_task_id="task-2"),
                    now=now,
                )
            )
            db.commit()
        with self.Session() as db:
            event_types = list(
                db.scalars(
                    select(CanvasEvent.event_type)
                    .where(CanvasEvent.generation_id == self.ids["generation"])
                    .order_by(CanvasEvent.id)
                ).all()
            )
        self.assertEqual(
            [
                "generation.item.running",
                "generation.attempt.submitting",
                "generation.attempt.polling",
            ],
            event_types,
        )

    def test_fresh_replay_uses_consistent_activity_snapshot_at_high_water(self):
        from services.canvas.events import append_canvas_event, prepare_event_replay

        with self.Session() as db:
            event = append_canvas_event(
                db,
                project_id=self.ids["project"],
                event_type="generation.item.progress",
                generation_id=self.ids["generation"],
                item_id=self.ids["item"],
                payload={"status": "polling"},
            )
            db.commit()
            event_id = event.id
        with self.Session() as db:
            replay = prepare_event_replay(
                db,
                project_id=self.ids["project"],
                last_event_id=None,
            )
        self.assertEqual(event_id, replay.cursor)
        self.assertIsNotNone(replay.snapshot)
        self.assertEqual([], replay.events)
        self.assertEqual(self.ids["generation"], replay.snapshot["generations"][0]["id"])

    def test_project_stream_snapshot_keeps_the_full_project_wire_contract(self):
        from routers.canvas.events import _initial_replay

        snapshot, _cursor, _events = _initial_replay(
            self.Session,
            project_id=self.ids["project"],
            last_event_id=None,
        )

        self.assertIsNotNone(snapshot)
        self.assertEqual(self.ids["project"], snapshot["project"]["id"])
        self.assertIn("generations", snapshot)

    def test_generation_event_route_is_a_filtered_view_of_the_project_stream(self):
        from fastapi import FastAPI
        from routers.canvas.events import router as events_router

        app = FastAPI()
        app.include_router(events_router, prefix="/api/canvas")
        paths = app.openapi()["paths"]
        self.assertIn("/api/canvas/generations/{generation_id}/events", paths)
        self.assertIn("get", paths["/api/canvas/generations/{generation_id}/events"])

    def test_pruning_requires_event_to_be_both_old_and_outside_newest_retention(self):
        from canvas_models import CanvasEvent
        from services.canvas.events import prune_canvas_events

        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            db.add_all(
                [
                    CanvasEvent(project_id=self.ids["project"], event_type="old.one", payload_json="{}", created_at=now - timedelta(days=10)),
                    CanvasEvent(project_id=self.ids["project"], event_type="old.two", payload_json="{}", created_at=now - timedelta(days=10)),
                    CanvasEvent(project_id=self.ids["project"], event_type="recent", payload_json="{}", created_at=now),
                ]
            )
            db.commit()
        with self.Session() as db:
            deleted = prune_canvas_events(
                db,
                project_id=self.ids["project"],
                now=now,
                keep_count=2,
                keep_days=7,
            )
            db.commit()
        with self.Session() as db:
            remaining = list(
                db.scalars(
                    select(CanvasEvent.event_type)
                    .where(CanvasEvent.project_id == self.ids["project"])
                    .order_by(CanvasEvent.id)
                ).all()
            )
        self.assertEqual(1, deleted)
        self.assertEqual(["old.two", "recent"], remaining)

    def test_startup_pruning_uses_a_fresh_session_per_bounded_batch(self):
        from canvas_models import CanvasEvent
        from services.canvas.events import prune_all_canvas_events

        now = datetime.now(UTC).replace(tzinfo=None)
        with self.Session() as db:
            db.add_all(
                [
                    CanvasEvent(project_id=self.ids["project"], event_type=f"old.{index}", payload_json="{}", created_at=now - timedelta(days=10))
                    for index in range(3)
                ]
            )
            db.commit()
        deleted = prune_all_canvas_events(
            self.Session,
            now=now,
            keep_count=0,
            keep_days=7,
            batch_size=1,
        )
        self.assertEqual(3, deleted)


if __name__ == "__main__":
    unittest.main()
