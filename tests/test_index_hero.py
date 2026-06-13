import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexHeroTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_hero_is_compact_single_paragraph_intro(self):
        self.assertIn('class="hero-copy"', self.page)
        self.assertRegex(
            self.page,
            r'<section class="hero"[^>]*>\s*<div class="hero-inner">\s*<p class="hero-copy">.*?</p>\s*</div>\s*</section>',
        )
        self.assertIn("AI 创作引擎：", self.page)
        self.assertIn("以创意与数据成就带货艺术", self.page)

    def test_hero_removes_large_visual_and_cta_elements(self):
        hero = re.search(
            r"<!-- ====== Hero Banner ====== -->(?P<body>.*?)<main class=\"page-main(?: [^\"]*)?\">",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(hero)
        body = hero.group("body")
        self.assertNotIn("hero-title", body)
        self.assertNotIn("hero-visual", body)
        self.assertNotIn("hero-img", body)
        self.assertNotIn("hero-cta", body)
        self.assertNotIn("hero-deco", body)


class IndexGenerateSeedanceTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_result_page_has_seedance_prompt_panel(self):
        self.assertIn("Seedance 2.0", self.page)
        self.assertIn('id="seedancePromptList"', self.page)
        self.assertIn('id="btnCopySeedanceAll"', self.page)
        self.assertIn("function getSeedancePrompts", self.page)
        self.assertIn("function buildSeedancePrompt", self.page)
        self.assertIn("function renderSeedancePrompts", self.page)

    def test_seedance_prompts_are_rendered_after_generation(self):
        self.assertIn("renderSeedancePrompts(currentScript)", self.page)
        self.assertIn("renderSeedancePrompts('')", self.page)
        self.assertIn("seedance-copy", self.page)
        self.assertIn("currentScript='';currentScriptId=null;renderSeedancePrompts('')", self.page)

    def test_seedance_panel_uses_rewrite_layout_pattern(self):
        self.assertIn("<main class=\"page-main generate-main\">", self.page)
        self.assertIn(".generate-main{max-width:1540px}", self.page)
        self.assertIn("grid-template-columns:minmax(480px,1fr) minmax(620px,720px)", self.page)
        self.assertIn(".generate-result-layout", self.page)
        self.assertIn(".seedance-panel", self.page)
        self.assertIn("@media (max-width: 1240px)", self.page)
        self.assertIn(".generate-result-layout { grid-template-columns: 1fr; }", self.page)
        self.assertIn(".seedance-list { grid-template-columns: 1fr; }", self.page)

    def test_result_buttons_match_rewrite_module_positions(self):
        header = re.search(
            r'<section id="step3".*?<div class="section-hd" style="justify-content:space-between">(?P<body>.*?)<div class="generate-result-layout">',
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(header)
        header_body = header.group("body")
        self.assertIn('id="btnBack"', header_body)
        self.assertNotIn('id="btnCopy"', header_body)
        self.assertNotIn('id="btnSave"', header_body)
        self.assertNotIn('id="btnRedo"', header_body)

        frame = re.search(
            r'<div class="script-output-frame">(?P<body>.*?)<div id="generatingHint"',
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(frame)
        frame_body = frame.group("body")
        self.assertRegex(
            frame_body,
            r'(?s)id="scriptOutput" class="so".*?id="resultActions" class="result-actions".*?id="btnCopy".*?id="btnSave".*?id="btnRedo"',
        )

        self.assertIn(".script-output-frame{position:relative;min-width:0}", self.page)
        self.assertIn(".generate-script-col .so{height:520px;max-height:520px;overflow:auto;padding-bottom:86px}", self.page)
        self.assertIn(".result-actions{position:absolute;left:18px;right:18px;bottom:12px;display:flex;justify-content:flex-end;gap:6px", self.page)
        self.assertIn(".result-actions { position: static; margin-top: 8px; flex-wrap: wrap; background: transparent; }", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='none'", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='flex'", self.page)

    def test_generate_can_run_without_video_type_using_template_library(self):
        self.assertIn("不选类型时自动用高成交模板库生成", self.page)
        self.assertIn("const selectedType=state.selectedType||''", self.page)
        self.assertIn("const engine=selectedType?document.getElementById('aiEngine').value:'template'", self.page)
        self.assertIn("if(selectedType)body.video_type=selectedType", self.page)
        self.assertIn("document.getElementById('btnGenerate').disabled=false", self.page)
        self.assertNotIn("document.getElementById('btnGenerate').disabled=!state.selectedType", self.page)

    def test_custom_video_type_can_be_added_and_reused(self):
        self.assertIn('id="customVideoTypeInput"', self.page)
        self.assertIn('id="btnAddCustomType"', self.page)
        self.assertIn("CUSTOM_VIDEO_TYPES_KEY", self.page)
        self.assertIn("function loadCustomVideoTypes", self.page)
        self.assertIn("function saveCustomVideoType", self.page)
        self.assertIn("function getAllVideoTypes", self.page)
        self.assertIn("function addCustomVideoType", self.page)
        self.assertIn("localStorage.getItem(CUSTOM_VIDEO_TYPES_KEY)", self.page)
        self.assertIn("localStorage.setItem(CUSTOM_VIDEO_TYPES_KEY", self.page)
        self.assertIn("getAllVideoTypes().map", self.page)
        self.assertIn("saveCustomVideoType(selectedType)", self.page)
        self.assertIn("document.getElementById('customVideoTypeInput').addEventListener('keydown'", self.page)

    def test_video_type_tags_can_be_deleted(self):
        self.assertIn("DELETED_VIDEO_TYPES_KEY", self.page)
        self.assertIn("function loadDeletedVideoTypes", self.page)
        self.assertIn("function deleteVideoType", self.page)
        self.assertIn("localStorage.getItem(DELETED_VIDEO_TYPES_KEY)", self.page)
        self.assertIn("localStorage.setItem(DELETED_VIDEO_TYPES_KEY", self.page)
        self.assertIn("deletedVideoTypes.includes(vt.v)", self.page)
        self.assertIn('class="type-delete"', self.page)
        self.assertIn("deleteVideoType(event,\\''+vt.v+'\\')", self.page)
        self.assertIn(".type-tag{position:relative", self.page)
        self.assertIn(".type-delete{position:absolute;top:-6px;right:-6px", self.page)
        self.assertIn("background:rgba(217,45,32,.78);color:#fff", self.page)
        self.assertIn("opacity:0;pointer-events:none", self.page)
        self.assertIn(".type-tag:hover .type-delete,.type-tag:focus-within .type-delete", self.page)
        self.assertIn("opacity:.82;pointer-events:auto", self.page)
        self.assertIn(".type-delete::before{content:\"\";width:8px;height:2px;background:#fff", self.page)
        self.assertIn("if(!window.confirm(", self.page)


if __name__ == "__main__":
    unittest.main()
