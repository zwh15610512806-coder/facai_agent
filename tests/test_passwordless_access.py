import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from integrations.settings import IntegrationSettings
from integrations.schemas import PurgeConnectionRequest
from pydantic import ValidationError


_AUTH_ENV_KEYS = (
    "FACAI_AUTH_ENABLED",
    "FACAI_ADMIN_TOKEN",
    "FACAI_OPERATOR_TOKEN",
    "FACAI_VIEWER_TOKEN",
    "FACAI_AUTH_SESSION_SECONDS",
    "FACAI_AUTH_COOKIE_SECURE",
)


@contextmanager
def without_application_credentials():
    previous = {key: os.environ.pop(key, None) for key in _AUTH_ENV_KEYS}
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


class PasswordlessApplicationAccessTests(unittest.TestCase):
    def test_pages_and_business_apis_are_open_without_credentials(self):
        with without_application_credentials():
            client = TestClient(app, raise_server_exceptions=False)

            page = client.get("/app", follow_redirects=False)
            api = client.get("/api/products/categories")

        self.assertEqual(page.status_code, 200)
        self.assertEqual(api.status_code, 200)

    def test_legacy_login_page_redirects_without_showing_a_form(self):
        with without_application_credentials():
            response = TestClient(app).get("/app/login", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app")

    def test_obsolete_login_submission_route_is_absent(self):
        with without_application_credentials():
            response = TestClient(app).post(
                "/api/auth/login",
                json={"token": "obsolete-token"},
            )

        self.assertEqual(response.status_code, 404)


class PasswordlessIntegrationAccessTests(unittest.TestCase):
    @staticmethod
    def _ready_settings() -> IntegrationSettings:
        return IntegrationSettings(
            master_key=b"m" * 32,
            internal_base_url="http://127.0.0.1:8765",
            public_base_url="https://callbacks.test.invalid",
            archive_dir=Path(__file__).resolve().parent / ".integration-archive",
            trusted_proxy_networks=(),
            worker_concurrency=4,
            credential_ready=True,
            errors=(),
        )

    def test_integration_page_and_admin_api_are_open_without_session_cookie(self):
        with (
            without_application_credentials(),
            patch(
                "integrations.settings.load_integration_settings",
                return_value=self._ready_settings(),
            ),
            patch(
                "routers.integrations.load_integration_settings",
                return_value=self._ready_settings(),
            ),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                page = client.get("/app/api-connections", follow_redirects=False)
                api = client.get("/api/integrations/providers")

        self.assertEqual(page.status_code, 200)
        self.assertEqual(api.status_code, 200)

    def test_legacy_integration_login_page_redirects_to_center(self):
        with without_application_credentials():
            response = TestClient(app).get(
                "/app/api-connections/login",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/api-connections")

    def test_purge_contract_uses_confirmation_only_and_rejects_password(self):
        payload = PurgeConnectionRequest.model_validate({"confirmation": "测试店铺"})
        self.assertEqual(payload.confirmation, "测试店铺")

        with self.assertRaises(ValidationError):
            PurgeConnectionRequest.model_validate(
                {"password": "obsolete", "confirmation": "测试店铺"}
            )

if __name__ == "__main__":
    unittest.main()
