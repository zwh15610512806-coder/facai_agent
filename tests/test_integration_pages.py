import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from integrations.settings import IntegrationSettings
from main import app
from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]


def _settings(*, credential_ready: bool) -> IntegrationSettings:
    return IntegrationSettings(
        master_key=b"m" * 32 if credential_ready else None,
        internal_base_url="http://127.0.0.1:8765" if credential_ready else None,
        public_base_url="https://callbacks.test.invalid" if credential_ready else None,
        archive_dir=ROOT / ".superpowers" / "test-archive" if credential_ready else None,
        trusted_proxy_networks=(),
        worker_concurrency=4,
        credential_ready=credential_ready,
        errors=() if credential_ready else ("FACAI_INTEGRATIONS_MASTER_KEY",),
    )


class IntegrationPageTests(unittest.TestCase):
    def test_legacy_login_url_redirects_and_center_opens_without_session(self):
        with patch(
            "integrations.settings.load_integration_settings",
            return_value=_settings(credential_ready=False),
        ):
            client = TestClient(app)
            legacy = client.get("/app/api-connections/login", follow_redirects=False)
            page = client.get("/app/api-connections")

        self.assertEqual(legacy.status_code, 303)
        self.assertEqual(legacy.headers["location"], "/app/api-connections")
        self.assertEqual(page.status_code, 200)
        self.assertIn("电商 API 接入中心", page.text)
        self.assertIn("连接器尚未配置", page.text)
        self.assertNotIn("退出管理", page.text)
        self.assertNotIn("管理员密码", page.text)

    def test_connection_page_keeps_confirmation_and_credential_safety(self):
        source = read_page_source("api_connections.html")
        for token in (
            'aria-busy="false"',
            'role="status"',
            'aria-live="polite"',
            'id="purgeConnectionDialog"',
            'data-purge-submit',
            '确认连接名称',
            '清除本地凭据',
            '最近失败任务',
            'data-connection-action="retry-run"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn('autocomplete="current-password"', source)
        self.assertNotIn('name="password"', source)
        self.assertNotIn("api-connections-login", source)
        self.assertNotIn("response.status === 401", source)
        for unsafe_sink in (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(unsafe_sink, source)
        self.assertNotIn("buyer_phone", source.lower())
        self.assertNotIn("access_token_ciphertext", source.lower())

    def test_operations_page_source_has_six_read_views(self):
        source = read_page_source("operations.html")
        for name in ("overview", "orders", "products", "refunds", "ads", "sync-runs"):
            self.assertEqual(source.count(f'data-tab="{name}"'), 1)
            self.assertIn(f'id="panel-{name}"', source)
        self.assertIn("/api/operations/overview", source)
        self.assertIn("FacaiUI.getApiErrorMessage", source)
        self.assertNotIn("buyer_phone", source.lower())


if __name__ == "__main__":
    unittest.main()
