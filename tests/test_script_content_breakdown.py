import asyncio
import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import GeneratedScript, Product, ScriptTemplate, SellingPoint
from routers import scripts as scripts_router


BREAKDOWN_PAYLOAD = {
    "generation_rationale": "先用门店痛点抓住烘焙从业者，再用产品证明承接转化。",
    "target_audience": "需要稳定出品和提高效率的烘焙店老板。",
    "structure": [
        {"stage": "开头", "copy_excerpt": "赶单时最怕奶冻不稳定", "purpose": "建立真实冲突"},
    ],
    "core_selling_points": ["操作简单", "成品稳定"],
    "conversion_triggers": [
        {"copy_excerpt": "冷藏后依然稳定", "reason": "用可见结果降低试错顾虑"},
    ],
    "optimization_suggestions": [
        {"issue": "证明略少", "recommendation": "增加一次切面或脱模实拍"},
    ],
    "shooting_notes": ["优先在真实烘焙工作台拍摄"],
    "shot_requirements": [
        {
            "script_segment": "成品稳定",
            "shot_type": "近景",
            "subject_action": "切开奶冻展示截面",
            "visual_requirement": "对焦质地并保持自然光",
        }
    ],
    "source": "ai",
}


class FakeBreakdownService:
    def __init__(self, result=None, error=None):
        self.result = result or BREAKDOWN_PAYLOAD
        self.error = error
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeAI:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class SlowAI:
    async def chat(self, messages, **kwargs):
        await asyncio.sleep(0.05)
        return json.dumps(BREAKDOWN_PAYLOAD, ensure_ascii=False)


class ScriptContentBreakdownApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        product = Product(name="奶冻粉", category="烘焙调味", price=12.8, brand="法采")
        product.selling_points.append(SellingPoint(point_type="品质", content="成品稳定", priority=1))
        template = ScriptTemplate(
            name="痛点类模板",
            video_type="痛点类",
            structure={"opening": "痛点冲突", "proof": "产品证明"},
        )
        self.db.add_all([product, template])
        self.db.flush()
        self.ai_record = GeneratedScript(
            product_id=product.id,
            script_content="赶单时最怕奶冻不稳定，这款冷藏后依然稳定。",
            video_type="痛点类",
            ai_model="AI生成 · test-model",
        )
        self.template_record = GeneratedScript(
            product_id=product.id,
            template_id=template.id,
            source_script_title="奶冻痛点参考稿",
            source_script_content="以前赶单总翻车，现在出品稳定。",
            script_content="赶单时最怕奶冻不稳定，这款冷藏后依然稳定。",
            video_type="痛点类",
            ai_model="模板库改写 · rewrite-model",
        )
        self.db.add_all([self.ai_record, self.template_record])
        self.db.commit()

        app = FastAPI()

        def override_db():
            yield self.db

        app.dependency_overrides[scripts_router.get_db] = override_db
        app.include_router(scripts_router.router, prefix="/api/scripts")
        self.client = TestClient(app)
        self.original_service = getattr(scripts_router, "script_content_breakdown_service", None)
        self.original_product_detail = scripts_router.build_product_detail_payload
        scripts_router.build_product_detail_payload = lambda product: {
            "profile_sections": [{"title": "用途", "items": [{"label": "场景", "content": "门店奶冻制作"}]}],
            "knowledge_sources": ["测试产品资料"],
        }

    def tearDown(self):
        if self.original_service is None:
            if hasattr(scripts_router, "script_content_breakdown_service"):
                delattr(scripts_router, "script_content_breakdown_service")
        else:
            scripts_router.script_content_breakdown_service = self.original_service
        scripts_router.build_product_detail_payload = self.original_product_detail
        self.client.close()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_endpoint_uses_generation_engine_and_product_context(self):
        fake = FakeBreakdownService()
        scripts_router.script_content_breakdown_service = fake

        for record, expected_engine in (
            (self.ai_record, "deepseek"),
            (self.template_record, "template"),
        ):
            with self.subTest(expected_engine=expected_engine):
                response = self.client.post(
                    "/api/scripts/content-breakdown",
                    json={"script_id": record.id, "script_content": "用户编辑后的有效脚本。"},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["generation_rationale"], BREAKDOWN_PAYLOAD["generation_rationale"])
                call = fake.calls[-1]
                self.assertEqual(call["engine"], expected_engine)
                self.assertEqual(call["script_content"], "用户编辑后的有效脚本。")
                self.assertEqual(call["product"]["name"], "奶冻粉")
                self.assertIn("测试产品资料", call["product"]["knowledge_sources"])
                if expected_engine == "template":
                    self.assertEqual(call["template"]["name"], "痛点类模板")
                    self.assertEqual(call["source_script"]["title"], "奶冻痛点参考稿")

    def test_endpoint_rejects_missing_record_and_blank_script(self):
        scripts_router.script_content_breakdown_service = FakeBreakdownService()

        missing = self.client.post(
            "/api/scripts/content-breakdown",
            json={"script_id": 999999, "script_content": "有效脚本"},
        )
        blank = self.client.post(
            "/api/scripts/content-breakdown",
            json={"script_id": self.ai_record.id, "script_content": " "},
        )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(blank.status_code, 422)


