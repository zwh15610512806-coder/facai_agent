import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import AIUsageRecord, AuditEvent, DurableTask, ProductRagQueryLog
from services.retention import apply_data_retention


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_expired_sensitive_records_are_deleted_but_recent_records_remain(self):
        now = datetime(2026, 7, 13, 12, 0, 0)
        old = now - timedelta(days=200)
        recent = now - timedelta(days=1)
        for created_at in (old, recent):
            self.session.add(
                AIUsageRecord(
                    interface_key="chat",
                    provider="test",
                    model="test",
                    status="ok",
                    created_at=created_at,
                )
            )
            self.session.add(
                AuditEvent(
                    actor_name="admin",
                    actor_role="admin",
                    auth_source="bearer",
                    method="POST",
                    path="/api/test",
                    status_code=200,
                    request_id=f"req-{created_at.timestamp()}",
                    created_at=created_at,
                )
            )
            self.session.add(
                ProductRagQueryLog(
                    query="sensitive question",
                    answer="business answer",
                    scope="all",
                    retrieval_mode="test",
                    created_at=created_at,
                )
            )
        self.session.add(
            DurableTask(
                task_type="test",
                payload={},
                status="succeeded",
                completed_at=old,
            )
        )
        self.session.commit()

        with patch.dict(
            os.environ,
            {
                "FACAI_AI_USAGE_RETENTION_DAYS": "90",
                "FACAI_RAG_LOG_RETENTION_DAYS": "30",
                "FACAI_AUDIT_RETENTION_DAYS": "180",
                "FACAI_TASK_RETENTION_DAYS": "30",
            },
        ):
            result = apply_data_retention(self.session, now=now)

        self.assertEqual(result.ai_usage, 1)
        self.assertEqual(result.rag_queries, 1)
        self.assertEqual(result.audit_events, 1)
        self.assertEqual(result.completed_tasks, 1)
        self.assertEqual(self.session.query(AIUsageRecord).count(), 1)
        self.assertEqual(self.session.query(ProductRagQueryLog).count(), 1)
        self.assertEqual(self.session.query(AuditEvent).count(), 1)


if __name__ == "__main__":
    unittest.main()
