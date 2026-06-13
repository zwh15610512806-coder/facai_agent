import re
import unittest
from pathlib import Path

from services.script_rewriter import ScriptRewriter


ROOT = Path(__file__).resolve().parents[1]


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

    def test_selected_product_and_preview_use_plain_text_symbols(self):
        self.assertNotIn("+ '&yen;'", self.page)
        self.assertNotIn("+ '&hellip;'", self.page)
        self.assertIn("| ¥", self.page)
        self.assertIn("selectedProduct.price", self.page)
        self.assertIn("+'...'", self.page)

    def test_rewrite_page_promises_material_script_format(self):
        self.assertIn("保留参考结构并输出为资料脚本格式", self.page)
        self.assertIn("画面括号 + 口播文案", self.page)
        self.assertIn("已保留参考结构并按资料脚本格式输出", self.page)
        self.assertNotIn("已保留原脚本结构", self.page)

    def test_rewriter_extracts_timestamped_reference_structure(self):
        original = """00:00 头些年我还是当记者的时候
00:01 我们采访老师就是说明黄水无所谓
00:04 但是社交距离内口气一定要清新
"""
        structure = ScriptRewriter()._build_reference_structure(original)
        self.assertIn("1. [00:00] 头些年我还是当记者的时候", structure)
        self.assertIn("2. [00:01] 我们采访老师就是说明黄水无所谓", structure)
        self.assertIn("3. [00:04] 但是社交距离内口气一定要清新", structure)

    def test_rewriter_prompt_prioritizes_reference_structure(self):
        self.assertIn("用户参考文案结构", ScriptRewriter.SYSTEM_PROMPT)
        self.assertIn("不能让同类参考脚本覆盖用户参考文案结构", ScriptRewriter.SYSTEM_PROMPT)

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
        self.assertIn("（口播画面）老板们别再乱买了！", cleaned)
        self.assertIn("（产品空镜）看一下法采这款产品", cleaned)
        self.assertIn("（指向小黄车口播）需要的点下方链接。", cleaned)
        self.assertNotIn("【0-3s 开场钩子】", cleaned)
        self.assertNotIn("改写后的脚本", cleaned)

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
            r'id="scriptOutput" class="so".*?id="resultActions" class="result-actions"',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(top_back)
        self.assertIsNotNone(bottom_actions)
        self.assertIsNotNone(script_actions)
        self.assertIn("btnBackToStep2FromResult", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='none'", self.page)
        self.assertIn("document.getElementById('resultActions').style.display='flex'", self.page)

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
        self.assertIn("function getSeedancePrompts", self.page)
        self.assertIn("function buildSeedancePrompt", self.page)
        self.assertIn("function renderSeedancePrompts", self.page)

    def test_seedance_prompts_are_rendered_after_rewrite(self):
        self.assertIn("renderSeedancePrompts(currentRewritten)", self.page)
        self.assertIn("renderSeedancePrompts('')", self.page)
        self.assertIn("seedance-copy", self.page)
        self.assertIn("竖屏9:16，真实商业烘焙短视频", self.page)

    def test_seedance_panel_is_on_right_desktop_and_stacks_mobile(self):
        self.assertIn("<main class=\"page-main rewrite-main\">", self.page)
        self.assertIn(".rewrite-main{max-width:1540px}", self.page)
        self.assertIn("grid-template-columns:minmax(480px,1fr) minmax(620px,720px)", self.page)
        self.assertIn("align-items:stretch", self.page)
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