class ScriptContentBreakdownServiceTests(unittest.TestCase):
    def test_service_uses_matching_generation_interface_and_structured_prompt(self):
        from services.script_content_breakdown import ScriptContentBreakdownService

        for engine, interface_key in (("deepseek", "script_generate"), ("template", "script_library_rewrite")):
            with self.subTest(engine=engine):
                ai = FakeAI("```json\n" + json.dumps(BREAKDOWN_PAYLOAD, ensure_ascii=False) + "\n```")
                service = ScriptContentBreakdownService(ai=ai)
                result = asyncio.run(service.generate(
                    script_content="赶单时最怕奶冻不稳定，这款冷藏后依然稳定。",
                    product={"name": "奶冻粉", "selling_points": [{"content": "成品稳定"}]},
                    video_type="痛点类",
                    engine=engine,
                    template={"name": "痛点类模板", "structure": {"opening": "痛点"}},
                    source_script={"title": "参考稿", "content": "原脚本"},
                ))

                self.assertEqual(result["source"], "ai")
                self.assertEqual(ai.calls[0]["interface_key"], interface_key)
                self.assertIs(ai.calls[0]["allow_fallback"], False)
                self.assertIs(ai.calls[0]["raise_on_error"], True)
                prompt = ai.calls[0]["messages"][-1]["content"]
                self.assertIn("奶冻粉", prompt)
                self.assertIn("痛点类", prompt)
                self.assertIn("不得虚构投放数据", prompt)
                self.assertIn("镜头与画面要求", prompt)

    def test_service_falls_back_when_analysis_is_invalid_or_provider_fails(self):
        from services.script_content_breakdown import ScriptContentBreakdownService

        for result in ("不是JSON", RuntimeError("provider down")):
            with self.subTest(result=result):
                service = ScriptContentBreakdownService(ai=FakeAI(result))
                breakdown = asyncio.run(service.generate(
                    script_content="赶单时最怕奶冻不稳定，这款冷藏后依然稳定。",
                    product={"name": "奶冻粉", "category": "烘焙调味"},
                    video_type="痛点类",
                    engine="deepseek",
                ))
                self.assertEqual(breakdown["source"], "local")
                self.assertTrue(breakdown["generation_rationale"])
                self.assertTrue(breakdown["structure"])
                self.assertTrue(breakdown["shot_requirements"])

    def test_service_keeps_partial_ai_analysis_and_fills_missing_sections(self):
        from services.script_content_breakdown import ScriptContentBreakdownService

        ai = FakeAI(json.dumps(
            {"generation_rationale": "AI识别出脚本先讲翻车风险，再给稳定性证明。"},
            ensure_ascii=False,
        ))
        breakdown = asyncio.run(ScriptContentBreakdownService(ai=ai).generate(
            script_content="赶单时最怕奶冻不稳定，这款冷藏后依然稳定。",
            product={"name": "奶冻粉", "category": "烘焙调味"},
            video_type="痛点类",
            engine="deepseek",
        ))

        self.assertEqual(breakdown["source"], "ai")
        self.assertEqual(
            breakdown["generation_rationale"],
            "AI识别出脚本先讲翻车风险，再给稳定性证明。",
        )
        self.assertTrue(breakdown["target_audience"])
        self.assertTrue(breakdown["structure"])
        self.assertTrue(breakdown["shot_requirements"])

    def test_service_timeout_returns_local_breakdown(self):
        from services import script_content_breakdown as module

        original_timeout = module.BREAKDOWN_TOTAL_TIMEOUT_SECONDS
        module.BREAKDOWN_TOTAL_TIMEOUT_SECONDS = 0.001
        try:
            service = module.ScriptContentBreakdownService(ai=SlowAI())
            breakdown = asyncio.run(service.generate(
                script_content="赶单时最怕奶冻不稳定，这款冷藏后依然稳定。",
                product={"name": "奶冻粉", "category": "烘焙调味"},
                video_type="痛点类",
                engine="deepseek",
            ))
            self.assertEqual(breakdown["source"], "local")
            self.assertTrue(breakdown["conversion_triggers"])
        finally:
            module.BREAKDOWN_TOTAL_TIMEOUT_SECONDS = original_timeout


if __name__ == "__main__":
    unittest.main()
