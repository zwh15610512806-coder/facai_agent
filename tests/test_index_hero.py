import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexHeroTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_generate_page_does_not_render_intro_hero_banner(self):
        self.assertNotIn("<!-- ====== Hero Banner ====== -->", self.page)
        self.assertNotIn('class="hero"', self.page)
        self.assertNotIn('class="hero-copy"', self.page)
        self.assertNotIn(".hero ", self.page)
        self.assertNotIn(".hero-copy", self.page)

    def test_generate_page_content_starts_without_intro_banner(self):
        self.assertRegex(
            self.page,
            r'</nav>\s*<a class="data-import-fab" href="/app/import"[^>]*>.*?</a>\s*<a class="ai-config-fab" href="/app/ai-config"[^>]*>.*?</a>\s*<style>\s*\.generate-main',
        )
        self.assertNotRegex(
            self.page,
            r"</nav>\s*<!-- ====== Hero Banner ====== -->",
        )


class IndexGenerateSeedanceTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_result_page_has_seedance_prompt_panel(self):
        self.assertIn("Seedance 2.0", self.page)
        self.assertIn('id="seedancePromptList"', self.page)
        self.assertIn('id="btnCopySeedanceAll"', self.page)
        self.assertIn('id="btnGenerateSeedance"', self.page)
        self.assertIn("function getSeedancePrompts", self.page)
        self.assertIn("function buildSeedancePrompt", self.page)
        self.assertIn("function renderSeedancePrompts", self.page)

    def test_seedance_prompts_are_generated_manually_from_edited_script(self):
        self.assertNotIn("renderSeedancePrompts(currentScript)", self.page)
        self.assertIn("btnGenerateSeedance').addEventListener('click'", self.page)
        self.assertIn("var script=getEditedScript()", self.page)
        self.assertIn("renderSeedancePrompts(script)", self.page)
        self.assertIn("currentSeedancePrompts", self.page)
        self.assertIn("请先点击生成提示词", self.page)
        self.assertIn("seedance-copy", self.page)
        self.assertIn("resetSeedancePrompts('可先直接编辑左侧生成脚本", self.page)

    def test_seedance_cards_label_uses_spoken_copy_not_camera_note(self):
        self.assertIn("function getSeedanceCardLabel", self.page)
        self.assertIn("getSeedanceCardLabel(item)", self.page)
        self.assertIn("画面'+(i+1)+' · '+escHtml(getSeedanceCardLabel(item))", self.page)
        self.assertIn("return (item.line||item.scene||'口播画面').slice(0,54)", self.page)
        self.assertIn("'画面'+(i+1)+'：'+getSeedanceCardLabel(x)", self.page)
        self.assertNotIn("画面'+(i+1)+' · '+escHtml(item.scene)", self.page)
        self.assertNotIn("'画面'+(i+1)+'：'+x.scene", self.page)

    def test_seedance_plain_spoken_copy_splits_into_sentence_cards(self):
        start = self.page.index("function splitSeedancePlainBeats(text){")
        end = self.page.index("function renderSeedancePrompts(script){")
        functions = self.page[start:end]
        script = f"""
var state={{selectedProduct:{{name:'白色翻糖膏',category:'烘焙装饰'}}}};
{functions}
const prompts=getSeedancePrompts('开头一句抓痛点，第二句给产品证明，第三句讲使用场景，第四句自然引导下单。');
if(prompts.length<4) throw new Error('expected at least 4 cards, got '+prompts.length);
if(!prompts[0].prompt.includes('开头一句抓痛点')) throw new Error('first card should keep first sentence');
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            script_path = Path(handle.name)

        try:
            result = subprocess.run(
                ["node", str(script_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        finally:
            script_path.unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_seedance_panel_uses_rewrite_layout_pattern(self):
        self.assertIn("<main class=\"page-main generate-main\">", self.page)
        self.assertIn(".generate-main{max-width:1540px}", self.page)
        self.assertIn("grid-template-columns:minmax(480px,1fr) minmax(620px,720px)", self.page)
        self.assertIn(".generate-result-hd{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr)", self.page)
        self.assertIn(".editable-output{cursor:text}", self.page)
        self.assertIn(".generate-result-layout", self.page)
        self.assertIn(".seedance-panel", self.page)
        self.assertIn("@media (max-width: 1240px)", self.page)
        self.assertIn(".generate-result-layout { grid-template-columns: 1fr; }", self.page)
        self.assertIn(".seedance-list { grid-template-columns: 1fr; }", self.page)

    def test_result_buttons_match_rewrite_module_positions(self):
        header = re.search(
            r'<section id="step3".*?<div class="section-hd generate-result-hd">(?P<body>.*?)<div class="generate-result-layout">',
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(header)
        header_body = header.group("body")
        self.assertIn('id="btnBack"', header_body)
        self.assertIn('id="btnGenerateSeedance"', header_body)
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
            r'(?s)id="scriptOutput" class="so editable-output".*?id="resultActions" class="result-actions".*?id="btnMatchShots".*?id="btnCopy".*?id="btnSave".*?id="btnRedo"',
        )

        self.assertIn('id="scriptOutput" class="so editable-output" contenteditable="true"', self.page)
        self.assertIn("function getEditedScript()", self.page)
        self.assertIn("document.getElementById('scriptOutput').addEventListener('input'", self.page)
        self.assertIn(".script-output-frame{position:relative;min-width:0;border-radius:var(--r);overflow:hidden}", self.page)
        self.assertIn(".generate-script-col .so{height:520px;max-height:520px;overflow:auto;padding-bottom:86px}", self.page)
        self.assertIn(".result-actions{position:absolute;left:0;right:0;bottom:0;display:flex;justify-content:flex-end;gap:6px", self.page)
        self.assertIn("padding:10px 18px 12px", self.page)
        self.assertIn(".result-actions { position: static; margin-top: 8px; flex-wrap: wrap; background: transparent; }", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='none'", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='flex'", self.page)

    def test_result_actions_can_match_shots_to_existing_copy(self):
        self.assertIn('id="btnMatchShots"', self.page)
        self.assertIn("为文案匹配画面", self.page)
        self.assertIn("async function matchShotsForScript()", self.page)
        self.assertIn("fetch('/api/scripts/match-shots'", self.page)
        self.assertIn("script_content:script", self.page)
        self.assertIn("script_id:currentScriptId", self.page)
        self.assertIn("currentScript=d.script_content;document.getElementById('scriptOutput').textContent=currentScript", self.page)
        self.assertIn("document.getElementById('btnMatchShots').addEventListener('click',matchShotsForScript)", self.page)

    def test_result_action_bar_masks_scrolled_script_content(self):
        match = re.search(r"\.result-actions\{(?P<body>.*?)\}", self.page, flags=re.S)

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("background:var(--surface-darker)", body)
        self.assertNotIn("rgba(245,243,240,0)", body)
        self.assertNotIn("linear-gradient(to bottom,rgba", body)

    def test_generate_without_video_type_respects_selected_engine(self):
        self.assertIn("AI生成未选类型会由 AI 自动推断", self.page)
        self.assertIn("模板库改写未选类型会自动用高成交模板库", self.page)
        self.assertNotIn("不选类型时自动用高成交模板库生成", self.page)
        self.assertIn("const selectedType=state.selectedType||''", self.page)
        self.assertIn("const engine=document.getElementById('aiEngine').value", self.page)
        self.assertNotIn("const engine=selectedType?document.getElementById('aiEngine').value:'template'", self.page)
        self.assertIn("if(selectedType)body.video_type=selectedType", self.page)
        self.assertIn("document.getElementById('btnGenerate').disabled=false", self.page)
        self.assertNotIn("document.getElementById('btnGenerate').disabled=!state.selectedType", self.page)

    def test_generate_page_has_optional_shot_design_toggle(self):
        engine_block = re.search(
            r'<select id="aiEngine".*?</select>(?P<body>.*?)<p style="font-size:12px;color:var\(--text-3\);margin-top:6px" id="engineHint">',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(engine_block)
        body = engine_block.group("body")
        self.assertIn('id="includeShotDesign"', body)
        self.assertIn('type="checkbox"', body)
        self.assertNotIn("checked", body)
        self.assertIn("需要设计画面", body)
        self.assertIn("未勾选只生成一段口播文案", self.page)
        self.assertIn("勾选会按每句话生成镜头说明", self.page)
        self.assertIn("include_shot_design:document.getElementById('includeShotDesign').checked", self.page)

    def test_deepseek_engine_is_displayed_as_generic_ai_generation(self):
        self.assertIn('<option value="deepseek">AI生成</option>', self.page)
        self.assertIn("AI生成：使用已配置模型和 API Key", self.page)
        self.assertNotIn("DeepSeek AI", self.page)

    def test_redo_requests_a_distinct_ai_regeneration(self):
        self.assertIn("function buildRegenerateRequirement()", self.page)
        self.assertIn("上一版脚本开头摘要：", self.page)
        self.assertIn("必须更换开头角度、第一句话句式、卖点顺序和 CTA", self.page)
        self.assertIn("const regenRequirement=buildRegenerateRequirement()", self.page)
        self.assertIn("doGenerate(regenRequirement)", self.page)
        self.assertNotIn("btnRedo').addEventListener('click',function(){state.step=2;document.getElementById('step1').style.display='none';document.getElementById('step2').style.display='none';document.getElementById('step3').style.display='none';currentScript='';currentScriptId=null;resetSeedancePrompts();doGenerate(null);}", self.page)

    def test_selected_product_bar_can_change_product_directly(self):
        selected_bar = re.search(
            r'<div class="step2-selected-box">(?P<body>.*?)</div>',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(selected_bar)
        body = selected_bar.group("body")
        self.assertIn('id="selectedProductLabel"', body)
        self.assertIn('id="btnChangeProduct"', body)
        self.assertIn('更换产品', body)
        self.assertIn('class="btn btn-soft btn-sm step2-change-product"', body)
        self.assertIn("function showProductSelection()", self.page)
        self.assertIn("document.getElementById('btnBackToStep1').addEventListener('click',showProductSelection)", self.page)
        self.assertIn("document.getElementById('btnChangeProduct').addEventListener('click',showProductSelection)", self.page)

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

    def test_generate_page_has_product_style_scroll_top_button(self):
        self.assertIn('id="scrollTopBtn"', self.page)
        self.assertIn('class="scroll-top-btn"', self.page)
        self.assertIn('aria-label="回到顶部"', self.page)
        self.assertIn('data-lucide="arrow-up"', self.page)
        self.assertIn(".scroll-top-btn{position:fixed;right:24px;bottom:96px", self.page)
        self.assertIn(".scroll-top-btn.show{opacity:1;pointer-events:auto;transform:translateY(0)}", self.page)
        self.assertIn("function scrollGenerateToTop(){window.scrollTo({top:0,behavior:'smooth'});}", self.page)
        self.assertIn("function toggleScrollTopButton(){const btn=document.getElementById('scrollTopBtn')", self.page)
        self.assertIn("window.addEventListener('scroll',toggleScrollTopButton,{passive:true});", self.page)
        self.assertIn("toggleScrollTopButton();", self.page)

    def test_product_tooltip_escapes_summary_parts_before_innerhtml(self):
        match = re.search(
            r"function showTip\(e,summary\)\{(?P<body>.*?)function hideTip",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("esc(m[1])", body)
        self.assertIn("esc(m[2])", body)
        self.assertIn("esc(s)", body)
        self.assertNotIn("'+m[1]+'", body)
        self.assertNotIn("'+m[2]+'", body)


if __name__ == "__main__":
    unittest.main()
