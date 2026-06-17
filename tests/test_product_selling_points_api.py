import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product, SellingPoint
from routers import products as products_router
from services.product_detail import HIDDEN_SELLING_POINT_TYPE


class ProductSellingPointApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.original_sync = products_router._sync_product_index
        self.sync_calls = []
        products_router._sync_product_index = lambda product_id, db: self.sync_calls.append(product_id)

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
        products_router._sync_product_index = self.original_sync
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_update_selling_point_saves_edited_content(self):
        product = Product(
            name="袋装刀叉",
            category="烘焙配件",
            price=12,
            brand="法采",
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        point = SellingPoint(
            product_id=product.id,
            point_type="基础功能",
            content="旧卖点",
            priority=1,
        )
        self.db.add(point)
        self.db.commit()

        response = self.client.put(
            f"/api/products/{product.id}/selling-points/{point.id}",
            json={"point_type": "基础功能", "content": "编辑后的卖点", "priority": 2},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["content"], "编辑后的卖点")
        self.assertEqual(data["priority"], 2)

        self.db.refresh(point)
        self.assertEqual(point.content, "编辑后的卖点")
        self.assertEqual(point.priority, 2)

    def test_update_selling_point_rejects_blank_content(self):
        product = Product(
            name="盒装刀叉",
            category="烘焙配件",
            price=18,
            brand="法采",
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        point = SellingPoint(
            product_id=product.id,
            point_type="基础功能",
            content="旧卖点",
            priority=1,
        )
        self.db.add(point)
        self.db.commit()

        response = self.client.put(
            f"/api/products/{product.id}/selling-points/{point.id}",
            json={"content": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.db.refresh(point)
        self.assertEqual(point.content, "旧卖点")

    def test_hide_material_selling_point_persists_delete_marker(self):
        product = Product(
            name="茶酱",
            category="烘焙调味",
            price=54,
            brand="法采",
            status="active",
        )
        self.db.add(product)
        self.db.commit()

        response = self.client.post(
            f"/api/products/{product.id}/selling-points/hide",
            json={"point_type": "门店方案", "content": "不要展示的资料块", "priority": 3},
        )

        self.assertEqual(response.status_code, 200)
        marker = self.db.query(SellingPoint).filter_by(product_id=product.id).one()
        self.assertEqual(marker.point_type, HIDDEN_SELLING_POINT_TYPE)
        self.assertEqual(marker.priority, 3)

    def test_delete_selling_point_hides_underlying_material_block(self):
        product = Product(
            name="茶酱",
            category="烘焙调味",
            price=54,
            brand="法采",
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        point = SellingPoint(
            product_id=product.id,
            point_type="门店方案",
            content="编辑后的资料块",
            priority=2,
        )
        self.db.add(point)
        self.db.commit()

        response = self.client.delete(
            f"/api/products/{product.id}/selling-points/{point.id}",
        )

        self.assertEqual(response.status_code, 200)
        markers = self.db.query(SellingPoint).filter_by(product_id=product.id).all()
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].point_type, HIDDEN_SELLING_POINT_TYPE)
        self.assertEqual(markers[0].priority, 2)
        self.assertEqual(self.sync_calls, [product.id])

    def test_hidden_selling_points_are_not_listed(self):
        product = Product(
            name="茶酱",
            category="烘焙调味",
            price=54,
            brand="法采",
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        visible = SellingPoint(
            product_id=product.id,
            point_type="门店方案",
            content="可展示卖点",
            priority=1,
        )
        hidden = SellingPoint(
            product_id=product.id,
            point_type=HIDDEN_SELLING_POINT_TYPE,
            content="hidden",
            priority=2,
        )
        useless = SellingPoint(
            product_id=product.id,
            point_type="资料标题",
            content="法采·茶酱产品——手卡；0.86",
            priority=3,
        )
        self.db.add_all([visible, hidden, useless])
        self.db.commit()

        response = self.client.get(f"/api/products/{product.id}/selling-points")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["content"], "可展示卖点")

    def test_create_product_syncs_product_index(self):
        response = self.client.post(
            "/api/products/",
            json={
                "name": "Index Sync Product",
                "category": "Baking",
                "price": 12.5,
                "brand": "Facai",
                "selling_points": [
                    {"point_type": "Core", "content": "Fresh point", "priority": 1}
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        product_id = response.json()["id"]
        self.assertEqual(self.sync_calls, [product_id])

    def test_add_selling_point_syncs_product_index(self):
        product = Product(
            name="Index Sync Selling Point",
            category="Baking",
            price=12,
            brand="Facai",
            status="active",
        )
        self.db.add(product)
        self.db.commit()

        response = self.client.post(
            f"/api/products/{product.id}/selling-points",
            params={"point_type": "Core", "content": "Added point", "priority": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sync_calls, [product.id])


if __name__ == "__main__":
    unittest.main()
