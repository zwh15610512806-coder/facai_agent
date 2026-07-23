import asyncio
import unittest

from services.script_generator import ScriptGenerationError, ScriptGenerator


class PromptCaptureAI:
    is_available = True

    def __init__(self, response="生成脚本正文"):
        self.response = response
        self.messages = None
        self.allow_fallback = None
        self.calls = []

    def get_model_name(self, *args, **kwargs):
        return "fake-model"

    async def chat(self, messages, temperature=0.85, interface_key="script_generate", **kwargs):
        self.messages = messages
        self.allow_fallback = kwargs.get("allow_fallback")
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "interface_key": interface_key,
            "allow_fallback": self.allow_fallback,
        })
        return self.response


class SequenceResponseAI(PromptCaptureAI):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)

    async def chat(self, messages, temperature=0.85, interface_key="script_generate", **kwargs):
        self.messages = messages
        self.allow_fallback = kwargs.get("allow_fallback")
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "interface_key": interface_key,
            "allow_fallback": self.allow_fallback,
        })
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class InterfaceAvailableAI(PromptCaptureAI):
    is_available = False

    def __init__(self, response="生成脚本正文"):
        super().__init__(response)
        self.checked_interface = None

    def is_interface_available(self, interface_key):
        self.checked_interface = interface_key
        return interface_key == "script_generate"


class UnavailableInterfaceAI(PromptCaptureAI):
    is_available = False

    def is_interface_available(self, interface_key):
        return False


class EmptyResponseAI(PromptCaptureAI):
    async def chat(self, messages, temperature=0.85, interface_key="script_generate", **kwargs):
        self.messages = messages
        self.allow_fallback = kwargs.get("allow_fallback")
        return ""


class FailingResponseAI(PromptCaptureAI):
    async def chat(self, messages, temperature=0.85, interface_key="script_generate", **kwargs):
        self.messages = messages
        self.allow_fallback = kwargs.get("allow_fallback")
        raise RuntimeError("provider authentication failed")


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


