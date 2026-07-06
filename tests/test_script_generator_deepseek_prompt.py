import asyncio
import unittest

from services.script_generator import ScriptGenerator


class PromptCaptureAI:
    is_available = True

    def __init__(self, response="生成脚本正文"):
        self.response = response
        self.messages = None

    def get_model_name(self, *args, **kwargs):
        return "fake-model"

    async def chat(self, messages, temperature=0.85, interface_key="script_generate"):
        self.messages = messages
        return self.response


class InterfaceAvailableAI(PromptCaptureAI):
    is_available = False

    def __init__(self, response="生成脚本正文"):
        super().__init__(response)
        self.checked_interface = None

    def is_interface_available(self, interface_key):
        self.checked_interface = interface_key
        return interface_key == "script_generate"


def make_product(**overrides):
    product = {
        "name": "袋装刀叉",
        "category": "烘焙配件",
        "price": 0.64,
        "original_price": 0.8,
        "brand": "法采",
        "description": "适合蛋糕配送和门店打包使用",
        "selling_points": [
            {"type": "包装", "content": "独立袋装，干净卫生，适合蛋糕配送", "priority": 1},
            {"type": "成本", "content": "单套成本低，适合门店批量备货", "priority": 2},
            {"type": "承托", "content": "加厚餐盘承托稳定，不容易塌", "priority": 3},
        ],
    }
    product.update(overrides)
    return product


def make_product_with_knowledge(**overrides):
    product = make_product(
        name="糖珠",
        category="烘焙装饰",
        price=9.18,
        description="适合蛋糕和甜品表面装饰",
        source_name="糖珠产品档案.md",
        manual_source="FC法采产品手册24年5月6日更新版.md",
        knowledge_sources=["【法采】2026年产品手卡.xlsx"],
        sku_prices=[
            {
                "product": "糖珠",
                "spec": "500g",
                "price": 9.18,
                "daily_price": 9.18,
                "activity_prices": [
                    {"mechanism": "淘宝A级-调整202603", "final_price": 8.26}
                ],
                "line": "糖珠 500g 售价¥9.18，活动到手¥8.26",
            }
        ],
        profile_sections=[
            {
                "id": "product_usage",
                "title": "产品用途",
                "items": [
                    {"label": "用途简述", "content": "用于蛋糕表面装饰、甜品杯点缀和节日款出样"},
                ],
                "sku_prices": [],
            },
            {
                "id": "usage_scenarios",
                "title": "使用场景",
                "items": [
                    {"label": "门店方案", "content": "适合烘焙门店做儿童款、节日款和陈列款蛋糕"},
                ],
                "sku_prices": [],
            },
            {
                "id": "main_selling_points",
                "title": "主要卖点",
                "items": [
                    {"label": "核心亮点", "content": "不用重新改配方，撒在表面就能增加成品视觉记忆点"},
                ],
                "sku_prices": [],
            },
            {
                "id": "product_price",
                "title": "产品价格",
                "items": [],
                "sku_prices": [
                    {
                        "product": "糖珠",
                        "spec": "500g",
                        "price": 9.18,
                        "daily_price": 9.18,
                        "activity_prices": [
                            {"mechanism": "淘宝A级-调整202603", "final_price": 8.26}
                        ],
                        "line": "糖珠 500g 售价¥9.18，活动到手¥8.26",
                    }
                ],
            },
        ],
    )
    product.update(overrides)
    return product


def make_template():
    return {
        "name": "模板库机制模板",
        "video_type": "机制类",
        "hook_templates": ["推荐开头钩子：这个模板钩子不应该进入 DeepSeek prompt"],
        "cta_templates": ["推荐CTA话术：这个模板 CTA 不应该进入 DeepSeek prompt"],
        "example_script": "模板库示例脚本不应该进入 DeepSeek prompt",
    }


