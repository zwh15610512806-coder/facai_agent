import base64
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from integrations.settings import (
    ARCHIVE_DIR_ENV,
    DATABASE_URL_ENV,
    INTERNAL_BASE_URL_ENV,
    MASTER_KEY_ENV,
    PUBLIC_BASE_URL_ENV,
    TRUSTED_PROXY_CIDRS_ENV,
    WORKER_CONCURRENCY_ENV,
)
from main import app
from main import _host_matches_origin


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class IntegrationPublicBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = {
            MASTER_KEY_ENV: _base64url(b"b" * 32),
            INTERNAL_BASE_URL_ENV: "https://internal.integration.test",
            PUBLIC_BASE_URL_ENV: "https://public.integration.test",
            ARCHIVE_DIR_ENV: str((Path(__file__).parents[1] / "data" / "task9-boundary").resolve()),
            TRUSTED_PROXY_CIDRS_ENV: "",
            WORKER_CONCURRENCY_ENV: "1",
            DATABASE_URL_ENV: os.environ.get("FACAI_TEST_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1/facai_test"),
        }

    def setUp(self):
        self.environment_patch = patch.dict(os.environ, self.environment, clear=False)
        self.environment_patch.start()

    def tearDown(self):
        self.environment_patch.stop()

    def test_public_host_can_reach_only_exact_callback_and_event_paths(self):
        with TestClient(app, base_url=self.environment[PUBLIC_BASE_URL_ENV], raise_server_exceptions=False) as client:
            for path in ("/", "/healthz", "/app", "/api/integrations/providers", "/static/css/style.css", "/docs"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 404, response.text)
                    self.assertEqual(response.json(), {"detail": "Not Found"})

            callback = client.get("/integrations/oauth/callback/qianchuan")
            self.assertEqual(callback.status_code, 400, callback.text)
            self.assertEqual(callback.json(), {"detail": {"code": "invalid_oauth_callback"}})
            for method in (client.get, client.post):
                event = method("/integrations/events/doudian")
                self.assertEqual(event.status_code, 503, event.text)
                self.assertEqual(event.json(), {"detail": {"code": "event_handler_unavailable"}})

    def test_public_host_rejects_method_suffix_and_traversal_with_generic_404(self):
        cases = (
            ("POST", "/integrations/oauth/callback/qianchuan"),
            ("GET", "/integrations/oauth/callback/qianchuan/"),
            ("GET", "/integrations/oauth/callback/qianchuan/extra"),
            ("GET", "/integrations/oauth/callback/not-a-provider"),
            ("PUT", "/integrations/events/pdd"),
            ("GET", "/integrations/events/pdd/"),
            ("GET", "/integrations/events//pdd"),
            ("GET", "/integrations/events/%2e%2e/app"),
        )
        with TestClient(app, base_url=self.environment[PUBLIC_BASE_URL_ENV], raise_server_exceptions=False) as client:
            for method, path in cases:
                with self.subTest(method=method, path=path):
                    response = client.request(method, path)
                    self.assertEqual(response.status_code, 404, response.text)
                    self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_internal_exact_host_is_allowed_and_unrelated_named_host_is_rejected(self):
        with TestClient(app, base_url=self.environment[INTERNAL_BASE_URL_ENV], raise_server_exceptions=False) as internal:
            self.assertNotEqual(internal.get("/app").status_code, 400)
        with TestClient(app, base_url="https://attacker.integration.test", raise_server_exceptions=False) as attacker:
            self.assertEqual(attacker.get("/healthz").status_code, 400)

    def test_origin_host_matching_enforces_effective_ports_and_ipv6_equivalence(self):
        self.assertTrue(
            _host_matches_origin(
                "public.integration.test",
                "https://public.integration.test",
            )
        )
        self.assertTrue(
            _host_matches_origin(
                "public.integration.test:443",
                "https://public.integration.test",
            )
        )
        self.assertFalse(
            _host_matches_origin(
                "public.integration.test:80",
                "https://public.integration.test",
            )
        )
        self.assertFalse(
            _host_matches_origin(
                "public.integration.test",
                "https://public.integration.test:8443",
            )
        )
        self.assertTrue(
            _host_matches_origin(
                "[2001:0db8:0:0:0:0:0:1]:8443",
                "https://[2001:db8::1]:8443",
            )
        )
        self.assertFalse(
            _host_matches_origin(
                "public.integration.test",
                "https://public.integration.test:80",
            )
        )
        self.assertFalse(
            _host_matches_origin(
                "public.integration.test",
                "http://public.integration.test:443",
            )
        )
        self.assertFalse(
            _host_matches_origin(
                "public.integration.test:",
                "https://public.integration.test",
            )
        )

    def test_configured_hostname_wrong_port_never_falls_back_to_legacy_allowlist(self):
        custom = dict(self.environment)
        custom[PUBLIC_BASE_URL_ENV] = "https://public.integration.test:8443"
        with (
            patch.dict(os.environ, custom, clear=False),
            patch("main.ALLOWED_HOSTS", ["public.integration.test"]),
            TestClient(
                app,
                base_url="https://public.integration.test",
                raise_server_exceptions=False,
            ) as client,
        ):
            wrong_port = client.get(
                "/app",
                headers={"Host": "public.integration.test:443"},
            )
            malformed_port = client.get(
                "/app",
                headers={"Host": "public.integration.test:"},
            )
            exact_public = client.get(
                "/app",
                headers={"Host": "public.integration.test:8443"},
            )
        self.assertEqual(wrong_port.status_code, 400, wrong_port.text)
        self.assertEqual(malformed_port.status_code, 400, malformed_port.text)
        self.assertEqual(exact_public.status_code, 404, exact_public.text)

    def test_configured_private_ip_wrong_port_is_not_accepted_as_generic_lan(self):
        custom = dict(self.environment)
        custom[PUBLIC_BASE_URL_ENV] = "https://10.20.30.40:8443"
        with (
            patch.dict(os.environ, custom, clear=False),
            TestClient(
                app,
                base_url="https://10.20.30.40",
                raise_server_exceptions=False,
            ) as client,
        ):
            response = client.get(
                "/app",
                headers={"Host": "10.20.30.40:443"},
            )
        self.assertEqual(response.status_code, 400, response.text)

    def test_identical_loopback_admin_and_public_origin_is_not_ready(self):
        identical = dict(self.environment)
        identical[INTERNAL_BASE_URL_ENV] = "http://127.0.0.1:8001"
        identical[PUBLIC_BASE_URL_ENV] = "http://127.0.0.1:8001"
        with (
            patch.dict(os.environ, identical, clear=False),
            TestClient(
                app,
                base_url="http://127.0.0.1:8001",
                raise_server_exceptions=False,
            ) as client,
        ):
            response = client.get("/api/integrations/providers")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "security_configuration_incomplete",
        )

    def test_ambiguous_default_loopback_ports_do_not_create_a_public_fence(self):
        ambiguous = dict(self.environment)
        ambiguous[INTERNAL_BASE_URL_ENV] = "http://localhost"
        ambiguous[PUBLIC_BASE_URL_ENV] = "https://localhost"
        with (
            patch.dict(os.environ, ambiguous, clear=False),
            TestClient(
                app,
                base_url="http://localhost",
                raise_server_exceptions=False,
            ) as client,
        ):
            response = client.get("/app")
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
