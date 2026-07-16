import json
import re
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

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

    def test_canvas_root_renders_independent_shell_without_project_id(self):
        response = self.client.get("/app/canvas")

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(1, response.text.count('<div id="canvas-app"></div>'))
        self.assertEqual(
            1,
            response.text.count(
                '<link rel="stylesheet" href="/static/canvas/canvas.css">'
            ),
        )
        self.assertEqual(
            1,
            response.text.count(
                '<script type="module" src="/static/canvas/canvas.js"></script>'
            ),
        )
        self.assertNotIn("/static/js/inspiration.js", response.text)
        _raw, bootstrap = self._bootstrap(response)
        self.assertEqual(
            {"apiBase": "/api/canvas", "projectId": None},
            bootstrap,
        )

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

    def test_canvas_unknown_project_returns_404(self):
        response = self.client.get(f"/app/canvas/{uuid4()}")

        self.assertEqual(404, response.status_code, response.text)
        self.assertEqual({"detail": "Canvas project not found"}, response.json())

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