def make_template_context():
    return {
        "id": 1,
        "name": "模板库改写测试模板",
        "video_type": "需求类",
        "structure": {"opening": "需求开场", "proof": "卖点证明", "cta": "下单引导"},
        "hook_templates": ["门店老板这个需求别忽略"],
        "cta_templates": ["需要就点左下角"],
        "duration_range": "15-25s",
        "description": "测试用脚本模板",
        "example_script": "门店需求先讲清，再自然引导下单。",
    }


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
    def test_ai_prompt_includes_opening_strategy_history_and_conversion_framework(self):
        ai = PromptCaptureAI("先把独立袋装刀叉摆到打包台上，配送时更干净。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="需求类",
            recent_openings=["先看承托稳不稳。", "门店急单别再临时找刀叉。"],
        ))

        prompt = "\n".join(message["content"] for message in ai.messages)
        self.assertIn("【本次开头策略】", prompt)
        self.assertRegex(prompt, r"策略家族：(action|scene_conflict|result_contrast|cognition|product_proof|customer_feedback)")
        self.assertIn("【近期首句去重】", prompt)
        self.assertIn("禁止复制这些首句的角度或句式", prompt)
        self.assertIn("CTR", prompt)
        self.assertIn("CVR", prompt)
        self.assertIn("真实烘焙门店场景", prompt)
        self.assertIn("具体产品证明", prompt)
        self.assertIn("内容重、营销轻", prompt)
        self.assertIn("一条清晰转化主线", prompt)
        self.assertIn("证明之后自然 CTA", prompt)
        self.assertNotIn("必须包含输入中已有的价格/活动信息", prompt)
        self.assertIn("本条脚本不要求价格", prompt)
        self.assertIn("不得为了制造广告压力强行插入价格或促销", prompt)

    def test_price_policy_allows_abstract_price_only_for_price_intent(self):
        cases = [
            ("机制类", None),
            ("成本低", None),
            ("需求类", "请突出优惠活动和到手价"),
        ]
        for video_type, extra_requirements in cases:
            with self.subTest(video_type=video_type, extra_requirements=extra_requirements):
                ai = PromptCaptureAI("门店备货先看独立包装，打包配送更省心。")
                generator = ScriptGenerator()
                generator.ai = ai
                asyncio.run(generator.generate(
                    product=make_product(),
                    template=None,
                    video_type=video_type,
                    extra_requirements=extra_requirements,
                ))
                prompt = "\n".join(message["content"] for message in ai.messages)
                self.assertIn("允许使用真实且抽象的价格/活动表达", prompt)
                self.assertNotIn("本条脚本不要求价格", prompt)

    def test_negative_price_requirements_do_not_enable_price_policy(self):
        for extra_requirements in (
            "不要写价格",
            "本条不提活动和优惠",
            "产品没有优惠，不要编造",
            "本条无活动",
            "不包含价格信息",
            "目前不存在促销",
        ):
            with self.subTest(extra_requirements=extra_requirements):
                ai = PromptCaptureAI("门店备货先看独立包装，打包配送更省心。")
                generator = ScriptGenerator()
                generator.ai = ai

                asyncio.run(generator.generate(
                    product=make_product(),
                    template=None,
                    video_type="需求类",
                    extra_requirements=extra_requirements,
                ))

                prompt = "\n".join(message["content"] for message in ai.messages)
                self.assertIn("本条脚本不要求价格", prompt)
                self.assertNotIn("允许使用真实且抽象的价格/活动表达", prompt)

    def test_no_threshold_coupon_is_treated_as_real_positive_promotion(self):
        for extra_requirements in ("无门槛优惠券", "没有门槛的优惠券"):
            with self.subTest(extra_requirements=extra_requirements):
                ai = PromptCaptureAI("门店备货先看独立包装，打包配送更省心。")
                generator = ScriptGenerator()
                generator.ai = ai

                asyncio.run(generator.generate(
                    product=make_product(),
                    template=None,
                    video_type="需求类",
                    extra_requirements=extra_requirements,
                ))

                prompt = "\n".join(message["content"] for message in ai.messages)
                self.assertIn("允许使用真实且抽象的价格/活动表达", prompt)

    def test_valid_first_response_uses_one_model_call(self):
        ai = PromptCaptureAI("先把独立袋装刀叉放到打包台上，配送时干净又稳。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(make_product(), None, "需求类"))

        self.assertIn("独立袋装刀叉", result)
        self.assertEqual(len(ai.calls), 1)

    def test_generic_audience_opening_triggers_one_repair(self):
        ai = SequenceResponseAI([
            "烘焙姐妹们看过来，袋装刀叉适合门店配送。",
            "先把独立袋装刀叉放到打包台上，配送时更干净。",
        ])
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(make_product(), None, "需求类"))

        self.assertEqual(len(ai.calls), 2)
        self.assertEqual(ai.calls[1]["temperature"], 0.95)
        self.assertIs(ai.calls[1]["allow_fallback"], False)
        repair_prompt = ai.calls[1]["messages"][-1]["content"]
        self.assertIn('"generic_audience_call"', repair_prompt)
        self.assertIn("烘焙姐妹们看过来", repair_prompt)
        self.assertIn("重排卖点推进顺序", repair_prompt)
        self.assertIn("先把独立袋装刀叉", result)

    def test_empty_attention_opening_triggers_one_repair(self):
        ai = SequenceResponseAI([
            "你们知道吗？这个真的很好用。",
            "先把独立袋装刀叉放到打包台上，配送时更干净。",
        ])
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(make_product(), None, "需求类"))

        self.assertEqual(len(ai.calls), 2)
        self.assertIn('"empty_attention_hook"', ai.calls[1]["messages"][-1]["content"])

    def test_recent_opening_similarity_triggers_one_repair(self):
        recent = ["先把独立袋装刀叉整整齐齐摆到门店打包台最顺手的位置，"]
        ai = SequenceResponseAI([
            recent[0],
            "急单打包最怕餐叉裸放，这套独立包装直接解决卫生冲突。",
        ])
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(make_product(), None, "需求类", recent_openings=recent))

        self.assertEqual(len(ai.calls), 2)
        repair_prompt = ai.calls[1]["messages"][-1]["content"]
        self.assertIn('"recent_opening_similarity"', repair_prompt)
        self.assertIn(recent[0], repair_prompt)

    def test_invalid_or_empty_repair_returns_best_available_script(self):
        second_responses = [
            "烘焙姐妹们看过来，还是这套餐叉。",
            "",
        ]
        for second_response in second_responses:
            with self.subTest(second_response=repr(second_response)):
                ai = SequenceResponseAI([
                    "烘焙姐妹们看过来，袋装刀叉适合门店配送。",
                    second_response,
                ])
                generator = ScriptGenerator()
                generator.ai = ai
                result = asyncio.run(generator.generate(make_product(), None, "需求类"))

                self.assertTrue(result)
                self.assertNotIn("姐妹们", result)
                if second_response:
                    self.assertIn("还是这套餐叉", result)
                else:
                    self.assertIn("袋装刀叉适合门店配送", result)
                self.assertEqual(len(ai.calls), 2)

    def test_provider_error_during_repair_returns_first_script(self):
        ai = SequenceResponseAI([
            "烘焙姐妹们看过来，袋装刀叉适合门店配送。",
            RuntimeError("provider failed"),
        ])
        generator = ScriptGenerator()
        generator.ai = ai

        with self.assertLogs("services.script_generator", level="WARNING"):
            result = asyncio.run(generator.generate(make_product(), None, "需求类"))

        self.assertEqual(result, "袋装刀叉适合门店配送。")
        self.assertEqual(len(ai.calls), 2)
    def test_generation_fails_instead_of_using_local_template_when_interface_unavailable(self):
        generator = ScriptGenerator()
        generator.ai = UnavailableInterfaceAI()

        with self.assertRaisesRegex(ScriptGenerationError, "AI生成模型未配置"):
            asyncio.run(generator.generate(
                product=make_product(name="糖珠", category="烘焙装饰"),
                template=None,
                video_type="AI智能生成",
            ))

    def test_generation_fails_instead_of_using_local_template_when_provider_errors_or_returns_empty(self):
        for ai in (FailingResponseAI(), EmptyResponseAI()):
            generator = ScriptGenerator()
            generator.ai = ai

            with self.assertRaisesRegex(ScriptGenerationError, "AI生成"):
                asyncio.run(generator.generate(
                    product=make_product(name="糖珠", category="烘焙装饰"),
                    template=None,
                    video_type="AI智能生成",
                ))

    def test_library_rewrite_fails_instead_of_using_local_template_when_interface_unavailable(self):
        generator = ScriptGenerator()
        generator.ai = UnavailableInterfaceAI()

        with self.assertRaisesRegex(ScriptGenerationError, "模板库改写模型未配置"):
            asyncio.run(generator.generate_from_library(
                product=make_product(name="糖珠", category="烘焙装饰"),
                video_type="需求类",
                template=make_template_context(),
            ))

    def test_library_rewrite_fails_without_ai_fallback_when_provider_errors_or_returns_empty(self):
        for ai in (FailingResponseAI(), EmptyResponseAI()):
            generator = ScriptGenerator()
            generator.ai = ai

            with self.assertRaisesRegex(ScriptGenerationError, "模板库改写"):
                asyncio.run(generator.generate_from_library(
                    product=make_product(name="糖珠", category="烘焙装饰"),
                    video_type="需求类",
                    template=make_template_context(),
                ))
            self.assertIs(ai.allow_fallback, False)

    def test_generation_uses_interface_availability_instead_of_deepseek_global_flag(self):
        ai = InterfaceAvailableAI("门店打包先把独立袋装刀叉摆好，配送时更干净。")
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
        self.assertIn("独立袋装刀叉", result)

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
        self.assertIn("黄金前3秒服务 CTR", system_prompt)
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
        ai = PromptCaptureAI("（主播手拿袋装刀叉）先把独立袋装餐叉摆上打包台，配送更干净。")
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
        self.assertIn("黄金前3秒服务 CTR", system_prompt)
        self.assertIn("烘焙店老板/烘焙从业者", system_prompt)
        self.assertIn("真实使用场景", system_prompt)
        self.assertIn("每句话添加镜头说明", user_prompt)
        self.assertIn("（镜头/画面说明）口播文案", user_prompt)
        self.assertNotIn("参考模板库脚本", user_prompt)
        self.assertNotIn("参考模板库脚本", system_prompt)

    def test_non_price_shot_design_prompt_omits_price_marker(self):
        ai = PromptCaptureAI("（打包台近景）先把独立袋装餐叉按订单摆好，配送更干净。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="需求类",
            include_shot_design=True,
        ))

        user_prompt = ai.messages[-1]["content"]

        self.assertIn("【钩子】【痛点】【卖点】【CTA】", user_prompt)
        self.assertNotIn("【价格】", user_prompt)

    def test_shot_design_prompt_uses_opening_brief_without_legacy_variation_directive(self):
        ai = PromptCaptureAI("（打包台近景）急单打包别让餐叉裸放，独立包装更稳。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="场景类",
            include_shot_design=True,
        ))

        system_prompt = ai.messages[0]["content"]

        self.assertIn("【本次开头策略】", system_prompt)
        self.assertNotIn("创意要求：", system_prompt)

    def test_plain_deepseek_prompt_discourages_default_sister_openers_and_varies_angle(self):
        ai = PromptCaptureAI("门店打包先看刀叉是不是独立包装，配送更干净。")
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

        self.assertIn("本次开头策略", system_prompt)
        self.assertIn("策略家族：", system_prompt)
        self.assertIn("禁止以“姐妹们”“烘焙姐妹们”", system_prompt)
        self.assertIn("第一口播小句必须直接提供", system_prompt)
        self.assertNotIn("可以使用“啊、姐妹们", system_prompt)
        self.assertNotIn("可以使用“啊、姐妹们", user_prompt)

    def test_generic_audience_call_ban_has_no_extra_requirements_exception(self):
        ai = PromptCaptureAI("急单打包先看独立包装，配送更干净。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="需求类",
            extra_requirements="请从配送卫生这个产品角度切入。",
        ))

        system_prompt = ai.messages[0]["content"]

        self.assertIn("禁止以“姐妹们”“烘焙姐妹们”“家人们”“老板们看过来”作为开头。", system_prompt)
        self.assertNotIn("除非用户额外要求", system_prompt)

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

        self.assertIn("本次开头策略", system_prompt)
        self.assertIn("禁止以“姐妹们”“烘焙姐妹们”", system_prompt)
        self.assertNotIn("像烘焙姐妹聊天一样自然", system_prompt)
        self.assertNotIn("使用口语化表达：姐妹们", system_prompt)

    def test_plain_ai_generation_repairs_default_sister_opening_before_post_process(self):
        ai = SequenceResponseAI([
            "烘焙姐妹们，袋装刀叉别只看便宜，门店配送更要看独立包装和承托稳定。",
            "门店配送袋装刀叉别只看便宜，独立包装和承托稳定更重要。",
        ])
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="痛点类",
            tone="直接",
            include_shot_design=False,
        ))

        self.assertEqual(len(ai.calls), 2)
        self.assertTrue(result.startswith("门店配送"))

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
        self.assertIn("糖珠 500g 售价十块以内，活动到手十块以内", user_prompt)
        self.assertIn("价格表达规则", user_prompt)
        self.assertIn("最终脚本禁止输出精确金额", user_prompt)
        self.assertNotIn("售价¥9.18", user_prompt)
        self.assertNotIn("活动到手¥8.26", user_prompt)
        self.assertNotIn("9.18元", user_prompt)

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
        self.assertIn("糖珠 500g 售价十块以内，活动到手十块以内", user_prompt)
        self.assertIn("最终脚本禁止输出精确金额", user_prompt)
        self.assertNotIn("售价¥9.18", user_prompt)
        self.assertNotIn("活动到手¥8.26", user_prompt)
        self.assertIn("每句话添加镜头说明", user_prompt)
        self.assertIn("（镜头/画面说明）口播文案", user_prompt)
        self.assertNotIn("参考模板库脚本", user_prompt)

    def test_deepseek_output_sanitizes_precise_prices_but_keeps_specs(self):
        ai = PromptCaptureAI("这款糖珠500g只要9.18元，活动到手¥8.26，6寸蛋糕用也很方便，12个月保质，30秒就能点缀好。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product_with_knowledge(),
            template=None,
            video_type="机制类",
            tone="直接",
            include_shot_design=False,
        ))

        self.assertIn("500g", result)
        self.assertIn("6寸", result)
        self.assertIn("12个月", result)
        self.assertIn("30秒", result)
        self.assertIn("十块以内", result)
        self.assertNotIn("9.18元", result)
        self.assertNotIn("¥8.26", result)

    def test_shot_design_output_sanitizes_precise_prices(self):
        ai = PromptCaptureAI("（产品近景）袋装刀叉0.64元一套，500g包装旁边展示，6寸蛋糕配送也能用。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product(name="袋装刀叉", category="烘焙配件", price=0.64),
            template=None,
            video_type="机制类",
            tone="直接",
            include_shot_design=True,
        ))

        self.assertIn("几毛钱一套", result)
        self.assertIn("500g", result)
        self.assertIn("6寸", result)
        self.assertNotIn("0.64元", result)

    def test_deepseek_prompt_uses_reference_structure_without_copying_reference_script_content(self):
        ai = PromptCaptureAI("先把独立袋装刀叉摆上打包台，配送出单更干净。")
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
        system_prompt = ai.messages[0]["content"]

        self.assertIn("抖音跑量自检框架", system_prompt)
        self.assertIn("【同类型脚本结构参考】", user_prompt)
        self.assertIn("结构参考 #1", user_prompt)
        self.assertIn("开头方式", user_prompt)
        self.assertIn("痛点推进", user_prompt)
        self.assertIn("卖点顺序", user_prompt)
        self.assertIn("价格/机制位置", user_prompt)
        self.assertIn("CTA节奏", user_prompt)
        self.assertIn("画面段落功能", user_prompt)
        self.assertIn("禁止复制参考脚本原文", user_prompt)
        self.assertNotIn("【参考模板】", user_prompt)
        self.assertNotIn("推荐开头钩子", user_prompt)
        self.assertNotIn("推荐CTA话术", user_prompt)
        self.assertNotIn("模板库示例脚本", user_prompt)
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
