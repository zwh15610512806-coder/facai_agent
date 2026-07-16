import asyncio
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Product
from routers import scripts as scripts_router
from schemas import ScriptRewriteRequest


class FakeRewriter:
    def __init__(self):
        self.include_shot_design = None

    async def rewrite(self, *args, include_shot_design=True, **kwargs):
        self.include_shot_design = include_shot_design
        return "改写后的脚本"


class RewriteShotDesignApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        product = Product(name="测试产品", category="烘焙调味", price=18.8, brand="法采")
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self.product = product
        self.original_rewriter = scripts_router.script_rewriter

    def tearDown(self):
        scripts_router.script_rewriter = self.original_rewriter
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_rewrite_endpoint_passes_shot_design_choice(self):
        fake = FakeRewriter()
        scripts_router.script_rewriter = fake
        request = ScriptRewriteRequest(
            original_script="老板们看过来，这个产品很适合门店用。",
            product_id=self.product.id,
            include_shot_design=False,
        )

        asyncio.run(scripts_router.rewrite_script(request, db=self.db))

        self.assertFalse(fake.include_shot_design)

    def test_rewrite_endpoint_defaults_to_plain_spoken_copy(self):
        fake = FakeRewriter()
        scripts_router.script_rewriter = fake
        request = ScriptRewriteRequest(
            original_script="老板们看过来，这个产品很适合门店用。",
            product_id=self.product.id,
        )

        asyncio.run(scripts_router.rewrite_script(request, db=self.db))

        self.assertFalse(fake.include_shot_design)

    def test_rewrite_endpoint_preserves_explicit_shot_design_request(self):
        fake = FakeRewriter()
        scripts_router.script_rewriter = fake
        request = ScriptRewriteRequest(
            original_script="老板们看过来，这个产品很适合门店用。",
            product_id=self.product.id,
            include_shot_design=True,
        )

        asyncio.run(scripts_router.rewrite_script(request, db=self.db))

        self.assertTrue(fake.include_shot_design)


if __name__ == "__main__":
    unittest.main()
