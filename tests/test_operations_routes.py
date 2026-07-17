import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class OperationsRouteTests(unittest.TestCase):
    def test_operations_page_and_read_api_are_open_without_credentials(self):
        client = TestClient(app, raise_server_exceptions=False)
        page = client.get("/app/operations")
        with patch("routers.integrations.overview", return_value={"summary": "ok"}):
            api = client.get(
                "/api/operations/overview",
                params={"date_from": "2026-07-01", "date_to": "2026-07-01"},
            )

        self.assertEqual(page.status_code, 200)
        self.assertIn("运营数据中台", page.text)
        self.assertEqual(api.status_code, 200)
        self.assertEqual(api.json(), {"summary": "ok"})

    def test_integration_center_no_longer_exposes_session_api(self):
        client = TestClient(app, raise_server_exceptions=False)
        self.assertEqual(client.get("/api/integrations/session").status_code, 404)
        self.assertEqual(client.delete("/api/integrations/session").status_code, 404)

    def test_old_authorization_headers_do_not_change_passwordless_access(self):
        client = TestClient(app)
        plain = client.get("/api/products/categories")
        obsolete = client.get(
            "/api/products/categories",
            headers={"Authorization": "Bearer obsolete-role-token"},
        )
        self.assertEqual(plain.status_code, 200)
        self.assertEqual(obsolete.status_code, 200)
        self.assertEqual(plain.json(), obsolete.json())


if __name__ == "__main__":
    unittest.main()
