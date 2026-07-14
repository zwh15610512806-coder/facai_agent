import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import AIUsageRecord, AuditEvent
from services.access_control import SlidingWindowLimiter, ai_budget_remaining, record_audit_event
from services.ai_config import record_usage
from services.request_context import request_actor
from services.security import Principal


class AccessControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        AIUsageRecord.__table__.create(self.engine)
        AuditEvent.__table__.create(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_audit_event_records_actor_and_route_without_request_body(self):
        record_audit_event(
            self.session_factory,
            principal=Principal("operator", "operator", "bearer"),
            method="POST",
            path="/api/import/excel",
            status_code=422,
            client_ip="192.168.1.20",
            request_id="req-123",
        )

        with self.session_factory() as session:
            event = session.query(AuditEvent).one()
            self.assertEqual(event.actor_name, "operator")
            self.assertEqual(event.actor_role, "operator")
            self.assertEqual(event.path, "/api/import/excel")
            self.assertEqual(event.status_code, 422)
            self.assertFalse(hasattr(event, "request_body"))

    def test_sliding_window_limiter_returns_retry_after(self):
        now = [100.0]
        limiter = SlidingWindowLimiter(clock=lambda: now[0])

        self.assertIsNone(limiter.check("operator:ai", limit=2, window_seconds=60))
        self.assertIsNone(limiter.check("operator:ai", limit=2, window_seconds=60))
        self.assertEqual(limiter.check("operator:ai", limit=2, window_seconds=60), 60)
        now[0] = 161.0
        self.assertIsNone(limiter.check("operator:ai", limit=2, window_seconds=60))

    def test_ai_usage_is_attributed_to_current_request_actor(self):
        with self.session_factory() as session, request_actor("operator"):
            record_usage(
                interface_key="inspiration_chat",
                provider="deepseek",
                model="deepseek-chat",
                total_tokens=123,
                status="success",
                db=session,
            )

        with self.session_factory() as session:
            record = session.query(AIUsageRecord).one()
            self.assertEqual(record.actor_name, "operator")

    def test_daily_ai_budget_is_calculated_per_actor(self):
        with self.session_factory() as session:
            session.add_all([
                AIUsageRecord(
                    interface_key="inspiration_chat",
                    provider="deepseek",
                    model="deepseek-chat",
                    total_tokens=700,
                    actor_name="operator",
                    status="success",
                ),
                AIUsageRecord(
                    interface_key="inspiration_chat",
                    provider="deepseek",
                    model="deepseek-chat",
                    total_tokens=900,
                    actor_name="admin",
                    status="success",
                ),
            ])
            session.commit()
            remaining = ai_budget_remaining(
                session,
                actor_name="operator",
                daily_limit=1000,
                now=datetime.now(),
            )

        self.assertEqual(remaining, 300)


if __name__ == "__main__":
    unittest.main()