class DeepSeekPromptTests(unittest.TestCase):
    def test_generation_uses_interface_availability_instead_of_deepseek_global_flag(self):
        ai = InterfaceAvailableAI("火山方舟生成脚本正文")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="需求类",
            tone="直接",
            include_shot_design=False,
        ))

        self.assertEqual(ai.checked_interface, "script_generate")
        self.assertIsNotNone(ai.messages)
        self.assertIn("火山方舟生成脚本正文", result)

    def test_plain_deepseek_prompt_adds_run_rate_self_check_and_keeps_plain_rules(self):
        ai = PromptCaptureAI("法采袋装刀叉很适合门店打包，左下角看看。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="需求类",
            tone="活泼",
            include_shot_design=False,
        ))

        system_prompt = ai.messages[0]["content"]
        user_prompt = ai.messages[-1]["content"]

        self.assertIn("抖音跑量自检框架", system_prompt)
        self.assertIn("3-5秒", system_prompt)
        self.assertIn("烘焙店老板/烘焙从业者", system_prompt)
        self.assertIn("真实使用场景", system_prompt)
        self.assertIn("至少引用2个产品资料里的具体卖点", system_prompt)
        self.assertIn("价格、活动、赠品必须与输入一致", system_prompt)
        self.assertIn("先内部自评并修正", system_prompt)
        self.assertIn("纯口播一段话", system_prompt)
        self.assertIn("禁止【】段落标签", system_prompt)
        self.assertIn("只输出一段连续视频文案", user_prompt)
        self.assertIn("禁止镜头说明", user_prompt)

    def test_shot_design_deepseek_prompt_uses_same_run_rate_logic_and_keeps_camera_requirements(self):
        ai = PromptCaptureAI("（主播手拿袋装刀叉）老板们看一下这套餐叉。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="场景类",
            tone="直接",
            include_shot_design=True,
        ))

        system_prompt = ai.messages[0]["content"]
        user_prompt = ai.messages[-1]["content"]

        self.assertIn("抖音跑量自检框架", system_prompt)
        self.assertIn("3-5秒", system_prompt)
        self.assertIn("烘焙店老板/烘焙从业者", system_prompt)
        self.assertIn("真实使用场景", system_prompt)
        self.assertIn("每句话添加镜头说明", user_prompt)
        self.assertIn("（镜头/画面说明）口播文案", user_prompt)
        self.assertNotIn("参考模板库脚本", user_prompt)
        self.assertNotIn("参考模板库脚本", system_prompt)

    def test_plain_deepseek_prompt_discourages_default_sister_openers_and_varies_angle(self):
        ai = PromptCaptureAI("开头不用默认称呼，直接进入门店打包场景。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="痛点类",
            tone="直接",
            include_shot_design=False,
        ))

        system_prompt = ai.messages[0]["content"]
        user_prompt = ai.messages[-1]["content"]

        self.assertIn("开头去重要求", system_prompt)
        self.assertIn("本次开头角度：", system_prompt)
        self.assertIn("禁止以“姐妹们”“烘焙姐妹们”", system_prompt)
        self.assertIn("每次重新生成必须更换开头角度", system_prompt)
        self.assertIn("第一小句必须直接进入", system_prompt)
        self.assertNotIn("可以使用“啊、姐妹们", system_prompt)
        self.assertNotIn("可以使用“啊、姐妹们", user_prompt)

    def test_shot_design_deepseek_prompt_removes_global_sister_tone_hint(self):
        ai = PromptCaptureAI("（主播展示袋装刀叉）门店打包刀叉别只看便宜。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="场景类",
            tone="直接",
            include_shot_design=True,
        ))

        system_prompt = ai.messages[0]["content"]

        self.assertIn("开头去重要求", system_prompt)
        self.assertIn("禁止以“姐妹们”“烘焙姐妹们”", system_prompt)
        self.assertNotIn("像烘焙姐妹聊天一样自然", system_prompt)
        self.assertNotIn("使用口语化表达：姐妹们", system_prompt)

    def test_plain_deepseek_post_process_removes_default_sister_opening(self):
        ai = PromptCaptureAI("烘焙姐妹们，袋装刀叉别只看便宜，门店配送更要看独立包装和承托稳定。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="痛点类",
            tone="直接",
            include_shot_design=False,
        ))

        self.assertFalse(result.startswith("烘焙姐妹们"))
        self.assertIn("袋装刀叉别只看便宜", result)

    def test_pending_price_deepseek_prompt_forbids_fabricating_price(self):
        ai = PromptCaptureAI("价格待更新，老板们先看规格。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(price=0, pending_fields=["price"]),
            template=None,
            video_type="机制类",
            tone="活泼",
            include_shot_design=False,
        ))

        prompt = "\n".join(message["content"] for message in ai.messages)

        self.assertIn("售价：待更新", prompt)
        self.assertIn("价格待更新时不得编造价格", prompt)
        self.assertNotIn("售价：0元", prompt)

    def test_ai_inferred_type_prompt_chooses_angle_without_template_references(self):
        ai = PromptCaptureAI("门店打包先看刀叉是不是独立袋装。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=make_template(),
            video_type="AI智能生成",
            tone="直接",
            reference_scripts=[
                {
                    "title": "不应进入 prompt 的模板库脚本",
                    "content": "推荐开头钩子：姐妹们这个模板不要进来",
                    "video_type": "机制类",
                    "category": "烘焙配件",
                    "is_high_conversion": True,
                }
            ],
            include_shot_design=False,
        ))

        prompt = "\n".join(message["content"] for message in ai.messages)

        self.assertIn("视频类型：AI智能生成", prompt)
        self.assertIn("根据产品资料、价格状态、卖点强弱和抖音跑量逻辑自动选择最适合的生成角度", prompt)
        self.assertNotIn("推荐开头钩子", prompt)
        self.assertNotIn("推荐CTA话术", prompt)
        self.assertNotIn("模板库示例脚本", prompt)
        self.assertNotIn("不应进入 prompt 的模板库脚本", prompt)

    def test_ai_prompt_includes_product_knowledge_sections_and_sku_prices(self):
        ai = PromptCaptureAI("糖珠适合门店做节日蛋糕装饰。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product_with_knowledge(),
            template=None,
            video_type="场景类",
            tone="直接",
            include_shot_design=False,
        ))

        user_prompt = ai.messages[-1]["content"]

        self.assertIn("【产品知识库资料】", user_prompt)
        self.assertIn("资料来源：糖珠产品档案.md、FC法采产品手册24年5月6日更新版.md", user_prompt)
        self.assertIn("【产品用途】", user_prompt)
        self.assertIn("用于蛋糕表面装饰、甜品杯点缀和节日款出样", user_prompt)
        self.assertIn("【使用场景】", user_prompt)
        self.assertIn("适合烘焙门店做儿童款、节日款和陈列款蛋糕", user_prompt)
        self.assertIn("【主要卖点】", user_prompt)
        self.assertIn("不用重新改配方", user_prompt)
        self.assertIn("糖珠 500g 售价¥9.18，活动到手¥8.26", user_prompt)

    def test_shot_design_prompt_includes_product_knowledge_and_camera_requirements(self):
        ai = PromptCaptureAI("（近景展示糖珠）糖珠适合做节日款蛋糕装饰。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product_with_knowledge(),
            template=None,
            video_type="场景类",
            tone="直接",
            include_shot_design=True,
        ))

        user_prompt = ai.messages[-1]["content"]

        self.assertIn("【产品知识库资料】", user_prompt)
        self.assertIn("糖珠 500g 售价¥9.18，活动到手¥8.26", user_prompt)
        self.assertIn("每句话添加镜头说明", user_prompt)
        self.assertIn("（镜头/画面说明）口播文案", user_prompt)
        self.assertNotIn("参考模板库脚本", user_prompt)

    def test_deepseek_prompt_ignores_template_and_reference_script_content(self):
        ai = PromptCaptureAI("姐妹们，别等恢复原价了才后悔。")
        generator = ScriptGenerator()
        generator.ai = ai

        dirty_reference = (
            "好的，没问题！作为拥有5年抖音烘焙带货经验的脚本改写专家，我完全理解你的需求。"
            "根据你提供的3条爆款脚本和目标产品“袋装刀叉”，我选择**爆款脚本 #1**进行改写。\n\n"
            "以下是为你全新改写的带货脚本：\n\n"
            "**改写自：爆款脚本 #1**\n\n"
            "【开场钩子】\n"
            "姐妹们，别等恢复原价了才后悔没有现在多囤几单！\n"
            "法采年终福利，力度搞这么大，确定不来看一下？"
        )

        asyncio.run(generator.generate(
            product=make_product(),
            template=make_template(),
            video_type="机制类",
            tone="活泼",
            reference_scripts=[
                {
                    "title": "脏参考脚本",
                    "content": dirty_reference,
                    "video_type": "机制类",
                    "category": "烘焙配件",
                    "is_high_conversion": True,
                }
            ],
            include_shot_design=False,
        ))

        user_prompt = ai.messages[-1]["content"]

        self.assertNotIn("【参考模板】", user_prompt)
        self.assertNotIn("推荐开头钩子", user_prompt)
        self.assertNotIn("推荐CTA话术", user_prompt)
        self.assertNotIn("模板库示例脚本", user_prompt)
        self.assertNotIn("【同类爆款脚本参考】", user_prompt)
        self.assertNotIn("脏参考脚本", user_prompt)
        self.assertNotIn("好的，没问题", user_prompt)
        self.assertNotIn("脚本改写专家", user_prompt)
        self.assertNotIn("我选择", user_prompt)
        self.assertNotIn("改写自：爆款脚本", user_prompt)
        self.assertNotIn("**", user_prompt)
        self.assertNotIn("姐妹们，别等恢复原价了才后悔没有现在多囤几单", user_prompt)
        self.assertNotIn("法采年终福利", user_prompt)


if __name__ == "__main__":
    unittest.main()
