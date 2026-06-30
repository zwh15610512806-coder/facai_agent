import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]


class SeedancePromptPageTests(unittest.TestCase):
    def test_seedance_page_route_renders_tool(self):
        response = TestClient(app).get("/app/seedance")

        self.assertEqual(response.status_code, 200)
        self.assertIn("分镜提示词生成", response.text)
        self.assertIn("/api/scripts/seedance-prompts", response.text)

    def test_seedance_template_has_inline_requirements_and_result_controls(self):
        page = (ROOT / "templates" / "seedance.html").read_text(encoding="utf-8-sig")

        for text in [
            'id="seedanceFileInput"',
            'accept=".txt,.md,.json,.csv,.pdf,.docx,.xlsx"',
            'id="seedanceScriptInput"',
            'id="seedanceRequirements"',
            'id="btnGenerateSeedancePrompts"',
            'id="btnCopySeedanceAll"',
            'id="seedancePromptList"',
            "/static/js/seedance.js",
        ]:
            self.assertIn(text, page)
        self.assertLess(page.find('id="seedanceScriptInput"'), page.find('id="seedanceRequirements"'))
        self.assertNotIn('id="requirementsModal"', page)
        self.assertNotIn('id="sceneCount"', page)
        self.assertNotIn("分镜数量", page)

    def test_seedance_layout_uses_equal_height_panels_and_larger_script_input(self):
        page = (ROOT / "templates" / "seedance.html").read_text(encoding="utf-8-sig")

        self.assertIn("align-items:stretch", page)
        self.assertIn("minmax(560px,1.12fr) minmax(520px,1fr)", page)
        self.assertIn(".seedance-panel{", page)
        self.assertIn("flex-direction:column", page)
        self.assertIn(".seedance-script-input{width:100%;min-height:460px;flex:1 1 auto", page)
        self.assertIn(".seedance-loading", page)

    def test_seedance_js_generates_directly_without_modal_or_scene_count(self):
        script = (ROOT / "static" / "js" / "seedance.js").read_text(encoding="utf-8-sig")

        self.assertIn('btnGenerateSeedancePrompts', script)
        self.assertIn('seedanceRequirements', script)
        self.assertIn('generatePrompts(request)', script)
        self.assertIn('DeepSeek V4 Pro', script)
        self.assertNotIn('requirementsModal', script)
        self.assertNotIn('sceneCount', script)
        self.assertNotIn('scene_count', script)
        self.assertNotIn('fallback', script)
        self.assertNotIn('本地规则', script)

    def test_seedance_js_loading_state_is_centered_without_empty_frame(self):
        script = (ROOT / "static" / "js" / "seedance.js").read_text(encoding="utf-8-sig")

        self.assertIn("seedance-loading", script)
        self.assertNotIn('<div class="seedance-empty"><div class="spin"', script)

    def test_all_main_templates_include_seedance_nav_after_rewrite(self):
        pages = [
            "index.html",
            "rewrite.html",
            "seedance.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]
        pattern = re.compile(
            r'href="/app/rewrite"[^>]*>爆款脚本改写</a>\s*<a href="/app/seedance"[^>]*>分镜提示词生成</a>',
            re.S,
        )

        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertRegex(page, pattern, name)
            seedance_link = re.findall(r'<a href="/app/seedance" class="([^"]*)">分镜提示词生成</a>', page)
            self.assertEqual(1, len(seedance_link), name)
            if name == "seedance.html":
                self.assertIn("on", seedance_link[0], name)
            else:
                self.assertNotIn("on", seedance_link[0], name)

    def test_seedance_js_has_valid_syntax(self):
        script = ROOT / "static" / "js" / "seedance.js"

        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
