import asyncio
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import GeneratedScript, Product, ReferenceScript, ScriptTemplate, ViralScript
from routers import scripts as scripts_router
from schemas import ScriptGenerateRequest
from services.script_generator import ScriptGenerator


ROOT = Path(__file__).resolve().parents[1]


class CapturingTemplateGenerator:
    def __init__(self):
        self.called = False
        self.source_script = None

    def get_model_name(self, interface_key="script_generate"):
        return "fake-model"

    async def generate_from_library(
        self,
        product,
        video_type,
        template,
        source_script,
        tone="活泼",
        extra_requirements=None,
        include_shot_design=False,
    ):
        self.called = True
        self.source_script = source_script
        return "根据结构模板和具体脚本重新创作的内容"


class CapturingAI:
    is_available = True

    def __init__(self):
        self.messages = []

    async def chat(self, messages, temperature=0.75):
        self.messages = messages
        return "急单打包先看操作效率，这款产品拿取更顺手。"


class TemplateRewriteSourceRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.product = Product(name="袋装刀叉", category="烘焙配件", price=0.64, brand="法采")
        self.template = ScriptTemplate(
            name="机制类结构模板",
            video_type="机制类",
            structure={"opening": "具体动作", "proof": "产品证明", "cta": "自然承接"},
            hook_templates=["从门店打包动作切入"],
            cta_templates=["自然引导下单"],
            example_script="结构模板示例",
        )
        self.db.add_all([self.product, self.template])
        self.db.commit()
        self.db.refresh(self.product)
        self.original_generator = scripts_router.generator

    def tearDown(self):
        scripts_router.generator = self.original_generator
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _generate(self, video_type="机制类"):
        fake = CapturingTemplateGenerator()
        scripts_router.generator = fake
        response = asyncio.run(scripts_router.generate_script(
            ScriptGenerateRequest(
                product_id=self.product.id,
                engine="template",
                video_type=video_type,
            ),
            db=self.db,
        ))
        return response, fake

    def test_same_type_concrete_script_is_used_and_red_box_title_is_snapshotted(self):
        self.db.add_all([
            ViralScript(
                category="烘焙配件",
                video_type="场景类",
                title="不应选中的其他类型脚本",
                script_content="其他类型内容",
            ),
            ReferenceScript(
                video_type="机制类",
                title="夹心饼 / 脚本参考 / 7.8价格（性价比）+丰富均衡 / 文案",
                script_content="先讲机制，再给产品证明，最后自然承接下单。",
            ),
        ])
        self.db.commit()

        response, fake = self._generate()

        self.assertTrue(fake.called)
        self.assertEqual(fake.source_script["title"], "夹心饼 / 脚本参考 / 7.8价格（性价比）+丰富均衡 / 文案")
        self.assertEqual(fake.source_script["source"], "other")
        self.assertEqual(response.source_script_title, fake.source_script["title"])
        self.assertEqual(response.source_script_source, "other")
        self.assertEqual(response.template_name, "机制类结构模板")
        record = self.db.query(GeneratedScript).one()
        self.assertEqual(record.template_id, self.template.id)
        self.assertEqual(record.source_script_id, response.source_script_id)
        self.assertEqual(record.source_script_source, "other")
        self.assertEqual(record.source_script_title, response.source_script_title)
        self.assertEqual(record.source_script_content, response.source_script_content)

    def test_missing_same_type_falls_back_to_all_concrete_scripts(self):
        source = ViralScript(
            category="烘焙配件",
            video_type="场景类",
            title="法采脚本库里的真实卡片标题",
            script_content="真实脚本内容",
        )
        self.db.add(source)
        self.db.commit()

        response, fake = self._generate(video_type="机制类")

        self.assertEqual(fake.source_script["id"], source.id)
        self.assertEqual(response.source_script_source, "facai")
        self.assertEqual(response.source_script_title, source.title)

    def test_empty_concrete_script_libraries_return_404_without_saving(self):
        fake = CapturingTemplateGenerator()
        scripts_router.generator = fake

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(scripts_router.generate_script(
                ScriptGenerateRequest(
                    product_id=self.product.id,
                    engine="template",
                    video_type="机制类",
                ),
                db=self.db,
            ))

        self.assertEqual(caught.exception.status_code, 404)
        self.assertIn("具体脚本", caught.exception.detail)
        self.assertFalse(fake.called)
        self.assertEqual(self.db.query(GeneratedScript).count(), 0)


class TemplateRewriteSourcePromptTests(unittest.TestCase):
    def test_prompt_contains_structure_template_and_concrete_source_with_no_copy_rules(self):
        ai = CapturingAI()
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate_from_library(
            product={
                "name": "袋装刀叉",
                "category": "烘焙配件",
                "price": 0.64,
                "brand": "法采",
                "selling_points": [{"type": "使用", "content": "独立袋装，拿取方便", "priority": 1}],
            },
            video_type="机制类",
            template={
                "id": 1,
                "name": "机制类结构模板",
                "video_type": "机制类",
                "structure": {"opening": "具体动作", "proof": "产品证明", "cta": "自然承接"},
                "hook_templates": ["从打包动作切入"],
                "cta_templates": ["自然引导下单"],
                "example_script": "结构模板示例",
            },
            source_script={
                "id": 9,
                "source": "facai",
                "title": "袋装刀叉 / 脚本参考 / 门店打包效率 / 文案",
                "video_type": "机制类",
                "content": "旧商品名称现在只要0.64元，老板们点左下角。",
            },
        ))

        prompt = "\n".join(message["content"] for message in ai.messages)
        self.assertIn("结构模板：机制类结构模板", prompt)
        self.assertIn("具体参考脚本", prompt)
        self.assertIn("袋装刀叉 / 脚本参考 / 门店打包效率 / 文案", prompt)
        self.assertIn("旧商品名称现在只要几毛钱", prompt)
        self.assertNotIn("0.64元", prompt)
        self.assertIn("禁止复制", prompt)
        self.assertIn("商品名", prompt)
        self.assertIn("精确价格", prompt)
        self.assertIn("CTA 原句", prompt)


class TemplateRewriteSourcePageTests(unittest.TestCase):
    def test_result_panel_uses_concrete_script_title_and_keeps_structure_template_separate(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

        self.assertIn("d.source_script_title", page)
        self.assertIn("d.source_script_content", page)
        self.assertIn("d.source_script_source", page)
        self.assertIn("结构模板", page)
        self.assertNotIn("if(d.template_name)showTemplateReference(d.template_name,d.template_reference_script)", page)


if __name__ == "__main__":
    unittest.main()
