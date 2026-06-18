import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


class InspirationApiTests(unittest.TestCase):
    def setUp(self):
        from routers import inspiration

        self.inspiration = inspiration
        self.original_client = inspiration.ai_service.client
        self.original_chat = inspiration.ai_service.chat
        self.original_model = inspiration.ai_service.model

        app = FastAPI()
        app.include_router(inspiration.router, prefix="/api/inspiration")
        self.client = TestClient(app)

    def tearDown(self):
        self.inspiration.ai_service.client = self.original_client
        self.inspiration.ai_service.chat = self.original_chat
        self.inspiration.ai_service.model = self.original_model

    def test_chat_requires_non_empty_message(self):
        response = self.client.post("/api/inspiration/chat", json={"message": "   "})

        self.assertEqual(response.status_code, 422)

    def test_chat_returns_ai_answer_when_service_responds(self):
        self.inspiration.ai_service.client = object()
        self.inspiration.ai_service.model = "deepseek-chat"

        async def fake_chat(messages, temperature=0.7, allow_fallback=False):
            self.assertFalse(allow_fallback)
            self.assertEqual(messages[0]["role"], "system")
            self.assertIn("法采新媒体运营灵感助手", messages[0]["content"])
            self.assertEqual(messages[-1], {"role": "user", "content": "帮我想 3 个新品短视频开头"})
            return "这里是 3 个开头。"

        self.inspiration.ai_service.chat = fake_chat

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "帮我想 3 个新品短视频开头"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], "这里是 3 个开头。")
        self.assertEqual(data["mode"], "ai")
        self.assertEqual(data["model"], "deepseek-chat")

    def test_chat_returns_local_fallback_when_ai_unavailable(self):
        self.inspiration.ai_service.client = None

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "今天拍什么内容？"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "fallback")
        self.assertIn("AI 服务暂时不可用", data["answer"])
        self.assertIn("今天拍什么内容？", data["answer"])

    def test_chat_sends_only_recent_valid_history(self):
        self.inspiration.ai_service.client = object()
        captured = {}

        async def fake_chat(messages, temperature=0.7, allow_fallback=False):
            captured["messages"] = messages
            return "已结合上下文回答。"

        self.inspiration.ai_service.chat = fake_chat
        history = []
        for index in range(20):
            role = "user" if index % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"历史 {index}"})
        history.append({"role": "system", "content": "should be ignored"})
        history.append({"role": "user", "content": ""})

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "继续", "history": history},
        )

        self.assertEqual(response.status_code, 200)
        roles = [item["role"] for item in captured["messages"]]
        contents = [item["content"] for item in captured["messages"]]
        self.assertEqual(roles[0], "system")
        self.assertEqual(roles[-1], "user")
        self.assertEqual(contents[-1], "继续")
        self.assertNotIn("should be ignored", contents)
        self.assertLessEqual(len(captured["messages"]), 14)
        self.assertIn("历史 8", contents)
        self.assertIn("历史 19", contents)


if __name__ == "__main__":
    unittest.main()
