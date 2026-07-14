import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import DurableTask
from services.task_queue import DurableTaskQueue


class DurableTaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        DurableTask.__table__.create(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.queue = DurableTaskQueue(self.session_factory)

    def tearDown(self):
        self.engine.dispose()

    def test_enqueued_task_is_claimed_and_completed(self):
        received = []
        self.queue.register("search_rebuild", lambda payload: received.append(payload["job_id"]))
        task_id = self.queue.enqueue("search_rebuild", {"job_id": 42})

        self.assertTrue(self.queue.process_once())

        with self.session_factory() as session:
            task = session.get(DurableTask, task_id)
            self.assertEqual(task.status, "succeeded")
            self.assertEqual(task.attempt_count, 1)
        self.assertEqual(received, [42])

    def test_expired_running_lease_is_recovered_after_restart(self):
        with self.session_factory() as session:
            task = DurableTask(
                task_type="workbook_import",
                payload={"path": "staged.xlsx"},
                status="running",
                attempt_count=1,
                max_attempts=3,
                next_attempt_at=datetime.utcnow(),
                lease_until=datetime.utcnow() - timedelta(minutes=1),
            )
            session.add(task)
            session.commit()
            task_id = task.id

        self.assertEqual(self.queue.recover_expired(), 1)
        with self.session_factory() as session:
            task = session.get(DurableTask, task_id)
            self.assertEqual(task.status, "pending")
            self.assertIsNone(task.lease_until)

    def test_failure_is_retried_with_bounded_attempts(self):
        self.queue.register("failing", lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")))
        task_id = self.queue.enqueue("failing", {}, max_attempts=2)

        self.assertTrue(self.queue.process_once())
        with self.session_factory() as session:
            task = session.get(DurableTask, task_id)
            self.assertEqual(task.status, "pending")
            self.assertEqual(task.attempt_count, 1)
            self.assertIn("boom", task.last_error)


if __name__ == "__main__":
    unittest.main()
