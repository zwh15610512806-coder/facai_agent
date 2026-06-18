import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]


class InspirationPageTests(unittest.TestCase):
    def test_inspiration_route_renders_page(self):
        response = TestClient(app).get("/app/inspiration")

        self.assertEqual(response.status_code, 200)
        self.assertIn("灵感", response.text)
        self.assertIn("inspiration-shell", response.text)

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
        self.assertIn("addConversationMessage('user',message)", page)
        self.assertIn("addConversationMessage('assistant',data.answer||'',{products:data.products})", page)
        self.assertIn("renderConversationHistory()", page)
        self.assertIn("clearCurrentConversation()", page)

    def test_inspiration_template_renders_reference_products(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn("function renderReferenceProducts(products)", page)
        self.assertIn("参考产品", page)
        self.assertIn("renderReferenceProducts(data.products)", page)
        self.assertIn("if(!products||!products.length)return ''", page)
        self.assertIn("产品资料 + AI 对话", page)

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
    def test_all_main_templates_link_to_inspiration_after_search(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertIn('href="/app/inspiration"', page, name)
            self.assertRegex(
                page,
                re.compile(r'href="/app/search"[^>]*>.*?</a>\s*<a href="/app/inspiration"', re.S),
                name,
            )

    def test_inspiration_nav_is_active_only_on_inspiration_page(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn('<a href="/app/inspiration" class="nav-link on">灵感</a>', page)


if __name__ == "__main__":
    unittest.main()
