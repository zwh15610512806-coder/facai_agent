import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database import Base, engine, get_db
from main import app
from models import Product


class SqliteConnectionSafetyTests(unittest.TestCase):
    def test_application_connections_enable_integrity_and_lock_pragmas(self):
        with engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
            journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()

        self.assertEqual(foreign_keys, 1)
        self.assertEqual(busy_timeout, 5000)
        self.assertEqual(str(journal_mode).lower(), "wal")

    def test_ai_config_page_exposes_vector_queue_status_and_retry(self):
        page = (Path(__file__).resolve().parents[1] / "templates" / "ai_config.html").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn('id="vectorSyncMetrics"', page)
        self.assertIn("/api/ai-config/vector-sync", page)
        self.assertIn("/api/ai-config/vector-sync/retry", page)
        self.assertIn('id="vectorSyncRecentError"', page)


class VectorSyncQueueTests(unittest.TestCase):
    def setUp(self):
        from services.vector_sync import VectorSyncJob

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "queue.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()
        self.VectorSyncJob = VectorSyncJob

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _add_product(self):
        product = Product(name="队列测试", category="烘焙调味", price=10)
        self.db.add(product)
        self.db.flush()
        return product

    def test_business_data_and_job_are_committed_together_then_failure_stays_pending(self):
        from services.vector_sync import enqueue_vector_sync, process_vector_sync_job

        product = self._add_product()
        job = enqueue_vector_sync(self.db, "product", product.id, "upsert")
        self.db.commit()

        with patch("services.vector_sync._execute_vector_operation", side_effect=RuntimeError("embedding down")):
            status = process_vector_sync_job(job.id, db=self.db)

        saved_product = self.db.query(Product).filter(Product.id == product.id).one()
        saved_job = self.db.query(self.VectorSyncJob).filter(self.VectorSyncJob.id == job.id).one()
        self.assertEqual(saved_product.name, "队列测试")
        self.assertEqual(status, "pending")
        self.assertEqual(saved_job.status, "pending")
        self.assertEqual(saved_job.attempt_count, 1)
        self.assertIn("embedding down", saved_job.last_error)
        self.assertIsNotNone(saved_job.next_attempt_at)

    def test_pending_job_succeeds_after_provider_recovers(self):
        from services.vector_sync import enqueue_vector_sync, process_vector_sync_job

        product = self._add_product()
        job = enqueue_vector_sync(self.db, "product", product.id, "upsert")
        self.db.commit()

        with patch("services.vector_sync._execute_vector_operation", side_effect=RuntimeError("temporary")):
            process_vector_sync_job(job.id, db=self.db)
        with patch("services.vector_sync._execute_vector_operation") as execute:
            status = process_vector_sync_job(job.id, db=self.db, force=True)

        self.assertEqual(status, "succeeded")
        execute.assert_called_once()
        saved_job = self.db.get(self.VectorSyncJob, job.id)
        self.assertEqual(saved_job.status, "succeeded")
        self.assertIsNotNone(saved_job.completed_at)

    def test_running_job_cannot_be_claimed_twice_even_with_force(self):
        from services.vector_sync import process_vector_sync_job

        product = self._add_product()
        job = self.VectorSyncJob(
            entity_type="product",
            entity_id=product.id,
            operation="upsert",
            status="running",
            attempt_count=1,
            next_attempt_at=datetime.utcnow(),
        )
        self.db.add(job)
        self.db.commit()

        with patch("services.vector_sync._execute_vector_operation") as execute:
            status = process_vector_sync_job(job.id, db=self.db, force=True)

        self.assertEqual(status, "running")
        execute.assert_not_called()

    def test_recovery_only_requeues_running_jobs_with_expired_lease(self):
        from datetime import timedelta
        from services.vector_sync import _recover_expired_running_jobs

        now = datetime.utcnow()
        product = self._add_product()
        fresh = self.VectorSyncJob(
            entity_type="product",
            entity_id=product.id,
            operation="upsert",
            status="running",
            next_attempt_at=now + timedelta(minutes=5),
        )
        expired = self.VectorSyncJob(
            entity_type="product",
            entity_id=product.id + 1,
            operation="upsert",
            status="running",
            next_attempt_at=now - timedelta(seconds=1),
        )
        self.db.add_all([fresh, expired])
        self.db.commit()

        recovered = _recover_expired_running_jobs(self.db, now=now)
        self.db.refresh(fresh)
        self.db.refresh(expired)

        self.assertEqual(recovered, 1)
        self.assertEqual(fresh.status, "running")
        self.assertEqual(expired.status, "pending")

    def test_new_delete_supersedes_an_unprocessed_upsert(self):
        from services.vector_sync import enqueue_vector_sync

        product = self._add_product()
        first = enqueue_vector_sync(self.db, "product", product.id, "upsert")
        second = enqueue_vector_sync(self.db, "product", product.id, "delete")
        self.db.commit()

        self.assertEqual(first.id, second.id)
        saved_job = self.db.get(self.VectorSyncJob, first.id)
        self.assertEqual(saved_job.operation, "delete")
        self.assertEqual(saved_job.status, "pending")
        self.assertLessEqual(saved_job.next_attempt_at, datetime.utcnow())

    def test_vector_sync_status_and_retry_endpoints_expose_queue_state(self):
        from services.vector_sync import enqueue_vector_sync

        product = self._add_product()
        job = enqueue_vector_sync(self.db, "product", product.id, "upsert")
        job.status = "failed"
        job.last_error = "endpoint unavailable"
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            status_response = client.get("/api/ai-config/vector-sync")
            retry_response = client.post("/api/ai-config/vector-sync/retry")

        self.assertEqual(status_response.status_code, 200)
        status = status_response.json()
        self.assertEqual(status["failed"], 1)
        self.assertEqual(status["recent_error"]["message"], "endpoint unavailable")
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(retry_response.json()["queued"], 1)
        self.db.refresh(job)
        self.assertEqual(job.status, "pending")

    def test_product_write_returns_pending_status_and_registers_job(self):
        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        with patch("routers.products._sync_product_index", return_value="pending"):
            with TestClient(app) as client:
                response = client.post(
                    "/api/products/",
                    json={"name": "写入测试", "category": "烘焙调味", "price": 12.5},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["index_sync_status"], "pending")
        product = self.db.query(Product).filter(Product.name == "写入测试").one()
        job = self.db.query(self.VectorSyncJob).filter(
            self.VectorSyncJob.entity_type == "product",
            self.VectorSyncJob.entity_id == product.id,
        ).one()
        self.assertEqual(job.status, "pending")

    def test_reconciliation_enqueues_product_when_chunk_hashes_are_stale(self):
        from services.vector_sync import reconcile_product_vector_index

        product = self._add_product()
        self.db.commit()

        class FakeCollection:
            def get(self, include):
                return {
                    "ids": [f"product_{product.id}:product_info"],
                    "metadatas": [
                        {
                            "product_id": product.id,
                            "content_hash": "stale-hash",
                        }
                    ],
                }

        fake_store = type("FakeProductStore", (), {"collection": FakeCollection()})()

        result = reconcile_product_vector_index(self.db, product_store=fake_store)

        self.assertEqual(result["stale"], 1)
        job = self.db.query(self.VectorSyncJob).one()
        self.assertEqual(job.entity_id, product.id)
        self.assertEqual(job.operation, "upsert")
        self.assertEqual(job.status, "pending")

    def test_reconciliation_requires_reindex_for_legacy_collection_without_hashes(self):
        from services.vector_sync import reconcile_product_vector_index

        product = self._add_product()
        self.db.commit()

        class FakeCollection:
            def get(self, include):
                return {
                    "ids": [f"product_{product.id}:legacy"],
                    "metadatas": [{"product_id": product.id}],
                }

        fake_store = type("FakeProductStore", (), {"collection": FakeCollection()})()

        result = reconcile_product_vector_index(self.db, product_store=fake_store)

        self.assertTrue(result["requires_reindex"])
        self.assertEqual(result["queued"], 0)
        self.assertEqual(self.db.query(self.VectorSyncJob).count(), 0)


if __name__ == "__main__":
    unittest.main()
