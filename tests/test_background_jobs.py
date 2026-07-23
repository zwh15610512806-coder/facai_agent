import unittest
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from integration_models import IntegrationJob
from integrations.types import JobStatus, JobType
from models import JobRun
from routers import inspiration, jobs
from services.background_jobs import create_background_job, sync_integration_sync_jobs
from services.task_queue import DurableTaskQueue


class BackgroundJobApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        app = FastAPI()
        app.include_router(jobs.router, prefix="/api/jobs")
        app.include_router(inspiration.router, prefix="/api/inspiration")

        def override_db():
            with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.client_id = str(uuid.uuid4())
        self.headers = {"X-Facai-Client-Id": self.client_id}

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def test_ai_submission_returns_browser_owned_pending_job(self):
        response = self.client.post(
            "/api/inspiration/chat/jobs",
            headers={**self.headers, "X-Facai-Source-Ref": "conv-1", "Idempotency-Key": "once"},
            json={"message": "后台运行测试"},
        )
        self.assertEqual(response.status_code, 202, response.text)
        job = response.json()["job"]
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["queue_group"], "ai")
        self.assertEqual(job["source_ref"], "conv-1")

        listing = self.client.get("/api/jobs", headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["public_id"], job["public_id"])

        hidden = self.client.get(
            f"/api/jobs/{job['public_id']}",
            headers={"X-Facai-Client-Id": str(uuid.uuid4())},
        )
        self.assertEqual(hidden.status_code, 404)

    def test_idempotency_cancel_and_retry_keep_one_public_job(self):
        request_headers = {**self.headers, "Idempotency-Key": "same-request"}
        first = self.client.post("/api/inspiration/chat/jobs", headers=request_headers, json={"message": "一次"})
        second = self.client.post("/api/inspiration/chat/jobs", headers=request_headers, json={"message": "一次"})
        self.assertEqual(first.json()["job"]["public_id"], second.json()["job"]["public_id"])
        self.assertFalse(second.json()["created"])

        public_id = first.json()["job"]["public_id"]
        cancelled = self.client.post(f"/api/jobs/{public_id}/cancel", headers=self.headers)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        retried = self.client.post(f"/api/jobs/{public_id}/retry", headers=self.headers)
        self.assertEqual(retried.json()["status"], "pending")


class BackgroundJobWorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_ai_worker_persists_result_and_attempt(self):
        with self.session_factory() as session:
            job, _created = create_background_job(
                session,
                owner_key="owner",
                job_type="test.ai",
                request_payload={"value": 7},
                origin_path="/app",
                queue_group="ai",
                max_attempts=2,
            )
            job_id = job.id
        queue = DurableTaskQueue(self.session_factory, lease_seconds=30)
        queue.register("test.ai", lambda payload: {"answer": payload["request"]["value"] * 2}, queue_group="ai")

        self.assertTrue(queue.process_once(queue_group="ai"))
        with self.session_factory() as session:
            saved = session.get(JobRun, job_id)
            self.assertEqual(saved.status, "succeeded")
            self.assertEqual(saved.attempt_count, 1)
            self.assertEqual(saved.result_payload, {"answer": 14})

    def test_existing_integration_sync_queue_is_mirrored_without_reexecution(self):
        request_id = str(uuid.uuid4())
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.session_factory() as session:
            parent = JobRun(
                public_id=str(uuid.uuid4()),
                owner_key="owner",
                job_type="integration.adapter.sync",
                queue_group="maintenance",
                origin_path="/app/api-connections",
                source_ref=f"integration-sync:{request_id}",
                status="pending",
                message="waiting",
                request_payload={},
                partial_result={},
                result_payload={},
                details={},
                version=1,
                attempt_count=0,
                max_attempts=6,
                created_at=now,
            )
            child = IntegrationJob(
                job_type=JobType.SYNC_RESOURCE,
                dedupe_key="a" * 64,
                payload={"manual_request_id": request_id},
                priority=0,
                status=JobStatus.SUCCEEDED,
                attempts=1,
                max_attempts=6,
                available_at=now,
                created_at=now,
                updated_at=now,
                completed_at=now,
            )
            session.add_all([parent, child])
            session.commit()

            self.assertEqual(sync_integration_sync_jobs(session, owner_key="owner"), 1)
            session.refresh(parent)
            self.assertEqual(parent.status, "succeeded")
            self.assertEqual(parent.progress_current, 1)
            self.assertEqual(parent.progress_total, 1)
            self.assertEqual(parent.result_payload["succeeded"], 1)


if __name__ == "__main__":
    unittest.main()
