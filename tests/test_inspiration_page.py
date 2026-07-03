import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]
NAV_STYLE_VERSION = "nav-20260703-data-import"


class InspirationPageTests(unittest.TestCase):
    def test_ai_work_route_renders_default_home_page(self):
        response = TestClient(app).get("/app")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI工作", response.text)
        self.assertIn("inspiration-shell", response.text)

    def test_legacy_inspiration_route_redirects_to_ai_work(self):
        response = TestClient(app).get("/app/inspiration", follow_redirects=False)

        self.assertIn(response.status_code, {302, 303, 307})
        self.assertEqual(response.headers["location"], "/app")

    def test_generate_route_renders_script_page(self):
        response = TestClient(app).get("/app/generate")

        self.assertEqual(response.status_code, 200)
        self.assertIn("生成脚本", response.text)
        self.assertIn("btnGenerate", response.text)

    def test_inspiration_template_has_chat_experience(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn('class="inspiration-shell"', page)
        self.assertIn('id="inspirationThread"', page)
        self.assertIn('id="inspirationInput"', page)
        self.assertIn('id="inspirationSend"', page)
        self.assertIn('id="clearChatBtn"', page)
        self.assertIn("sendInspirationChat", page)
        self.assertIn("appendMessage", page)
        self.assertIn("copyAssistantMessage", page)
        self.assertIn("submitOnEnter", page)
        self.assertIn("fetch('/api/inspiration/chat'", page)
        self.assertIn("/static/js/common.js", page)

    def test_inspiration_template_has_prompt_chips_and_responsive_css(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("inspiration-empty-prompts", page)
        for label in ["新品开头", "低成本选题", "直播话术", "促单文案"]:
            self.assertIn(label, page)
        self.assertIn("@media (max-width: 900px)", page)
        self.assertIn(".inspiration-shell{grid-template-columns:1fr", page)
        self.assertIn("@media (max-width: 640px)", page)
        self.assertIn(".inspiration-page{height:auto", page)

    def test_inspiration_sidebar_is_conversation_history(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("历史对话", page)
        self.assertIn('id="conversationHistoryList"', page)
        self.assertIn("conversation-item", page)
        self.assertIn("暂无历史对话", page)
        self.assertIn("startNewConversation()", page)
        self.assertNotIn("常用提示", page)

    def test_inspiration_template_persists_conversation_history(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("INSPIRATION_HISTORY_KEY", page)
        self.assertIn("function loadConversations()", page)
        self.assertIn("function saveConversations()", page)
        self.assertIn("function renderConversationHistory()", page)
        self.assertIn("function selectConversation(id)", page)
        self.assertIn("function addConversationMessage(role,content,extras)", page)
        self.assertIn("localStorage.getItem(INSPIRATION_HISTORY_KEY)", page)
        self.assertIn("localStorage.setItem(INSPIRATION_HISTORY_KEY", page)

    def test_inspiration_send_and_clear_sync_current_conversation(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("ensureActiveConversation()", page)
        self.assertIn("addConversationMessage('user',message,{attachments:selectedAttachments})", page)
        self.assertIn("addConversationMessage('assistant',data.answer||'',{products:data.products,reasoning:data.reasoning,sources:data.sources})", page)
        self.assertIn("renderConversationHistory()", page)
        self.assertIn("clearCurrentConversation()", page)

    def test_inspiration_template_renders_reference_products(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("function renderReferenceProducts(products)", page)
        self.assertIn("参考产品", page)
        self.assertIn("renderReferenceProducts(data.products)", page)
        self.assertIn("if(!products||!products.length)return ''", page)
        self.assertIn("product_context_used", page)

    def test_inspiration_template_can_generate_word_document_from_answer(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("生成文档", page)
        self.assertIn("function generateAssistantDocument(button)", page)
        self.assertIn("function renderGeneratedDocument(document)", page)
        self.assertIn("fetch('/api/inspiration/documents'", page)
        self.assertIn("download_url", page)
        self.assertIn("Word 文档", page)
        self.assertIn("function formatInspirationApiError(data,fallback)", page)
        self.assertIn("Array.isArray(data.detail)", page)
        self.assertIn("new Error(formatInspirationApiError(data,'文档生成失败'))", page)

    def test_inspiration_composer_has_tool_modes_and_upload(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        for label in ["产品库优先", "上传文件", "思考模式", "深入研究", "数据分析", "分镜提示词生成"]:
            self.assertIn(label, page)
        self.assertLess(page.index("产品库优先"), page.index("上传文件"))
        self.assertIn('id="productContextToggle"', page)
        self.assertIn("function toggleProductContextMode()", page)
        self.assertIn("function getProductContextMode()", page)
        self.assertIn('id="inspirationFileInput"', page)
        self.assertIn('accept=".txt,.md,.json,.csv,.pdf,.docx,.xlsx"', page)
        self.assertIn('data-tool-mode="seedance"', page)
        self.assertIn("function setInspirationMode(mode)", page)
        self.assertIn("function uploadInspirationFiles(files)", page)
        self.assertIn("fetch('/api/inspiration/attachments'", page)

    def test_inspiration_seedance_mode_updates_label_and_placeholder(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("seedance:'粘贴脚本，或上传脚本文件后填写生成要求...'", page)
        self.assertIn("function updateInspirationPlaceholder()", page)
        self.assertIn("updateInspirationPlaceholder()", page)
        self.assertIn("seedance:'分镜提示词生成'", page)
        self.assertNotIn("DeepSeek V4 Pro", page)

    def test_inspiration_model_pill_loads_configured_interface_models(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("fetch('/api/ai-config/interfaces'", page)
        self.assertIn("function loadInspirationModelConfig()", page)
        self.assertIn("const INSPIRATION_MODE_INTERFACE_KEYS={chat:'inspiration_chat',thinking:'inspiration_tools',seedance:'script_creation',research:'inspiration_tools',analysis:'inspiration_tools'}", page)
        self.assertIn("provider_label", page)
        self.assertIn("display_model", page)

    def test_inspiration_model_pill_uses_response_model_after_chat(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("function updateModelPillForMode(mode,overrideModel,productContextUsed)", page)
        self.assertIn("updateModelPillForMode(data.tool_mode||getActiveInspirationMode(),data.model,data.product_context_used)", page)
        self.assertIn("产品库优先", page)
        self.assertIn("isProductContextAlways()", page)
        self.assertIn("modelPill.title=labelText", page)

    def test_inspiration_chat_request_sends_tool_mode_and_attachments(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("tool_mode:getActiveInspirationMode()", page)
        self.assertIn("product_context_mode:getProductContextMode()", page)
        self.assertIn("attachments:attachmentsForRequest", page)
        self.assertIn("addConversationMessage('user',message,{attachments:selectedAttachments})", page)
        self.assertIn("selectedAttachments=[]", page)
        self.assertIn("renderSelectedAttachments()", page)

    def test_inspiration_template_renders_reasoning_and_sources(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("function renderReasoning(reasoning)", page)
        self.assertIn("思考过程", page)
        self.assertIn("function renderSources(sources)", page)
        self.assertIn("外网参考", page)
        self.assertIn("reasoning:data.reasoning", page)
        self.assertIn("sources:data.sources", page)

    def test_inspiration_template_formats_fetch_failures(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("function formatInspirationChatError(error)", page)
        self.assertIn("Failed to fetch", page)
        self.assertIn("连接后端失败或响应超时", page)

    def test_inspiration_long_answers_scroll_to_answer_start(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("function scrollChatToMessage(message,mode)", page)
        self.assertIn("mode==='top'", page)
        self.assertIn("thread.scrollTo({top:top,behavior:'smooth'})", page)
        self.assertIn("role==='assistant'&&!(options&&options.thinking)", page)
        self.assertIn("?'top':'bottom'", page)

    def test_common_js_test_includes_inspiration_page(self):
        test_file = (ROOT / "tests" / "test_frontend_common_js.py").read_text(encoding="utf-8-sig")

        self.assertIn('"inspiration.html"', test_file)

    def test_inspiration_inline_script_has_valid_syntax(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")
        scripts = re.findall(r"<script>\s*(.*?)</script>", page, re.S)
        self.assertEqual(1, len(scripts))

        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(scripts[0])
            script_path = Path(handle.name)

        try:
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        finally:
            script_path.unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)


class InspirationNavigationTests(unittest.TestCase):
    def test_all_main_templates_show_ai_work_before_generate(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertIn('href="/app"', page, name)
            self.assertIn('href="/app/generate"', page, name)
            self.assertNotIn('href="/app/seedance"', page, name)
            self.assertNotIn('>灵感</a>', page, name)
            self.assertRegex(
                page,
                re.compile(r'href="/app"[^>]*>AI工作</a>\s*<a href="/app/generate"[^>]*>生成脚本</a>', re.S),
                name,
            )

    def test_data_import_is_brand_side_button_not_main_nav_item(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            brand_group = re.search(
                r'<div class="nav-brand-group">(?P<body>.*?)</div>\s*<div class="nav-links">',
                page,
                flags=re.S,
            )
            self.assertIsNotNone(brand_group, name)
            self.assertIn('class="nav-import-btn', brand_group.group("body"), name)
            self.assertIn('href="/app/import"', brand_group.group("body"), name)
            self.assertIn(">数据导入</a>", brand_group.group("body"), name)

            nav_links = re.search(
                r'<div class="nav-links">(?P<body>.*?)</div></div></nav>',
                page,
                flags=re.S,
            )
            self.assertIsNotNone(nav_links, name)
            self.assertNotIn(">数据导入</a>", nav_links.group("body"), name)

            if name == "import.html":
                self.assertIn('class="nav-import-btn on"', brand_group.group("body"), name)
            else:
                self.assertNotIn('class="nav-import-btn on"', brand_group.group("body"), name)

    def test_data_import_nav_button_uses_fresh_shared_css_version(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")

            self.assertIn(f'/static/css/style.css?v={NAV_STYLE_VERSION}', page, name)
            self.assertNotIn("/static/css/style.css?v=nav-20260630", page, name)

    def test_ai_work_nav_is_active_only_on_ai_work_page(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn('<a href="/app" class="nav-link on">AI工作</a>', page)

    def test_rewrite_top_nav_label_is_script_rewrite(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            nav_links = re.search(
                r'<div class="nav-links">(?P<body>.*?)</div></div></nav>',
                page,
                flags=re.S,
            )
            self.assertIsNotNone(nav_links, name)
            self.assertRegex(nav_links.group("body"), r'href="/app/rewrite"[^>]*>脚本改写</a>', name)
            self.assertNotIn(">爆款脚本改写</a>", nav_links.group("body"), name)


if __name__ == "__main__":
    unittest.main()
