import math
import importlib.util
import asyncio
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app
from schemas import (
    ProductCreate,
    ProductUpdate,
    ScriptGenerateRequest,
    ScriptRewriteRequest,
    SellingPointCreate,
    ViralScriptCreate,
)


ROOT = Path(__file__).resolve().parents[1]


class DependencySecurityPinsTests(unittest.TestCase):
    def test_known_vulnerable_direct_dependencies_are_upgraded(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("fastapi==0.139.0", requirements)
        self.assertIn("starlette==1.3.1", requirements)
        self.assertIn("python-multipart==0.0.32", requirements)
        self.assertIn("jinja2==3.1.6", requirements)
        self.assertIn("pdfminer.six==20260107", requirements)


class RequestSchemaHardeningTests(unittest.TestCase):
    def test_product_numbers_must_be_finite_and_non_negative(self):
        invalid_payloads = (
            {"name": "产品", "category": "烘焙调味", "price": -1},
            {"name": "产品", "category": "烘焙调味", "price": math.nan},
            {"name": "产品", "category": "烘焙调味", "price": math.inf},
            {"name": "产品", "category": "烘焙调味", "price": 1, "commission_rate": 101},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ProductCreate.model_validate(payload)

    def test_product_and_selling_point_text_limits_are_enforced(self):
        with self.assertRaises(ValidationError):
            ProductCreate(name="   ", category="烘焙调味", price=1)
        with self.assertRaises(ValidationError):
            ProductUpdate(brand="x" * 101)
        with self.assertRaises(ValidationError):
            SellingPointCreate(point_type="卖点", content="x" * 8001)

    def test_generation_requests_reject_unknown_engines_extras_and_huge_prompts(self):
        with self.assertRaises(ValidationError):
            ScriptGenerateRequest(product_id=1, engine="typo")
        with self.assertRaises(ValidationError):
            ScriptGenerateRequest.model_validate({"product_id": 1, "unknown": True})
        with self.assertRaises(ValidationError):
            ScriptGenerateRequest(product_id=1, extra_requirements="x" * 4001)
        with self.assertRaises(ValidationError):
            ScriptRewriteRequest(original_script="x" * 24001, product_id=1)
        with self.assertRaises(ValidationError):
            ViralScriptCreate(
                category="烘焙调味",
                video_type="机制类",
                title="标题",
                script_content="x" * 120001,
            )


class RequestMiddlewareHardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_cross_origin_mutating_api_request_is_rejected(self):
        response = self.client.post(
            "/api/inspiration/chat",
            headers={"Origin": "https://attacker.example"},
            json={},
        )

        self.assertEqual(response.status_code, 403)

    def test_same_origin_mutating_api_request_remains_allowed(self):
        response = self.client.post(
            "/api/inspiration/chat",
            headers={"Origin": "http://testserver"},
            json={},
        )

        self.assertEqual(response.status_code, 422)

    def test_same_origin_https_request_behind_http_proxy_remains_allowed(self):
        response = self.client.post(
            "/api/inspiration/chat",
            headers={
                "Host": "preview.serveousercontent.com:443",
                "Origin": "https://preview.serveousercontent.com",
                "Sec-Fetch-Site": "same-origin",
            },
            json={},
        )

        self.assertEqual(response.status_code, 422)

    def test_proxy_scheme_fallback_requires_browser_confirmed_same_origin(self):
        response = self.client.post(
            "/api/inspiration/chat",
            headers={
                "Host": "preview.serveousercontent.com:443",
                "Origin": "https://preview.serveousercontent.com",
                "Sec-Fetch-Site": "same-site",
            },
            json={},
        )

        self.assertEqual(response.status_code, 403)

    def test_untrusted_host_is_rejected(self):
        response = self.client.get("/healthz", headers={"Host": "attacker.example"})

        self.assertEqual(response.status_code, 400)

    def test_security_headers_are_added_to_app_responses(self):
        response = self.client.get("/app")

        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")
        self.assertIn("camera=()", response.headers.get("permissions-policy", ""))

    def test_oversize_json_body_is_rejected_before_validation(self):
        response = self.client.post(
            "/api/inspiration/chat",
            content=b'{"prompt":"' + (b"x" * (2 * 1024 * 1024)) + b'"}',
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 413)

    def test_route_specific_request_limits_keep_large_workbook_support(self):
        self.assertIsNotNone(importlib.util.find_spec("services.request_hardening"))
        from services.request_hardening import request_body_limit_for

        self.assertEqual(
            request_body_limit_for(
                "/api/templates/viral/import-workbook",
                "multipart/form-data; boundary=test",
            ),
            100 * 1024 * 1024,
        )
        self.assertEqual(
            request_body_limit_for("/api/inspiration/attachments", "multipart/form-data"),
            13 * 1024 * 1024,
        )
        self.assertEqual(
            request_body_limit_for("/api/auth/login", "application/json"),
            2 * 1024 * 1024,
        )

    def test_chunked_body_without_content_length_cannot_bypass_limit(self):
        from services.request_hardening import RequestBodyLimitMiddleware

        sent = []
        chunks = [
            {"type": "http.request", "body": b"x" * (1024 * 1024), "more_body": True},
            {"type": "http.request", "body": b"x" * (1024 * 1024 + 1), "more_body": False},
        ]

        async def receive():
            return chunks.pop(0)

        async def send(message):
            sent.append(message)

        async def downstream(_scope, receive_body, send_body):
            while True:
                message = await receive_body()
                if not message.get("more_body"):
                    break
            await send_body({"type": "http.response.start", "status": 200, "headers": []})
            await send_body({"type": "http.response.body", "body": b"ok"})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [(b"content-type", b"application/json")],
        }
        asyncio.run(RequestBodyLimitMiddleware(downstream)(scope, receive, send))

        self.assertEqual(sent[0]["status"], 413)


if __name__ == "__main__":
    unittest.main()
