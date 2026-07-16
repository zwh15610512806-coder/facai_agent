import io
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


def _png_bytes(size=(8, 6)):
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = ((x * 31) % 256, (y * 47) % 256, ((x + y) * 23) % 256)
    output = io.BytesIO()
    image.save(output, format="PNG")
    image.close()
    return output.getvalue()


class _PatternMasker:
    def __init__(self):
        self.calls = 0

    def create_mask(self, image):
        self.calls += 1
        mask = Image.new("L", image.size)
        pixels = mask.load()
        for y in range(image.height):
            for x in range(image.width):
                pixels[x, y] = 0 if x == 0 else min(255, 40 + x * 25 + y)
        return mask


class CanvasCutoutOperationTests(unittest.TestCase):
    def setUp(self):
        import canvas_models  # noqa: F401
        from database import Base
        from services.canvas import storage

        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-data"
        self.db_path = Path(self.tmp.name) / "canvas-worker.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
            dbapi_connection.execute("PRAGMA busy_timeout=5000")
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.storage_patch = patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root))
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def _claimed_cutout(self):
        from canvas_models import CanvasProject
        from services.canvas import assets, operations
        from services.canvas.project_state import empty_project_state_json

        semantic_state, layout_state = empty_project_state_json()
        with self.Session() as db:
            project = CanvasProject(
                id=str(uuid4()),
                name="Worker cutout",
                semantic_state=semantic_state,
                layout_state=layout_state,
            )
            db.add(project)
            db.commit()
            uploaded = assets.persist_uploaded_source(
                db,
                project_id=project.id,
                filename="product.png",
                declared_mime="image/png",
                data=_png_bytes(),
            )
            uploaded.working.transparency_status = "opaque"
            operation = operations.enqueue_automatic_cutout(
                db,
                project_id=project.id,
                input_asset_id=uploaded.working.id,
            )
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="rembg-test-worker",
                lane="rembg",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()
            return project.id, uploaded.source.id, uploaded.working.id, operation.id, claimed

    def test_success_persists_full_cutout_and_distinct_preview_with_source_rgb(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import assets, previews
        from services.canvas.rembg_cpu import run_cutout_operation

        project_id, source_id, working_id, operation_id, claimed = self._claimed_cutout()
        masker = _PatternMasker()

        result = run_cutout_operation(
            operation_id,
            masker=masker,
            db_factory=self.Session,
            worker_id=claimed.worker_id,
            attempt_count=claimed.attempt_count,
        )

        self.assertEqual(1, masker.calls)
        with self.Session() as db:
            operation = db.get(CanvasAssetOperation, operation_id)
            working = db.get(CanvasAsset, working_id)
            cutout = db.get(CanvasAsset, result.id)
            self.assertEqual("succeeded", operation.status)
            self.assertEqual(cutout.id, operation.output_asset_id)
            self.assertEqual("cutout", cutout.asset_type)
            self.assertEqual(working.id, cutout.source_asset_id)
            self.assertEqual("transparent", cutout.transparency_status)
            preview = previews.resolve_preview_asset(db, asset=cutout)
            self.assertEqual("preview", preview.asset_type)
            self.assertEqual(cutout.id, preview.source_asset_id)
            self.assertNotEqual(cutout.id, preview.id)
            source_bytes = assets.read_verified_asset_bytes(db, asset=working)
            cutout_bytes = assets.read_verified_asset_bytes(db, asset=cutout)
            with Image.open(io.BytesIO(source_bytes)) as source_image, Image.open(
                io.BytesIO(cutout_bytes)
            ) as cutout_image:
                source_rgb = source_image.convert("RGB")
                output_rgba = cutout_image.convert("RGBA")
                expected_mask = _PatternMasker().create_mask(source_image)
                alpha_bytes = output_rgba.getchannel("A").tobytes()
                self.assertEqual(expected_mask.tobytes(), alpha_bytes)
                source_rgb_bytes = source_rgb.tobytes()
                output_rgba_bytes = output_rgba.tobytes()
                for index, alpha in enumerate(alpha_bytes):
                    if alpha > 0:
                        self.assertEqual(
                            source_rgb_bytes[index * 3 : index * 3 + 3],
                            output_rgba_bytes[index * 4 : index * 4 + 3],
                        )
            self.assertIsNotNone(db.get(CanvasAsset, source_id))
            self.assertIsNotNone(db.get(CanvasAsset, working_id))
            self.assertEqual(
                {"source", "working", "cutout", "preview"},
                set(db.scalars(select(CanvasAsset.asset_type)).all()),
            )

    def test_model_failure_is_safe_retryable_and_retry_creates_no_duplicate_success_assets(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import operations
        from services.canvas.rembg_cpu import CanvasRembgModelUnavailable, run_cutout_operation

        _project_id, _source_id, _working_id, operation_id, claimed = (
            CanvasCutoutOperationTests._claimed_cutout(self)
        )

        class FailingMasker:
            def create_mask(self, _image):
                raise CanvasRembgModelUnavailable()

        with self.assertRaises(CanvasRembgModelUnavailable):
            run_cutout_operation(
                operation_id,
                masker=FailingMasker(),
                db_factory=self.Session,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
            )

        with self.Session() as db:
            failed = db.get(CanvasAssetOperation, operation_id)
            self.assertEqual("failed", failed.status)
            self.assertEqual(
                {
                    "code": "rembg_model_unavailable",
                    "message": "Background removal model is unavailable",
                    "retryable": True,
                },
                json.loads(failed.safe_error_json),
            )
            self.assertEqual(0, len(db.scalars(select(CanvasAsset).where(
                CanvasAsset.asset_type.in_(("cutout", "preview"))
            )).all()))
            queued_retry = operations.retry_asset_operation(db, operation_id=operation_id)
            db.commit()
            retried = operations.claim_next_operation(
                db,
                worker_id="rembg-retry-worker",
                lane="rembg",
                now=queued_retry.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        result = run_cutout_operation(
            operation_id,
            masker=_PatternMasker(),
            db_factory=self.Session,
            worker_id=retried.worker_id,
            attempt_count=retried.attempt_count,
        )
        with self.Session() as db:
            self.assertEqual(
                1,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "cutout")).all()),
            )
            self.assertEqual(
                1,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "preview")).all()),
            )
            self.assertEqual(result.id, db.get(CanvasAssetOperation, operation_id).output_asset_id)

    def test_explicit_recutout_creates_a_new_pair_and_preserves_prior_history(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import operations
        from services.canvas.rembg_cpu import run_cutout_operation

        _project_id, _source_id, working_id, first_operation_id, first_claim = (
            self._claimed_cutout()
        )
        first_result = run_cutout_operation(
            first_operation_id,
            masker=_PatternMasker(),
            db_factory=self.Session,
            worker_id=first_claim.worker_id,
            attempt_count=first_claim.attempt_count,
        )
        with self.Session() as db:
            explicit = operations.retry_cutout_for_asset(
                db,
                input_asset_id=working_id,
                client_request_id="explicit-history-pair",
            )
            db.commit()
            explicit_claim = operations.claim_next_operation(
                db,
                worker_id="explicit-history-worker",
                lane="rembg",
                now=explicit.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        second_result = run_cutout_operation(
            explicit.id,
            masker=_PatternMasker(),
            db_factory=self.Session,
            worker_id=explicit_claim.worker_id,
            attempt_count=explicit_claim.attempt_count,
        )
        self.assertNotEqual(first_result.id, second_result.id)
        with self.Session() as db:
            first_operation = db.get(CanvasAssetOperation, first_operation_id)
            second_operation = db.get(CanvasAssetOperation, explicit.id)
            self.assertEqual(first_result.id, first_operation.output_asset_id)
            self.assertEqual(second_result.id, second_operation.output_asset_id)
            self.assertEqual(
                2,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "cutout")).all()),
            )
            self.assertEqual(
                2,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "preview")).all()),
            )


