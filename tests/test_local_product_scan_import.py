import tempfile
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product, SellingPoint
from routers import import_data as import_router
from services import selling_point_extractor


ROOT = Path(__file__).resolve().parents[1]


class ImportPageLocalProductScanTests(unittest.TestCase):
    def test_import_page_exposes_local_product_scan(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn('id="btnScanLocalProducts"', page)
        self.assertIn("扫描本地产品资料", page)
        self.assertIn("scanLocalProducts", page)
        self.assertIn("pollLocalProductScanStatus", page)
        self.assertIn("renderLocalProductScanState", page)
        self.assertIn("/api/import/scan-local-products", page)
        self.assertIn("/api/import/scan-local-products/status", page)


class LocalProductScanApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local_source = Path(self.tmp.name) / "source"
        self.local_source.mkdir()
        self.product_files_dir = Path(self.tmp.name) / "product_files"
        self.product_files_dir.mkdir()

        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.sync_calls = []

        self.original_source_dir = getattr(import_router, "LOCAL_PRODUCT_SOURCE_DIR", None)
        self.had_source_dir = hasattr(import_router, "LOCAL_PRODUCT_SOURCE_DIR")
        self.original_session_factory = getattr(import_router, "LOCAL_PRODUCT_SCAN_SESSION_FACTORY", None)
        self.had_session_factory = hasattr(import_router, "LOCAL_PRODUCT_SCAN_SESSION_FACTORY")
        self.original_product_files_dir = import_router.PRODUCT_FILES_DIR
        self.original_sync = import_router._sync_product_index
        self.original_extract = selling_point_extractor.extract_selling_points

        import_router.LOCAL_PRODUCT_SOURCE_DIR = str(self.local_source)
        import_router.LOCAL_PRODUCT_SCAN_SESSION_FACTORY = self.Session
        import_router.PRODUCT_FILES_DIR = str(self.product_files_dir)
        import_router._sync_product_index = lambda product_id, db: self.sync_calls.append(product_id)
        selling_point_extractor.extract_selling_points = self._extract_points
        if hasattr(import_router, "_reset_local_product_scan_state"):
            import_router._reset_local_product_scan_state()

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
        if self.had_source_dir:
            import_router.LOCAL_PRODUCT_SOURCE_DIR = self.original_source_dir
        elif hasattr(import_router, "LOCAL_PRODUCT_SOURCE_DIR"):
            delattr(import_router, "LOCAL_PRODUCT_SOURCE_DIR")
        if self.had_session_factory:
            import_router.LOCAL_PRODUCT_SCAN_SESSION_FACTORY = self.original_session_factory
        elif hasattr(import_router, "LOCAL_PRODUCT_SCAN_SESSION_FACTORY"):
            delattr(import_router, "LOCAL_PRODUCT_SCAN_SESSION_FACTORY")
        import_router.PRODUCT_FILES_DIR = self.original_product_files_dir
        import_router._sync_product_index = self.original_sync
        selling_point_extractor.extract_selling_points = self.original_extract
        if hasattr(import_router, "_reset_local_product_scan_state"):
            import_router._reset_local_product_scan_state()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    async def _extract_points(self, file_path, product_name, category):
        return [{"point_type": "资料", "content": f"{product_name} 附件卖点", "priority": 1}]

    def _wait_for_scan(self):
        deadline = time.time() + 10
        last_status = None
        while time.time() < deadline:
            response = self.client.get("/api/import/scan-local-products/status")
            self.assertEqual(response.status_code, 200)
            last_status = response.json()
            data = last_status["data"]
            if not data["is_running"]:
                return data
            time.sleep(0.05)
        self.fail(f"local product scan did not finish: {last_status}")

    def _start_scan(self):
        response = self.client.post("/api/import/scan-local-products")
        self.assertEqual(response.status_code, 200)
        return self._wait_for_scan()

    def test_scan_recursively_imports_markdown_products_and_syncs_index(self):
        nested = self.local_source / "调味系列"
        nested.mkdir()
        source = nested / "新品果酱.md"
        source.write_text(
            """---
name: 新品果酱
category: 烘焙调味
price: 27.5
brand: 法采
---
# 新品果酱

## 卖点
- 果香稳定，适合夹心和抹面
""",
            encoding="utf-8",
        )

        status = self._start_scan()

        self.assertEqual(status["total"], 1)
        self.assertEqual(status["created"], 1)
        self.assertEqual(status["updated"], 0)
        self.assertEqual(status["error_count"], 0)
        product = self.db.query(Product).one()
        self.assertEqual(product.name, "新品果酱")
        self.assertEqual(product.category, "烘焙调味")
        self.assertEqual(product.price, 27.5)
        self.assertTrue(product.info_file)
        self.assertTrue(Path(product.info_file).exists())
        self.assertEqual(self.db.query(SellingPoint).count(), 1)
        self.assertEqual(self.sync_calls, [product.id])
        self.assertEqual(status["ids"], [product.id])

    def test_scan_imports_csv_products_with_existing_rules(self):
        csv_path = self.local_source / "products.csv"
        csv_path.write_text(
            "name,category,price,brand,selling_point_type,selling_point_content,selling_point_priority\n"
            "CSV产品,烘焙配件,12.8,法采,场景,适合门店日常补货,1\n",
            encoding="utf-8-sig",
        )

        status = self._start_scan()

        self.assertEqual(status["total"], 1)
        self.assertEqual(status["created"], 1)
        product = self.db.query(Product).one()
        self.assertEqual(product.name, "CSV产品")
        self.assertEqual(product.category, "烘焙配件")
        self.assertEqual(self.db.query(SellingPoint).one().content, "适合门店日常补货")
        self.assertEqual(self.sync_calls, [product.id])

    def test_scan_attaches_matching_file_without_overwriting_existing_info_file(self):
        attach_product = Product(name="附件产品", category="烘焙配件", price=9.9, status="active")
        kept_product = Product(name="保留资料", category="烘焙调味", price=18.0, status="active")
        self.db.add_all([attach_product, kept_product])
        self.db.flush()
        existing = self.product_files_dir / "existing.md"
        existing.write_text("old source", encoding="utf-8")
        kept_product.info_file = str(existing)
        self.db.commit()

        (self.local_source / "附件产品.pdf").write_bytes(b"pdf bytes")
        (self.local_source / "保留资料.pdf").write_bytes(b"new bytes")

        status = self._start_scan()

        self.assertEqual(status["total"], 2)
        self.assertEqual(status["attached"], 1)
        self.assertGreaterEqual(status["skipped"], 1)
        self.db.refresh(attach_product)
        self.db.refresh(kept_product)
        self.assertTrue(attach_product.info_file)
        self.assertTrue(Path(attach_product.info_file).exists())
        self.assertEqual(kept_product.info_file, str(existing))
        points = self.db.query(SellingPoint).filter_by(product_id=attach_product.id).all()
        self.assertEqual([point.content for point in points], ["附件产品 附件卖点"])
        self.assertIn(attach_product.id, self.sync_calls)
        self.assertNotIn(kept_product.id, self.sync_calls)

    def test_second_scan_does_not_duplicate_products_or_attachment_points(self):
        (self.local_source / "重复产品.md").write_text(
            "# 重复产品\n\n品类：烘焙夹心\n价格：19\n\n## 卖点\n- 第一次卖点",
            encoding="utf-8",
        )

        first = self._start_scan()
        self.assertEqual(first["created"], 1)
        second = self._start_scan()

        self.assertEqual(second["created"], 0)
        self.assertEqual(self.db.query(Product).count(), 1)
        product = self.db.query(Product).one()
        points = self.db.query(SellingPoint).filter_by(product_id=product.id).all()
        self.assertEqual(len(points), 1)

    def test_scan_rejects_inaccessible_source_directory(self):
        import_router.LOCAL_PRODUCT_SOURCE_DIR = str(self.local_source / "missing")

        response = self.client.post("/api/import/scan-local-products")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_scan_empty_directory_finishes_without_error(self):
        status = self._start_scan()

        self.assertEqual(status["total"], 0)
        self.assertEqual(status["processed"], 0)
        self.assertEqual(status["error_count"], 0)
        self.assertIn("未发现", status["message"])


if __name__ == "__main__":
    unittest.main()
