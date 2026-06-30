import asyncio
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from routers import scripts as scripts_router


class FakeSeedanceService:
    def __init__(self):
        self.calls = []

    async def generate(self, *, script_content, requirements=None, db=None):
        self.calls.append({
            "script_content": script_content,
            "requirements": requirements,
            "db": db,
        })
        return {
            "prompt_text": "画面1：竖屏9:16，产品包装近景，无字幕无水印。",
            "items": [
                {
                    "scene_number": 1,
                    "label": "产品包装近景",
                    "prompt": "竖屏9:16，产品包装近景，无字幕无水印。",
                }
            ],
            "source": "ai",
        }


class FakeAI:
    is_available = True

    def __init__(self, response):
        self.response = response
        self.messages = None
        self.interface_key = None
        self.allow_fallback = None

    async def chat(self, messages, temperature=0.7, interface_key="default", db=None, **kwargs):
        self.messages = messages
        self.interface_key = interface_key
        self.allow_fallback = kwargs.get("allow_fallback")
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class UnavailableAI(FakeAI):
    is_available = False


class SeedancePromptApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[scripts_router.get_db] = override_db
        app.include_router(scripts_router.router, prefix="/api/scripts")
        self.client = TestClient(app)
        self.original_seedance_prompt_generator = getattr(scripts_router, "seedance_prompt_generator", None)

    def tearDown(self):
        if self.original_seedance_prompt_generator is None:
            if hasattr(scripts_router, "seedance_prompt_generator"):
                delattr(scripts_router, "seedance_prompt_generator")
        else:
            scripts_router.seedance_prompt_generator = self.original_seedance_prompt_generator
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_upload_extracts_text_script_without_persisting(self):
        response = self.client.post(
            "/api/scripts/seedance-prompts/upload",
            files={"file": ("script.txt", "（产品包装近景）老板们看这个奶冻粉。".encode("utf-8"), "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "script.txt")
        self.assertEqual(data["file_type"], "txt")
        self.assertIn("奶冻粉", data["text"])
        self.assertEqual(data["char_count"], len(data["text"]))

    def test_upload_rejects_images_and_oversize_files(self):
        image_response = self.client.post(
            "/api/scripts/seedance-prompts/upload",
            files={"file": ("shot.png", b"not-an-image", "image/png")},
        )
        self.assertEqual(image_response.status_code, 415)

        original_limit = getattr(scripts_router, "MAX_ATTACHMENT_BYTES", None)
        original_extract = getattr(scripts_router, "extract_attachment_text", None)
        scripts_router.MAX_ATTACHMENT_BYTES = 4

        def fail_if_called(*args, **kwargs):
            raise AssertionError("oversize uploads should be rejected before extraction")

        scripts_router.extract_attachment_text = fail_if_called
        try:
            oversize_response = self.client.post(
                "/api/scripts/seedance-prompts/upload",
                files={"file": ("too-large.txt", b"12345", "text/plain")},
            )
        finally:
            if original_extract is None:
                delattr(scripts_router, "extract_attachment_text")
            else:
                scripts_router.extract_attachment_text = original_extract
            if original_limit is None:
                delattr(scripts_router, "MAX_ATTACHMENT_BYTES")
            else:
                scripts_router.MAX_ATTACHMENT_BYTES = original_limit

        self.assertEqual(oversize_response.status_code, 413)

    def test_generate_endpoint_passes_request_to_seedance_service(self):
        fake = FakeSeedanceService()
        scripts_router.seedance_prompt_generator = fake

        response = self.client.post(
            "/api/scripts/seedance-prompts",
            json={
                "script_content": "（产品包装近景）老板们看这个奶冻粉。",
                "requirements": "更强调门店出品效率",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "ai")
        self.assertEqual(data["items"][0]["scene_number"], 1)
        self.assertIn("奶冻粉", fake.calls[0]["script_content"])
        self.assertEqual(fake.calls[0]["requirements"], "更强调门店出品效率")
        self.assertIs(fake.calls[0]["db"], self.db)

    def test_generate_endpoint_validates_blank_script_and_requirements(self):
        for payload in [
            {"script_content": " "},
            {"script_content": "有效脚本", "requirements": "x" * 2001},
        ]:
            response = self.client.post("/api/scripts/seedance-prompts", json=payload)
            self.assertEqual(response.status_code, 422, payload)

    def test_endpoint_returns_seedance_generation_error(self):
        from services.seedance_prompt_generator import SeedancePromptGenerationError

        class FailingSeedanceService:
            async def generate(self, *, script_content, requirements=None, db=None):
                raise SeedancePromptGenerationError(503, "DeepSeek V4 Pro / 脚本改写配置不可用")

        scripts_router.seedance_prompt_generator = FailingSeedanceService()

        response = self.client.post(
            "/api/scripts/seedance-prompts",
            json={"script_content": "老板们看这个奶冻粉。"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("DeepSeek V4 Pro", response.json()["detail"])


class SeedancePromptServiceTests(unittest.TestCase):
    def test_extract_beats_pairs_trailing_parenthesized_scene_with_spoken_line(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        generator = SeedancePromptGenerator(ai=FakeAI(""))

        beats = generator._extract_beats(
            "这才是新品冲量该有的大羊毛（提着好几袋放出来）\n法采足足2斤重的新品（四包不同口味）",
            24,
        )

        self.assertEqual([
            {"scene": "提着好几袋放出来", "line": "这才是新品冲量该有的大羊毛"},
            {"scene": "四包不同口味", "line": "法采足足2斤重的新品"},
        ], beats)

    def test_extract_beats_pairs_leading_parenthesized_scene_with_following_spoken_line(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        generator = SeedancePromptGenerator(ai=FakeAI(""))

        beats = generator._extract_beats(
            "（往蛋糕上洒糖珠的镜头，然后展示蛋糕）很多人没有意识到法采这款装饰糖珠是不用挑尺寸挑款式的。",
            24,
        )

        self.assertEqual([
            {
                "scene": "往蛋糕上洒糖珠的镜头，然后展示蛋糕",
                "line": "很多人没有意识到法采这款装饰糖珠是不用挑尺寸挑款式的。",
            },
        ], beats)

    def test_extract_beats_preserves_mixed_parenthesis_order(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        generator = SeedancePromptGenerator(ai=FakeAI(""))

        beats = generator._extract_beats(
            "跳跳糖夹心珠，居然拿来送（有切面的陪衬+倒夹心珠用手拿出来看）\n"
            "（产品展示）因为是新品上新\n"
            "三块多6寸的价格（倒一勺在胚子里）",
            24,
        )

        self.assertEqual([
            {"scene": "有切面的陪衬+倒夹心珠用手拿出来看", "line": "跳跳糖夹心珠，居然拿来送"},
            {"scene": "产品展示", "line": "因为是新品上新"},
            {"scene": "倒一勺在胚子里", "line": "三块多6寸的价格"},
        ], beats)

    def test_build_messages_marks_parentheses_as_scene_drafts_and_spoken_context(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI(
            "画面1：竖屏9:16，提着好几袋新品包装展示，无字幕无水印。\n\n"
            "画面2：竖屏9:16，产品展示近景，无字幕无水印。"
        )
        generator = SeedancePromptGenerator(ai=ai)

        result = asyncio.run(generator.generate(
            script_content="这才是新品冲量该有的大羊毛（提着好几袋放出来）\n（产品展示）因为是新品上新",
            requirements="突出新品冲量",
        ))

        user_prompt = ai.messages[-1]["content"]
        self.assertEqual(result["source"], "ai")
        self.assertIn("画面初稿：提着好几袋放出来", user_prompt)
        self.assertIn("口播/上下文：这才是新品冲量该有的大羊毛", user_prompt)
        self.assertIn("画面初稿：产品展示", user_prompt)
        self.assertIn("口播/上下文：因为是新品上新", user_prompt)
        self.assertIn("括号内文字是画面初稿", user_prompt)

    def test_service_uses_spoken_script_line_as_item_label(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI("画面1：垂直9:16短视频，产品包装近景，无字幕无水印。")
        generator = SeedancePromptGenerator(ai=ai)

        result = asyncio.run(generator.generate(
            script_content="这才是新品冲量该有的大羊毛（提着好几袋放出来）",
            requirements="突出新品冲量",
        ))

        self.assertEqual(result["items"][0]["label"], "这才是新品冲量该有的大羊毛")
        self.assertNotIn("垂直9:16", result["items"][0]["label"])

    def test_talking_head_scene_is_marked_for_real_person_sales_video(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI("画面1：竖屏9:16，真人主播入镜，手持糖珠包装对镜讲解，无字幕无水印。")
        generator = SeedancePromptGenerator(ai=ai)

        asyncio.run(generator.generate(
            script_content="（口播，主播拿着糖珠介绍）这款糖珠不用挑尺寸，拆开就能用。",
            requirements="自然带货",
        ))

        user_prompt = ai.messages[-1]["content"]
        self.assertIn("视频类型：真人口播带货视频", user_prompt)
        self.assertIn("真人主播入镜", user_prompt)
        self.assertIn("自然对镜讲解", user_prompt)
        self.assertIn("手持/指向/展示产品", user_prompt)

    def test_regular_product_scene_is_not_marked_as_talking_head(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI("画面1：竖屏9:16，产品包装近景展示，无字幕无水印。")
        generator = SeedancePromptGenerator(ai=ai)

        asyncio.run(generator.generate(
            script_content="（产品展示）这款糖珠不用挑尺寸，拆开就能用。",
            requirements="多展示包装",
        ))

        user_prompt = ai.messages[-1]["content"]
        self.assertNotIn("视频类型：真人口播带货视频", user_prompt)

    def test_mixed_script_marks_only_talking_head_scene(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI(
            "画面1：竖屏9:16，产品包装展示，无字幕无水印。\n\n"
            "画面2：竖屏9:16，真人主播手持产品对镜讲解，无字幕无水印。\n\n"
            "画面3：竖屏9:16，蛋糕成品细节展示，无字幕无水印。"
        )
        generator = SeedancePromptGenerator(ai=ai)

        asyncio.run(generator.generate(
            script_content=(
                "（产品展示）这款糖珠不用挑尺寸。\n"
                "（主播出镜，拿着白色糖珠说）一袋自带多尺寸多造型。\n"
                "（蛋糕成品展示）急单直接拆开就能用。"
            ),
            requirements="真实门店带货",
        ))

        user_prompt = ai.messages[-1]["content"]
        first_block = user_prompt[user_prompt.index("1. 画面初稿"):user_prompt.index("\n2. 画面初稿")]
        second_block = user_prompt[user_prompt.index("2. 画面初稿"):user_prompt.index("\n3. 画面初稿")]
        third_block = user_prompt[user_prompt.index("3. 画面初稿"):user_prompt.index("\n用户脚本")]
        self.assertNotIn("视频类型：真人口播带货视频", first_block)
        self.assertIn("视频类型：真人口播带货视频", second_block)
        self.assertNotIn("视频类型：真人口播带货视频", third_block)

    def test_user_sample_style_keeps_multiple_scene_drafts_in_ai_prompt(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI(
            "画面1：竖屏9:16，提着好几袋新品包装展示，无字幕无水印。\n\n"
            "画面2：竖屏9:16，四包不同口味包装平铺展示，无字幕无水印。\n\n"
            "画面3：竖屏9:16，切面蛋糕旁倒出夹心珠，无字幕无水印。\n\n"
            "画面4：竖屏9:16，往蛋糕上洒糖珠并展示成品，无字幕无水印。"
        )
        generator = SeedancePromptGenerator(ai=ai)

        result = asyncio.run(generator.generate(
            script_content=(
                "这才是新品冲量该有的大羊毛（提着好几袋放出来）\n"
                "法采足足2斤重的新品（四包不同口味）\n"
                "跳跳糖夹心珠，居然拿来送（有切面的陪衬+倒夹心珠用手拿出来看）\n"
                "（往蛋糕上洒糖珠的镜头，然后展示蛋糕）很多人没有意识到法采这款装饰糖珠是不用挑尺寸挑款式的。"
            ),
            requirements="按括号画面扩写",
        ))

        user_prompt = ai.messages[-1]["content"]
        self.assertEqual(4, len(result["items"]))
        for scene in [
            "画面初稿：提着好几袋放出来",
            "画面初稿：四包不同口味",
            "画面初稿：有切面的陪衬+倒夹心珠用手拿出来看",
            "画面初稿：往蛋糕上洒糖珠的镜头，然后展示蛋糕",
        ]:
            self.assertIn(scene, user_prompt)
        self.assertIn("口播/上下文：很多人没有意识到法采这款装饰糖珠是不用挑尺寸挑款式的。", user_prompt)

    def test_service_uses_seedance_skill_as_system_prompt_and_interface_alias(self):
        from services.seedance_prompt_generator import SeedancePromptGenerator

        ai = FakeAI("画面1：竖屏9:16，短商业视频，产品包装近景，无字幕无水印。")
        generator = SeedancePromptGenerator(ai=ai)

        result = asyncio.run(generator.generate(
            script_content="（产品包装近景）老板们看这个奶冻粉。",
            requirements="更强调真实门店操作",
        ))

        self.assertEqual(result["source"], "ai")
        self.assertEqual(ai.interface_key, "seedance_prompt")
        self.assertIs(ai.allow_fallback, False)
        self.assertIn("Seedance 2.0 Prompt", ai.messages[0]["content"])
        self.assertIn("Scene Prompt Recipe", ai.messages[0]["content"])
        self.assertIn("no captions", ai.messages[0]["content"])
        self.assertIn("更强调真实门店操作", ai.messages[-1]["content"])
        self.assertIn("按脚本断句", ai.messages[-1]["content"])
        self.assertIn("每个句子生成 1 个", ai.messages[-1]["content"])
        self.assertEqual(result["items"][0]["scene_number"], 1)

    def test_service_rejects_empty_or_unparseable_ai_output_without_fallback(self):
        from services.seedance_prompt_generator import SeedancePromptGenerationError, SeedancePromptGenerator

        for response in ["", "我不能生成这个内容"]:
            generator = SeedancePromptGenerator(ai=FakeAI(response))

            with self.assertRaises(SeedancePromptGenerationError) as cm:
                asyncio.run(generator.generate(
                    script_content="老板们看这个奶冻粉。加水搅拌很快。成品夹心很稳定。",
                    requirements="突出门店出品",
                ))

            self.assertEqual(cm.exception.status_code, 502)

    def test_service_rejects_ai_call_errors_without_fallback(self):
        from services.seedance_prompt_generator import SeedancePromptGenerationError, SeedancePromptGenerator

        generator = SeedancePromptGenerator(ai=FakeAI(RuntimeError("missing api key")))

        with self.assertRaises(SeedancePromptGenerationError) as cm:
            asyncio.run(generator.generate(
                script_content="老板们看这个奶冻粉。加水搅拌很快。",
                requirements="突出门店出品",
            ))

        self.assertEqual(cm.exception.status_code, 503)

if __name__ == "__main__":
    unittest.main()
