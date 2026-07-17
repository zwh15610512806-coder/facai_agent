import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from database import get_db
from integrations.actor import IntegrationActor, current_integration_actor
from integrations.management import (
    ManagementConflict,
    authorization_view,
    connection_view,
    enqueue_manual_sync,
)
from integrations.schemas import ManualSyncRequest
from integrations.types import (
    AuthorizationStatus,
    ConnectionStatus,
    ConnectionType,
    JobStatus,
    Provider,
)
from main import app


UTC = timezone.utc


class ManagementSafeViewTests(unittest.TestCase):
    def setUp(self):
        self.authorization = SimpleNamespace(
            id=4,
            provider=Provider.DOUDIAN,
            external_subject_id="subject-4",
            scopes=["order.read"],
            access_token_ciphertext="ciphertext-must-not-appear",
            access_token_tail="1234",
            refresh_token_ciphertext="refresh-must-not-appear",
            refresh_token_tail="5678",
            access_expires_at=datetime(2026, 7, 14, tzinfo=UTC),
            refresh_expires_at=datetime(2026, 8, 14, tzinfo=UTC),
            status=AuthorizationStatus.ACTIVE,
            last_authorized_at=datetime(2026, 7, 13, tzinfo=UTC),
            last_refreshed_at=None,
        )
        self.connection = SimpleNamespace(
            id=9,
            authorization_id=4,
            provider=Provider.DOUDIAN,
            connection_type=ConnectionType.SHOP,
            external_account_id="shop-9",
            display_name="测试店铺",
            status=ConnectionStatus.ACTIVE,
            capability_report={
                "verified_resources": ["orders", "refunds"],
                "resources": {
                    "orders": {"available": True},
                    "refunds": {
                        "available": False,
                        "reason": "permission_denied",
                    },
                }
            },
            earliest_available_date=None,
            last_successful_sync_at=None,
            disabled_at=None,
        )

    def test_safe_views_expose_masks_but_never_ciphertexts_or_tokens(self):
        payload = {
            "authorization": authorization_view(self.authorization),
            "connection": connection_view(self.connection, self.authorization),
        }
        encoded = repr(payload).lower()

        self.assertIn("••••1234", encoded)
        self.assertIn("••••5678", encoded)
        self.assertNotIn("external_subject_id", payload["authorization"])
        self.assertNotIn("subject-4", encoded)
        self.assertEqual(
            payload["connection"]["capabilities"],
            {
                "verified_resources": ["orders"],
                "limited_resources": [
                    {"resource": "refunds", "reason": "permission_denied"}
                ],
                "status": "permission_limited",
            },
        )
        for forbidden in (
            "ciphertext-must-not-appear",
            "refresh-must-not-appear",
            "access_token_ciphertext",
            "refresh_token_ciphertext",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_explicit_permission_denial_overrides_legacy_verified_resource(self):
        db = Mock()
        db.scalar.return_value = self.connection
        request = ManualSyncRequest(
            request_id=uuid4(),
            resources=["refunds"],
            date_from=date(2026, 7, 13),
            date_to=date(2026, 7, 13),
        )

        with self.assertRaisesRegex(ManagementConflict, "not verified"):
            enqueue_manual_sync(
                db,
                connection_id=self.connection.id,
                request=request,
                now=datetime(2026, 7, 13, tzinfo=UTC),
            )


class ManagementEndpointContractTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[current_integration_actor] = lambda: IntegrationActor("test-actor")
        app.dependency_overrides[get_db] = lambda: object()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_connection_list_and_unknown_id_contracts(self):
        with patch(
            "routers.integrations.list_connection_views",
            return_value=[],
            create=True,
        ):
            response = self.client.get("/api/integrations/connections")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"connections": []})

    def test_confirmed_purge_rearms_a_terminal_job_and_reports_real_status(self):
        now = datetime(2026, 7, 13, 4, 0, tzinfo=UTC)
        connection = SimpleNamespace(
            id=9,
            provider=Provider.DOUDIAN,
            display_name="测试店铺",
            status=ConnectionStatus.DISABLED,
            disabled_at=now,
            updated_at=now,
        )
        job = SimpleNamespace(
            id=77,
            status=JobStatus.FAILED,
            attempts=6,
            available_at=now,
            lease_owner="old-worker",
            lease_expires_at=now,
            heartbeat_at=now,
            last_error_code="internal_error",
            last_error_summary="internal worker failure",
            completed_at=now,
            updated_at=now,
        )
        db = Mock()
        db.scalar.return_value = connection
        claims = IntegrationActor("a" * 64)
        app.dependency_overrides[current_integration_actor] = lambda: claims
        app.dependency_overrides[get_db] = lambda: db

        with (
            patch("routers.integrations.enqueue_job", return_value=job),
            patch("routers.integrations.write_security_audit"),
            patch("routers.integrations.utc_now", return_value=now),
        ):
            response = self.client.post(
                "/api/integrations/connections/9/purge",
                json={"confirmation": "测试店铺"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            {"connection_id": 9, "job_id": 77, "status": "queued"},
        )
        self.assertIs(job.status, JobStatus.QUEUED)
        self.assertEqual(job.attempts, 0)
        self.assertIsNone(job.lease_owner)
        self.assertIsNone(job.last_error_code)
        self.assertIsNone(job.completed_at)
        db.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
