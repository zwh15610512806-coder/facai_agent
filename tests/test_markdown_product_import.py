import unittest
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product, SellingPoint
from routers import import_data as import_router


ROOT = Path(__file__).resolve().parents[1]


class MarkdownProductParserTests(unittest.TestCase):
    def test_parse_markdown_product_fields_and_selling_points(self):
        from services.product_markdown_importer import parse_product_markdown

        parsed = parse_product_markdown(
            """---
name: Matcha Cream
category: Baking Filling
price: 29.8
brand: Facai
---
# Fallback Title

Description paragraph for the product.

## Selling Points
- Smooth texture
- Stable for piping
""",
            filename="ignored.md",
        )

        self.assertEqual(parsed.name, "Matcha Cream")
        self.assertEqual(parsed.category, "Baking Filling")
        self.assertEqual(parsed.price, 29.8)
        self.assertEqual(parsed.brand, "Facai")
        self.assertIn("Description paragraph", parsed.description)
        self.assertEqual([point.content for point in parsed.selling_points], ["Smooth texture", "Stable for piping"])
        self.assertEqual(parsed.pending_fields, [])

    def test_missing_required_fields_are_marked_pending(self):
        from services.product_markdown_importer import parse_product_markdown

        parsed = parse_product_markdown("# New Cake Tool\n\nUseful product copy.", filename="new-cake-tool.md")

        self.assertEqual(parsed.name, "New Cake Tool")
        self.assertEqual(parsed.category, "待更新")
        self.assertEqual(parsed.price, 0.0)
        self.assertEqual(parsed.pending_fields, ["category", "price"])


class MarkdownProductImportApiTests(unittest.TestCase):
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
        self.original_product_files_dir = import_router.PRODUCT_FILES_DIR
        self.product_files_tmp = tempfile.TemporaryDirectory()
        import_router._sync_product_index = lambda product_id, db: None
        import_router.PRODUCT_FILES_DIR = self.product_files_tmp.name

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[import_router.get_db] = override_db
        app.include_router(import_router.router, prefix="/api/import")
        self.client = TestClient(app)

    def tearDown(self):
        import_router._sync_product_index = self.original_sync
        import_router.PRODUCT_FILES_DIR = self.original_product_files_dir
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.product_files_tmp.cleanup()

    def test_markdown_upload_creates_product_with_pending_fields(self):
        response = self.client.post(
            "/api/import/markdown",
            files=[
                (
                    "files",
                    (
                        "new-product.md",
                        "# New Product\n\n## Selling Points\n- Easy to use",
                        "text/markdown",
                    ),
                )
            ],
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["updated"], 0)
        self.assertEqual(data["products"][0]["action"], "created")
        self.assertEqual(data["products"][0]["pending_fields"], ["category", "price"])

        product = self.db.query(Product).one()
        self.assertEqual(product.name, "New Product")
        self.assertEqual(product.category, "待更新")
        self.assertEqual(product.price, 0.0)
        self.assertEqual(product.pending_fields, ["category", "price"])
        self.assertTrue(product.info_file.endswith("new-product.md"))
        self.assertEqual(self.db.query(SellingPoint).count(), 1)

    def test_markdown_upload_rejects_files_over_configured_limit(self):
        had_limit = hasattr(import_router, "MAX_UPLOAD_SIZE")
        original_limit = getattr(import_router, "MAX_UPLOAD_SIZE", None)
        import_router.MAX_UPLOAD_SIZE = 4
        try:
            response = self.client.post(
                "/api/import/markdown",
                files=[("files", ("too-large.md", "12345", "text/markdown"))],
            )
        finally:
            if had_limit:
                import_router.MAX_UPLOAD_SIZE = original_limit
            else:
                delattr(import_router, "MAX_UPLOAD_SIZE")

        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_markdown_upload_rejects_too_many_files(self):
        original_limit = import_router.MAX_MARKDOWN_UPLOAD_FILES
        import_router.MAX_MARKDOWN_UPLOAD_FILES = 2
        try:
            response = self.client.post(
                "/api/import/markdown",
                files=[
                    ("files", (f"product-{index}.md", f"# Product {index}", "text/markdown"))
                    for index in range(3)
                ],
            )
        finally:
            import_router.MAX_MARKDOWN_UPLOAD_FILES = original_limit

        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_same_name_markdown_updates_existing_without_clearing_blank_fields(self):
        product = Product(
            name="Existing Product",
            category="Old Category",
            price=12.5,
            brand="Old Brand",
            description="Old description",
            status="active",
            pending_fields=["price"],
        )
        self.db.add(product)
        self.db.flush()
        self.db.add(SellingPoint(product_id=product.id, point_type="卖点", content="Old point", priority=1))
        self.db.commit()

        response = self.client.post(
            "/api/import/markdown",
            files=[
                (
                    "files",
                    (
                        "existing.md",
                        """# Existing Product

品牌：New Brand
价格：18.8

## 卖点
- New point A
- New point B
""",
                        "text/markdown",
                    ),
                )
            ],
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["updated"], 1)
        self.assertEqual(data["products"][0]["action"], "updated")

        products = self.db.query(Product).all()
        self.assertEqual(len(products), 1)
        updated = products[0]
        self.assertEqual(updated.category, "Old Category")
        self.assertEqual(updated.price, 18.8)
        self.assertEqual(updated.brand, "New Brand")
        self.assertEqual(updated.description, "Old description")
        self.assertEqual(updated.pending_fields, [])
        self.assertEqual(
            [point.content for point in self.db.query(SellingPoint).order_by(SellingPoint.priority).all()],
            ["New point A", "New point B"],
        )

    def test_same_name_markdown_without_selling_points_keeps_existing_points(self):
        product = Product(name="Keep Points", category="Tools", price=8.0, status="active", pending_fields=[])
        self.db.add(product)
        self.db.flush()
        self.db.add(SellingPoint(product_id=product.id, point_type="卖点", content="Existing point", priority=1))
        self.db.commit()

        response = self.client.post(
            "/api/import/markdown",
            files=[("files", ("keep.md", "# Keep Points\n\n品牌：Updated", "text/markdown"))],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(self.db.query(SellingPoint).count(), 1)
        self.assertEqual(self.db.query(SellingPoint).one().content, "Existing point")


class MarkdownProductImportUiTests(unittest.TestCase):
    def test_import_page_accepts_markdown_and_routes_to_markdown_endpoint(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn(".md,.markdown", page)
        self.assertIn("/api/import/markdown", page)
        self.assertIn("uploadProductFiles", page)
        self.assertIn("multiple", page)
        self.assertIn("/api/import/csv", page)
        self.assertIn("/api/import/excel", page)

    def test_import_page_renders_detailed_product_import_results(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn("function renderProductImportResult", page)
        self.assertIn("renderResultList('products'", page)
        self.assertIn("renderResultList('warnings'", page)
        self.assertIn("renderResultList('errors'", page)
        self.assertIn("result-detail-list", page)
        self.assertIn("escHtml", page)


if __name__ == "__main__":
    unittest.main()
