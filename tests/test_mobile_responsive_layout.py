import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SharedMobileResponsiveCssTests(unittest.TestCase):
    def setUp(self):
        self.css = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8-sig")

    def test_shared_mobile_breakpoint_protects_small_screen_layout(self):
        mobile = re.search(r"@media \(max-width: 768px\)\s*\{(?P<body>.*?)\n\}", self.css, flags=re.S)

        self.assertIsNotNone(mobile)
        body = mobile.group("body")
        self.assertIn(".nav-inner", body)
        self.assertIn("flex-direction: column", body)
        self.assertIn(".nav-links", body)
        self.assertIn("overflow-x: auto", body)
        self.assertIn(".product-grid", body)
        self.assertIn("grid-template-columns: 1fr", body)
        self.assertIn("safe-area-inset-bottom", body)
        self.assertIn(".mo-box", body)
        self.assertIn("100dvh", body)

    def test_toast_defaults_to_bottom_right_on_desktop(self):
        toast = re.search(r"\.toast\s*\{(?P<body>.*?)\n\}", self.css, flags=re.S)

        self.assertIsNotNone(toast)
        body = toast.group("body")
        self.assertIn("position: fixed", body)
        self.assertIn("bottom: 32px", body)
        self.assertIn("right: 32px", body)


class GeneratePageMobileLayoutTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_generate_page_mobile_category_sidebar_becomes_horizontal_chips(self):
        mobile = re.search(r"@media \(max-width: 760px\)\s*\{(?P<body>.*?)\n\}", self.page, flags=re.S)

        self.assertIsNotNone(mobile)
        body = mobile.group("body")
        self.assertIn("#step1 .section-hd", body)
        self.assertIn(".category-sidebar", body)
        self.assertIn("flex-direction: row", body)
        self.assertIn("overflow-x: auto", body)
        self.assertIn(".product-picker-layout", body)
        self.assertIn("grid-template-columns: 1fr", body)


class PageSpecificMobileLayoutTests(unittest.TestCase):
    def test_import_page_has_mobile_single_column_forms(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn("@media (max-width: 768px)", page)
        self.assertIn("main.page-main > div", page)
        self.assertIn("grid-template-columns: 1fr !important", page)

    def test_rewrite_page_has_mobile_single_column_picker_and_compare(self):
        page = (ROOT / "templates" / "rewrite.html").read_text(encoding="utf-8-sig")

        self.assertIn("@media (max-width: 768px)", page)
        self.assertIn("#productPicker > div", page)
        self.assertIn("#productGrid", page)
        self.assertIn("#comparePanel > div", page)
        self.assertIn("grid-template-columns: 1fr !important", page)


if __name__ == "__main__":
    unittest.main()