class CanvasOperationWorkerLoopTests(unittest.TestCase):
    setUp = CanvasCutoutOperationTests.setUp
    tearDown = CanvasCutoutOperationTests.tearDown

    def test_periodic_recovery_is_not_starved_by_a_continuous_backlog(self):
        from services.canvas.operation_worker import CanvasOperationWorker

        worker = CanvasOperationWorker(
            db_factory=lambda: None,
            lane="rembg",
            worker_id="continuous-backlog-worker",
            handlers={"cutout": lambda _claim: None},
        )
        claims = [object(), object(), object()]
        handled = []

        def execute(claimed):
            handled.append(claimed)
            if len(handled) == len(claims):
                worker.request_stop()

        with (
            patch.object(worker, "_recover") as recover_spy,
            patch.object(worker, "_claim", side_effect=claims) as claim_spy,
            patch.object(worker, "_execute_claim", side_effect=execute),
        ):
            worker._run()

        self.assertEqual(claims, handled)
        self.assertEqual(3, claim_spy.call_count)
        self.assertEqual(4, recover_spy.call_count)

    def test_stop_requested_during_recovery_prevents_a_new_claim(self):
        from services.canvas.operation_worker import CanvasOperationWorker

        worker = CanvasOperationWorker(
            db_factory=lambda: None,
            lane="rembg",
            worker_id="stop-during-recovery-worker",
            handlers={"cutout": lambda _claim: None},
        )
        recovery_started = threading.Event()
        release_recovery = threading.Event()
        recovery_calls = 0

        def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            if recovery_calls == 2:
                recovery_started.set()
                self.assertTrue(release_recovery.wait(5))

        with (
            patch.object(worker, "_recover", side_effect=recover),
            patch.object(worker, "_claim") as claim_spy,
        ):
            worker.start()
            self.assertTrue(recovery_started.wait(5))
            worker.request_stop()
            release_recovery.set()
            self.assertTrue(worker.join(timeout=5))

        claim_spy.assert_not_called()

    def test_stop_requested_during_claim_releases_it_without_execution(self):
        from services.canvas.operation_worker import CanvasOperationWorker

        worker = CanvasOperationWorker(
            db_factory=lambda: None,
            lane="rembg",
            worker_id="stop-during-claim-worker",
            handlers={"cutout": lambda _claim: None},
        )
        claim_started = threading.Event()
        release_claim = threading.Event()
        claimed = object()

        def claim():
            claim_started.set()
            self.assertTrue(release_claim.wait(5))
            return claimed

        with (
            patch.object(worker, "_recover"),
            patch.object(worker, "_claim", side_effect=claim),
            patch.object(worker, "_execute_claim") as execute_spy,
            patch.object(worker, "_release_unstarted_claim", create=True) as release_spy,
        ):
            worker.start()
            self.assertTrue(claim_started.wait(5))
            worker.request_stop()
            release_claim.set()
            self.assertTrue(worker.join(timeout=5))

        execute_spy.assert_not_called()
        release_spy.assert_called_once_with(claimed)

    def test_success_remains_success_when_session_refresh_would_fail_after_commit(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas.rembg_cpu import run_cutout_operation

        _project_id, _source_id, _working_id, operation_id, claimed = (
            CanvasCutoutOperationTests._claimed_cutout(self)
        )
        with patch("sqlalchemy.orm.Session.refresh", side_effect=RuntimeError("post-commit refresh")):
            result = run_cutout_operation(
                operation_id,
                masker=_PatternMasker(),
                db_factory=self.Session,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
            )

        with self.Session() as db:
            self.assertEqual("succeeded", db.get(CanvasAssetOperation, operation_id).status)
            self.assertEqual(result.id, db.get(CanvasAssetOperation, operation_id).output_asset_id)
            self.assertEqual(
                1,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "cutout")).all()),
            )
            self.assertEqual(
                1,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "preview")).all()),
            )

    def test_stop_finishes_current_stage_without_claiming_the_next_job(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation, CanvasProject
        from services.canvas import operations
        from services.canvas.operation_worker import CanvasOperationWorker
        from services.canvas.project_state import empty_project_state_json

        semantic_state, layout_state = empty_project_state_json()
        now = datetime(2026, 7, 14, 8, 0)
        with self.Session() as db:
            project = CanvasProject(
                id=str(uuid4()),
                name="Worker stop",
                semantic_state=semantic_state,
                layout_state=layout_state,
            )
            db.add(project)
            db.flush()
            working = CanvasAsset(
                id=str(uuid4()),
                project_id=project.id,
                asset_type="working",
                relative_path=f"working/{uuid4()}.png",
                original_filename="working.png",
                mime_type="image/png",
                byte_count=1,
                width=1,
                height=1,
                sha256="a" * 64,
                transparency_status="opaque",
            )
            # Keep the disk name canonical for storage-independent DB-only worker testing.
            working.relative_path = f"working/{working.id}.png"
            db.add(working)
            db.flush()
            first = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="cutout",
                input_asset_id=working.id,
                idempotency_key="worker-stop-first",
                request_snapshot={},
            )
            second = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="cutout",
                input_asset_id=working.id,
                idempotency_key="worker-stop-second",
                request_snapshot={},
            )
            first.next_attempt_at = now - timedelta(seconds=1)
            second.next_attempt_at = now
            db.commit()
            first_id, second_id = first.id, second.id

        started = threading.Event()
        release = threading.Event()
        handler_threads = []

        def handler(claimed):
            handler_threads.append(threading.current_thread().name)
            started.set()
            self.assertTrue(release.wait(5))
            with self.Session() as db:
                output = CanvasAsset(
                    id=str(uuid4()),
                    project_id=claimed.project_id,
                    asset_type="cutout",
                    relative_path="cutout/" + str(uuid4()) + ".png",
                    original_filename="cutout.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256="b" * 64,
                    source_asset_id=claimed.input_asset_id,
                    transparency_status="transparent",
                )
                output.relative_path = f"cutout/{output.id}.png"
                db.add(output)
                db.flush()
                completed = operations.mark_claimed_operation_succeeded(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    output_asset_id=output.id,
                    now=now,
                )
                self.assertIsNotNone(completed)
                db.commit()

        worker = CanvasOperationWorker(
            db_factory=self.Session,
            lane="rembg",
            worker_id="worker-stop-test",
            handlers={"cutout": handler},
            poll_interval_seconds=0.01,
            heartbeat_interval_seconds=0.05,
            clock=lambda: now,
        )
        worker.start()
        self.assertTrue(started.wait(5))
        worker.request_stop()
        release.set()
        self.assertTrue(worker.join(timeout=5))

        self.assertEqual(1, len(handler_threads))
        self.assertNotEqual(threading.current_thread().name, handler_threads[0])
        with self.Session() as db:
            self.assertEqual("succeeded", db.get(CanvasAssetOperation, first_id).status)
            self.assertEqual("queued", db.get(CanvasAssetOperation, second_id).status)

    def test_rembg_worker_never_claims_local_lane_operations(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation, CanvasProject
        from services.canvas import operations
        from services.canvas.operation_worker import CanvasOperationWorker
        from services.canvas.project_state import empty_project_state_json

        semantic_state, layout_state = empty_project_state_json()
        now = datetime(2026, 7, 14, 8, 30)
        with self.Session() as db:
            project = CanvasProject(
                id=str(uuid4()),
                name="Lane separation",
                semantic_state=semantic_state,
                layout_state=layout_state,
            )
            db.add(project)
            db.flush()
            working = CanvasAsset(
                id=str(uuid4()),
                project_id=project.id,
                asset_type="working",
                relative_path="working/pending.png",
                original_filename="working.png",
                mime_type="image/png",
                byte_count=1,
                width=1,
                height=1,
                sha256="c" * 64,
            )
            working.relative_path = f"working/{working.id}.png"
            db.add(working)
            db.flush()
            compose = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="compose",
                input_asset_id=working.id,
                idempotency_key="local-compose",
                request_snapshot={},
            )
            compose.next_attempt_at = now
            db.commit()
            compose_id = compose.id

        called = threading.Event()
        worker = CanvasOperationWorker(
            db_factory=self.Session,
            lane="rembg",
            worker_id="rembg-lane-test",
            handlers={"cutout": lambda _claim: called.set()},
            poll_interval_seconds=0.01,
            heartbeat_interval_seconds=0.05,
            clock=lambda: now,
        )
        worker.start()
        self.assertFalse(called.wait(0.15))
        worker.request_stop()
        self.assertTrue(worker.join(timeout=5))
        with self.Session() as db:
            self.assertEqual("queued", db.get(CanvasAssetOperation, compose_id).status)

    def test_stop_timeout_interrupts_claim_and_late_handler_cannot_publish(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation, CanvasProject
        from services.canvas import operations
        from services.canvas.operation_worker import CanvasOperationWorker
        from services.canvas.project_state import empty_project_state_json

        semantic_state, layout_state = empty_project_state_json()
        now = datetime(2026, 7, 14, 9, 0)
        with self.Session() as db:
            project = CanvasProject(
                id=str(uuid4()),
                name="Worker interruption",
                semantic_state=semantic_state,
                layout_state=layout_state,
            )
            db.add(project)
            db.flush()
            working = CanvasAsset(
                id=str(uuid4()),
                project_id=project.id,
                asset_type="working",
                relative_path="working/pending.png",
                original_filename="working.png",
                mime_type="image/png",
                byte_count=1,
                width=1,
                height=1,
                sha256="d" * 64,
            )
            working.relative_path = f"working/{working.id}.png"
            db.add(working)
            db.flush()
            operation = operations.enqueue_asset_operation(
                db,
                project_id=project.id,
                operation_type="cutout",
                input_asset_id=working.id,
                idempotency_key="interrupt-cutout",
                request_snapshot={},
            )
            operation.next_attempt_at = now
            db.commit()
            operation_id = operation.id

        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def late_handler(claimed):
            started.set()
            release.wait(5)
            with self.Session() as db:
                output = CanvasAsset(
                    id=str(uuid4()),
                    project_id=claimed.project_id,
                    asset_type="cutout",
                    relative_path="cutout/pending.png",
                    original_filename="cutout.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256="e" * 64,
                    source_asset_id=claimed.input_asset_id,
                    transparency_status="transparent",
                )
                output.relative_path = f"cutout/{output.id}.png"
                db.add(output)
                db.flush()
                completed = operations.mark_claimed_operation_succeeded(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    output_asset_id=output.id,
                    now=now,
                )
                if completed is None:
                    db.rollback()
                else:
                    db.commit()
            finished.set()

        worker = CanvasOperationWorker(
            db_factory=self.Session,
            lane="rembg",
            worker_id="interrupt-worker",
            handlers={"cutout": late_handler},
            poll_interval_seconds=0.01,
            heartbeat_interval_seconds=0.05,
            clock=lambda: now,
        )
        worker.start()
        self.assertTrue(started.wait(5))
        self.assertFalse(worker.stop(graceful_timeout_seconds=0))
        with self.Session() as db:
            self.assertEqual("interrupted", db.get(CanvasAssetOperation, operation_id).status)
        release.set()
        self.assertTrue(finished.wait(5))
        self.assertTrue(worker.join(timeout=5))
        with self.Session() as db:
            self.assertEqual(
                0,
                len(db.scalars(select(CanvasAsset).where(CanvasAsset.asset_type == "cutout")).all()),
            )


if __name__ == "__main__":
    unittest.main()
