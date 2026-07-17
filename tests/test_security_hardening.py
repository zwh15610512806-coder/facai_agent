import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from main import app
from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]


class SecurityHardeningTests(unittest.TestCase):
    def test_cross_site_and_untrusted_origin_requests_are_rejected(self):
        client = TestClient(app)
        cross_site = client.get(
            "/api/products/categories",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        wrong_origin = client.post(
            "/api/products/",
            json={},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(cross_site.status_code, 403)
        self.assertEqual(
            {"detail": "Cross-site API requests are not allowed"},
            cross_site.json(),
        )
        self.assertEqual(wrong_origin.status_code, 403)
        self.assertEqual(
            {"detail": "Request origin is not allowed"},
            wrong_origin.json(),
        )
        for response in (cross_site, wrong_origin):
            self.assertRegex(response.headers.get("x-request-id", ""), r"^[a-f0-9-]{36}$")
            self.assertEqual("nosniff", response.headers.get("x-content-type-options"))
            self.assertEqual("SAMEORIGIN", response.headers.get("x-frame-options"))
            self.assertEqual("no-referrer", response.headers.get("referrer-policy"))
            self.assertEqual(
                "camera=(), microphone=(), geolocation=()",
                response.headers.get("permissions-policy"),
            )

    def test_request_protection_is_pure_asgi_and_adds_headers_to_responses(self):
        self.assertFalse(
            any(issubclass(middleware.cls, BaseHTTPMiddleware) for middleware in app.user_middleware),
            "Streaming responses must not pass through BaseHTTPMiddleware",
        )
        client = TestClient(app)
        try:
            response = client.get("/healthz")
        finally:
            client.close()

        self.assertEqual(200, response.status_code)
        self.assertRegex(response.headers.get("x-request-id", ""), r"^[a-f0-9-]{36}$")
        self.assertEqual("nosniff", response.headers.get("x-content-type-options"))
        self.assertEqual("SAMEORIGIN", response.headers.get("x-frame-options"))
        self.assertEqual("no-referrer", response.headers.get("referrer-policy"))
        self.assertEqual(
            "camera=(), microphone=(), geolocation=()",
            response.headers.get("permissions-policy"),
        )

    def test_cors_is_not_wildcard_with_credentials(self):
        main_py = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn('allow_origins=["*"]', main_py)
        self.assertIn("allow_origins=ALLOWED_ORIGINS", main_py)
        self.assertIn("allow_credentials=False", main_py)

    def test_env_files_are_gitignored_except_example(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(gitignore, r"(?m)^\.env\.\*$")
        self.assertRegex(gitignore, r"(?m)^!\.env\.example$")

    def test_env_example_has_no_login_switches_and_keeps_service_placeholders(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        for obsolete in (
            "FACAI_AUTH_",
            "FACAI_ADMIN_TOKEN",
            "FACAI_OPERATOR_TOKEN",
            "FACAI_VIEWER_TOKEN",
            "FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH",
            "FACAI_INTEGRATIONS_SESSION_SECRET",
            "CANVAS_ACCESS_TOKEN",
        ):
            self.assertNotIn(obsolete, content)
        self.assertRegex(content, r"(?m)^DEEPSEEK_API_KEY=change-me$")
        self.assertRegex(content, r"(?m)^ARK_API_KEY=change-me$")

    def test_app_templates_do_not_depend_on_external_cdn_assets(self):
        for template in (ROOT / "templates").glob("*.html"):
            page = template.read_text(encoding="utf-8-sig")
            for marker in ("fonts.googleapis.com", "unpkg.com", "jsdelivr", "cdnjs"):
                self.assertNotIn(marker, page)

    def test_search_and_template_pages_escape_api_backed_fields(self):
        template_page = read_page_source("templates.html")
        search_page = read_page_source("search.html")
        self.assertIn("function escHtml", template_page)
        self.assertIn("escHtml(s.title||'无标题')", template_page)
        self.assertIn("function escHtml", search_page)
        self.assertIn("escHtml(f.file_name)", search_page)
        self.assertNotIn("f.file_path", search_page)

    def test_search_api_does_not_expose_roots_or_absolute_paths(self):
        client = TestClient(app)
        status_response = client.get("/api/search-proxy/index/status")
        search_response = client.get("/api/search-proxy/search")
        self.assertEqual(status_response.status_code, 200)
        self.assertNotIn("roots", status_response.json())
        for item in search_response.json().get("files", []):
            self.assertNotIn("file_path", item)
            self.assertNotIn("_parent_path", item)

    def test_mutating_request_is_audited_with_network_actor_and_request_id(self):
        from models import AuditEvent

        with TemporaryDirectory() as temp_dir:
            engine = create_engine(f"sqlite:///{Path(temp_dir) / 'audit.db'}")
            AuditEvent.__table__.create(engine)
            session_factory = sessionmaker(bind=engine)
            with patch("services.access_control.CONTROL_SESSION_FACTORY", session_factory):
                response = TestClient(app).post("/api/products/", json={})
            self.assertEqual(response.status_code, 422)
            self.assertRegex(response.headers.get("x-request-id", ""), r"^[a-f0-9-]{36}$")
            with session_factory() as session:
                self.assertEqual(1, session.query(AuditEvent).count())
                event = session.query(AuditEvent).one()
                self.assertEqual(event.actor_name, "intranet:testclient")
                self.assertEqual(event.actor_role, "trusted-intranet")
                self.assertEqual(event.auth_source, "network")
            engine.dispose()

    def test_ai_requests_remain_rate_limited(self):
        from models import AuditEvent
        from services.access_control import SlidingWindowLimiter

        with TemporaryDirectory() as temp_dir:
            engine = create_engine(f"sqlite:///{Path(temp_dir) / 'rate-audit.db'}")
            AuditEvent.__table__.create(engine)
            session_factory = sessionmaker(bind=engine)
            with (
                patch.dict(
                    os.environ,
                    {"FACAI_AI_RATE_LIMIT_PER_MINUTE": "1", "FACAI_AI_DAILY_TOKEN_BUDGET": "0"},
                ),
                patch("services.access_control.REQUEST_LIMITER", SlidingWindowLimiter()),
                patch("services.access_control.CONTROL_SESSION_FACTORY", session_factory),
            ):
                client = TestClient(app)
                try:
                    first = client.post("/api/scripts/generate", json={})
                    second = client.post("/api/scripts/generate", json={})
                finally:
                    client.close()
            self.assertEqual(first.status_code, 422)
            self.assertEqual(second.status_code, 429)
            self.assertEqual(second.headers.get("retry-after"), "60")
            self.assertRegex(second.headers.get("x-request-id", ""), r"^[a-f0-9-]{36}$")
            self.assertEqual("nosniff", second.headers.get("x-content-type-options"))
            self.assertEqual("SAMEORIGIN", second.headers.get("x-frame-options"))
            self.assertEqual("no-referrer", second.headers.get("referrer-policy"))
            self.assertEqual(
                "camera=(), microphone=(), geolocation=()",
                second.headers.get("permissions-policy"),
            )
            with session_factory() as session:
                events = session.query(AuditEvent).order_by(AuditEvent.id).all()
                self.assertEqual([422, 429], [event.status_code for event in events])
                self.assertEqual(len({event.request_id for event in events}), 2)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
