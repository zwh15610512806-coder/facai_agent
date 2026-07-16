"""Security contract tests for the Product Canvas paid-access session."""
from __future__ import annotations

import base64
import hmac
import io
import logging
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from database import Base, get_db
from routers.canvas import router as canvas_router


TOKEN = "canvas-test-token-that-must-never-be-persisted"


class CanvasAccessContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-access.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401 - register Canvas metadata.

        Base.metadata.create_all(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _app(self, *, include_paid_probe: bool = False) -> FastAPI:
        app = FastAPI()
        app.include_router(canvas_router, prefix="/api/canvas")

        if include_paid_probe:
            from services.canvas.access import require_canvas_paid_access

            @app.post(
                "/api/canvas/test-paid",
                dependencies=[Depends(require_canvas_paid_access)],
            )
            def paid_probe():
                return {"paid": True}

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        return app

    @staticmethod
    def _access_paths(app: FastAPI) -> set[tuple[str, str]]:
        paths = app.openapi()["paths"]
        return {
            (method.upper(), path)
            for path, definition in paths.items()
            if path.startswith("/api/canvas/access/")
            for method in definition
        }

    def test_openapi_exposes_exactly_the_three_access_routes(self) -> None:
        self.assertEqual(
            {
                ("GET", "/api/canvas/access/status"),
                ("POST", "/api/canvas/access/unlock"),
                ("POST", "/api/canvas/access/lock"),
            },
            self._access_paths(self._app()),
        )

    def test_status_reports_configuration_and_lock_without_token_disclosure(self) -> None:
        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app()) as client:
                response = client.get("/api/canvas/access/status")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({"configured": True, "locked": True}, response.json())
        self.assertNotIn(TOKEN, response.text)

    def test_missing_token_is_503_and_wrong_token_is_401_without_cookie(self) -> None:
        with patch.object(config, "CANVAS_ACCESS_TOKEN", "", create=True):
            with TestClient(self._app()) as client:
                missing = client.post(
                    "/api/canvas/access/unlock", json={"token": TOKEN}
                )
        self.assertEqual(503, missing.status_code, missing.text)
        self.assertNotIn("set-cookie", missing.headers)

        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app()) as client:
                wrong = client.post(
                    "/api/canvas/access/unlock", json={"token": "wrong"}
                )
        self.assertEqual(401, wrong.status_code, wrong.text)
        self.assertNotIn("set-cookie", wrong.headers)

    def test_paid_dependency_requires_configuration_and_a_valid_session(self) -> None:
        with patch.object(config, "CANVAS_ACCESS_TOKEN", "", create=True):
            with TestClient(self._app(include_paid_probe=True)) as client:
                missing = client.post("/api/canvas/test-paid")
        self.assertEqual(503, missing.status_code, missing.text)

        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app(include_paid_probe=True)) as client:
                locked = client.post("/api/canvas/test-paid")
                self.assertEqual(401, locked.status_code, locked.text)
                client.post("/api/canvas/access/unlock", json={"token": TOKEN})
                allowed = client.post("/api/canvas/test-paid")
        self.assertEqual(200, allowed.status_code, allowed.text)
        self.assertEqual({"paid": True}, allowed.json())

    def test_unlock_uses_fixed_length_constant_time_comparison(self) -> None:
        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app()) as client:
                with patch(
                    "services.canvas.access.hmac.compare_digest",
                    wraps=hmac.compare_digest,
                ) as compare:
                    response = client.post(
                        "/api/canvas/access/unlock", json={"token": "x"}
                    )
        self.assertEqual(401, response.status_code, response.text)
        compare.assert_called_once()
        supplied, configured = compare.call_args.args
        self.assertEqual((32, 32), (len(supplied), len(configured)))

    def test_unlock_cookie_is_strict_http_only_and_secure_only_on_https(self) -> None:
        encoded_token = base64.urlsafe_b64encode(TOKEN.encode()).decode().rstrip("=")
        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app(), base_url="http://testserver") as client:
                response = client.post(
                    "/api/canvas/access/unlock", json={"token": TOKEN}
                )
                status = client.get("/api/canvas/access/status")
        self.assertEqual(200, response.status_code, response.text)
        cookie = response.headers["set-cookie"]
        self.assertIn("httponly", cookie.lower())
        self.assertIn("samesite=strict", cookie.lower())
        self.assertNotIn("secure", cookie.lower())
        self.assertNotIn(TOKEN, cookie)
        self.assertNotIn(encoded_token, cookie)
        self.assertEqual({"configured": True, "locked": False}, status.json())

        cookie_name, cookie_value = cookie.split(";", 1)[0].split("=", 1)
        tampered = cookie_value[:-1] + ("A" if cookie_value[-1] != "A" else "B")
        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app()) as client:
                client.cookies.set(cookie_name, tampered, path="/api/canvas")
                invalid = client.get("/api/canvas/access/status")
        self.assertEqual({"configured": True, "locked": True}, invalid.json())

        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app(), base_url="https://testserver") as client:
                https = client.post(
                    "/api/canvas/access/unlock", json={"token": TOKEN}
                )
        self.assertIn("secure", https.headers["set-cookie"].lower())

    def test_lock_expiry_rotation_and_new_lifespan_invalidate_session(self) -> None:
        with (
            patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True),
            patch.object(config, "CANVAS_ACCESS_SESSION_TTL_SECONDS", 1, create=True),
        ):
            first_app = self._app()
            with TestClient(first_app) as first:
                unlock = first.post(
                    "/api/canvas/access/unlock", json={"token": TOKEN}
                )
                self.assertEqual(200, unlock.status_code, unlock.text)
                cookie_name, cookie_value = (
                    unlock.headers["set-cookie"].split(";", 1)[0].split("=", 1)
                )
                locked = first.post("/api/canvas/access/lock")
                self.assertIn("max-age=0", locked.headers["set-cookie"].lower())
                self.assertTrue(first.get("/api/canvas/access/status").json()["locked"])
                first.cookies.set(cookie_name, cookie_value, path="/api/canvas")
                self.assertFalse(first.get("/api/canvas/access/status").json()["locked"])

            with TestClient(self._app()) as restarted:
                restarted.cookies.set(cookie_name, cookie_value, path="/api/canvas")
                self.assertTrue(restarted.get("/api/canvas/access/status").json()["locked"])

            with TestClient(self._app()) as rotated:
                rotated.cookies.set(cookie_name, cookie_value, path="/api/canvas")
                with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN + "-rotated"):
                    self.assertTrue(rotated.get("/api/canvas/access/status").json()["locked"])

            with TestClient(self._app()) as expired:
                fresh = expired.post(
                    "/api/canvas/access/unlock", json={"token": TOKEN}
                )
                name, value = (
                    fresh.headers["set-cookie"].split(";", 1)[0].split("=", 1)
                )
                expired.cookies.set(name, value, path="/api/canvas")
                time.sleep(1.05)
                self.assertTrue(expired.get("/api/canvas/access/status").json()["locked"])

    def test_locked_clients_can_browse_and_save_projects_without_token_storage(self) -> None:
        with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
            with TestClient(self._app()) as client:
                created = client.post(
                    "/api/canvas/projects", json={"name": "Locked local project"}
                )
                self.assertEqual(201, created.status_code, created.text)
                project_id = created.json()["project"]["id"]
                saved = client.put(
                    f"/api/canvas/projects/{project_id}/state",
                    json={
                        "revision": 1,
                        "semanticState": {
                            "nodes": [], "edges": [], "outputBoards": [],
                            "mode": "complete-set", "advancedCustomized": False,
                            "completeSet": {"selectedOutputTypes": [], "outputs": []},
                            "compositionGroups": [],
                        },
                        "layoutState": {
                            "viewport": {"x": 0, "y": 0, "zoom": 1},
                            "nodePositions": {},
                            "objectTransforms": {}, "productLayers": [],
                            "textSnapshots": [],
                        },
                    },
                )
                listed = client.get("/api/canvas/projects")
        self.assertEqual(200, saved.status_code, saved.text)
        self.assertEqual([project_id], [row["id"] for row in listed.json()["projects"]])
        self.assertNotIn(TOKEN.encode(), self.db_path.read_bytes())

    def test_raw_token_is_absent_from_application_state_and_logs(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            app = self._app()
            with patch.object(config, "CANVAS_ACCESS_TOKEN", TOKEN, create=True):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/canvas/access/unlock", json={"token": TOKEN}
                    )
                    self.assertEqual(200, response.status_code, response.text)
                    self.assertNotIn(TOKEN, repr(vars(app.state)))
        finally:
            root.removeHandler(handler)
        self.assertNotIn(TOKEN, stream.getvalue())

    def test_lock_reports_unconfigured_after_clearing_cookie(self) -> None:
        with patch.object(config, "CANVAS_ACCESS_TOKEN", "", create=True):
            with TestClient(self._app()) as client:
                response = client.post("/api/canvas/access/lock")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({"configured": False, "locked": True}, response.json())

    def test_access_session_ttl_has_a_bounded_positive_default(self) -> None:
        self.assertGreater(config.CANVAS_ACCESS_SESSION_TTL_SECONDS, 0)
        self.assertLessEqual(config.CANVAS_ACCESS_SESSION_TTL_SECONDS, 86_400)
        with patch.dict(os.environ, {"TEST_CANVAS_TTL": "0"}):
            with self.assertRaisesRegex(ValueError, "positive integer"):
                config._bounded_positive_env_int(
                    "TEST_CANVAS_TTL", 10, maximum=86_400
                )

    def test_environment_example_does_not_enable_a_known_access_token(self) -> None:
        example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("CANVAS_ACCESS_TOKEN=\n", example)
        self.assertNotIn("CANVAS_ACCESS_TOKEN=change-me", example)
        with patch.dict(os.environ, {"TEST_CANVAS_TTL": "86401"}):
            with self.assertRaisesRegex(ValueError, "at most 86400"):
                config._bounded_positive_env_int(
                    "TEST_CANVAS_TTL", 10, maximum=86_400
                )


if __name__ == "__main__":
    unittest.main()
