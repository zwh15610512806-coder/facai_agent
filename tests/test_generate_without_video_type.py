import asyncio
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Product, ReferenceScript, SellingPoint, ViralScript
from routers import scripts as scripts_router
from schemas import ScriptGenerateRequest
from services.script_generator import ScriptGenerationError, ScriptGenerator


class FakeTemplateLibraryGenerator:
    def __init__(self):
        self.high_only_called = False
        self.library_called = False
        self.include_shot_design = None
        self.product = None

    def get_model_name(self, interface_key="script_generate"):
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
        self.product = product
        self.include_shot_design = include_shot_design
        assert video_type == "高成交模板库"
        assert reference_scripts
        assert all(script["is_high_conversion"] for script in reference_scripts)
        return "根据高成交模板库生成的脚本"


class FakeFailingTemplateLibraryGenerator(FakeTemplateLibraryGenerator):
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
        raise ScriptGenerationError("模板库改写模型调用失败：provider unavailable", status_code=503)


class FakeEmptyTemplateLibraryGenerator(FakeTemplateLibraryGenerator):
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
        return ""


class FakeDeepSeekGenerator:
    def __init__(self):
        self.similar_called = False
        self.type_structure_called = False
        self.high_only_called = False
        self.generate_called = False
        self.reference_scripts = None
        self.template = None
        self.video_type = None
        self.product = None

    def get_model_name(self, interface_key="script_generate"):
        return "fake-model"

    def find_similar_scripts(self, product, video_type, db, limit=3):
        self.similar_called = True
        return [
            {
                "title": "Legacy similar search should not be used by AI generation",
                "content": "旧相似脚本检索结果不应该进入 AI生成",
                "video_type": video_type,
                "category": product["category"],
                "tags": "",
                "performance": None,
                "is_high_conversion": True,
            }
        ]

    def find_type_structure_scripts(self, video_type, db, limit=3):
        self.type_structure_called = True
        return [
            {
                "title": "同类型机制脚本",
                "content": "先用价格机制开头，再讲门店囤货痛点，最后引导左下角下单。",
                "video_type": video_type,
                "category": "烘焙配件",
                "tags": "机制,囤货",
                "performance": None,
                "is_high_conversion": True,
            }
        ]

    def find_high_conversion_scripts(self, product, db, limit=5):
        self.high_only_called = True
        return []

    async def generate_from_library(self, *args, **kwargs):
        raise AssertionError("explicit DeepSeek generation should not use template-library rewrite")

    async def generate(
        self,
        product,
        template,
        video_type,
        tone="活泼",
        extra_requirements=None,
        reference_scripts=None,
        include_shot_design=False,
    ):
        self.generate_called = True
        self.product = product
        self.template = template
        self.reference_scripts = reference_scripts
        self.video_type = video_type
        return "DeepSeek 只结合产品资料和跑量逻辑生成的脚本"


