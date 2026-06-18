import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product, SellingPoint
from routers import products as products_router
from services import selling_point_extractor


class ProductFileApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.tmp = tempfile.TemporaryDirectory()
        self.original_product_files_dir = products_router.PRODUCT_FILES_DIR
        self.original_extract = selling_point_extractor.extract_selling_points
        self.original_sync = products_router._sync_product_index
        self.sync_calls = []
        products_router.PRODUCT_FILES_DIR = self.tmp.name
        products_router._sync_product_index = lambda product_id, db: self.sync_calls.append(product_id)
        selling_point_extractor.extract_selling_points = self._extract_points

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[products_router.get_db] = override_db
        app.include_router(products_router.router, prefix="/api/products")
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        products_router.PRODUCT_FILES_DIR = self.original_product_files_dir
        products_router._sync_product_index = self.original_sync
        selling_point_extractor.extract_selling_points = self.original_extract
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    async def _extract_points(self, file_path, product_name, category):
        return []

    def _add_product(self, name="Safe Upload Product"):
        product = Product(
            name=name,
            category="Baking",
            price=12.5,
            brand="Facai",
            status="active",
        )
        self.db.add(product)
        self.db.commit()
        return product

    def test_upload_sanitizes_client_filename_and_stays_inside_product_dir(self):
        product = self._add_product()

        response = self.client.post(
            f"/api/products/{product.id}/upload",
            files={"file": ("..\\outside<script>.md", b"file body", "text/markdown")},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        saved_path = Path(data["file_path"])
        product_dir = Path(self.tmp.name).resolve()
        self.assertEqual(os.path.commonpath([str(product_dir), str(saved_path.resolve())]), str(product_dir))
        self.assertNotIn("..", saved_path.name)
        self.assertNotIn("<", saved_path.name)
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.read_bytes(), b"file body")
        self.assertEqual(self.sync_calls, [product.id])

    def test_upload_rejects_files_over_configured_limit(self):
        product = self._add_product()
        had_limit = hasattr(products_router, "MAX_UPLOAD_SIZE")
        original_limit = getattr(products_router, "MAX_UPLOAD_SIZE", None)
        products_router.MAX_UPLOAD_SIZE = 4
        try:
            response = self.client.post(
                f"/api/products/{product.id}/upload",
                files={"file": ("too-large.md", b"12345", "text/markdown")},
            )
        finally:
            if had_limit:
                products_router.MAX_UPLOAD_SIZE = original_limit
            else:
                delattr(products_router, "MAX_UPLOAD_SIZE")

        self.assertEqual(response.status_code, 413)
        self.assertEqual(list(Path(self.tmp.name).glob("*")), [])
        self.assertEqual(self.sync_calls, [])

    def test_extract_points_syncs_product_index(self):
        product = self._add_product()
        source = Path(self.tmp.name) / "product.md"
        source.write_text("source", encoding="utf-8")
        product.info_file = str(source)
        self.db.commit()

        async def extract_points(file_path, product_name, category):
            return [{"point_type": "Core", "content": "Fresh point", "priority": 1}]

        selling_point_extractor.extract_selling_points = extract_points

        response = self.client.post(f"/api/products/{product.id}/extract-points")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sync_calls, [product.id])
        points = self.db.query(SellingPoint).filter_by(product_id=product.id).all()
        self.assertEqual([point.content for point in points], ["Fresh point"])

    def test_extract_all_points_syncs_each_successful_product(self):
        first = self._add_product("First")
        second = self._add_product("Second")
        for product in [first, second]:
            source = Path(self.tmp.name) / f"{product.id}.md"
            source.write_text("source", encoding="utf-8")
            product.info_file = str(source)
        self.db.commit()

        async def extract_points(file_path, product_name, category):
            return [{"point_type": "Core", "content": f"{product_name} point", "priority": 1}]

        selling_point_extractor.extract_selling_points = extract_points

        response = self.client.post("/api/products/extract-all-points")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sync_calls, [first.id, second.id])

    def test_delete_product_file_syncs_product_index_without_clearing_points(self):
        product = self._add_product()
        source = Path(self.tmp.name) / "product.md"
        source.write_text("source", encoding="utf-8")
        product.info_file = str(source)
        self.db.add(SellingPoint(
            product_id=product.id,
            point_type="Core",
            content="Retained point",
            priority=1,
        ))
        self.db.commit()

        response = self.client.delete(f"/api/products/{product.id}/file")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sync_calls, [product.id])
        self.db.refresh(product)
        self.assertIsNone(product.info_file)
        self.assertFalse(source.exists())
        points = self.db.query(SellingPoint).filter_by(product_id=product.id).all()
        self.assertEqual([point.content for point in points], ["Retained point"])

    def test_download_and_delete_reject_unsafe_info_file_path(self):
        product = self._add_product()
        with tempfile.TemporaryDirectory() as outside_dir:
            secret = Path(outside_dir) / "secret.txt"
            secret.write_text("do not serve", encoding="utf-8")
            product.info_file = str(secret)
            self.db.commit()

            async def fail_if_called(file_path, product_name, category):
                raise AssertionError("unsafe product files should not be extracted")

            selling_point_extractor.extract_selling_points = fail_if_called
            download = self.client.get(f"/api/products/{product.id}/download")
            extract = self.client.post(f"/api/products/{product.id}/extract-points")
            delete = self.client.delete(f"/api/products/{product.id}/file")

            self.assertEqual(download.status_code, 404)
            self.assertEqual(extract.status_code, 400)
            self.assertEqual(delete.status_code, 400)
            self.assertTrue(secret.exists())
            self.db.refresh(product)
            self.assertEqual(product.info_file, str(secret))

    def test_source_preview_returns_text_material_and_download_url(self):
        response = self.client.get(
            "/api/products/source-preview",
            params={"source": "00_产品知识总索引.md"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "00_产品知识总索引.md")
        self.assertEqual(data["preview_kind"], "text")
        self.assertTrue(data["content"].strip())
        self.assertIn("/api/products/source-download?", data["download_url"])

        download = self.client.get(data["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertGreater(len(download.content), 0)

    def test_source_preview_marks_large_binary_material_as_download_only(self):
        root = Path(__file__).resolve().parents[1]
        source_name = next((root / "资料" / "2026产品知识库").glob("*.xlsx")).name

        response = self.client.get(
            "/api/products/source-preview",
            params={"source": source_name},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], source_name)
        self.assertEqual(data["preview_kind"], "download_only")
        self.assertEqual(data["content"], "")
        self.assertIn("/api/products/source-download?", data["download_url"])

    def test_source_preview_allows_matching_uploaded_product_file(self):
        product = self._add_product()
        source = Path(self.tmp.name) / "product.md"
        source.write_text("# Uploaded source\nThis came from upload.", encoding="utf-8")
        product.info_file = str(source)
        self.db.commit()

        response = self.client.get(
            "/api/products/source-preview",
            params={"source": source.name, "product_id": product.id},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], source.name)
        self.assertEqual(data["preview_kind"], "text")
        self.assertIn("This came from upload.", data["content"])

        download = self.client.get(
            "/api/products/source-download",
            params={"source": source.name, "product_id": product.id},
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, source.read_bytes())

    def test_source_preview_rejects_unsafe_or_unknown_sources(self):
        for unsafe in ["../secret.md", r"..\\secret.md", str(Path(self.tmp.name) / "product.md")]:
            response = self.client.get("/api/products/source-preview", params={"source": unsafe})
            self.assertEqual(response.status_code, 400)

        missing = self.client.get("/api/products/source-preview", params={"source": "not-a-source.md"})
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
