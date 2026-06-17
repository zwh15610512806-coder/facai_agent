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
        self.assertIn("水性色素", data["answer"])
        self.assertNotIn("姐妹们", data["answer"])

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
        self.assertIn("茶酱", data["answer"])
        self.assertNotIn("水性色素", str(data))


if __name__ == "__main__":
    unittest.main()
