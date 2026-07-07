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
        self.assertIn(".nav-brand-group", body)
        self.assertIn("justify-content: flex-start", body)
        self.assertIn(".nav-links", body)
        self.assertIn("overflow-x: auto", body)
        self.assertIn("scroll-padding-inline", body)
        self.assertIn(".nav-link.on", body)
        self.assertIn("min-height: 42px", body)
        self.assertIn(".product-grid", body)
        self.assertIn("grid-template-columns: 1fr", body)
        self.assertIn("safe-area-inset-bottom", body)
        self.assertIn(".mo-box", body)
        self.assertIn("100dvh", body)

    def test_shared_mobile_breakpoint_handles_overflow_prone_content(self):
        mobile = re.search(r"@media \(max-width: 768px\)\s*\{(?P<body>.*?)\n\}", self.css, flags=re.S)

        self.assertIsNotNone(mobile)
        body = mobile.group("body")
        self.assertIn(".nav-brand-group", body)
        self.assertIn(".nav-brand span:last-child", body)
        self.assertIn("text-overflow: ellipsis", body)
        self.assertIn("img, video, iframe", body)
        self.assertIn("table", body)
        self.assertIn("overflow-x: auto", body)
        self.assertIn(".float-bar", body)
        self.assertIn("flex-wrap: wrap", body)
        self.assertIn(".float-bar .btn", body)
        self.assertIn("min-width: 0", body)
        self.assertIn(".scroll-top-btn", body)
        self.assertIn("safe-area-inset-bottom", body)

    def test_toast_defaults_to_bottom_right_on_desktop(self):
        toast = re.search(r"\.toast\s*\{(?P<body>.*?)\n\}", self.css, flags=re.S)

        self.assertIsNotNone(toast)
        body = toast.group("body")
        self.assertIn("position: fixed", body)
        self.assertIn("bottom: 32px", body)
        self.assertIn("right: 32px", body)

    def test_bottom_right_fabs_are_fixed_and_mobile_safe(self):
        fab = re.search(r"\.ai-config-fab,\s*\n\.data-import-fab\s*\{(?P<body>.*?)\n\}", self.css, flags=re.S)
        mobile = re.search(r"@media \(max-width: 768px\)\s*\{(?P<body>.*?)\n\}", self.css, flags=re.S)

        self.assertIsNotNone(fab)
        self.assertIsNotNone(mobile)
        fab_body = fab.group("body")
        mobile_body = mobile.group("body")
        self.assertIn("position: fixed", fab_body)
        self.assertIn("right: 28px", fab_body)
        self.assertIn("z-index: 90", fab_body)
        self.assertIn(".ai-config-fab { bottom: 28px; }", self.css)
        self.assertIn(".data-import-fab { bottom: 88px; }", self.css)
        self.assertIn(".ai-config-fab", mobile_body)
        self.assertIn(".data-import-fab", mobile_body)
        self.assertIn("bottom: max(72px", mobile_body)
        self.assertIn("bottom: max(126px", mobile_body)
        self.assertIn("env(safe-area-inset-bottom)", mobile_body)


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

    def test_generate_page_mobile_detail_modal_header_and_float_bar_do_not_squeeze(self):
        modal_mobile = re.search(r"@media \(max-width: 680px\)\s*\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        step_mobile = re.search(r"@media \(max-width: 760px\)\s*\{(?P<body>.*?)\n\}", self.page, flags=re.S)

        self.assertIsNotNone(modal_mobile)
        self.assertIsNotNone(step_mobile)
        modal_body = modal_mobile.group("body")
        step_body = step_mobile.group("body")
        self.assertIn(".product-detail-hd", modal_body)
        self.assertIn("flex-wrap: wrap", modal_body)
        self.assertIn(".product-detail-top-actions", modal_body)
        self.assertIn("width: 100%", modal_body)
        self.assertIn(".product-detail-next", modal_body)
        self.assertIn(".float-bar", step_body)
        self.assertIn("align-items: stretch", step_body)
        self.assertIn("flex-wrap: wrap", step_body)


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

    def test_templates_page_mobile_detail_modal_controls_stack_cleanly(self):
        page = (ROOT / "templates" / "templates.html").read_text(encoding="utf-8-sig")

        self.assertIn("@media (max-width: 768px)", page)
        self.assertIn(".script-detail-modal", page)
        self.assertIn("width: 100%", page)
        self.assertIn(".script-preview-actions .btn", page)
        self.assertIn(".modal-product-list.has-results", page)
        self.assertIn("grid-template-columns:1fr", page)
        self.assertIn(".modal-product-toolbar { display:block; height:auto; }", page)
        self.assertIn(".modal-product-toolbar .input { height:auto; min-height:44px; }", page)
        self.assertIn(".modal-product-list .modal-product-card { flex:initial; height:auto; min-height:60px; }", page)
        self.assertNotIn(".modal-product-toolbar .btn", page)

    def test_search_page_mobile_filter_chips_scroll_horizontally(self):
        page = (ROOT / "templates" / "search.html").read_text(encoding="utf-8-sig")

        self.assertIn("@media (max-width: 768px)", page)
        self.assertIn(".filter-chips", page)
        self.assertIn("flex-wrap: nowrap", page)
        self.assertIn(".fchip", page)
        self.assertIn("flex: 0 0 auto", page)


class ProductsPageMobileWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "products.html").read_text(encoding="utf-8-sig")

    def test_products_page_has_mobile_segmented_workspace_controls(self):
        self.assertIn('data-mobile-view="list"', self.page)
        self.assertIn('class="mobile-product-tabs"', self.page)
        self.assertIn('class="mobile-product-tab on"', self.page)
        self.assertIn('data-view="list"', self.page)
        self.assertIn('data-view="detail"', self.page)
        self.assertIn('data-view="chat"', self.page)
        self.assertIn('onclick="setMobileProductView(\'list\')"', self.page)
        self.assertIn('onclick="setMobileProductView(\'detail\')"', self.page)
        self.assertIn('onclick="setMobileProductView(\'chat\')"', self.page)

    def test_products_page_mobile_breakpoint_shows_only_active_panel(self):
        mobile = re.search(r"@media \(max-width: 768px\)\s*\{(?P<body>.*?)\n\}", self.page, flags=re.S)

        self.assertIsNotNone(mobile)
        body = mobile.group("body")
        self.assertIn(".mobile-product-tabs", body)
        self.assertIn(".products-page[data-mobile-view=\"list\"] .sidebar-panel", body)
        self.assertIn(".products-page[data-mobile-view=\"detail\"] .detail-panel", body)
        self.assertIn(".products-page[data-mobile-view=\"chat\"] .chat-panel", body)
        self.assertIn("display:flex", body)
        self.assertIn(".products-panel{display:none", body)
        self.assertIn("calc(100dvh - 142px - env(safe-area-inset-bottom))", body)
        self.assertIn(".chat-composer", body)
        self.assertIn("padding-bottom:max(12px, env(safe-area-inset-bottom))", body)

    def test_products_page_mobile_source_modal_and_chat_avoid_horizontal_overflow(self):
        mobile = re.search(r"@media \(max-width: 768px\)\s*\{(?P<body>.*?)\n\}", self.page, flags=re.S)

        self.assertIsNotNone(mobile)
        body = mobile.group("body")
        self.assertIn(".source-modal-box", body)
        self.assertIn("width:100vw", body)
        self.assertIn("max-width:100vw", body)
        self.assertIn(".source-download-link", body)
        self.assertIn("width:100%", body)
        self.assertIn(".chat-bubble", body)
        self.assertIn("max-width:94%", body)
        self.assertIn(".chat-input", body)
        self.assertIn("font-size:16px", body)


if __name__ == "__main__":
    unittest.main()
