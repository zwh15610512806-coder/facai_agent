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
        self.assertIn("withBusyButton", common)
        self.assertIn("renderPager", common)

    def test_optimized_pages_include_common_js(self):
        for name in ["templates.html", "history.html", "import.html", "products.html", "search.html"]:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertIn('/static/js/common.js', page, name)


if __name__ == "__main__":
    unittest.main()
