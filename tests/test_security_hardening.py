import unittest
import os
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]


class SecurityHardeningTests(unittest.TestCase):
    def test_admin_token_protects_app_and_api_when_configured(self):
        old_token = os.environ.get("FACAI_ADMIN_TOKEN")
        os.environ["FACAI_ADMIN_TOKEN"] = "launch-secret"
        try:
            client = TestClient(app)

            api_response = client.get("/api/products/categories")
            app_response = client.get("/app", follow_redirects=False)
            authed_response = client.get(
                "/api/products/categories",
                headers={"Authorization": "Bearer launch-secret"},
            )

            self.assertEqual(api_response.status_code, 401)
            self.assertEqual(app_response.status_code, 303)
            self.assertIn("/app/login", app_response.headers["location"])
            self.assertNotEqual(authed_response.status_code, 401)
        finally:
            if old_token is None:
                os.environ.pop("FACAI_ADMIN_TOKEN", None)
            else:
                os.environ["FACAI_ADMIN_TOKEN"] = old_token

    def test_login_sets_admin_cookie_when_token_matches(self):
        old_token = os.environ.get("FACAI_ADMIN_TOKEN")
        os.environ["FACAI_ADMIN_TOKEN"] = "launch-secret"
        try:
            client = TestClient(app)

            response = client.post("/api/auth/login", json={"token": "launch-secret"})

            self.assertEqual(response.status_code, 200)
            self.assertIn("facai_admin_token=", response.headers.get("set-cookie", ""))
            self.assertIn("httponly", response.headers.get("set-cookie", "").lower())
        finally:
            if old_token is None:
                os.environ.pop("FACAI_ADMIN_TOKEN", None)
            else:
                os.environ["FACAI_ADMIN_TOKEN"] = old_token

    def test_cross_site_api_requests_are_rejected(self):
        client = TestClient(app)

        response = client.get(
            "/api/products/categories",
            headers={"Sec-Fetch-Site": "cross-site"},
        )

        self.assertEqual(response.status_code, 403)

    def test_cors_is_not_wildcard_with_credentials(self):
        main_py = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn('allow_origins=["*"]', main_py)
        self.assertIn("allow_origins=ALLOWED_ORIGINS", main_py)
        self.assertIn("allow_credentials=False", main_py)

    def test_search_index_cache_is_gitignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("data/search_index.json", gitignore)

    def test_app_templates_do_not_depend_on_external_cdn_assets(self):
        blocked = ("fonts.googleapis.com", "unpkg.com", "jsdelivr", "cdnjs")
        for template in (ROOT / "templates").glob("*.html"):
            page = template.read_text(encoding="utf-8-sig")
            for marker in blocked:
                with self.subTest(template=template.name, marker=marker):
                    self.assertNotIn(marker, page)

    def test_template_library_escapes_api_backed_html(self):
        page = (ROOT / "templates" / "templates.html").read_text(encoding="utf-8-sig")

        self.assertIn("function escHtml", page)
        self.assertIn("escHtml(s.title||'无标题')", page)
        self.assertIn("escHtml((s.script_content||'').substring(0,150))", page)
        self.assertIn("escHtml(currentScript.category)", page)

    def test_search_page_escapes_indexed_file_fields(self):
        page = (ROOT / "templates" / "search.html").read_text(encoding="utf-8-sig")

        self.assertIn("function escHtml", page)
        self.assertIn("escHtml(f.file_name)", page)
        self.assertIn("escHtml(f.file_path)", page)


if __name__ == "__main__":
    unittest.main()
