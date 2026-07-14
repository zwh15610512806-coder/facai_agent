import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from integrations.audit import write_security_audit
from integrations.redaction import PayloadSafetyError
from integration_models import IntegrationSecurityAudit
from integrations.types import Provider


class IntegrationSecurityAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[IntegrationSecurityAudit.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_event_specific_allowlist_persists_only_sanitized_details(self):
        audit = write_security_audit(
            self.db,
            event_type="login_failed",
            outcome="failure",
            source_digest="a" * 64,
            summary_code="password_mismatch",
            details={"attempt_count": 3},
            created_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )
        self.db.commit()

        self.assertIsInstance(audit, IntegrationSecurityAudit)
        self.assertEqual(audit.details, {"attempt_count": 3})
        self.assertEqual(audit.source_digest, "a" * 64)

    def test_sensitive_or_non_allowlisted_detail_keys_are_rejected_before_insert(self):
        forbidden_keys = (
            "request_body",
            "exception",
            "headers",
            "ip",
            "password",
            "authorization_code",
            "raw_state",
            "cookie",
            "session_id",
        )
        for key in forbidden_keys:
            with self.subTest(key=key), self.assertRaises((ValueError, PayloadSafetyError)):
                write_security_audit(
                    self.db,
                    event_type="login_failed",
                    outcome="failure",
                    source_digest="b" * 64,
                    summary_code="password_mismatch",
                    details={key: "sensitive-sentinel"},
                )
        self.assertEqual(len(self.db.new), 0)

    def test_detail_values_and_summary_codes_are_constrained_per_event(self):
        invalid_calls = (
            {"event_type": "unknown", "summary_code": "password_mismatch", "details": {}},
            {"event_type": "login_failed", "summary_code": "arbitrary", "details": {}},
            {
                "event_type": "login_failed",
                "summary_code": "password_mismatch",
                "details": {"attempt_count": "3"},
            },
            {
                "event_type": "login_rejected",
                "summary_code": "https_required",
                "details": {"reason": "sensitive-sentinel"},
            },
        )
        for values in invalid_calls:
            with self.subTest(values=values), self.assertRaises(ValueError):
                write_security_audit(
                    self.db,
                    outcome="failure",
                    source_digest="c" * 64,
                    **values,
                )
        self.assertEqual(len(self.db.new), 0)

    def test_administration_events_require_a_session_and_exact_safe_target(self):
        audit = write_security_audit(
            self.db,
            event_type="manual_sync_enqueued",
            outcome="success",
            session_digest="d" * 64,
            provider=Provider.DOUDIAN,
            target_type="connection",
            target_id="42",
            summary_code="manual_sync_enqueued",
            details={"resource_count": 2, "unit_count": 4},
        )
        self.assertEqual(audit.target_id, "42")

        invalid_calls = (
            {"session_digest": None, "target_type": "connection", "target_id": "42"},
            {"session_digest": "d" * 64, "target_type": "authorization", "target_id": "42"},
            {"session_digest": "d" * 64, "target_type": "connection", "target_id": "../42"},
        )
        for values in invalid_calls:
            with self.subTest(values=values), self.assertRaises(ValueError):
                write_security_audit(
                    self.db,
                    event_type="manual_sync_enqueued",
                    outcome="success",
                    provider=Provider.DOUDIAN,
                    summary_code="manual_sync_enqueued",
                    details={"resource_count": 2, "unit_count": 4},
                    **values,
                )

    def test_export_poll_audit_accepts_only_digest_metadata(self):
        audit = write_security_audit(
            self.db,
            event_type="integration_export_polled",
            outcome="success",
            session_digest="e" * 64,
            target_type="integration_export",
            target_id="018f5ad8-02bd-7f11-8fa0-4d05074b68db",
            summary_code="integration_export_polled",
            details={"creator_session_digest": "f" * 64},
        )
        self.assertEqual(audit.details["creator_session_digest"], "f" * 64)

        with self.assertRaises(ValueError):
            write_security_audit(
                self.db,
                event_type="integration_export_polled",
                outcome="success",
                session_digest="e" * 64,
                target_type="integration_export",
                target_id="018f5ad8-02bd-7f11-8fa0-4d05074b68db",
                summary_code="integration_export_polled",
                details={"creator_session_digest": "not-a-digest"},
            )

    def test_mutation_rejection_audit_has_closed_operation_and_reason_sets(self):
        audit = write_security_audit(
            self.db,
            event_type="integration_mutation_rejected",
            outcome="failure",
            session_digest="1" * 64,
            target_type="integration_command",
            target_id="purge_connection:42",
            summary_code="integration_mutation_rejected",
            details={"operation": "purge_connection", "reason": "password_invalid"},
        )
        self.assertEqual(audit.details["reason"], "password_invalid")

        with self.assertRaises(ValueError):
            write_security_audit(
                self.db,
                event_type="integration_mutation_rejected",
                outcome="failure",
                session_digest="1" * 64,
                target_type="integration_command",
                target_id="purge_connection:42",
                summary_code="integration_mutation_rejected",
                details={"operation": "purge_connection", "reason": "raw exception"},
            )


if __name__ == "__main__":
    unittest.main()
