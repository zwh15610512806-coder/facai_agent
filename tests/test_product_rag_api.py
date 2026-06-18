import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product, SellingPoint
from routers import products as products_router
from services import product_rag


class ProductRagApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.original_ai_client = product_rag.ai_service.client
        self.original_ai_chat = product_rag.ai_service.chat
        product_rag.ai_service.client = None

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[products_router.get_db] = override_db
        app.include_router(products_router.router, prefix="/api/products")
        self.client = TestClient(app)

    def tearDown(self):
        product_rag.ai_service.client = self.original_ai_client
        product_rag.ai_service.chat = self.original_ai_chat
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

    def test_global_rag_chat_returns_retrieved_products_with_fallback_answer(self):
        self._add_product(
            "水性色素",
            "烘焙调色",
            18.59,
            "适合蛋糕调色和翻糖上色",
            "少量即可上色，适合烘焙门店做调色备货。",
        )
        self._add_product(
            "袋装刀叉",
            "烘焙配件",
            44.53,
            "餐盘仪式感配件",
            "适合打包随餐搭配。",
        )

        response = self.client.post("/api/products/rag-chat", json={"query": "调色产品", "limit": 5})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scope"], "global")
        self.assertEqual(data["mode"], "fallback")
        self.assertTrue(any(item["name"] == "水性色素" for item in data["results"]))
        self.assertIn("根据产品资料", data["answer"])
        self.assertIn("水性色素", data["answer"])
        self.assertNotIn("来源：", data["answer"])
        self.assertNotIn("已检索到", data["answer"])
        self.assertNotIn("姐妹们", data["answer"])

    def test_product_query_policy_identifies_known_product_selection_intents(self):
        filling_policy = product_rag._product_query_policy("有哪些适合蛋糕夹心的产品？")
        self.assertEqual(filling_policy.intent, "cake_filling")
        self.assertTrue(filling_policy.broad)
        self.assertTrue(filling_policy.strict_primary_filter)

        color_policy = product_rag._product_query_policy("调色产品")
        self.assertEqual(color_policy.intent, "coloring")
        self.assertEqual(color_policy.intents, ("coloring",))
        self.assertTrue(color_policy.broad)
        self.assertTrue(color_policy.strict_primary_filter)
        self.assertEqual(color_policy.categories, ("烘焙调色",))

        self.assertEqual(product_rag._product_query_policy("推荐调味产品").intent, "flavoring")
        self.assertEqual(product_rag._product_query_policy("有哪些装饰产品").intent, "decoration")
        self.assertEqual(product_rag._product_query_policy("适合打包的配件有哪些？").intent, "packaging")

        usage_policy = product_rag._product_query_policy("调色怎么用")
        self.assertEqual(usage_policy.intent, "default")
        self.assertFalse(usage_policy.broad)

        unknown_policy = product_rag._product_query_policy("有哪些适合新品上新的产品？")
        self.assertEqual(unknown_policy.intent, "broad_product")
        self.assertTrue(unknown_policy.broad)
        self.assertFalse(unknown_policy.strict_primary_filter)

    def test_broad_coloring_question_filters_to_primary_coloring_products(self):
        products = [
            ("水性色素", "烘焙调色", 17.41, "适合奶油、蛋糕胚和翻糖调色。", "少量即可上色，适合烘焙门店做调色备货。"),
            ("油性色素", "烘焙调色", 29.29, "适合巧克力和奶油霜调色。", "油性色素适合油脂体系调色。"),
            ("水溶色粉", "烘焙调色", 18.59, "高浓缩粉状，主要用于马卡龙调色。", "适合水溶性体系调色。"),
            ("油溶色粉", "烘焙调色", 31.29, "悬浮于油性原料内着色。", "适合巧克力、油脂原料调色。"),
            ("胶状色素-小", "烘焙调色", 17.41, "胶状色素属于调色系列。", "适合奶油和蛋糕调色。"),
            ("天然色素", "烘焙调色", 0, "天然色素属于调色系列。", "用于天然色系调色。"),
            ("浅柔色素", "烘焙调色", 0, "低饱和度浅色蛋糕调色。", "适合低饱和度浅色蛋糕。"),
            ("翻糖压片", "烘焙装饰", 31.53, "彩色翻糖片，可用于造型蛋糕装饰。", "装饰翻糖，不是调色主体产品。"),
            ("手绘膏", "烘焙装饰", 16.7, "造型蛋糕快速出单，可画图案。", "装饰用手绘膏。"),
            ("夹心芋泥", "烘焙夹心", 49.29, "免调色、芋头含量高、夹心支撑稳定。", "夹心支撑稳定，适合做蛋糕夹心。"),
            ("夹心果泥", "烘焙夹心", 0, "蛋糕夹心，其次为调奶油与装饰。", "免熬开袋即用，适合蛋糕夹心。"),
            ("开心果酱", "烘焙调味", 23.17, "适合调味奶油和蛋糕风味上新。", "用于调味奶油，不是调色主体。"),
            ("调味果酱", "烘焙调味", 27.06, "可搭配蛋糕调色和风味延展。", "用于调味奶油、淋面和风味搭配。"),
            ("糖珠", "烘焙装饰", 9.18, "适合蛋糕装饰和表面点缀。", "装饰小料。"),
            ("盒装刀叉", "烘焙配件", 44.53, "餐盘仪式感配件。", "适合打包随餐搭配。"),
        ]
        for item in products:
            self._add_product(*item)

        response = self.client.post("/api/products/rag-chat", json={"query": "适合调色的产品有哪些？", "limit": 30})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = [item["name"] for item in data["results"]]
        answer = data["answer"]

        for expected in ["水性色素", "油性色素", "水溶色粉", "油溶色粉", "胶状色素-小", "天然色素", "浅柔色素"]:
            self.assertIn(expected, names)
            self.assertIn(expected, answer)
        for unexpected in ["翻糖压片", "手绘膏", "夹心芋泥", "夹心果泥", "开心果酱", "调味果酱", "糖珠", "盒装刀叉"]:
            self.assertNotIn(unexpected, names)
            self.assertNotIn(unexpected, answer)

    def test_multi_intent_product_question_uses_union_of_primary_products(self):
        products = [
            ("水性色素", "烘焙调色", 17.41, "适合奶油调色。", "调色主体产品。"),
            ("油溶色粉", "烘焙调色", 31.29, "适合油性原料调色。", "调色主体产品。"),
            ("糖珠", "烘焙装饰", 9.18, "适合蛋糕装饰和表面点缀。", "装饰主体产品。"),
            ("手绘膏", "烘焙装饰", 16.7, "适合造型蛋糕装饰。", "装饰主体产品。"),
            ("夹心芋泥", "烘焙夹心", 49.29, "免调色，适合夹心。", "夹心主体产品。"),
            ("盒装刀叉", "烘焙配件", 44.53, "餐盘仪式感配件。", "适合打包随餐搭配。"),
        ]
        for item in products:
            self._add_product(*item)

        response = self.client.post("/api/products/rag-chat", json={"query": "适合调色和装饰的产品有哪些？", "limit": 30})

        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()["results"]]
        self.assertIn("水性色素", names)
        self.assertIn("油溶色粉", names)
        self.assertIn("糖珠", names)
        self.assertIn("手绘膏", names)
        self.assertNotIn("夹心芋泥", names)
        self.assertNotIn("盒装刀叉", names)

    def test_strict_known_intent_does_not_fall_back_to_weak_results_when_empty(self):
        self._add_product(
            "夹心芋泥",
            "烘焙夹心",
            49.29,
            "免调色、芋头含量高、夹心支撑稳定。",
            "夹心支撑稳定，适合做蛋糕夹心。",
        )
        self._add_product(
            "调味果酱",
            "烘焙调味",
            27.06,
            "可搭配蛋糕调色和风味延展。",
            "用于调味奶油、淋面和风味搭配。",
        )

        response = self.client.post("/api/products/rag-chat", json={"query": "适合调色的产品有哪些？", "limit": 30})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"], [])
        self.assertIn("没有在产品资料里检索到", data["answer"])
        self.assertNotIn("夹心芋泥", data["answer"])
        self.assertNotIn("调味果酱", data["answer"])

    def test_broad_cake_filling_question_covers_powders_and_core_filling_products(self):
        products = [
            ("夹心珠", "烘焙夹心", 29.41, "主要场景：蛋糕夹心与装饰。", "夹心约 8-10 小时保持跳感，适合蛋糕夹心。"),
            ("夹心脆", "烘焙夹心", 24.47, "主要场景：蛋糕夹心与装饰。", "夹心约 8-10 小时保持酥脆，增加蛋糕夹心口感。"),
            ("夹心芋泥", "烘焙夹心", 49.29, "适合蛋糕夹心、甜品、面包和调奶油。", "夹心支撑稳定，适合做蛋糕夹心。"),
            ("夹心果泥", "烘焙夹心", 0, "蛋糕夹心，其次为调奶油与装饰。", "免熬开袋即用，适合蛋糕夹心。"),
            ("奶冻粉", "烘焙夹心", 12.71, "奶冻粉属于夹心系列，可制作蛋糕夹心奶冻。", "风味兼容性强，能制作各种契合口味蛋糕的奶冻夹心。"),
            ("慕斯粉", "烘焙夹心", 23.29, "平均制作一个6寸冰淇淋慕斯夹心成本3元左右。", "制作成本低，适合慕斯蛋糕夹心。"),
            ("布蕾粉", "烘焙夹心", 18.59, "主要场景：蛋糕夹心、装饰、甜品、饮品小料。", "夹心稳定、操作步骤标准。"),
            ("开心果酱", "烘焙调味", 23.17, "可搭配蛋糕夹心做风味延展。", "适合调味奶油和蛋糕风味上新。"),
            ("调味果酱", "烘焙调味", 27.06, "口味蛋糕与趋势上新，可搭配夹心方案。", "用于调味奶油、淋面和风味搭配。"),
            ("茶酱", "烘焙调味", 54, "口味蛋糕趋势上新，可配合蛋糕夹心。", "用于调味奶油和茶味蛋糕风味。"),
            ("盒装刀叉", "烘焙配件", 44.53, "餐盘仪式感配件。", "适合打包随餐搭配。"),
        ]
        for item in products:
            self._add_product(*item)

        response = self.client.post("/api/products/rag-chat", json={"query": "有哪些适合蛋糕夹心的产品？", "limit": 10})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = [item["name"] for item in data["results"]]
        answer = data["answer"]

        for expected in ["奶冻粉", "慕斯粉", "布蕾粉", "夹心珠", "夹心脆", "夹心芋泥", "夹心果泥"]:
            self.assertIn(expected, names)
            self.assertIn(expected, answer)
        for unexpected in ["盒装刀叉", "开心果酱", "调味果酱", "茶酱"]:
            self.assertNotIn(unexpected, names)
            self.assertNotIn(unexpected, answer)
        self.assertIn("简要回答：", answer)
        self.assertIn("具体信息：", answer)
        self.assertNotIn("来源：", answer)

    def test_broad_product_answer_keeps_all_retrieved_products_when_ai_omits_them(self):
        products = [
            ("\u5939\u5fc3\u73e0", "\u70d8\u7119\u5939\u5fc3", 29.41, "\u4e3b\u8981\u573a\u666f\uff1a\u86cb\u7cd5\u5939\u5fc3\u4e0e\u88c5\u9970\u3002", "\u5939\u5fc3\u7ea6 8-10 \u5c0f\u65f6\u4fdd\u6301\u8df3\u611f\uff0c\u9002\u5408\u86cb\u7cd5\u5939\u5fc3\u3002"),
            ("\u5939\u5fc3\u8106", "\u70d8\u7119\u5939\u5fc3", 24.47, "\u4e3b\u8981\u573a\u666f\uff1a\u86cb\u7cd5\u5939\u5fc3\u4e0e\u88c5\u9970\u3002", "\u5939\u5fc3\u7ea6 8-10 \u5c0f\u65f6\u4fdd\u6301\u9165\u8106\uff0c\u589e\u52a0\u86cb\u7cd5\u5939\u5fc3\u53e3\u611f\u3002"),
            ("\u5976\u51bb\u7c89", "\u70d8\u7119\u5939\u5fc3", 12.71, "\u5976\u51bb\u7c89\u5c5e\u4e8e\u5939\u5fc3\u7cfb\u5217\uff0c\u53ef\u5236\u4f5c\u86cb\u7cd5\u5939\u5fc3\u5976\u51bb\u3002", "\u80fd\u5236\u4f5c\u5404\u79cd\u5951\u5408\u53e3\u5473\u86cb\u7cd5\u7684\u5976\u51bb\u5939\u5fc3\u3002"),
            ("\u6155\u65af\u7c89", "\u70d8\u7119\u5939\u5fc3", 23.29, "\u5e73\u5747\u5236\u4f5c\u4e00\u4e2a6\u5bf8\u51b0\u6dc7\u6dcb\u6155\u65af\u5939\u5fc3\u6210\u672c3\u5143\u5de6\u53f3\u3002", "\u5236\u4f5c\u6210\u672c\u4f4e\uff0c\u9002\u5408\u6155\u65af\u86cb\u7cd5\u5939\u5fc3\u3002"),
            ("\u5e03\u857e\u7c89", "\u70d8\u7119\u5939\u5fc3", 18.59, "\u4e3b\u8981\u573a\u666f\uff1a\u86cb\u7cd5\u5939\u5fc3\u3001\u88c5\u9970\u3001\u751c\u54c1\u3001\u996e\u54c1\u5c0f\u6599\u3002", "\u5939\u5fc3\u7a33\u5b9a\u3001\u64cd\u4f5c\u6b65\u9aa4\u6807\u51c6\u3002"),
        ]
        for item in products:
            self._add_product(*item)

        async def incomplete_ai_answer(*args, **kwargs):
            return "\u7b80\u8981\u56de\u7b54\uff1a\u53ea\u63a8\u8350\u5939\u5fc3\u8106\u3002\n\n\u5177\u4f53\u4fe1\u606f\uff1a\n- \u5939\u5fc3\u8106\n\n\u6765\u6e90\uff1a\u4ea7\u54c1\u8d44\u6599"

        product_rag.ai_service.chat = incomplete_ai_answer

        response = self.client.post(
            "/api/products/rag-chat",
            json={"query": "\u6709\u54ea\u4e9b\u9002\u5408\u86cb\u7cd5\u5939\u5fc3\u7684\u4ea7\u54c1\uff1f", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        for expected in ["\u5939\u5fc3\u73e0", "\u5939\u5fc3\u8106", "\u5976\u51bb\u7c89", "\u6155\u65af\u7c89", "\u5e03\u857e\u7c89"]:
            self.assertIn(expected, answer)

    def test_unknown_broad_product_question_keeps_existing_retrieval(self):
        self._add_product(
            "水性色素",
            "烘焙调色",
            18.59,
            "适合蛋糕调色和翻糖上色",
            "少量即可上色，适合烘焙门店做调色备货。",
        )
        self._add_product(
            "红丝绒液",
            "烘焙调色",
            55.91,
            "红丝绒蛋糕调色和风味方案",
            "适合做红丝绒蛋糕、蛋糕调色和节日款上新。",
        )
        self._add_product(
            "盒装刀叉",
            "烘焙配件",
            44.53,
            "餐盘仪式感配件。",
            "适合打包随餐搭配。",
        )

        response = self.client.post("/api/products/rag-chat", json={"query": "有哪些适合蛋糕调色的产品？", "limit": 10})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = [item["name"] for item in data["results"]]
        self.assertIn("水性色素", names)
        self.assertIn("红丝绒液", names)
        self.assertIn("水性色素", data["answer"])
        self.assertIn("红丝绒液", data["answer"])

    def test_global_rag_chat_get_redirects_instead_of_parsing_as_product_id(self):
        response = self.client.get("/api/products/rag-chat", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/products")

    def test_product_rag_chat_is_scoped_to_selected_product(self):
        tea = self._add_product(
            "茶酱",
            "烘焙调味",
            54,
            "用于茶味蛋糕和奶油调味",
            "搭配奶油、蛋糕胚和坚果酱使用。",
        )
        self._add_product(
            "水性色素",
            "烘焙调色",
            18.59,
            "适合蛋糕调色",
            "上色稳定。",
        )

        response = self.client.post(f"/api/products/{tea.id}/rag-chat", json={"query": "适合什么场景"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scope"], "product")
        self.assertEqual(data["product_id"], tea.id)
        self.assertEqual([item["product_id"] for item in data["results"]], [tea.id])
        self.assertIn("根据「茶酱」的产品资料", data["answer"])
        self.assertIn("茶酱", data["answer"])
        self.assertNotIn("来源：", data["answer"])
        self.assertNotIn("已在", data["answer"])
        self.assertNotIn("水性色素", str(data))


if __name__ == "__main__":
    unittest.main()