class FakeEmptyDeepSeekGenerator(FakeDeepSeekGenerator):
    async def generate(
        self,
        product,
        template,
        video_type,
        tone="活泼",
        extra_requirements=None,
        reference_scripts=None,
        include_shot_design=False,
    ):
        self.generate_called = True
        self.product = product
        self.template = template
        self.reference_scripts = reference_scripts
        self.video_type = video_type
        return ""


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
        self.db.add(SellingPoint(
            product_id=product.id,
            point_type="使用场景",
            content="门店做糖珠蛋糕、甜品杯和儿童款装饰时使用",
            priority=1,
        ))
        self.db.commit()
        self.product = product
        self.original_generator = scripts_router.generator

    def tearDown(self):
        scripts_router.generator = self.original_generator
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_ai_generation_without_video_type_uses_ai_inferred_type_without_template_library(self):
        fake = FakeDeepSeekGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(product_id=self.product.id, engine="deepseek", video_type=None)

        response = asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.generate_called)
        self.assertFalse(fake.similar_called)
        self.assertFalse(fake.type_structure_called)
        self.assertFalse(fake.high_only_called)
        self.assertEqual(fake.reference_scripts, [])
        self.assertIsNone(fake.template)
        self.assertEqual(fake.video_type, "AI智能生成")
        self.assertIn("profile_sections", fake.product)
        self.assertTrue(fake.product["profile_sections"])
        section_titles = {section["title"] for section in fake.product["profile_sections"]}
        self.assertIn("使用场景", section_titles)
        self.assertEqual(response.video_type, "AI智能生成")
        record = self.db.query(scripts_router.GeneratedScript).first()
        self.assertEqual(record.video_type, "AI智能生成")
        self.assertEqual(record.ai_model, "AI生成 · fake-model")

    def test_template_generation_without_video_type_forces_template_high_conversion_library(self):
        fake = FakeTemplateLibraryGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(product_id=self.product.id, engine="template", video_type=None)

        response = asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.high_only_called)
        self.assertTrue(fake.library_called)
        self.assertNotIn("profile_sections", fake.product)
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

    def test_template_library_generation_error_returns_clear_error_without_saving_record(self):
        fake = FakeFailingTemplateLibraryGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(product_id=self.product.id, engine="template", video_type=None)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.library_called)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("模板库改写失败", caught.exception.detail)
        self.assertIsNone(self.db.query(scripts_router.GeneratedScript).first())

    def test_template_library_empty_result_returns_clear_error_without_saving_record(self):
        fake = FakeEmptyTemplateLibraryGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(product_id=self.product.id, engine="template", video_type=None)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.library_called)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("模板库改写失败", caught.exception.detail)
        self.assertIsNone(self.db.query(scripts_router.GeneratedScript).first())

    def test_explicit_ai_generation_uses_same_type_script_structure_references(self):
        fake = FakeDeepSeekGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(
            product_id=self.product.id,
            engine="deepseek",
            video_type="机制类",
        )

        response = asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.generate_called)
        self.assertFalse(fake.similar_called)
        self.assertTrue(fake.type_structure_called)
        self.assertFalse(fake.high_only_called)
        self.assertEqual(fake.reference_scripts[0]["title"], "同类型机制脚本")
        self.assertEqual(fake.video_type, "机制类")
        self.assertIsNone(fake.template)
        self.assertIn("profile_sections", fake.product)
        self.assertTrue(fake.product["profile_sections"])
        self.assertEqual(response.script_content, "DeepSeek 只结合产品资料和跑量逻辑生成的脚本")
        self.assertEqual(self.db.query(scripts_router.GeneratedScript).first().ai_model, "AI生成 · fake-model")

    def test_ai_generation_empty_model_result_returns_error_without_saving_record(self):
        fake = FakeEmptyDeepSeekGenerator()
        scripts_router.generator = fake
        request = ScriptGenerateRequest(
            product_id=self.product.id,
            engine="deepseek",
            video_type="AI智能生成",
        )

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(scripts_router.generate_script(request, db=self.db))

        self.assertTrue(fake.generate_called)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("AI生成失败", caught.exception.detail)
        self.assertIsNone(self.db.query(scripts_router.GeneratedScript).first())


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

    def test_type_structure_search_uses_only_exact_video_type_and_prioritizes_high_conversion(self):
        self.db.add_all([
            ViralScript(
                category="烘焙调味",
                video_type="机制类",
                title="普通机制脚本",
                script_content="普通机制脚本内容",
                is_high_conversion=0,
            ),
            ReferenceScript(
                video_type="机制类",
                title="参考机制脚本",
                script_content="参考库机制脚本内容",
                is_high_conversion=1,
            ),
            ViralScript(
                category="烘焙调味",
                video_type="需求类",
                title="高成交需求脚本",
                script_content="需求类不应该出现",
                is_high_conversion=1,
            ),
        ])
        self.db.commit()

        scripts = ScriptGenerator().find_type_structure_scripts("机制类", self.db, limit=3)

        self.assertEqual(3, len(scripts))
        self.assertTrue(all(script["video_type"] == "机制类" for script in scripts))
        self.assertEqual(["高成交脚本A", "参考机制脚本", "普通机制脚本"], [script["title"] for script in scripts])
        self.assertNotIn("高成交需求脚本", {script["title"] for script in scripts})


if __name__ == "__main__":
    unittest.main()
