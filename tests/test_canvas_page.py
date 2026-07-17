import json
import re
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from database import Base, get_db
from services.canvas import projects as project_service


BOOTSTRAP_PATTERN = re.compile(
    r'<script\s+id="canvas-bootstrap"\s+type="application/json">(?P<body>.*?)</script>',
    flags=re.S,
)


class CanvasPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-page.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)

        def override_db():
            with self.Session() as db:
                yield db

        self.app = main.app
        self.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()
        self.tmp.cleanup()

    def _bootstrap(self, response):
        match = BOOTSTRAP_PATTERN.search(response.text)
        self.assertIsNotNone(match, response.text)
        raw = match.group("body").strip()
        return raw, json.loads(raw)

    def test_canvas_root_redirects_to_main_workbench_canvas_without_project_id(self):
        response = self.client.get("/app/canvas")

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(1, response.text.count('<div id="canvas-app"></div>'))
        self.assertEqual(
            1,
            response.text.count(
                '<link rel="stylesheet" href="/static/canvas/canvas.css?v=workbench-canvas-20260717">'
            ),
        )
        self.assertEqual(
            1,
            response.text.count(
                '<script type="module" src="/static/canvas/canvas.js?v=workbench-canvas-20260717"></script>'
            ),
        )
        self.assertIn('<link rel="stylesheet" href="/static/css/style.css?v=canvas-usability-20260716">', response.text)
        self.assertIn('href="/app?workspace=canvas" class="nav-link on"', response.text)
        self.assertIn('请使用桌面端打开产品视觉画布', response.text)
        self.assertIn('class="canvas-page-main"', response.text)
        self.assertIn('<script src="/static/js/common.js?v=canvas-usability-20260716"></script>', response.text)
        self.assertNotIn("api_key", response.text.casefold())
        self.assertNotIn("/static/js/inspiration.js", response.text)
        _raw, bootstrap = self._bootstrap(response)
        self.assertEqual(
            {"apiBase": "/api/canvas", "projectId": None},
            bootstrap,
        )

        redirect = self.client.get("/app/canvas", follow_redirects=False)
        self.assertEqual(303, redirect.status_code, redirect.text)
        self.assertEqual("/app?workspace=canvas", redirect.headers["location"])

    def test_canvas_project_page_requires_existing_project_and_embeds_only_minimal_bootstrap(self):
        malicious_name = (
            'Hidden </script><script>alert("canvas")</script> '
            "\u2028\u2029 C:\\server-secret\\CANVAS_DATA_DIR"
        )
        with self.Session() as db:
            project = project_service.create_project(db, name=malicious_name)

        response = self.client.get(f"/app/canvas/{project.id}")

        self.assertEqual(200, response.status_code, response.text)
        raw, bootstrap = self._bootstrap(response)
        self.assertEqual({"apiBase", "projectId"}, set(bootstrap))
        self.assertEqual("/api/canvas", bootstrap["apiBase"])
        self.assertEqual(project.id, bootstrap["projectId"])
        self.assertNotIn(malicious_name, response.text)
        for forbidden in (
            "semanticState",
            "semantic_state",
            "layoutState",
            "layout_state",
            "secret",
            "apiKey",
            "api_key",
            "CANVAS_DATA_DIR",
            "C:\\server-secret",
        ):
            self.assertNotIn(forbidden, raw)

        redirect = self.client.get(f"/app/canvas/{project.id}", follow_redirects=False)
        self.assertEqual(303, redirect.status_code, redirect.text)
        self.assertEqual(
            f"/app?workspace=canvas&project_id={project.id}",
            redirect.headers["location"],
        )

    def test_canvas_unknown_project_returns_404(self):
        response = self.client.get(f"/app/canvas/{uuid4()}")

        self.assertEqual(404, response.status_code, response.text)
        self.assertEqual({"detail": "Canvas project not found"}, response.json())

    def test_canvas_shell_reserves_nav_height_and_blocks_narrow_editing(self):
        styles = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "canvas"
            / "src"
            / "styles.css"
        ).read_text(encoding="utf-8")

        self.assertIn("height: calc(100dvh - 68px);", styles)
        self.assertIn("@media (max-width: 1023px)", styles)
        self.assertIn(".canvas-page #canvas-app", styles)
        self.assertIn(".canvas-page .canvas-desktop-gate", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn(".canvas-page .facai-tools-launcher", styles)
        self.assertIn("right: calc(368px + 28px);", styles)
        self.assertIn("bottom: 54px;", styles)

    def test_canvas_bootstrap_serializer_cannot_close_script_or_emit_js_separators(self):
        payload = {
            "apiBase": "</script><script>alert(1)</script>&",
            "projectId": "project\u2028line\u2029paragraph",
        }

        self.assertTrue(
            hasattr(main, "_serialize_canvas_bootstrap"),
            "a server-side Canvas bootstrap serializer is required",
        )
        serialized = main._serialize_canvas_bootstrap(payload)

        self.assertEqual(payload, json.loads(serialized))
        self.assertNotIn("</script", serialized.casefold())
        self.assertNotIn("<", serialized)
        self.assertNotIn("&", serialized)
        self.assertNotIn("\u2028", serialized)
        self.assertNotIn("\u2029", serialized)


if __name__ == "__main__":
    unittest.main()
