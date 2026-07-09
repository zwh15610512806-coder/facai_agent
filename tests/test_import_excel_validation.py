from io import BytesIO
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product
from routers import import_data as import_router


def _xlsx_bytes(rows):
    import pandas as pd

    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


class ImportExcelValidationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.original_sync = import_router._sync_product_index
        import_router._sync_product_index = lambda product_id, db: None
        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[import_router.get_db] = override_db
        app.include_router(import_router.router, prefix="/api/import")
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        import_router._sync_product_index = self.original_sync
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_excel_upload_rejects_legacy_xls_extension(self):
        response = self.client.post(
            "/api/import/excel",
            files={"file": ("products.xls", b"not an xlsx file", "application/vnd.ms-excel")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(".xlsx", response.json()["detail"])

    def test_excel_import_skips_blank_category_instead_of_string_nan(self):
        content = _xlsx_bytes([{
            "name": "空品类产品",
            "category": None,
            "price": 12.5,
        }])

        response = self.client.post(
            "/api/import/excel",
            files={
                "file": (
                    "products.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], 0)
        self.assertIn("品类或价格缺失", body["errors"][0])
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_excel_import_updates_existing_product_price(self):
        product = Product(
            name="浅柔色素",
            category="烘焙调色",
            price=0,
            pending_fields=["price"],
            status="active",
        )
        self.db.add(product)
        self.db.commit()
        content = _xlsx_bytes([{
            "name": "浅柔色素",
            "category": "烘焙调色",
            "price": 38.6,
            "original_price": 45,
        }])

        response = self.client.post(
            "/api/import/excel",
            files={
                "file": (
                    "products.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], 1)
        self.assertEqual(body["skipped"], 0)
        self.db.refresh(product)
        self.assertEqual(product.price, 38.6)
        self.assertEqual(product.original_price, 45)
        self.assertNotIn("price", product.pending_fields or [])


if __name__ == "__main__":
    unittest.main()
