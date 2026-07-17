import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendCommonJsTests(unittest.TestCase):
    SHARED_TOOLS_ASSET_VERSION = "canvas-usability-20260716"
    TOOL_TEMPLATES = [
        "index.html",
        "rewrite.html",
        "products.html",
        "creators.html",
        "import.html",
        "templates.html",
        "history.html",
        "search.html",
        "inspiration.html",
        "ai_config.html",
        "operations.html",
        "api_connections.html",
    ]

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

    def test_all_business_pages_include_the_tools_common_js(self):
        for name in self.TOOL_TEMPLATES:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            version = self.SHARED_TOOLS_ASSET_VERSION
            self.assertIn(f'/static/css/style.css?v={version}', page, name)
            self.assertIn(f'/static/js/common.js?v={version}', page, name)
            self.assertIn('href="/app?workspace=canvas" class="nav-link', page, name)
            self.assertNotIn('data-import-fab', page, name)
            self.assertNotIn('ai-config-fab', page, name)

    def test_common_js_is_the_single_tools_navigation_source(self):
        common = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8")

        self.assertIn("var TOOL_LINKS = [", common)
        self.assertIn("{label: '数据导入', href: '/app/import', icon: 'upload'}", common)
        self.assertIn("{label: 'AI配置', href: '/app/ai-config', icon: 'settings'}", common)
        self.assertIn("{label: 'API接入', href: '/app/api-connections', icon: 'plug-zap'}", common)
        self.assertIn("facai-tools-launcher", common)
        self.assertIn("facaiToolsToggle", common)
        self.assertIn("facaiToolsMenu", common)
        self.assertIn("aria-expanded", common)
        self.assertIn("aria-controls", common)
        self.assertIn("aria-label", common)
        self.assertIn("event.key === 'Escape'", common)
        self.assertIn("toggle.focus()", common)
        self.assertIn("facai-tools-open", common)
        self.assertIn("Object.freeze", common)
        self.assertIn("initToolNavigation", common)
        self.assertNotIn("href: '/app/canvas'", common)

    def test_canvas_is_the_primary_nav_item_immediately_after_ai_work(self):
        canvas_link = r'<a href="/app\?workspace=canvas"[^>]*>产品视觉画布</a>'
        ai_link = r'<a href="/app"[^>]*>AI工作</a>'
        for name in self.TOOL_TEMPLATES:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertRegex(page, ai_link + r"\s*" + canvas_link, name)

    def test_mobile_tools_links_are_built_from_the_same_array(self):
        common = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8")

        self.assertIn("TOOL_LINKS.forEach", common)
        self.assertIn("nav-mobile-utility", common)
        self.assertIn("isCurrentTool", common)

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
