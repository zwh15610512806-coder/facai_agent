import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]


class SeedancePromptPageTests(unittest.TestCase):
    def test_legacy_seedance_route_redirects_to_ai_work(self):
        response = TestClient(app).get("/app/seedance", follow_redirects=False)

        self.assertIn(response.status_code, {302, 303, 307})
        self.assertEqual(response.headers["location"], "/app")

    def test_standalone_seedance_assets_are_removed(self):
        self.assertFalse((ROOT / "templates" / "seedance.html").exists())
        self.assertFalse((ROOT / "static" / "js" / "seedance.js").exists())

    def test_all_main_templates_remove_seedance_top_nav(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]

        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertNotIn('href="/app/seedance"', page, name)


if __name__ == "__main__":
    unittest.main()
