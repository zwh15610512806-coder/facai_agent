import asyncio
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from schemas import ScriptRewriteRequest
from services.script_rewriter import ScriptRewriter


ROOT = Path(__file__).resolve().parents[1]


class RewriteFailingAI:
    async def chat(self, *args, **kwargs):
        raise RuntimeError("provider unavailable")


class RewriteEmptyAI:
    async def chat(self, *args, **kwargs):
        return ""


class RewritePageTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "rewrite.html").read_text(encoding="utf-8-sig")

    def test_product_picker_hides_after_target_product_is_selected(self):
        self.assertIn('id="productPicker"', self.page)
        select_product = re.search(
            r"function selectProduct\(id\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(select_product)
        body = select_product.group("body")
        self.assertIn("productPicker", body)
        self.assertIn(".style.display='none'", body)
        self.assertIn("btnRewrite", body)

    def test_target_product_can_be_reselected_after_selection(self):
        self.assertIn('id="selectedProductText"', self.page)
        self.assertIn('id="btnReselectProduct"', self.page)
        self.assertIn("hint.style.display='flex'", self.page)
        self.assertIn("document.getElementById('selectedProductText').textContent='目标产品：'", self.page)
        self.assertIn("function reselectProduct()", self.page)
        self.assertIn("document.getElementById('productPicker').style.display=''", self.page)
        self.assertIn("renderProducts(document.getElementById('productSearch').value)", self.page)
        self.assertIn("btnReselectProduct').addEventListener('click',reselectProduct)", self.page)

    def test_selected_product_and_preview_use_plain_text_symbols(self):
        self.assertNotIn("+ '&yen;'", self.page)
        self.assertNotIn("+ '&hellip;'", self.page)
        self.assertIn("| ¥", self.page)
        self.assertIn("selectedProduct.price", self.page)
        self.assertIn("+'...'", self.page)

    def test_product_cards_escape_api_fields_before_innerhtml(self):
        match = re.search(
            r"function renderProducts\(filter\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("jsStringLiteral(p.selling_point_summary||'暂无卖点')", body)
        self.assertIn("escHtml(productCategoryLabel(p))", body)
        self.assertIn("escHtml(p.name)", body)
        self.assertIn("escHtml(productPriceLabel(p))", body)
        self.assertIn("Number(p.selling_point_count||0)", body)
        self.assertNotIn("'+p.name+'", body)
        self.assertNotIn("'+productCategoryLabel(p)+'", body)

    def test_product_tooltip_escapes_summary_parts_before_innerhtml(self):
        match = re.search(
            r"function showTip\(e,summary\)\{(?P<body>.*?)function hideTip",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("escHtml(m[1])", body)
        self.assertIn("escHtml(m[2])", body)
        self.assertIn("escHtml(s)", body)
        self.assertNotIn("'+m[1]+'", body)
        self.assertNotIn("'+m[2]+'", body)

    def test_rewrite_page_promises_material_script_format(self):
        self.assertIn("保留参考结构并输出为资料脚本格式", self.page)
        self.assertIn("画面括号 + 口播文案", self.page)
        self.assertIn("已保留参考结构并按资料脚本格式输出", self.page)
        self.assertNotIn("已保留原脚本结构", self.page)

    def test_rewrite_page_has_demand_prefill(self):
        self.assertIn("需求预填写", self.page)
        self.assertIn("id=\"rewriteReqPreFill\"", self.page)
        self.assertIn("填写你对改写脚本的限制、方向、活动卖点或语气要求", self.page)
        self.assertIn("document.getElementById('rewriteReqPreFill').value.trim()", self.page)
        self.assertIn("reqs.push('用户需求：'+preFill)", self.page)

    def test_rewrite_page_has_optional_shot_design_toggle(self):
        self.assertIn("需要设计画面", self.page)
        self.assertIn('id="includeShotDesign" type="checkbox" checked', self.page)
        self.assertIn("取消勾选后只输出一段口播文案", self.page)
        self.assertIn("var includeShotDesign=document.getElementById('includeShotDesign').checked", self.page)
        self.assertIn("include_shot_design:includeShotDesign", self.page)

    def test_rewrite_request_defaults_to_existing_shot_design_format(self):
        request = ScriptRewriteRequest(original_script="老板们看过来", product_id=1)

        self.assertTrue(request.include_shot_design)

    def test_rewriter_extracts_timestamped_reference_structure(self):
        original = """00:00 头些年我还是当记者的时候
00:01 我们采访老师就是说明黄水无所谓
00:04 但是社交距离内口气一定要清新
"""
        structure = ScriptRewriter()._build_reference_structure(original)
        self.assertIn("1. [00:00] 头些年我还是当记者的时候", structure)
        self.assertIn("2. [00:01] 我们采访老师就是说明黄水无所谓", structure)
        self.assertIn("3. [00:04] 但是社交距离内口气一定要清新", structure)

    def test_rewriter_uses_user_supplied_ai_rewrite_prompt(self):
        prompt = ScriptRewriter.SYSTEM_PROMPT

        self.assertIn("# 角色", prompt)
        self.assertIn("专业的带货文案结构分析师与改写专家", prompt)
        self.assertIn("精准分析原文案结构", prompt)
        self.assertIn("深度理解产品核心信息", prompt)
        self.assertIn("结构化改写并保持一致性", prompt)
        self.assertIn("严格禁止改变原文案的核心结构", prompt)
        self.assertIn("只专注于文案改写任务", prompt)
        self.assertIn("输出1条文案，500字以内", prompt)
        self.assertIn("结构分析只在内部完成，不输出结构分析", prompt)

    def test_rewriter_cleanup_converts_sectioned_output_to_material_style(self):
        text = """改写后的脚本：
【0-3s 开场钩子】
老板们别再乱买了！

【产品卖点展示】
看一下法采这款产品，颜色稳定还好用。

【CTA】
需要的点下方链接。
"""
        cleaned = ScriptRewriter()._cleanup_rewrite_output(text)
        self.assertIn("（主播半身站在烘焙台前开场，手边摆放产品包装）老板们别再乱买了！", cleaned)
        self.assertIn("（产品包装正面近景，手拿转动展示规格）看一下法采这款产品", cleaned)
        self.assertIn("（主播手指下方小黄车，引导查看详情）需要的点下方链接。", cleaned)
        self.assertNotIn("（口播画面）", cleaned)
        self.assertNotIn("（产品空镜）", cleaned)
        self.assertNotIn("【0-3s 开场钩子】", cleaned)
        self.assertNotIn("改写后的脚本", cleaned)

    def test_rewriter_enriches_generic_scene_labels(self):
        cleaned = ScriptRewriter()._cleanup_rewrite_output(
            "（口播画面）老板们看过来。（产品空镜）看一下这款奶冻粉。（操作演示）加水搅拌。"
        )

        self.assertNotIn("（口播画面）", cleaned)
        self.assertNotIn("（产品空镜）", cleaned)
        self.assertIn("（主播半身站在烘焙台前开场，手边摆放产品包装）", cleaned)
        self.assertIn("（产品包装正面近景，手拿转动展示规格）", cleaned)
        self.assertIn("（俯拍操作台，手部演示使用步骤和状态变化）", cleaned)

    def test_offline_rewrite_uses_detailed_scene_labels(self):
        output = ScriptRewriter()._offline_material_rewrite(
            "奶冻粉",
            "烘焙夹心",
            12.71,
            [{"content": "凝固稳定，不容易出水"}],
            original_script="00:00 老板们看过来\n00:01 看一下这个产品\n00:02 加水搅拌",
        )

        self.assertNotIn("（口播画面）", output)
        self.assertNotIn("（产品空镜）", output)
        self.assertIn("主播半身站在烘焙台前开场", output)
        self.assertIn("奶冻粉包装正面近景", output)
        self.assertIn("俯拍操作台", output)

    def test_rewriter_raises_clear_error_when_ai_call_fails_instead_of_offline_rewrite(self):
        rewriter = ScriptRewriter()
        rewriter.ai = RewriteFailingAI()

        with self.assertRaisesRegex(RuntimeError, "脚本改写失败"):
            asyncio.run(rewriter.rewrite(
                original_script="老板们看过来，这款材料很适合门店用。",
                target_product={
                    "name": "奶冻粉",
                    "category": "烘焙夹心",
                    "price": 12.71,
                    "selling_points": [{"type": "稳定性", "content": "凝固稳定，不容易出水"}],
                },
            ))

    def test_rewriter_raises_clear_error_when_ai_returns_empty_instead_of_offline_rewrite(self):
        rewriter = ScriptRewriter()
        rewriter.ai = RewriteEmptyAI()

        with self.assertRaisesRegex(RuntimeError, "模型未返回有效改写脚本"):
            asyncio.run(rewriter.rewrite(
                original_script="老板们看过来，这款材料很适合门店用。",
                target_product={
                    "name": "奶冻粉",
                    "category": "烘焙夹心",
                    "price": 12.71,
                    "selling_points": [{"type": "稳定性", "content": "凝固稳定，不容易出水"}],
                },
            ))

    def test_rewriter_plain_cleanup_removes_shot_design(self):
        cleaned = ScriptRewriter()._cleanup_plain_rewrite_output(
            "【开场钩子】\n00:00 （主播半身站在烘焙台前开场，手边摆放产品包装）老板们看过来。\n"
            "00:02 （产品包装正面近景，手拿转动展示规格）这款奶冻粉很适合门店用。"
        )

        self.assertNotIn("【开场钩子】", cleaned)
        self.assertNotIn("00:00", cleaned)
        self.assertNotIn("主播半身", cleaned)
        self.assertNotIn("产品包装正面近景", cleaned)
        self.assertNotIn("\n", cleaned)
        self.assertIn("老板们看过来", cleaned)
        self.assertIn("这款奶冻粉很适合门店用", cleaned)

    def test_rewrite_copy_button_has_fallback_and_error_feedback(self):
        self.assertIn("function fallbackCopyText", self.page)
        self.assertIn("function copyText", self.page)
        self.assertIn("copyText(t).then", self.page)
        self.assertIn("已成功复制到剪贴板", self.page)
        self.assertIn("复制失败，请手动选中文案复制", self.page)

    def test_result_actions_include_back_before_copy(self):
        top_back = re.search(
            r'id="resultMeta".*?id="btnBackToStep2FromResult"',
            self.page,
            flags=re.S,
        )
        bottom_actions = re.search(
            r'id="resultActions" class="result-actions".*?id="btnCopy".*?id="btnRedo".*?id="btnToggleCompare"',
            self.page,
            flags=re.S,
        )
        script_actions = re.search(
            r'id="scriptOutput" class="so editable-output".*?id="resultActions" class="result-actions"',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(top_back)
        self.assertIsNotNone(bottom_actions)
        self.assertIsNotNone(script_actions)
        self.assertIn("btnBackToStep2FromResult", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='none'", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='flex'", self.page)

    def test_rewrite_output_is_editable(self):
        self.assertIn('id="scriptOutput" class="so editable-output" contenteditable="true"', self.page)
        self.assertIn('role="textbox" aria-multiline="true"', self.page)
        self.assertIn("function getEditedScript()", self.page)
        self.assertIn("document.getElementById('scriptOutput').addEventListener('input'", self.page)
        self.assertIn("document.getElementById('compareRewritten').textContent=currentRewritten", self.page)
        self.assertIn("var t=getEditedScript()", self.page)

    def test_rewrite_result_meta_escapes_api_product_name_before_innerhtml(self):
        match = re.search(
            r"async function submitRewrite\(extraOverride\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("escHtml(d.product_name)", body)
        self.assertNotIn("'<b>'+d.product_name+'</b>", body)

    def test_redo_directly_submits_rewrite_without_returning_to_step2(self):
        self.assertIn("async function submitRewrite", self.page)
        self.assertIn("submitRewrite('请在保留参考文案结构的前提下，直接生成一个不同于上一版的新版本", self.page)
        self.assertNotIn("document.getElementById('extraReq').value='请生成一个不同于上一版的版本'", self.page)

    def test_result_back_button_returns_to_previous_step(self):
        handler = re.search(
            r"btnBackToStep2FromResult'\)\.addEventListener\('click',function\(\)\{(?P<body>.*?)\}\);",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(handler)
        body = handler.group("body")
        self.assertIn("step2", body)
        self.assertIn(".style.display=''", body)
        self.assertIn("step3", body)
        self.assertIn(".style.display='none'", body)

    def test_result_page_has_seedance_prompt_panel(self):
        self.assertIn("Seedance 2.0", self.page)
        self.assertIn("id=\"seedancePromptList\"", self.page)
        self.assertIn("id=\"btnCopySeedanceAll\"", self.page)
        self.assertIn("id=\"btnGenerateSeedance\"", self.page)
        self.assertIn("function getSeedancePrompts", self.page)
        self.assertIn("function buildSeedancePrompt", self.page)
        self.assertIn("function renderSeedancePrompts", self.page)

    def test_seedance_prompts_are_generated_manually_from_edited_script(self):
        self.assertNotIn("renderSeedancePrompts(currentRewritten)", self.page)
        self.assertIn("resetSeedancePrompts('可先直接编辑左侧改写脚本", self.page)
        self.assertIn("btnGenerateSeedance').addEventListener('click'", self.page)
        self.assertIn("var script=getEditedScript()", self.page)
        self.assertIn("renderSeedancePrompts(script)", self.page)
        self.assertIn("currentSeedancePrompts", self.page)
        self.assertIn("请先点击生成提示词", self.page)
        self.assertIn("seedance-copy", self.page)
        self.assertIn("竖屏9:16，真实商业烘焙短视频", self.page)

    def test_seedance_plain_rewrite_copy_splits_into_sentence_cards(self):
        start = self.page.index("function splitSeedancePlainBeats(text){")
        end = self.page.index("function renderSeedancePrompts(script){")
        functions = self.page[start:end]
        script = f"""
var selectedProduct={{name:'糖珠',category:'烘焙装饰'}};
{functions}
const prompts=getSeedancePrompts('第一句讲痛点，第二句讲包装证明，第三句讲使用场景，第四句引导下单。');
if(prompts.length<4) throw new Error('expected at least 4 cards, got '+prompts.length);
if(!prompts[1].prompt.includes('第二句讲包装证明')) throw new Error('second card should keep second sentence');
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

    def test_seedance_panel_is_on_right_desktop_and_stacks_mobile(self):
        self.assertIn("<main class=\"page-main rewrite-main\">", self.page)
        self.assertIn(".rewrite-main{max-width:1540px}", self.page)
        self.assertIn("grid-template-columns:minmax(480px,1fr) minmax(620px,720px)", self.page)
        self.assertIn("align-items:stretch", self.page)
        self.assertIn(".rewrite-result-hd{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr)", self.page)
        self.assertIn(".editable-output{cursor:text}", self.page)
        self.assertIn(".script-output-frame{position:relative;min-width:0}", self.page)
        self.assertIn(".rewrite-script-col .so{height:520px;max-height:520px;overflow:auto;padding-bottom:86px}", self.page)
        self.assertIn(".result-actions{position:absolute;left:18px;right:18px;bottom:12px;display:flex;justify-content:flex-end;gap:6px", self.page)
        self.assertIn(".seedance-panel{border:1px solid var(--border);border-radius:var(--r);background:var(--surface-darker);padding:0;height:520px;max-height:520px;overflow:auto}", self.page)
        self.assertIn(".seedance-hd{position:sticky;top:0;z-index:3", self.page)
        self.assertIn("margin:0 0 12px;padding:14px 14px 10px", self.page)
        self.assertIn(".seedance-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:0 14px 14px}", self.page)
        self.assertNotIn("margin:-14px -14px", self.page)
        self.assertIn(".seedance-card{border:1px solid var(--border-soft);border-radius:var(--r-sm);background:#fff;padding:10px 12px;min-height:0;overflow:visible}", self.page)
        self.assertNotIn("height:205px;overflow:auto", self.page)
        self.assertIn("@media (max-width: 1240px)", self.page)
        self.assertIn(".rewrite-result-layout { grid-template-columns: 1fr; }", self.page)
        self.assertIn(".seedance-list { grid-template-columns: 1fr; }", self.page)
        self.assertIn(".seedance-card { max-height: none; overflow: visible; }", self.page)


if __name__ == "__main__":
    unittest.main()
