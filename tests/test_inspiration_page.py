import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]
NAV_STYLE_VERSION = "app-shell-20260723-tasks-stack"


class InspirationPageTests(unittest.TestCase):
    def test_ai_work_route_renders_default_home_page(self):
        response = TestClient(app).get("/app")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI工作", response.text)
        self.assertIn("inspiration-shell", response.text)
        self.assertNotIn('workspace=canvas', response.text)
        self.assertNotIn('id="canvas-app"', response.text)

    def test_removed_canvas_workspace_parameter_renders_ai_work(self):
        response = TestClient(app).get("/app?workspace=canvas")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('inspiration-shell', response.text)
        self.assertNotIn('canvas-app', response.text)
        self.assertNotIn('/static/canvas/', response.text)

    def test_product_visual_canvas_routes_are_not_registered(self):
        client = TestClient(app)

        self.assertEqual(client.get("/app/canvas").status_code, 404)
        self.assertEqual(client.get("/api/canvas/projects").status_code, 404)
        self.assertFalse(
            any(path.startswith("/api/canvas") for path in app.openapi()["paths"])
        )

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
        page = read_page_source("inspiration.html")

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
        page = read_page_source("inspiration.html")

        self.assertIn("inspiration-empty-prompts", page)
        for label in ["新品开头", "低成本选题", "直播话术", "促单文案"]:
            self.assertIn(label, page)
        self.assertIn("@media (max-width: 900px)", page)
        self.assertIn(".inspiration-shell{grid-template-columns:1fr", page)
        self.assertIn("@media (max-width: 640px)", page)
        self.assertIn(".inspiration-page{height:auto", page)

    def test_inspiration_sidebar_is_conversation_history(self):
        page = read_page_source("inspiration.html")

        self.assertIn("历史对话", page)
        self.assertIn('id="conversationHistoryList"', page)
        self.assertIn("conversation-item", page)
        self.assertIn("暂无历史对话", page)
        self.assertIn("startNewConversation()", page)
        self.assertNotIn("常用提示", page)

    def test_inspiration_template_persists_conversation_history(self):
        page = read_page_source("inspiration.html")

        self.assertIn("INSPIRATION_HISTORY_KEY", page)
        self.assertIn("function loadConversations()", page)
        self.assertIn("function saveConversations()", page)
        self.assertIn("function renderConversationHistory()", page)
        self.assertIn("function selectConversation(id)", page)
        self.assertIn("function addConversationMessage(role,content,extras)", page)
        self.assertIn("localStorage.getItem(INSPIRATION_HISTORY_KEY)", page)
        self.assertIn("localStorage.setItem(INSPIRATION_HISTORY_KEY", page)
        self.assertIn("CONVERSATION_RETENTION_MS=30*24*60*60*1000", page)
        self.assertIn("Number(conversation.updatedAt)>=cutoff", page)

    def test_inspiration_history_has_pin_archive_delete_actions(self):
        page = read_page_source("inspiration.html")

        self.assertIn("pinned:Boolean(raw.pinned)", page)
        self.assertIn("archived:Boolean(raw.archived)", page)
        self.assertIn("function toggleConversationPin(id,event)", page)
        self.assertIn("function archiveConversation(id,event)", page)
        self.assertIn("function restoreConversation(id,event)", page)
        self.assertIn("function deleteConversation(id,event)", page)
        self.assertIn("function selectNextAvailableConversation()", page)
        self.assertIn("!conversation.archived", page)
        self.assertIn("conversation.archived", page)
        self.assertIn("conversation-action-pin", page)
        self.assertIn("conversation-menu-button", page)
        self.assertIn("conversation-action-menu", page)
        self.assertIn('id="conversationFloatingMenu"', page)
        self.assertIn("function showConversationMenu(id,isArchived,anchor,event)", page)
        self.assertIn("function positionConversationMenu(anchor,menu)", page)
        self.assertIn("function hideConversationMenu()", page)
        self.assertIn("function hideConversationMenuOnOutsideClick(event)", page)
        self.assertIn("conversation-archive-section", page)
        self.assertIn('id="archivedConversationList"', page)
        self.assertIn("event.stopPropagation()", page)
        self.assertIn("confirm('删除这条对话？此操作不可恢复。')", page)

    def test_inspiration_history_uses_compact_chatgpt_style_rows(self):
        page = read_page_source("inspiration.html")

        self.assertIn(".conversation-row", page)
        self.assertIn(".conversation-actions", page)
        self.assertIn("grid-template-columns:minmax(0,1fr) auto", page)
        self.assertIn(".conversation-item.is-pinned .conversation-action-pin", page)
        self.assertIn(".conversation-item:hover .conversation-action", page)
        self.assertIn(".conversation-floating-menu{position:fixed", page)
        self.assertIn(".conversation-action-menu.is-open", page)
        self.assertNotIn(".conversation-menu-wrap:focus-within .conversation-action-menu", page)
        self.assertIn("aria-label=\"置顶对话\"", page)
        self.assertIn("aria-label=\"更多对话操作\"", page)

    def test_inspiration_send_and_clear_sync_current_conversation(self):
        page = read_page_source("inspiration.html")

        self.assertIn("ensureActiveConversation()", page)
        self.assertIn("addConversationMessage('user',message,{attachments:selectedAttachments})", page)
        self.assertIn("submitBackgroundJob('/api/inspiration/chat/jobs'", page)
        self.assertIn("syncConversationJob(job)", page)
        self.assertIn("renderConversationHistory()", page)
        self.assertIn("clearCurrentConversation()", page)

    def test_inspiration_template_renders_reference_products(self):
        page = read_page_source("inspiration.html")

        self.assertIn("function renderReferenceProducts(products)", page)
        self.assertIn("参考产品", page)
        self.assertIn("products:result.products", page)
        self.assertIn("if(!products||!products.length)return ''", page)
        self.assertIn("product_context_used", page)

    def test_inspiration_template_renders_agent_trace_tools(self):
        page = read_page_source("inspiration.html")

        self.assertIn("function renderAgentTrace(agentTrace)", page)
        self.assertIn("已使用", page)
        self.assertIn("agent_trace", page)
        self.assertIn("agentTrace:result.agent_trace", page)
        self.assertIn("renderAgentTrace(options.agentTrace)", page)
        self.assertIn("agentTrace:message.agentTrace", page)

    def test_inspiration_template_can_generate_word_document_from_answer(self):
        page = read_page_source("inspiration.html")

        self.assertIn("生成文档", page)
        self.assertIn("function generateAssistantDocument(button)", page)
        self.assertIn("function renderGeneratedDocument(document)", page)
        self.assertIn("submitBackgroundJob('/api/inspiration/documents/jobs'", page)
        self.assertIn("waitForBackgroundJob(job.public_id)", page)
        self.assertIn("download_url", page)
        self.assertIn("Word 文档", page)
        self.assertIn("function formatInspirationApiError(data,fallback)", page)
        self.assertIn("Array.isArray(data.detail)", page)
        self.assertIn("文档生成失败", page)

    def test_inspiration_composer_has_tool_modes_and_upload(self):
        page = read_page_source("inspiration.html")
        composer_tools = page.split('<div class="composer-tools" aria-label="AI工作对话功能">', 1)[1].split('<input id="inspirationFileInput"', 1)[0]

        for label in ["基于产品资料", "上传文件", "思考模式", "深入研究", "联网搜索", "分镜提示词生成"]:
            self.assertIn(label, page)
        self.assertNotIn("产品库优先", page)
        self.assertNotIn('data-tool-mode="analysis"', composer_tools)
        self.assertNotIn(">数据分析<", composer_tools)
        self.assertLess(page.index("基于产品资料"), page.index("上传文件"))
        self.assertIn('id="productContextToggle"', page)
        self.assertIn("function toggleProductContextMode()", page)
        self.assertIn("function getProductContextMode()", page)
        self.assertIn('id="webSearchToggle"', page)
        self.assertIn("function toggleWebSearchMode()", page)
        self.assertIn("function getWebSearchMode()", page)
        self.assertIn('id="inspirationFileInput"', page)
        self.assertIn('accept=".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"', page)
        self.assertIn('data-tool-mode="seedance"', page)
        self.assertIn("function setInspirationMode(mode)", page)
        self.assertIn("function uploadInspirationFiles(files)", page)
        self.assertIn("fetch('/api/inspiration/attachments'", page)
        self.assertIn("function handleInspirationPaste(event)", page)
        self.assertIn("clipboardData.items", page)
        self.assertIn("item.type.indexOf('image/')===0", page)
        self.assertIn("uploadInspirationFiles(files)", page)
        self.assertIn("attachment.kind==='image'", page)
        self.assertIn("preview_url", page)

    def test_inspiration_composer_input_matches_buttons_then_auto_resizes(self):
        page = read_page_source("inspiration.html")

        self.assertIn(".inspiration-input{flex:1;min-height:44px;max-height:260px;", page)
        self.assertIn(".inspiration-input{min-height:44px;max-height:210px}", page)
        self.assertIn("overflow-y:auto", page)
        self.assertIn('rows="1"', page)
        self.assertIn("function resizeInspirationInput()", page)
        self.assertIn("const minHeight=Number.parseFloat(computed.minHeight)||44;", page)
        self.assertIn("const maxHeight=Number.parseFloat(computed.maxHeight)||260;", page)
        self.assertIn("Math.min(Math.max(input.scrollHeight,minHeight),maxHeight)", page)
        self.assertIn("input.style.overflowY=input.scrollHeight>maxHeight?'auto':'hidden';", page)
        self.assertIn("addEventListener('input',resizeInspirationInput)", page)
        self.assertIn("resizeInspirationInput();", page)

    def test_inspiration_composer_reserves_desktop_tools_space_only(self):
        page = read_page_source("inspiration.html")

        self.assertIn(".inspiration-composer{flex:0 0 auto;border-top:1px solid var(--border-soft);padding:12px var(--facai-tools-reserve,128px) 12px 12px", page)
        self.assertNotIn("calc(184px + env(safe-area-inset-bottom))", page)
        self.assertIn(".inspiration-composer{padding:9px 8px calc(9px + env(safe-area-inset-bottom))}", page)

    def test_inspiration_user_message_visuals_put_attachments_above_text(self):
        page = read_page_source("inspiration.html")

        self.assertIn(".chat-message.user .chat-bubble{background:#f4f7ea;border-color:#d9e5b5;color:var(--text);", page)
        self.assertIn(".chat-message.user .message-attachments{order:0;margin:0 0 8px;padding:0 0 8px;", page)
        self.assertIn(".chat-message.user .message-content{order:1}", page)
        self.assertIn("const bodyHtml='<div class=\"message-content\">'+safe+'</div>';", page)
        self.assertIn("const bubbleContent=role==='user'?attachmentHtml+bodyHtml:bodyHtml+attachmentHtml+reasoningHtml+agentTraceHtml+references+sourceHtml+tools;", page)

    def test_inspiration_seedance_mode_updates_label_and_placeholder(self):
        page = read_page_source("inspiration.html")

        self.assertIn("seedance:'粘贴脚本，或上传脚本文件后填写生成要求...'", page)
        self.assertIn("function updateInspirationPlaceholder()", page)
        self.assertIn("updateInspirationPlaceholder()", page)
        self.assertIn("seedance:'分镜提示词生成'", page)
        self.assertNotIn("DeepSeek V4 Pro", page)

    def test_inspiration_model_pill_loads_configured_interface_models(self):
        page = read_page_source("inspiration.html")

        self.assertIn("fetch('/api/ai-config/interfaces'", page)
        self.assertIn("function loadInspirationModelConfig()", page)
        self.assertIn("const INSPIRATION_MODE_INTERFACE_KEYS={chat:'inspiration_chat',thinking:'inspiration_tools',seedance:'script_creation',research:'inspiration_tools',analysis:'inspiration_tools'}", page)
        self.assertIn("provider_label", page)
        self.assertIn("display_model", page)

    def test_inspiration_model_pill_uses_response_model_after_chat(self):
        page = read_page_source("inspiration.html")

        self.assertIn("function updateModelPillForMode(mode,overrideModel,productContextUsed)", page)
        self.assertIn("updateModelPillForMode(result.tool_mode||getActiveInspirationMode(),result.model,result.product_context_used)", page)
        self.assertIn("基于产品资料", page)
        self.assertNotIn("parts.push('产品资料')", page)
        self.assertIn("isProductContextAlways()", page)
        self.assertIn("modelPill.title=labelText", page)

    def test_inspiration_chat_request_sends_tool_mode_and_attachments(self):
        page = read_page_source("inspiration.html")

        self.assertIn("tool_mode:getActiveInspirationMode()", page)
        self.assertIn("product_context_mode:getProductContextMode()", page)
        self.assertIn("web_search_mode:getWebSearchMode()", page)
        self.assertIn("?'always':'off'", page)
        self.assertIn("return isProductContextAlways()&&getActiveInspirationMode()!=='seedance'?'always':'off';", page)
        self.assertIn("return isWebSearchAlways()&&getActiveInspirationMode()!=='seedance'?'always':'auto';", page)
        self.assertIn("attachments:attachmentsForRequest", page)
        self.assertIn("addConversationMessage('user',message,{attachments:selectedAttachments})", page)
        self.assertIn("selectedAttachments=[]", page)
        self.assertIn("renderSelectedAttachments()", page)

    def test_inspiration_template_renders_reasoning_and_sources(self):
        page = read_page_source("inspiration.html")

        self.assertIn("function renderReasoning(reasoning)", page)
        self.assertIn("思考过程", page)
        self.assertIn("function renderSources(sources)", page)
        self.assertIn("外网参考", page)
        self.assertIn("reasoning:result.reasoning", page)
        self.assertIn("sources:result.sources", page)

    def test_inspiration_template_formats_fetch_failures(self):
        page = read_page_source("inspiration.html")

        self.assertIn("function formatInspirationChatError(error)", page)
        self.assertIn("Failed to fetch", page)
        self.assertIn("连接后端失败或响应超时", page)

    def test_inspiration_long_answers_scroll_to_answer_start(self):
        page = read_page_source("inspiration.html")

        self.assertIn("function scrollChatToMessage(message,mode)", page)
        self.assertIn("mode==='top'", page)
        self.assertIn("thread.scrollTo({top:top,behavior:'smooth'})", page)
        self.assertIn("role==='assistant'&&!(options&&options.thinking)", page)
        self.assertIn("?'top':'bottom'", page)

    def test_common_js_test_includes_inspiration_page(self):
        test_file = (ROOT / "tests" / "test_frontend_common_js.py").read_text(encoding="utf-8-sig")

        self.assertIn('"inspiration.html"', test_file)

    def test_inspiration_inline_script_has_valid_syntax(self):
        page = read_page_source("inspiration.html")
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
    def test_all_main_templates_show_ai_work_then_generate(self):
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
            self.assertNotIn('workspace=canvas', page, name)
            self.assertIn('href="/app/generate"', page, name)
            self.assertNotIn('href="/app/seedance"', page, name)
            self.assertNotIn('>灵感</a>', page, name)
            self.assertRegex(
                page,
                re.compile(
                    r'href="/app"[^>]*>AI工作</a>\s*'
                    r'<a href="/app/generate"[^>]*>生成脚本</a>',
                    re.S,
                ),
                name,
            )

    def test_tools_are_injected_by_common_js_and_not_hard_coded_in_templates(self):
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
            brand_body = brand_group.group("body")
            self.assertNotIn('href="/app/import"', brand_body, name)
            self.assertNotIn('class="nav-import-btn', brand_body, name)

            nav_links = re.search(
                r'<div class="nav-links">(?P<body>.*?)</div></div></nav>',
                page,
                flags=re.S,
            )
            self.assertIsNotNone(nav_links, name)
            self.assertNotIn('href="/app/import"', nav_links.group("body"), name)
            self.assertNotIn(">数据导入</a>", nav_links.group("body"), name)
            self.assertNotIn('class="data-import-fab"', page, name)
            self.assertNotIn('class="ai-config-fab"', page, name)
            self.assertIn('/static/js/common.js?v=app-shell-20260723-tasks-stack', page, name)

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
        page = read_page_source("inspiration.html")

        self.assertIn('href="/app" class="nav-link on" aria-current="page"', page)
        self.assertNotIn('active_workspace', page)

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
