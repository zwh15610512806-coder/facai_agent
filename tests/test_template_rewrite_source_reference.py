import asyncio
import unittest
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError
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
        self.extra_requirements = None

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
        self.extra_requirements = extra_requirements
        return "根据结构模板和具体脚本重新创作的内容"


class CapturingAI:
    is_available = True

    def __init__(self):
        self.messages = []

    async def chat(self, messages, temperature=0.75):
        self.messages = messages
        return "[[BEAT_1]]法采袋装刀叉现在几毛钱，打包拿取更顺手，需要的点左下角。"


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

    def _generate(self, video_type="机制类", **request_fields):
        fake = CapturingTemplateGenerator()
        scripts_router.generator = fake
        payload = {
            "product_id": self.product.id,
            "engine": "template",
            "video_type": video_type,
        }
        payload.update(request_fields)
        response = asyncio.run(scripts_router.generate_script(
            ScriptGenerateRequest(**payload),
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

    def test_reference_keyword_limits_random_source_to_matching_same_type_scripts(self):
        self.db.add_all([
            ViralScript(
                category="烘焙装饰",
                video_type="机制类",
                title="翻糖 / 法采机制脚本 / 文案",
                tags="翻糖,蛋糕装饰",
                script_content="翻糖同类型法采参考脚本。",
            ),
            ReferenceScript(
                video_type="机制类",
                title="翻糖 / 外部机制脚本 / 文案",
                tags="翻糖,造型蛋糕",
                script_content="翻糖同类型外部参考脚本。",
            ),
            ViralScript(
                category="烘焙调味",
                video_type="机制类",
                title="调味果酱 / 机制脚本 / 文案",
                tags="果酱,调味",
                script_content="绝不能被当前产品匹配选中的调味果酱脚本。",
            ),
        ])
        self.db.commit()

        source = scripts_router._select_rewrite_source_script(
            self.db,
            "机制类",
            reference_query="翻糖",
        )

        self.assertIn(source["title"], {
            "翻糖 / 法采机制脚本 / 文案",
            "翻糖 / 外部机制脚本 / 文案",
        })
        self.assertNotIn("调味果酱", source["title"])

    def test_template_rewrite_excludes_target_product_from_both_script_sources(self):
        target = Product(name="调味果酱", category="烘焙调味", price=18.8)
        self.db.add_all([
            target,
            ViralScript(
                category="烘焙调味",
                video_type="痛点类",
                title="调味果酱 / 法采痛点脚本 / 文案",
                tags="调味果酱",
                script_content="调味果酱同产品参考脚本。",
            ),
            ReferenceScript(
                video_type="痛点类",
                title="调味果酱 / 其他痛点脚本 / 文案",
                tags="调味果酱",
                notes="调味果酱历史脚本",
                script_content="另一条调味果酱同产品参考脚本。",
            ),
            ViralScript(
                category="烘焙夹心",
                video_type="痛点类",
                title="布蕾粉 / 法采痛点脚本 / 文案",
                tags="布蕾粉",
                script_content="布蕾粉其他产品参考脚本。",
            ),
        ])
        self.db.commit()

        source = scripts_router._select_rewrite_source_script(
            self.db,
            "痛点类",
            exclude_product_query=target.name,
        )

        self.assertEqual(source["title"], "布蕾粉 / 法采痛点脚本 / 文案")

    def test_target_product_exclusion_applies_to_cross_type_fallback(self):
        self.db.add_all([
            Product(name="调味果酱", category="烘焙调味", price=18.8),
            ViralScript(
                category="烘焙调味",
                video_type="场景类",
                title="调味果酱 / 场景脚本 / 文案",
                script_content="调味果酱跨类型脚本。",
            ),
            ReferenceScript(
                video_type="需求类",
                title="慕斯粉 / 需求脚本 / 文案",
                tags="慕斯粉",
                script_content="慕斯粉跨类型参考脚本。",
            ),
        ])
        self.db.commit()

        source = scripts_router._select_rewrite_source_script(
            self.db,
            "痛点类",
            exclude_product_query="调味果酱",
        )

        self.assertEqual(source["title"], "慕斯粉 / 需求脚本 / 文案")

    def test_route_excludes_target_product_before_random_template_rewrite(self):
        target = Product(name="调味果酱", category="烘焙调味", price=18.8)
        pain_template = ScriptTemplate(
            name="痛点类结构模板",
            video_type="痛点类",
            structure={"opening": "痛点", "proof": "证明", "cta": "承接"},
        )
        self.db.add_all([
            target,
            pain_template,
            ViralScript(
                category="烘焙调味",
                video_type="痛点类",
                title="调味果酱 / 同产品痛点脚本 / 文案",
                script_content="调味果酱同产品参考脚本。",
            ),
            ViralScript(
                category="烘焙夹心",
                video_type="痛点类",
                title="夹心脆 / 其他产品痛点脚本 / 文案",
                script_content="夹心脆其他产品参考脚本。",
            ),
        ])
        self.db.commit()
        self.db.refresh(target)

        response, fake = self._generate(
            video_type="痛点类",
            product_id=target.id,
        )

        self.assertEqual(response.product_name, "调味果酱")
        self.assertEqual(fake.source_script["title"], "夹心脆 / 其他产品痛点脚本 / 文案")

    def test_requesting_target_product_as_reference_returns_422_without_history(self):
        target = Product(name="调味果酱", category="烘焙调味", price=18.8)
        self.db.add_all([
            target,
            ViralScript(
                category="烘焙调味",
                video_type="机制类",
                title="调味果酱 / 机制脚本 / 文案",
                tags="调味果酱",
                script_content="调味果酱同产品参考脚本。",
            ),
        ])
        self.db.commit()
        self.db.refresh(target)

        with self.assertRaises(HTTPException) as caught:
            self._generate(
                video_type="机制类",
                product_id=target.id,
                extra_requirements="用户需求：使用调味果酱的机制类脚本模板生成",
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("当前生成产品相同", caught.exception.detail)
        self.assertEqual(self.db.query(GeneratedScript).count(), 0)

    def test_missing_reference_keyword_stops_generation_without_history(self):
        with self.assertRaises(HTTPException) as caught:
            scripts_router._select_rewrite_source_script(
                self.db,
                "机制类",
                reference_query="翻糖",
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("翻糖", caught.exception.detail)
        self.assertEqual(self.db.query(GeneratedScript).count(), 0)

    def test_natural_reference_instruction_selects_fandang_and_is_not_sent_to_model(self):
        source = ViralScript(
            category="烘焙装饰",
            video_type="机制类",
            title="翻糖 / 法采机制脚本 / 文案",
            tags="翻糖,蛋糕装饰",
            script_content="翻糖同类型法采参考脚本。",
        )
        self.db.add(source)
        self.db.commit()

        response, fake = self._generate(
            extra_requirements="用户需求：找一个翻糖的改写",
        )

        self.assertEqual(fake.source_script["id"], source.id)
        self.assertIsNone(fake.extra_requirements)
        self.assertEqual(response.source_match_query, "翻糖")

    def test_natural_same_type_template_instruction_extracts_keyword(self):
        reference_query, remaining_requirements = (
            scripts_router._extract_reference_query_from_requirements(
                "用户需求：找一个翻糖的同类型的模板"
            )
        )

        self.assertEqual(reference_query, "翻糖")
        self.assertIsNone(remaining_requirements)

    def test_reference_intent_understands_select_product_and_explicit_video_type(self):
        intent = scripts_router._parse_reference_selection_intent(
            "用户需求：选一个翻糖的机制类脚本改写"
        )

        self.assertEqual(intent.product_query, "翻糖")
        self.assertEqual(intent.explicit_video_type, "机制类")
        self.assertIsNone(intent.remaining_requirements)

    def test_reference_intent_understands_use_product_template_for_generation(self):
        intent = scripts_router._parse_reference_selection_intent(
            "用户需求：使用白色翻糖膏的脚本模板进行生成"
        )

        self.assertEqual(intent.product_query, "白色翻糖膏")
        self.assertIsNone(intent.explicit_video_type)
        self.assertIsNone(intent.remaining_requirements)

    def test_reference_intent_keeps_requirements_outside_selection_command(self):
        intent = scripts_router._parse_reference_selection_intent(
            "用户需求：从翻糖产品的脚本模板库中选一条参考改写，同时强调卫生和操作效率"
        )

        self.assertEqual(intent.product_query, "翻糖")
        self.assertIsNone(intent.explicit_video_type)
        self.assertEqual(intent.remaining_requirements, "同时强调卫生和操作效率")

    def test_reference_intent_does_not_consume_normal_generation_requirements(self):
        intent = scripts_router._parse_reference_selection_intent(
            "用户需求：强调产品使用方便，不要模板腔"
        )

        self.assertIsNone(intent.product_query)
        self.assertIsNone(intent.explicit_video_type)
        self.assertEqual(intent.remaining_requirements, "用户需求：强调产品使用方便，不要模板腔")

    def test_reference_intent_does_not_treat_product_materials_as_a_product_name(self):
        requirement = "用户需求：使用产品资料生成脚本，同时强调卫生"

        intent = scripts_router._parse_reference_selection_intent(requirement)

        self.assertIsNone(intent.product_query)
        self.assertIsNone(intent.explicit_video_type)
        self.assertEqual(intent.remaining_requirements, requirement)

    def test_exact_product_name_does_not_match_family_siblings(self):
        self.db.add_all([
            Product(name="白色翻糖膏", category="烘焙装饰", price=17.41),
            Product(name="彩色翻糖膏", category="烘焙装饰", price=19.8),
            ViralScript(
                category="烘焙装饰",
                video_type="机制类",
                title="白色翻糖膏 / 机制脚本 / 文案",
                tags="白色翻糖膏",
                script_content="白色翻糖膏参考脚本。",
            ),
            ViralScript(
                category="烘焙装饰",
                video_type="机制类",
                title="彩色翻糖膏 / 机制脚本 / 文案",
                tags="彩色翻糖膏",
                script_content="彩色翻糖膏参考脚本。",
            ),
        ])
        self.db.commit()

        source = scripts_router._select_rewrite_source_script(
            self.db,
            "机制类",
            reference_query="白色翻糖膏",
        )

        self.assertEqual(source["title"], "白色翻糖膏 / 机制脚本 / 文案")

    def test_family_product_query_matches_related_product_names(self):
        self.db.add_all([
            Product(name="白色翻糖膏", category="烘焙装饰", price=17.41),
            Product(name="果味翻糖", category="烘焙装饰", price=12.8),
            ViralScript(
                category="烘焙装饰",
                video_type="机制类",
                title="白色翻糖膏 / 机制脚本 / 文案",
                script_content="白色翻糖膏参考脚本。",
            ),
            ReferenceScript(
                video_type="机制类",
                title="果味翻糖 / 外部机制脚本 / 文案",
                script_content="果味翻糖参考脚本。",
            ),
        ])
        self.db.commit()

        source = scripts_router._select_rewrite_source_script(
            self.db,
            "机制类",
            reference_query="翻糖",
        )

        self.assertIn(source["title"], {
            "白色翻糖膏 / 机制脚本 / 文案",
            "果味翻糖 / 外部机制脚本 / 文案",
        })

    def test_product_query_can_match_legacy_script_content(self):
        self.db.add(Product(name="白色翻糖膏", category="烘焙装饰", price=17.41))
        self.db.add(ViralScript(
            category="烘焙装饰",
            video_type="机制类",
            title="未写产品名的历史脚本",
            tags="历史导入",
            script_content="这条脚本完整讲解白色翻糖膏的延展性和操作方法。",
        ))
        self.db.commit()

        source = scripts_router._select_rewrite_source_script(
            self.db,
            "机制类",
            reference_query="白色翻糖膏",
        )

        self.assertEqual(source["title"], "未写产品名的历史脚本")

    def test_explicit_requirement_type_overrides_page_type(self):
        self.db.add_all([
            Product(name="翻糖膏", category="烘焙装饰", price=16.8),
            ScriptTemplate(
                name="痛点类结构模板",
                video_type="痛点类",
                structure={"opening": "痛点", "proof": "证明", "cta": "承接"},
            ),
            ViralScript(
                category="烘焙装饰",
                video_type="痛点类",
                title="翻糖膏 / 痛点脚本 / 文案",
                tags="翻糖膏",
                script_content="翻糖膏痛点参考脚本。",
            ),
        ])
        self.db.commit()

        response, fake = self._generate(
            video_type="机制类",
            extra_requirements="用户需求：选一个翻糖的痛点类脚本改写",
        )

        self.assertEqual(response.video_type, "痛点类")
        self.assertEqual(response.template_name, "痛点类结构模板")
        self.assertEqual(fake.source_script["title"], "翻糖膏 / 痛点脚本 / 文案")
        self.assertIsNone(fake.extra_requirements)

    def test_missing_explicit_product_type_returns_422_without_history(self):
        self.db.add_all([
            Product(name="翻糖膏", category="烘焙装饰", price=16.8),
            ScriptTemplate(
                name="痛点类结构模板",
                video_type="痛点类",
                structure={"opening": "痛点", "proof": "证明", "cta": "承接"},
            ),
            ViralScript(
                category="烘焙装饰",
                video_type="场景类",
                title="翻糖膏 / 场景脚本 / 文案",
                tags="翻糖膏",
                script_content="翻糖膏场景参考脚本。",
            ),
        ])
        self.db.commit()

        with self.assertRaises(HTTPException) as caught:
            self._generate(
                video_type="机制类",
                extra_requirements="用户需求：使用翻糖的痛点类脚本模板生成",
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("翻糖", caught.exception.detail)
        self.assertIn("痛点类", caught.exception.detail)
        self.assertEqual(self.db.query(GeneratedScript).count(), 0)

    def test_implicit_type_falls_back_within_product_and_syncs_structure(self):
        self.db.add_all([
            Product(name="夹心脆", category="烘焙夹心", price=26.8),
            ScriptTemplate(
                name="场景类结构模板",
                video_type="场景类",
                structure={"opening": "场景", "proof": "证明", "cta": "承接"},
            ),
            ViralScript(
                category="烘焙夹心",
                video_type="场景类",
                title="夹心脆 / 场景脚本 / 文案",
                tags="夹心脆",
                script_content="夹心脆场景参考脚本。",
            ),
        ])
        self.db.commit()

        response, fake = self._generate(
            video_type="机制类",
            extra_requirements="用户需求：使用夹心脆的脚本模板进行生成",
        )

        self.assertEqual(response.video_type, "场景类")
        self.assertEqual(response.template_name, "场景类结构模板")
        self.assertEqual(fake.source_script["title"], "夹心脆 / 场景脚本 / 文案")

    def test_template_id_conflicting_with_instruction_type_returns_422(self):
        with self.assertRaises(HTTPException) as caught:
            self._generate(
                video_type="机制类",
                template_id=self.template.id,
                extra_requirements="用户需求：使用翻糖的痛点类脚本模板生成",
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("结构模板", caught.exception.detail)

    def test_reference_instruction_without_video_type_uses_matching_source_type(self):
        self.db.add(ViralScript(
            category="烘焙装饰",
            video_type="机制类",
            title="翻糖 / 法采机制脚本 / 文案",
            tags="翻糖",
            script_content="翻糖同类型法采参考脚本。",
        ))
        self.db.commit()

        response, fake = self._generate(
            video_type="",
            extra_requirements="用户需求：找一个翻糖的改写",
        )

        self.assertEqual(response.video_type, "机制类")
        self.assertEqual(fake.source_script["title"], "翻糖 / 法采机制脚本 / 文案")

    def test_legacy_manual_reference_fields_are_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            ScriptGenerateRequest(
                product_id=self.product.id,
                engine="template",
                video_type="机制类",
                reference_script_id=1,
                reference_script_source="facai",
            )

        self.assertIn("reference_script_id", str(caught.exception))


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

    def test_page_only_uses_natural_language_for_reference_script_matching(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

        self.assertIn("选一个翻糖的机制类脚本改写", page)
        self.assertIn("使用白色翻糖膏的脚本模板生成", page)
        self.assertIn("匹配产品：", page)
        self.assertIn("source_match_query", page)
        self.assertNotIn("referenceScriptQuery", page)
        self.assertNotIn("referenceScriptSelection", page)
        self.assertNotIn("reference_script_id", page)
        self.assertNotIn("reference_script_source", page)
        self.assertNotIn("rewrite-sources", page)


if __name__ == "__main__":
    unittest.main()
