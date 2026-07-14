import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from services import security
from tests.frontend_source import read_page_source

ROOT = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "admin-" + "a" * 48
OPERATOR_TOKEN = "operator-" + "b" * 48
VIEWER_TOKEN = "viewer-" + "c" * 48


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
    def test_business_routes_default_to_deny_anonymous_access(self):
        with patched_env(
            FACAI_AUTH_ENABLED=None,
            FACAI_ADMIN_TOKEN=ADMIN_TOKEN,
            FACAI_OPERATOR_TOKEN=OPERATOR_TOKEN,
            FACAI_VIEWER_TOKEN=VIEWER_TOKEN,
        ):
            client = TestClient(app, raise_server_exceptions=False)

            api_response = client.get("/api/products/categories")
            app_response = client.get("/app", follow_redirects=False)

        self.assertEqual(api_response.status_code, 401)
        self.assertEqual(app_response.status_code, 303)
        self.assertIn("/app/login", app_response.headers["location"])

    def test_login_sets_http_only_session_cookie_and_reports_role(self):
        with patched_env(
            FACAI_AUTH_ENABLED="1",
            FACAI_ADMIN_TOKEN=ADMIN_TOKEN,
            FACAI_OPERATOR_TOKEN=OPERATOR_TOKEN,
            FACAI_VIEWER_TOKEN=VIEWER_TOKEN,
        ):
            client = TestClient(app)

            response = client.post("/api/auth/login", json={"token": OPERATOR_TOKEN})
            status_response = client.get("/api/auth/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "operator")
        self.assertEqual(response.json()["authenticated"], True)
        cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn("facai_session_token=", cookie)
        self.assertNotIn(OPERATOR_TOKEN.lower(), cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertEqual(status_response.json()["role"], "operator")

    def test_role_matrix_separates_read_write_delete_and_sensitive_routes(self):
        with patched_env(
            FACAI_AUTH_ENABLED="1",
            FACAI_ADMIN_TOKEN=ADMIN_TOKEN,
            FACAI_OPERATOR_TOKEN=OPERATOR_TOKEN,
            FACAI_VIEWER_TOKEN=VIEWER_TOKEN,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            viewer = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
            operator = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}
            admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

            self.assertEqual(client.get("/api/products/categories", headers=viewer).status_code, 200)
            self.assertEqual(client.post("/api/products/", json={}, headers=viewer).status_code, 403)
            self.assertEqual(client.post("/api/products/", json={}, headers=operator).status_code, 422)
            self.assertEqual(client.delete("/api/products/999999", headers=operator).status_code, 403)
            self.assertNotEqual(client.delete("/api/products/999999", headers=admin).status_code, 403)
            self.assertEqual(client.get("/api/ai-config/providers", headers=operator).status_code, 403)
            self.assertEqual(client.get("/api/ai-config/providers", headers=admin).status_code, 200)
            self.assertEqual(client.get("/api/creators/1/private-contact", headers=viewer).status_code, 403)
            self.assertNotEqual(client.get("/api/creators/1/private-contact", headers=operator).status_code, 403)
            self.assertEqual(client.get("/api/search-proxy/files/1/download", headers=viewer).status_code, 403)
            self.assertNotEqual(client.get("/api/search-proxy/files/1/download", headers=operator).status_code, 403)

    def test_cookie_authenticated_mutation_requires_csrf_evidence(self):
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=ADMIN_TOKEN):
            client = TestClient(app)
            self.assertEqual(
                client.post("/api/auth/login", json={"token": ADMIN_TOKEN}).status_code,
                200,
            )

            rejected = client.post("/api/products/", json={})
            accepted_by_csrf = client.post(
                "/api/products/",
                json={},
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(accepted_by_csrf.status_code, 422)

    def test_public_bind_requires_enabled_and_configured_auth(self):
        guard = getattr(security, "assert_startup_security", None)
        self.assertIsNotNone(guard, "startup security guard must be testable")
        with patched_env(FACAI_AUTH_ENABLED="0", FACAI_ADMIN_TOKEN=ADMIN_TOKEN):
            with self.assertRaisesRegex(RuntimeError, "cannot be disabled"):
                guard("0.0.0.0")
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=None):
            with self.assertRaisesRegex(RuntimeError, "FACAI_ADMIN_TOKEN"):
                guard("0.0.0.0")
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=ADMIN_TOKEN):
            guard("0.0.0.0")

    def test_unconfigured_auth_still_denies_business_routes(self):
        with patched_env(FACAI_AUTH_ENABLED=None, FACAI_ADMIN_TOKEN=None):
            client = TestClient(app, base_url="http://192.168.1.50:8001", raise_server_exceptions=False)

            app_response = client.get("/app", follow_redirects=False)
            api_response = client.get("/api/products/categories")

        self.assertEqual(app_response.status_code, 303)
        self.assertEqual(api_response.status_code, 401)

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
        self.assertRegex(content, r"(?m)^FACAI_AUTH_ENABLED=1$")
        self.assertRegex(content, r"(?m)^FACAI_ADMIN_TOKEN=change-me-high-entropy-token$")
        self.assertRegex(content, r"(?m)^FACAI_OPERATOR_TOKEN=change-me-high-entropy-token$")
        self.assertRegex(content, r"(?m)^FACAI_VIEWER_TOKEN=change-me-high-entropy-token$")
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
        page = read_page_source("templates.html")

        self.assertIn("function escHtml", page)
        self.assertIn("escHtml(s.title||'无标题')", page)
        self.assertIn("escHtml((s.script_content||'').substring(0,150))", page)
        self.assertIn("escHtml(currentScript.category)", page)

    def test_search_page_escapes_indexed_file_fields(self):
        page = read_page_source("search.html")

        self.assertIn("function escHtml", page)
        self.assertIn("escHtml(f.file_name)", page)
        self.assertNotIn("f.file_path", page)

    def test_generated_result_metadata_escapes_api_fields_before_inner_html(self):
        index_page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")
        rewrite_page = (ROOT / "templates" / "rewrite.html").read_text(encoding="utf-8-sig")

        self.assertIn("escHtml(d.product_name)", index_page)
        self.assertIn("escHtml(d.video_type)", index_page)
        self.assertIn("escHtml(d.product_name)", rewrite_page)
        self.assertNotIn("'<b>'+d.product_name+'</b>", index_page)
        self.assertNotIn("'<b>'+d.product_name+'</b>", rewrite_page)

    def test_search_page_uses_js_literal_escaping_for_inline_actions(self):
        page = read_page_source("search.html")

        self.assertIn("function jsStringLiteral", page)
        self.assertIn("filterByFolder(${fileId},${folderNameArg},${folderPathArg})", page)
        self.assertIn("const typeArg = jsStringLiteral(f.file_type);", page)
        self.assertIn("const extArg = jsStringLiteral(f.file_extension||'');", page)
        self.assertIn("previewFile(${fileId},${typeArg},${extArg})", page)
        self.assertNotIn("f.file_path", page)

    def test_search_api_does_not_expose_roots_or_absolute_paths(self):
        with patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=ADMIN_TOKEN):
            client = TestClient(app)
            headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

            status_response = client.get("/api/search-proxy/index/status", headers=headers)
            search_response = client.get("/api/search-proxy/search", headers=headers)

        self.assertEqual(status_response.status_code, 200)
        self.assertNotIn("roots", status_response.json())
        for item in search_response.json().get("files", []):
            self.assertNotIn("file_path", item)
            self.assertNotIn("_parent_path", item)

    def test_mutating_request_is_audited_with_actor_and_request_id(self):
        from models import AuditEvent

        with TemporaryDirectory() as temp_dir:
            engine = create_engine(f"sqlite:///{Path(temp_dir) / 'audit.db'}")
            AuditEvent.__table__.create(engine)
            session_factory = sessionmaker(bind=engine)
            with (
                patched_env(FACAI_AUTH_ENABLED="1", FACAI_ADMIN_TOKEN=ADMIN_TOKEN),
                patch("services.access_control.CONTROL_SESSION_FACTORY", session_factory),
            ):
                response = TestClient(app).post(
                    "/api/products/",
                    json={},
                    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                )

            self.assertEqual(response.status_code, 422)
            self.assertRegex(response.headers.get("x-request-id", ""), r"^[a-f0-9-]{36}$")
            with session_factory() as session:
                event = session.query(AuditEvent).one()
                self.assertEqual(event.actor_name, "admin")
                self.assertEqual(event.path, "/api/products/")
                self.assertEqual(event.status_code, 422)
            engine.dispose()

    def test_ai_requests_are_rate_limited_per_actor(self):
        from services.access_control import SlidingWindowLimiter

        with (
            patched_env(
                FACAI_AUTH_ENABLED="1",
                FACAI_OPERATOR_TOKEN=OPERATOR_TOKEN,
                FACAI_AI_RATE_LIMIT_PER_MINUTE="1",
                FACAI_AI_DAILY_TOKEN_BUDGET="0",
            ),
            patch("services.access_control.REQUEST_LIMITER", SlidingWindowLimiter()),
        ):
            client = TestClient(app)
            headers = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}
            first = client.post("/api/scripts/generate", json={}, headers=headers)
            second = client.post("/api/scripts/generate", json={}, headers=headers)

        self.assertEqual(first.status_code, 422)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.headers.get("retry-after"), "60")

    def test_products_page_uses_js_literal_escaping_for_category_toggle(self):
        page = (ROOT / "templates" / "products.html").read_text(encoding="utf-8-sig")

        self.assertIn("function jsStringLiteral", page)
        self.assertIn("onclick=\"toggleCategory('+jsStringLiteral(category)+')\"", page)
        self.assertNotIn("onclick=\"toggleCategory(\\''+jsq(category)+'\\')", page)
        self.assertNotIn("escAttr(f.file_type)", page)
        self.assertNotIn("escAttr(f.file_extension||'')", page)


if __name__ == "__main__":
    unittest.main()
