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
        self.assertRegex(self.page, r'/static/js/common\.js\?v=app-shell-[^"\']+')
        self.assertNotIn('class="nav-import-btn"', self.page)
        self.assertNotIn('class="data-import-fab"', self.page)
        self.assertNotIn('class="ai-config-fab"', self.page)
        self.assertRegex(
            self.page,
            r'</nav>\s*<style>\s*\.generate-main',
        )
        self.assertNotRegex(
            self.page,
            r"</nav>\s*<!-- ====== Hero Banner ====== -->",
        )


class IndexGenerateBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_result_page_has_content_breakdown_panel(self):
        self.assertIn("内容拆解", self.page)
        self.assertIn('id="contentBreakdownList"', self.page)
        self.assertIn('id="btnRefreshBreakdown"', self.page)
        self.assertIn('id="btnCopyBreakdown"', self.page)
        self.assertNotIn("Seedance 2.0", self.page)
        self.assertNotIn('id="seedancePromptList"', self.page)
        self.assertNotIn('id="btnGenerateSeedance"', self.page)
        self.assertNotIn("function getSeedancePrompts", self.page)

    def test_breakdown_is_automatic_nonblocking_and_refreshes_edited_script(self):
        self.assertIn("async function loadContentBreakdown", self.page)
        self.assertIn("loadContentBreakdown(currentScriptId,currentScript)", self.page)
        self.assertIn("/api/scripts/content-breakdown", self.page)
        self.assertIn("脚本已修改，拆解待更新", self.page)
        self.assertIn("btnRefreshBreakdown').addEventListener('click'", self.page)
        self.assertIn("var script=getEditedScript()", self.page)
        self.assertIn("renderContentBreakdown", self.page)
        self.assertIn("左侧脚本不受影响", self.page)
        self.assertIn("已根据当前脚本和产品资料完成可靠拆解", self.page)

    def test_generate_workspace_uses_versioned_session_storage(self):
        self.assertIn("const GENERATE_WORKSPACE_KEY='facai.generate.workspace.v1'", self.page)
        self.assertIn("const GENERATE_WORKSPACE_VERSION=1", self.page)
        self.assertIn("sessionStorage.setItem(GENERATE_WORKSPACE_KEY", self.page)
        self.assertIn("sessionStorage.getItem(GENERATE_WORKSPACE_KEY)", self.page)
        self.assertIn("sessionStorage.removeItem(GENERATE_WORKSPACE_KEY)", self.page)
        self.assertNotIn("localStorage.setItem(GENERATE_WORKSPACE_KEY", self.page)
        self.assertIn("window.addEventListener('pagehide',writeGenerateWorkspaceNow)", self.page)

    def test_generate_workspace_captures_complete_editing_state(self):
        self.assertIn("function buildGenerateWorkspaceSnapshot()", self.page)
        for field in (
            "selection:",
            "settings:",
            "script_content:getEditedScript()||currentScript||''",
            "template_reference:currentTemplateReference",
            "breakdown:currentBreakdown",
            "breakdown_stale:",
            "optimize_input:",
            "active_job_id:activeGenerationJobId",
            "script_top:",
            "breakdown_top:",
        ):
            self.assertIn(field, self.page)

    def test_generate_workspace_restores_after_data_load_and_job_query_wins(self):
        bootstrap = re.search(
            r"async function bootstrapGeneratePage\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(bootstrap)
        body = bootstrap.group("body")
        self.assertLess(body.index("await Promise.all([loadCategories(),loadProducts()])"), body.index("restoreGenerateWorkspace(saved)"))
        self.assertLess(body.index("const backgroundJobId="), body.index("if(backgroundJobId)await restoreGeneratedJob(backgroundJobId)"))
        self.assertIn("else if(savedJobId)await restoreGeneratedJob(savedJobId)", body)

    def test_generate_workspace_keeps_text_when_history_record_is_missing(self):
        self.assertIn("async function validateRestoredScriptContext()", self.page)
        self.assertIn("if(response.status===404)", self.page)
        self.assertIn("currentScriptId=null", self.page)
        self.assertIn("原生成记录已不存在，已保留当前脚本文字", self.page)
        self.assertIn("document.getElementById('btnSave').disabled=!validRecord", self.page)

    def test_breakdown_panel_uses_rewrite_layout_pattern(self):
        self.assertIn("<main class=\"page-main generate-main\">", self.page)
        self.assertIn(".generate-main{max-width:1540px}", self.page)
        self.assertIn("grid-template-columns:minmax(480px,1fr) minmax(620px,720px)", self.page)
        self.assertIn(".generate-result-hd{display:flex;align-items:center;justify-content:space-between", self.page)
        self.assertIn(".editable-output{cursor:text}", self.page)
        self.assertIn(".generate-result-layout", self.page)
        self.assertIn(".breakdown-panel", self.page)
        self.assertIn("@media (max-width: 1240px)", self.page)
        self.assertIn(".generate-result-layout { grid-template-columns: 1fr; }", self.page)
        self.assertIn(".breakdown-list { grid-template-columns: 1fr; }", self.page)

    def test_result_buttons_match_rewrite_module_positions(self):
        header = re.search(
            r'<section id="step3".*?<div class="section-hd generate-result-hd">(?P<body>.*?)<div class="generate-result-layout">',
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(header)
        header_body = header.group("body")
        self.assertIn('id="btnBack"', header_body)
        self.assertNotIn('id="btnGenerateSeedance"', header_body)
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
            r'(?s)id="scriptOutput" class="so editable-output".*?id="resultActions" class="result-actions".*?id="btnCopy".*?id="btnSave".*?id="btnRedo"',
        )
        self.assertNotIn('id="btnGenerateSeedance"', frame_body)

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

    def test_result_actions_do_not_offer_match_shots_button(self):
        self.assertNotIn('id="btnMatchShots"', self.page)
        self.assertNotIn("为文案匹配画面", self.page)
        self.assertNotIn("async function matchShotsForScript()", self.page)
        self.assertNotIn("fetch('/api/scripts/match-shots'", self.page)
        self.assertNotIn("document.getElementById('btnMatchShots').addEventListener", self.page)

    def test_result_action_bar_masks_scrolled_script_content(self):
        match = re.search(r"\.result-actions\{(?P<body>.*?)\}", self.page, flags=re.S)

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("background:var(--surface-darker)", body)
        self.assertNotIn("rgba(245,243,240,0)", body)
        self.assertNotIn("linear-gradient(to bottom,rgba", body)

    def test_generate_without_video_type_respects_selected_engine(self):
        self.assertIn("AI生成未选类型会由 AI 自动推断", self.page)
        self.assertIn("模板库改写未选类型会从脚本模板库选择模板", self.page)
        self.assertNotIn("模板库改写未选类型会自动用高成交模板库", self.page)
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
        self.assertIn("AI生成：结合产品资料、跑量逻辑，并在已选类型时参考同类型脚本结构创作", self.page)
        self.assertIn("模板库改写：从脚本模板库按同类型优先选择模板，改写为当前产品脚本", self.page)
        self.assertNotIn("DeepSeek AI", self.page)

    def test_generation_result_displays_referenced_script_when_available(self):
        self.assertIn("d.source_script_title", self.page)
        self.assertIn("d.source_script_content", self.page)
        self.assertIn("d.source_script_source", self.page)
        self.assertIn("d.template_name", self.page)
        self.assertIn('id="templateReferencePanel"', self.page)
        self.assertIn('id="templateReferenceName"', self.page)
        self.assertIn('id="templateReferenceSource"', self.page)
        self.assertIn('id="templateReferenceStructure"', self.page)
        self.assertIn("引用脚本名称", self.page)
        self.assertIn('id="templateReferenceDetails"', self.page)
        self.assertIn('id="templateReferenceScript"', self.page)
        self.assertIn("document.getElementById('templateReferenceName').textContent=currentTemplateReference.source_title", self.page)
        self.assertIn("结构模板：", self.page)
        self.assertIn("该参考脚本暂无正文。", self.page)
        self.assertIn("resetTemplateReference", self.page)
        self.assertNotIn("var templateInfo=d.template_name", self.page)

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
        self.assertIn(".scroll-top-btn{position:fixed;right:24px;bottom:148px", self.page)
        self.assertIn(".scroll-top-btn.show{opacity:1;pointer-events:auto;transform:translateY(0)}", self.page)
        self.assertIn("function scrollGenerateToTop(){window.scrollTo({top:0,behavior:'smooth'});}", self.page)
        self.assertIn("function toggleScrollTopButton(){const btn=document.getElementById('scrollTopBtn')", self.page)
        self.assertIn("window.addEventListener('scroll',function(){toggleScrollTopButton();scheduleGenerateWorkspaceSave();},{passive:true});", self.page)
        self.assertIn("toggleScrollTopButton();", self.page)

    def test_product_cards_escape_api_fields_before_innerhtml(self):
        match = re.search(
            r"function renderProducts\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("jsStringLiteral(p.selling_point_summary||'暂无卖点')", body)
        self.assertIn("escHtml(p.category)", body)
        self.assertIn("escHtml(p.name)", body)
        self.assertIn("Number(p.selling_point_count||0)", body)
        self.assertNotIn("'+esc(p.selling_point_summary||'暂无卖点')+'", body)

    def test_generate_result_meta_escapes_api_fields_before_innerhtml(self):
        match = re.search(
            r"function setResultMeta\(productName,videoType,note\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("escHtml(currentResultInfo.product_name)", body)
        self.assertIn("escHtml(currentResultInfo.video_type)", body)
        self.assertIn("escHtml(currentResultInfo.note)", body)
        self.assertNotIn("'<b>'+d.product_name+'</b>", body)

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
