import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]


class SecurityHardeningTests(unittest.TestCase):
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
