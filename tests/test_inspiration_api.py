import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import Product, SellingPoint


class InspirationApiTests(unittest.TestCase):
    def setUp(self):
        from routers import inspiration

        self.inspiration = inspiration
        self.original_client = inspiration.ai_service.client
        self.original_chat = inspiration.ai_service.chat
        self.original_model = inspiration.ai_service.model
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.include_router(inspiration.router, prefix="/api/inspiration")
        self.client = TestClient(app)

    def tearDown(self):
        self.inspiration.ai_service.client = self.original_client
        self.inspiration.ai_service.chat = self.original_chat
        self.inspiration.ai_service.model = self.original_model
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _add_product(self, name, category, price, description, point):
        product = Product(
            name=name,
            category=category,
            price=price,
            brand="法采",
            description=description,
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        self.db.add(SellingPoint(
            product_id=product.id,
            point_type="核心卖点",
            content=point,
            priority=1,
        ))
        self.db.commit()
        return product

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
        self.assertFalse(data["product_context_used"])
        self.assertEqual(data["products"], [])

    def test_chat_uses_product_context_when_message_mentions_product_intent(self):
        product = self._add_product(
            "水性色素",
            "烘焙调色",
            18.59,
            "适合蛋糕调色和翻糖上色",
            "少量即可上色，适合烘焙门店做调色备货。",
        )
        self.inspiration.ai_service.client = object()
        captured = {}

        async def fake_chat(messages, temperature=0.7, allow_fallback=False):
            captured["messages"] = messages
            return "可以围绕水性色素做一个调色前后对比脚本。"

        self.inspiration.ai_service.chat = fake_chat

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "帮我想一个调色产品短视频脚本"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["product_context_used"])
        self.assertEqual(data["products"][0]["product_id"], product.id)
        self.assertEqual(data["products"][0]["name"], "水性色素")
        self.assertIn("产品资料", captured["messages"][-1]["content"])
        self.assertIn("水性色素", captured["messages"][-1]["content"])

    def test_chat_uses_product_context_for_product_names_and_selling_point_keywords(self):
        fondant = self._add_product(
            "翻糖压片",
            "烘焙装饰",
            31.53,
            "彩色翻糖片，可用于造型蛋糕装饰。",
            "适合做蛋糕表面造型和节日款装饰。",
        )
        puree = self._add_product(
            "夹心果泥",
            "烘焙夹心",
            49.29,
            "果肉含量高，适合蛋糕夹心和奶油调味。",
            "开袋即用，适合活动款蛋糕做夹心卖点。",
        )
        self.inspiration.ai_service.client = object()

        async def fake_chat(messages, temperature=0.7, allow_fallback=False):
            return "已结合产品资料给出内容方向。"

        self.inspiration.ai_service.chat = fake_chat

        fondant_response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "翻糖怎么做内容选题"},
        )
        puree_response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "果泥适合什么活动文案"},
        )

        self.assertEqual(fondant_response.status_code, 200)
        self.assertEqual(puree_response.status_code, 200)
        self.assertIn(fondant.id, [item["product_id"] for item in fondant_response.json()["products"]])
        self.assertIn(puree.id, [item["product_id"] for item in puree_response.json()["products"]])

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

    def test_chat_ai_unavailable_still_returns_product_references(self):
        product = self._add_product(
            "水性色素",
            "烘焙调色",
            18.59,
            "适合蛋糕调色和翻糖上色",
            "少量即可上色，适合烘焙门店做调色备货。",
        )
        self.inspiration.ai_service.client = None

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "调色产品怎么拍"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "fallback")
        self.assertTrue(data["product_context_used"])
        self.assertEqual(data["products"][0]["product_id"], product.id)

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
