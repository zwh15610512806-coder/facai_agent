import asyncio
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Product, ViralScript
from routers import scripts as scripts_router
from schemas import ScriptGenerateRequest
from services.script_generator import ScriptGenerator


class FakeTemplateLibraryGenerator:
    def __init__(self):
        self.high_only_called = False
        self.library_called = False
        self.include_shot_design = None

    def get_model_name(self):
        return "fake-model"

    def find_similar_scripts(self, *args, **kwargs):
        raise AssertionError("empty video type should not use typed similar-script search")

    def find_high_conversion_scripts(self, product, db, limit=5):
        self.high_only_called = True
        return [
            {
                "title": "High conversion source",
                "content": "（口播画面）高成交模板脚本",
                "video_type": "需求类",
                "category": product["category"],
                "tags": "",
                "performance": None,
                "is_high_conversion": True,
            }
        ]

    async def generate_from_library(self, product, video_type, reference_scripts, tone="活泼", extra_requirements=None):
        self.library_called = True
        assert video_type == "高成交模板库"
        assert reference_scripts
        assert all(script["is_high_conversion"] for script in reference_scripts)
        return "（口播画面）根据高成交模板库生成的脚本"

    async def generate(self, *args, **kwargs):
        raise AssertionError("empty video type should not fall back to free generation")

    async def generate_from_library(
        self,
        product,
        video_type,
        reference_scripts,
        tone="活泼",
        extra_requirements=None,
        include_shot_design=None,
    ):
        self.library_called = True
        self.include_shot_design = include_shot_design
        assert video_type == "高成交模板库"
        assert reference_scripts
        assert all(script["is_high_conversion"] for script in reference_scripts)
        return "根据高成交模板库生成的脚本"


class GenerateWithoutVideoTypeApiTests(unittest.TestCase):
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
        self.original_generator = scripts_router.generator

    def tearDown(self):
        scripts_router.generator = self.original_generator
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_generate_without_video_type_forces_template_high_conversion_library(self):
        fake = FakeTemplateLibraryGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(product_id=self.product.id, engine="deepseek", video_type=None)

        response = asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.high_only_called)
        self.assertTrue(fake.library_called)
        self.assertEqual(response.video_type, "高成交模板库")
        self.assertIn("高成交模板库", self.db.query(scripts_router.GeneratedScript).first().video_type)


    def test_generate_request_defaults_to_no_shot_design(self):
        request = ScriptGenerateRequest(product_id=self.product.id)

        self.assertFalse(request.include_shot_design)

    def test_generate_passes_shot_design_choice_to_template_library(self):
        fake = FakeTemplateLibraryGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(
            product_id=self.product.id,
            engine="template",
            video_type=None,
            include_shot_design=True,
        )

        asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.include_shot_design)


class ScriptGeneratorHighConversionSearchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add_all([
            ViralScript(category="烘焙调味", video_type="需求类", title="普通脚本", script_content="普通脚本内容", is_high_conversion=0),
            ViralScript(category="烘焙调味", video_type="机制类", title="高成交脚本A", script_content="高成交脚本内容A", is_high_conversion=1),
            ViralScript(category="烘焙夹心", video_type="场景类", title="高成交脚本B", script_content="高成交脚本内容B", is_high_conversion=1),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_high_conversion_search_never_returns_normal_scripts(self):
        scripts = ScriptGenerator().find_high_conversion_scripts(
            {"name": "调味果酱", "category": "烘焙调味"},
            self.db,
            limit=5,
        )

        self.assertEqual([script["title"] for script in scripts], ["高成交脚本A", "高成交脚本B"])
        self.assertTrue(all(script["is_high_conversion"] for script in scripts))


if __name__ == "__main__":
    unittest.main()
