import unittest
import os
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from services import security


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def patched_env(**updates):
    old_values = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class SecurityHardeningTests(unittest.TestCase):
    def test_admin_token_no_longer_protects_app_or_api(self):
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN="launch-secret"):
            client = TestClient(app, raise_server_exceptions=False)

            api_response = client.get("/api/products/categories")
            app_response = client.get("/app", follow_redirects=False)

        self.assertNotEqual(api_response.status_code, 401)
        self.assertNotEqual(api_response.status_code, 503)
        self.assertEqual(app_response.status_code, 200)

    def test_login_endpoint_is_compatibility_noop_without_cookie(self):
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN="launch-secret"):
            client = TestClient(app)

            response = client.post("/api/auth/login", json={"token": "anything"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["enabled"], False)
        self.assertEqual(response.json()["authenticated"], True)
        self.assertNotIn("facai_admin_token=", response.headers.get("set-cookie", ""))

    def test_login_page_redirects_to_app(self):
        client = TestClient(app)
        response = client.get("/app/login", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app")

    def test_auth_enabled_without_token_still_allows_app_and_api(self):
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=None):
            client = TestClient(app, raise_server_exceptions=False)

            api_response = client.get("/api/products/categories")
            app_response = client.get("/app", follow_redirects=False)

        self.assertNotEqual(api_response.status_code, 401)
        self.assertNotEqual(api_response.status_code, 503)
        self.assertEqual(app_response.status_code, 200)

    def test_public_bind_without_token_does_not_require_startup_lockout(self):
        guard = getattr(security, "assert_startup_security", None)
        self.assertIsNotNone(guard, "startup security guard must be testable")
        with patched_env(FACAI_AUTH_ENABLED=None, FACAI_ADMIN_TOKEN=None):
            guard("0.0.0.0")

    def test_public_bind_with_auth_enabled_and_missing_token_does_not_lock(self):
        guard = getattr(security, "assert_startup_security", None)
        self.assertIsNotNone(guard, "startup security guard must be testable")
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=None):
            guard("0.0.0.0")

    def test_lan_host_without_token_still_allows_app_and_api(self):
        with patched_env(FACAI_AUTH_ENABLED=None, FACAI_ADMIN_TOKEN=None):
            client = TestClient(app, base_url="http://192.168.1.50:8001", raise_server_exceptions=False)

            app_response = client.get("/app", follow_redirects=False)
            api_response = client.get("/api/products/categories")

        self.assertEqual(app_response.status_code, 200)
        self.assertNotEqual(api_response.status_code, 401)
        self.assertNotEqual(api_response.status_code, 503)

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

    def test_env_files_are_gitignored_except_example(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertRegex(gitignore, r"(?m)^\.env\.\*$")
        self.assertRegex(gitignore, r"(?m)^!\.env\.example$")

    def test_env_example_exists_with_safe_placeholders(self):
        env_example = ROOT / ".env.example"

        self.assertTrue(env_example.exists())
        content = env_example.read_text(encoding="utf-8")
        self.assertRegex(content, r"(?m)^FACAI_AUTH_ENABLED=0$")
        self.assertNotIn("FACAI_ADMIN_TOKEN=", content)
        self.assertRegex(content, r"(?m)^DEEPSEEK_API_KEY=change-me$")
        self.assertRegex(content, r"(?m)^ARK_API_KEY=change-me$")
        for marker in ("sk-", "Bearer ", "eyJ", "AKLT", "AIza"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, content)

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

    def test_generated_result_metadata_escapes_api_fields_before_inner_html(self):
        index_page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")
        rewrite_page = (ROOT / "templates" / "rewrite.html").read_text(encoding="utf-8-sig")

        self.assertIn("escHtml(d.product_name)", index_page)
        self.assertIn("escHtml(d.video_type)", index_page)
        self.assertIn("escHtml(d.product_name)", rewrite_page)
        self.assertNotIn("'<b>'+d.product_name+'</b>", index_page)
        self.assertNotIn("'<b>'+d.product_name+'</b>", rewrite_page)

    def test_search_page_uses_js_literal_escaping_for_inline_actions(self):
        page = (ROOT / "templates" / "search.html").read_text(encoding="utf-8-sig")

        self.assertIn("function jsStringLiteral", page)
        self.assertIn("const folderArg = jsStringLiteral(f.file_path);", page)
        self.assertIn("const typeArg = jsStringLiteral(f.file_type);", page)
        self.assertIn("const extArg = jsStringLiteral(f.file_extension||'');", page)
        self.assertIn("filterByFolder(${folderArg})", page)
        self.assertIn("previewFile(${fileId},${typeArg},${extArg})", page)
        self.assertNotIn("escPath(f.file_path)", page)

    def test_products_page_uses_js_literal_escaping_for_category_toggle(self):
        page = (ROOT / "templates" / "products.html").read_text(encoding="utf-8-sig")

        self.assertIn("function jsStringLiteral", page)
        self.assertIn("onclick=\"toggleCategory('+jsStringLiteral(category)+')\"", page)
        self.assertNotIn("onclick=\"toggleCategory(\\''+jsq(category)+'\\')", page)
        self.assertNotIn("escAttr(f.file_type)", page)
        self.assertNotIn("escAttr(f.file_extension||'')", page)


if __name__ == "__main__":
    unittest.main()
