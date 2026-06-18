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

        self.assertGreaterEqual(page.count("prompt-chip"), 4)
        self.assertIn("@media (max-width: 900px)", page)
        self.assertIn(".inspiration-shell{grid-template-columns:1fr", page)
        self.assertIn("@media (max-width: 640px)", page)
        self.assertIn(".inspiration-page{height:auto", page)

    def test_common_js_test_includes_inspiration_page(self):
        test_file = (ROOT / "tests" / "test_frontend_common_js.py").read_text(encoding="utf-8-sig")

        self.assertIn('"inspiration.html"', test_file)


if __name__ == "__main__":
    unittest.main()
