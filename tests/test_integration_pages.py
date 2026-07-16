import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from integrations.admin_auth import INTEGRATION_ADMIN_COOKIE, issue_admin_session
from integrations.settings import IntegrationSettings
from main import app
from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]
SESSION_SECRET = b"integration-pages-session-secret-20260713"
VIEWER_TOKEN = "viewer-" + "c" * 48
ADMIN_TOKEN = "admin-" + "a" * 48


def _settings(*, login_ready: bool, credential_ready: bool) -> IntegrationSettings:
    errors = () if credential_ready else ("FACAI_INTEGRATIONS_MASTER_KEY",)
    return IntegrationSettings(
        admin_password_hash="$scrypt$test" if login_ready else None,
        session_secret=SESSION_SECRET if login_ready else None,
        master_key=b"m" * 32 if credential_ready else None,
        internal_base_url="http://127.0.0.1:8765" if credential_ready else None,
        public_base_url="https://callbacks.test.invalid" if credential_ready else None,
        archive_dir=ROOT / ".superpowers" / "test-archive" if credential_ready else None,
        trusted_proxy_networks=(),
        worker_concurrency=4,
        login_ready=login_ready,
        credential_ready=credential_ready,
        errors=errors,
    )


class IntegrationPageTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in (
                "FACAI_AUTH_ENABLED",
                "FACAI_ADMIN_TOKEN",
                "FACAI_VIEWER_TOKEN",
            )
        }
        os.environ.update(
            {
                "FACAI_AUTH_ENABLED": "1",
                "FACAI_ADMIN_TOKEN": ADMIN_TOKEN,
                "FACAI_VIEWER_TOKEN": VIEWER_TOKEN,
            }
        )

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client(self) -> TestClient:
        return TestClient(
            app,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
        )

    def _authenticated_client(self, settings: IntegrationSettings) -> TestClient:
        client = self._client()
        cookie = issue_admin_session(session_secret=SESSION_SECRET)
        client.cookies.set(INTEGRATION_ADMIN_COOKIE, cookie)
        return client

    def test_login_page_after_system_auth_never_loads_shared_tools(self):
        with patch(
            "integrations.settings.load_integration_settings",
            return_value=_settings(login_ready=False, credential_ready=False),
        ):
            response = self._client().get("/app/api-connections/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn("API 接入中心", response.text)
        self.assertIn("安全配置未完成", response.text)
        self.assertNotIn("/static/js/common.js", response.text)
        self.assertIn("/static/js/api-connections-login.js", response.text)

    def test_main_page_redirects_without_session_but_api_keeps_json_401(self):
        ready = _settings(login_ready=True, credential_ready=True)
        with patch(
            "integrations.settings.load_integration_settings",
            return_value=ready,
        ):
            client = self._client()
            page = client.get("/app/api-connections", follow_redirects=False)
            api = client.get("/api/integrations/session")

        self.assertEqual(page.status_code, 303)
        self.assertEqual(
            page.headers["location"],
            "/app/api-connections/login?next=%2Fapp%2Fapi-connections",
        )
        self.assertEqual(api.status_code, 401)
        self.assertEqual(
            api.json(),
            {"detail": "Integration administrator session required"},
        )

    def test_valid_cookie_returns_protected_page_and_safe_read_only_banner(self):
        partial = _settings(login_ready=True, credential_ready=False)
        with patch(
            "integrations.settings.load_integration_settings",
            return_value=partial,
        ):
            response = self._authenticated_client(partial).get(
                "/app/api-connections"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("电商 API 接入中心", response.text)
        self.assertIn("连接器尚未配置", response.text)
        self.assertIn('id="integrationLogout"', response.text)
        self.assertIn("/static/js/common.js?v=canvas-usability-20260716", response.text)
        self.assertNotIn("FACAI_INTEGRATIONS_MASTER_KEY", response.text)
        self.assertNotIn("ciphertext", response.text.lower())
        self.assertNotIn("access_token", response.text.lower())

    def test_login_next_accepts_only_the_exact_local_connection_page(self):
        ready = _settings(login_ready=True, credential_ready=True)
        cases = {
            "https://evil.example/steal": "/app/api-connections",
            "//evil.example/steal": "/app/api-connections",
            "/app/api-connections-evil": "/app/api-connections",
            "/app/api-connections?tab=orders": "/app/api-connections",
            "/app/api-connections/login": "/app/api-connections",
            "/app/api-connections": "/app/api-connections",
        }
        with patch(
            "integrations.settings.load_integration_settings",
            return_value=ready,
        ):
            client = self._client()
            for supplied, expected in cases.items():
                with self.subTest(supplied=supplied):
                    response = client.get(
                        "/app/api-connections/login",
                        params={"next": supplied},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(
                        f'data-next="{expected.replace("&", "&amp;")}"',
                        response.text,
                    )
                    self.assertNotIn("evil.example", response.text)

    def test_page_assets_define_accessible_login_and_protected_shell(self):
        login = (ROOT / "templates" / "api_connections_login.html").read_text(
            encoding="utf-8-sig"
        )
        page = (ROOT / "templates" / "api_connections.html").read_text(
            encoding="utf-8-sig"
        )
        script = (ROOT / "static" / "js" / "api-connections-login.js").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn('autocomplete="current-password"', login)
        self.assertIn('role="alert"', login)
        self.assertIn('aria-live="polite"', login)
        self.assertNotIn("common.js", login)
        self.assertIn('aria-label="API 接入中心主导航"', page)
        self.assertIn('id="integrationSecurityBanner"', page)
        self.assertIn("passwordInput.value = ''", script)
        self.assertIn("retry_after_seconds", script)
        self.assertIn("window.location.assign(nextPath)", script)

    def test_connection_page_source_is_admin_only_and_has_no_data_center(self):
        source = read_page_source("api_connections.html")
        for token in (
            'aria-busy="false"',
            'role="status"',
            'aria-live="polite"',
            'id="purgeConnectionDialog"',
            'autocomplete="current-password"',
            'data-purge-submit',
            'disabled',
            'role="region"',
            '清除本地凭据',
            '最近失败任务',
            'data-connection-action="retry-run"',
            '错误摘要',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)

        for endpoint in (
            "/api/integrations/providers",
            "/api/integrations/connections",
            "/api/integrations/sync-runs",
            "/api/integrations/sync-runs/",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, source)

        self.assertIn("FacaiUI.getApiErrorMessage", source)
        self.assertIn("response.status === 401", source)
        self.assertIn("textContent", source)
        self.assertIn("overflow-x: auto", source)
        self.assertNotIn('role="tablist"', source)
        self.assertNotIn('data-tab="overview"', source)
        self.assertNotIn('id="productLinkDialog"', source)
        self.assertNotIn('/api/operations/', source)
        self.assertNotIn('data-export', source)
        for unsafe_sink in (
            ".innerHTML",
            ".outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
        ):
            with self.subTest(unsafe_sink=unsafe_sink):
                self.assertNotIn(unsafe_sink, source)
        self.assertNotIn("buyer_name", source.lower())
        self.assertNotIn("buyer_phone", source.lower())
        self.assertNotIn("access_token_ciphertext", source.lower())
        self.assertNotIn("refresh_token_ciphertext", source.lower())

    def test_operations_page_source_has_six_read_views_and_no_admin_calls(self):
        source = read_page_source("operations.html")
        tab_names = ("overview", "orders", "products", "refunds", "ads", "sync-runs")

        self.assertIn('role="tablist"', source)
        for name in tab_names:
            with self.subTest(tab=name):
                self.assertEqual(source.count(f'data-tab="{name}"'), 1)
                self.assertIn(f'id="panel-{name}"', source)
                self.assertIn(f'aria-controls="panel-{name}"', source)

        for endpoint in (
            "/api/operations/filter-options",
            "/api/operations/overview",
            "/api/operations/orders",
            "/api/operations/products",
            "/api/operations/refunds",
            "/api/operations/ad-entities",
            "/api/operations/ad-metrics",
            "/api/operations/sync-runs",
            "/api/operations/exports",
            "/api/operations/products/",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, source)

        for token in (
            'aria-busy="false"',
            'role="status"',
            'aria-live="polite"',
            'name="provider"',
            'name="connection_id"',
            'name="date_from"',
            'name="date_to"',
            '<option value="50">50',
            '<option value="100">100',
            '<option value="200">200',
            'id="productLinkDialog"',
            '实际成交',
            '广告归因成交',
            '广告消耗',
            '广告实体搜索（不影响指标）',
            'Asia/Shanghai',
            'AbortController',
            'FacaiUI.getApiErrorMessage',
            'response.status === 401',
            '2000',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)

        self.assertNotIn('/api/integrations/providers', source)
        self.assertNotIn('/api/integrations/connections', source)
        self.assertNotIn('/api/integrations/sync-runs/', source)
        self.assertNotIn('retry-run', source)
        self.assertNotIn('id="purgeConnectionDialog"', source)
        self.assertNotIn('window.setInterval', source)
        for unsafe_sink in (
            ".innerHTML",
            ".outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
        ):
            with self.subTest(unsafe_sink=unsafe_sink):
                self.assertNotIn(unsafe_sink, source)
        self.assertNotIn("buyer_name", source.lower())
        self.assertNotIn("buyer_phone", source.lower())
        self.assertNotIn("access_token", source.lower())


if __name__ == "__main__":
    unittest.main()
