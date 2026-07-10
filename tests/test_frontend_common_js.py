import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendCommonJsTests(unittest.TestCase):
    def test_common_js_exposes_shared_helpers(self):
        common = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8")

        self.assertIn("window.FacaiUI", common)
        self.assertIn("escHtml", common)
        self.assertIn("toast", common)
        self.assertIn("copyText", common)
        self.assertIn("getApiErrorMessage", common)
        self.assertIn("formatApiErrorMessage", common)
        self.assertIn("withBusyButton", common)
        self.assertIn("fetchWithTimeout", common)
        self.assertIn("renderPager", common)

    def test_common_js_formats_structured_api_errors(self):
        common = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8")

        self.assertIn("function formatApiErrorMessage(value, fallback)", common)
        self.assertIn("Array.isArray(value)", common)
        self.assertIn("value.msg", common)
        self.assertIn("JSON.stringify(value)", common)
        self.assertIn("return formatApiErrorMessage(data.detail || data.message || data, fallback)", common)

    def test_optimized_pages_include_common_js(self):
        for name in ["templates.html", "history.html", "import.html", "products.html", "search.html", "inspiration.html", "ai_config.html"]:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertIn('/static/js/common.js?v=20260710-hardening', page, name)

    def test_large_page_assets_are_external_and_syntax_checked(self):
        assets = {
            "inspiration.html": ("inspiration.css", "inspiration.js"),
            "templates.html": ("templates-library.css", "templates-library.js"),
            "search.html": ("search.css", "search.js"),
        }
        for template_name, (css_name, js_name) in assets.items():
            page = (ROOT / "templates" / template_name).read_text(encoding="utf-8-sig")
            self.assertNotIn("<style>", page, template_name)
            self.assertNotIn("<script>", page, template_name)
            self.assertIn(f"/static/css/{css_name}", page, template_name)
            self.assertIn(f"/static/js/{js_name}", page, template_name)
            self.assertTrue((ROOT / "static" / "css" / css_name).is_file())
            self.assertTrue((ROOT / "static" / "js" / js_name).is_file())


if __name__ == "__main__":
    unittest.main()
