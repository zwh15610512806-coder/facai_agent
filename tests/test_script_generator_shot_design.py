import asyncio
import unittest

from services.script_generator import ScriptGenerationError, ScriptGenerator


class CapturingAI:
    is_available = True

    def __init__(self, response):
        self.response = response
        self.messages = None
        self.calls = 0

    def get_model_name(self):
        return "fake-model"

    async def chat(self, messages, temperature=0.75):
        self.messages = messages
        self.calls += 1
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


def make_product():
    return {
        "name": "慕斯粉（液）",
        "category": "烘焙夹心",
        "price": 46.94,
        "brand": "法采",
        "selling_points": [
            {"type": "口感", "content": "口感细腻，冷藏后稳定", "priority": 1},
        ],
    }


def make_template_context():
    return {
        "id": 7,
        "name": "机制类出单模板",
        "video_type": "机制类",
        "structure": {
            "opening": "3秒内抛出活动机制和门店囤货理由",
            "proof": "用真实使用场景承接产品证明",
            "cta": "自然引导左下角下单",
        },
        "hook_templates": ["现在还在用老办法配夹心的老板看过来"],
        "cta_templates": ["需要稳定出品的老板点左下角"],
        "duration_range": "15-25s",
        "description": "适合烘焙店老板的机制类成交模板",
        "example_script": "老板们，急单夹心不想等太久，就用这个结构先讲机制再给证明。",
    }


def make_neutral_template():
    return {
        "id": 8,
        "name": "机制类低价模板",
        "video_type": "成本低",
        "structure": {
            "opening": "从急单场景切入",
            "proof": "展示产品稳定性",
            "cta": "自然引导左下角下单",
        },
        "hook_templates": ["急单夹心来不及冷藏，就先看凝固速度。"],
        "cta_templates": ["需要稳定出品就点左下角"],
        "duration_range": "15-25s",
        "description": "适合急单场景的产品证明模板",
        "example_script": "急单夹心来不及等，就先展示凝固速度，再证明口感稳定。",
    }


class ScriptGeneratorShotDesignTests(unittest.TestCase):
    def test_library_template_without_audience_call_forbids_and_strips_model_added_call(self):
        responses = {
            False: "姐妹们，快看过来！这款慕斯粉冷藏后更稳定。",
            True: "（镜头推近慕斯切面）做蛋糕的姐妹们，别划走！这款慕斯粉冷藏后更稳定。",
        }

        for include_shot_design, response in responses.items():
            with self.subTest(include_shot_design=include_shot_design):
                ai = CapturingAI(response)
                generator = ScriptGenerator()
                generator.ai = ai

                result = asyncio.run(generator.generate_from_library(
                    product=make_product(),
                    video_type="需求类",
                    template=make_neutral_template(),
                    include_shot_design=include_shot_design,
                ))

                system_prompt = ai.messages[0]["content"]
                user_prompt = ai.messages[1]["content"]
                for prompt in (system_prompt, user_prompt):
                    self.assertIn("模板不包含人群召唤", prompt)
                    self.assertIn("禁止新增", prompt)
                self.assertNotIn("姐妹们", result)
                self.assertNotIn("别划走", result)
                self.assertIn("这款慕斯粉冷藏后更稳定。", result)
                if include_shot_design:
                    self.assertTrue(result.startswith("（镜头推近慕斯切面）"))

    def test_library_template_hook_audience_call_is_allowed_and_preserved(self):
        template = make_neutral_template()
        template["hook_templates"] = ["老板们看过来，急单先看凝固速度。"]
        ai = CapturingAI("老板们看过来，急单先看这款慕斯粉。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=template,
        ))

        for message in ai.messages:
            self.assertIn("模板明确包含人群召唤", message["content"])
            self.assertIn("可保留相同结构的人群召唤", message["content"])
        self.assertTrue(result.startswith("老板们看过来，"))

    def test_library_matching_plain_audience_call_is_preserved_in_pure_and_shot_modes(self):
        responses = {
            False: "姐妹们，这款慕斯粉冷藏后更稳定。",
            True: "（镜头推近慕斯切面）姐妹们，这款慕斯粉冷藏后更稳定。",
        }
        for include_shot_design, response in responses.items():
            with self.subTest(include_shot_design=include_shot_design):
                template = make_neutral_template()
                template["hook_templates"] = ["姐妹们，急单先看凝固速度。"]
                ai = CapturingAI(response)
                generator = ScriptGenerator()
                generator.ai = ai

                result = asyncio.run(generator.generate_from_library(
                    product=make_product(),
                    video_type="需求类",
                    template=template,
                    include_shot_design=include_shot_design,
                ))

                self.assertIn("姐妹们", result)
                self.assertEqual(ai.calls, 1)

    def test_library_intensified_audience_cue_is_stripped_in_pure_and_shot_modes(self):
        cases = (
            (
                "老板们看过来，急单先看凝固速度。",
                "老板们，别划走！这款慕斯粉冷藏后更稳定。",
                False,
            ),
            (
                "老板们看过来，急单先看凝固速度。",
                "（镜头推近慕斯切面）老板们，别划走！这款慕斯粉冷藏后更稳定。",
                True,
            ),
            (
                "姐妹们，急单先看凝固速度。",
                "姐妹们注意了，这款慕斯粉冷藏后更稳定。",
                False,
            ),
            (
                "姐妹们，急单先看凝固速度。",
                "（镜头推近慕斯切面）姐妹们看过来，这款慕斯粉冷藏后更稳定。",
                True,
            ),
        )
        for template_hook, response, include_shot_design in cases:
            with self.subTest(response=response):
                template = make_neutral_template()
                template["hook_templates"] = [template_hook]
                ai = CapturingAI(response)
                generator = ScriptGenerator()
                generator.ai = ai

                result = asyncio.run(generator.generate_from_library(
                    product=make_product(),
                    video_type="需求类",
                    template=template,
                    include_shot_design=include_shot_design,
                ))

                self.assertNotIn("老板们", result)
                self.assertNotIn("姐妹们", result)
                self.assertNotIn("别划走", result)
                self.assertNotIn("注意了", result)
                self.assertNotIn("看过来", result)
                self.assertIn("这款慕斯粉冷藏后更稳定。", result)
                self.assertEqual(ai.calls, 1)

    def test_library_template_example_audience_call_is_allowed_and_preserved(self):
        template = make_neutral_template()
        template["example_script"] = "姐妹们，先看夹心凝固速度，再看切面。"
        ai = CapturingAI("姐妹们，先看这款慕斯粉的凝固速度。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=template,
        ))

        self.assertIn("模板明确包含人群召唤", ai.messages[0]["content"])
        self.assertIn("模板明确包含人群召唤", ai.messages[1]["content"])
        self.assertTrue(result.startswith("姐妹们，"))

    def test_library_substituted_audience_phrase_is_stripped_even_when_template_allows_one(self):
        template = make_neutral_template()
        template["hook_templates"] = ["老板们看过来，急单先看凝固速度。"]
        ai = CapturingAI("姐妹们，别划走！这款慕斯粉冷藏后更稳定。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=template,
        ))

        self.assertEqual(ai.calls, 1)
        self.assertEqual(result, "这款慕斯粉冷藏后更稳定。")

    def test_library_declarative_audience_subject_does_not_allow_model_added_call(self):
        responses = {
            False: "开烘焙店的朋友们，先看这款慕斯粉。",
            True: "（镜头推近慕斯切面）开烘焙店的朋友们，先看这款慕斯粉。",
        }
        for include_shot_design, response in responses.items():
            with self.subTest(include_shot_design=include_shot_design):
                template = make_neutral_template()
                template["hook_templates"] = ["做蛋糕的姐妹们每天都会提前备料。"]
                ai = CapturingAI(response)
                generator = ScriptGenerator()
                generator.ai = ai

                result = asyncio.run(generator.generate_from_library(
                    product=make_product(),
                    video_type="需求类",
                    template=template,
                    include_shot_design=include_shot_design,
                ))

                self.assertIn("模板不包含人群召唤", ai.messages[0]["content"])
                self.assertNotIn("朋友们", result)
                self.assertIn("先看这款慕斯粉。", result)
                if include_shot_design:
                    self.assertTrue(result.startswith("（镜头推近慕斯切面）"))

    def test_library_generalized_audience_substitution_is_stripped_in_pure_and_shot_paths(self):
        responses = {
            False: "经营烘焙店的朋友们先看这款慕斯粉。",
            True: "（镜头推近慕斯切面）经营烘焙店的朋友们先看这款慕斯粉。",
        }
        for include_shot_design, response in responses.items():
            with self.subTest(include_shot_design=include_shot_design):
                template = make_neutral_template()
                template["hook_templates"] = ["开烘焙店的朋友们先看凝固速度。"]
                ai = CapturingAI(response)
                generator = ScriptGenerator()
                generator.ai = ai

                result = asyncio.run(generator.generate_from_library(
                    product=make_product(),
                    video_type="需求类",
                    template=template,
                    include_shot_design=include_shot_design,
                ))

                self.assertIn("模板明确包含人群召唤", ai.messages[0]["content"])
                self.assertNotIn("经营烘焙店的朋友们", result)
                self.assertIn("这款慕斯粉。", result)

    def test_library_rewrite_uses_one_model_call_without_ai_opening_history_or_repair_blocks(self):
        ai = CapturingAI("姐妹们，快看过来！这款慕斯粉冷藏后更稳定。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=make_neutral_template(),
        ))

        combined_prompt = "\n".join(message["content"] for message in ai.messages)
        self.assertEqual(ai.calls, 1)
        self.assertNotIn("本次开头策略", combined_prompt)
        self.assertNotIn("近期首句去重", combined_prompt)
        self.assertNotIn("机器校验原因", combined_prompt)
        self.assertEqual(result, "这款慕斯粉冷藏后更稳定。")

    def test_library_template_without_price_structure_forbids_price_even_when_name_and_type_suggest_it(self):
        ai = CapturingAI("急单先看凝固速度，这款慕斯粉冷藏后更稳定。")
        generator = ScriptGenerator()
        generator.ai = ai

        asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="成本低",
            template=make_neutral_template(),
        ))

        for message in ai.messages:
            self.assertIn("模板没有价格或机制段落", message["content"])
            self.assertIn("不得新增价格、优惠、折扣、赠品或促销内容", message["content"])
        user_prompt = ai.messages[1]["content"]
        self.assertNotIn("价格/机制位置", user_prompt)
        self.assertNotIn("价格/机制 →", user_prompt)

    def test_library_non_price_content_mechanism_does_not_enable_price_copy(self):
        template = make_neutral_template()
        template["description"] = "强调内容机制和口播推进，保持产品证明段落。"
        template["structure"] = {
            "opening": "从急单场景切入",
            "proof": "解释内容机制，再展示凝固稳定性",
            "cta": "自然引导左下角下单",
        }
        ai = CapturingAI("急单先看凝固速度，现在8折，点左下角。")
        generator = ScriptGenerator()
        generator.ai = ai

        with self.assertRaisesRegex(
            ScriptGenerationError,
            "模板库改写结果擅自加入价格或促销信息，请重试。",
        ):
            asyncio.run(generator.generate_from_library(
                product=make_product(),
                video_type="需求类",
                template=template,
            ))

        for message in ai.messages:
            self.assertIn("模板没有价格或机制段落", message["content"])

    def test_library_template_with_price_structure_allows_abstract_price_in_matching_position(self):
        template = make_neutral_template()
        template["structure"] = {
            "opening": "从急单场景切入",
            "price": "产品证明后承接活动价和优惠机制",
            "cta": "自然引导左下角下单",
        }
        ai = CapturingAI("急单先看凝固速度，稳定后再说几十块的活动价，最后点左下角。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=template,
        ))

        for message in ai.messages:
            self.assertIn("模板包含价格或机制功能", message["content"])
            self.assertIn("在模板对应结构位置使用目标产品的抽象价格", message["content"])
            self.assertIn("价格待更新时不得编造", message["content"])
        self.assertIn("几十块", result)

    def test_library_template_without_price_structure_rejects_model_price_copy(self):
        forbidden_outputs = (
            "急单先看凝固速度，现在活动价十来块，点左下角。",
            "急单先看凝固速度，买一送一，点左下角。",
            "急单先看凝固速度，一杯奶茶钱就能入手。",
            "急单先看凝固速度，现在8折，点左下角。",
            "急单先看凝固速度，现在立减10，点左下角。",
            "急单先看凝固速度，现在十九块九，点左下角。",
        )
        for response in forbidden_outputs:
            with self.subTest(response=response):
                ai = CapturingAI(response)
                generator = ScriptGenerator()
                generator.ai = ai

                with self.assertRaisesRegex(
                    ScriptGenerationError,
                    "模板库改写结果擅自加入价格或促销信息，请重试。",
                ) as raised:
                    asyncio.run(generator.generate_from_library(
                        product=make_product(),
                        video_type="需求类",
                        template=make_neutral_template(),
                    ))

                self.assertEqual(raised.exception.status_code, 502)
                self.assertEqual(ai.calls, 1)

    def test_library_template_without_price_structure_allows_numeric_specs_time_and_count(self):
        ai = CapturingAI(
            "这款500g慕斯粉适合6寸蛋糕，保质期12个月，30秒看完3个稳定细节。"
        )
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=make_neutral_template(),
        ))

        self.assertIn("500g", result)
        self.assertIn("6寸", result)
        self.assertIn("12个月", result)
        self.assertIn("30秒", result)
        self.assertEqual(ai.calls, 1)

    def test_ai_generation_repairs_invalid_opening_once_in_pure_and_shot_modes(self):
        for include_shot_design in (False, True):
            with self.subTest(include_shot_design=include_shot_design):
                first_response = "姐妹们，别划走！这款慕斯粉冷藏后更稳定。"
                repaired_response = "急单夹心最怕冷藏后还站不住，这款慕斯粉凝固更稳定。"
                if include_shot_design:
                    first_response = f"（镜头推近慕斯切面）{first_response}"
                    repaired_response = f"（镜头推近慕斯切面）{repaired_response}"
                ai = CapturingAI([first_response, repaired_response])
                generator = ScriptGenerator()
                generator.ai = ai

                result = asyncio.run(generator.generate(
                    product=make_product(),
                    template=None,
                    video_type="需求类",
                    include_shot_design=include_shot_design,
                ))

                self.assertEqual(ai.calls, 2)
                self.assertIn("急单夹心最怕", result)

    def test_ai_shot_design_validates_spoken_opening_after_leading_camera_parentheses(self):
        ai = CapturingAI("（手部近景，把独立袋装刀叉摆上打包台）先把餐叉按订单摆好，配送打包更干净。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="场景类",
            include_shot_design=True,
        ))

        self.assertEqual(ai.calls, 1)
        self.assertIn("（手部近景", result)
        self.assertIn("每句话添加镜头说明", ai.messages[-1]["content"])
    def test_plain_copy_prompt_and_post_process_remove_shot_design(self):
        ai = CapturingAI("【痛点】\n0-3s\n（镜头推进展示产品）急单夹心先看凝固速度。\n慕斯粉（液）口感细腻，3秒凝固也没问题。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate(
            product=make_product(),
            template=None,
            video_type="需求类",
            tone="活泼",
            include_shot_design=False,
        ))

        system_prompt = ai.messages[0]["content"]
        prompt = ai.messages[-1]["content"]
        self.assertIn("纯口播一段话", system_prompt)
        self.assertIn("禁止【】段落标签", system_prompt)
        self.assertNotIn("用【】标记每个段落功能", system_prompt)
        self.assertIn("只输出一段连续视频文案", prompt)
        self.assertIn("禁止镜头说明", prompt)
        self.assertIn("禁止换行", prompt)
        self.assertNotIn("时间标记：每个段落标注时间范围", prompt)
        self.assertNotIn("段落标记：用【钩子】", prompt)
        self.assertNotIn("\n", result)
        self.assertNotIn("【痛点】", result)
        self.assertNotIn("0-3s", result)
        self.assertNotIn("镜头推进", result)
        self.assertIn("急单夹心先看凝固速度。", result)
        self.assertIn("慕斯粉（液）口感细腻，3秒凝固也没问题。", result)

    def test_plain_library_rewrite_outputs_single_spoken_paragraph(self):
        ai = CapturingAI(
            "---\n\n"
            "**改写自：爆款脚本 #3**\n\n"
            "【开场钩子-前3秒】\n"
            "（镜头对准，手里端着一杯奶冻，语气惊讶又兴奋）\n"
            "姐妹们！2024年了，我才发现这个烘焙界的出单神器！\n\n"
            "【痛点激发】\n"
            "（镜头切换到展示用吉利丁片制作奶冻时，等待凝固时间长、操作麻烦的画面）\n"
            "以前做个蛋糕夹心，用吉利丁片泡半天、煮半天，还要等冷藏好几个小时才能定型，急单根本接不了。"
        )
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="机制类",
            template=make_template_context(),
            tone="活泼",
            include_shot_design=False,
        ))

        system_prompt = ai.messages[0]["content"]
        prompt = ai.messages[-1]["content"]
        self.assertIn("专业的带货文案结构分析师与改写专家", system_prompt)
        self.assertIn("结构分析只在内部完成，不输出结构分析", system_prompt)
        self.assertIn("当前输出模式：纯口播一段话", system_prompt)
        self.assertIn("只输出一段连续自然口播文案", system_prompt)
        self.assertNotIn("保持结构和节奏", system_prompt)
        self.assertNotIn("用【】标记每个段落功能", system_prompt)
        self.assertIn("引用模板：机制类出单模板", prompt)
        self.assertIn("3秒内抛出活动机制和门店囤货理由", prompt)
        self.assertIn("现在还在用老办法配夹心的老板看过来", prompt)
        self.assertIn("需要稳定出品的老板点左下角", prompt)
        self.assertIn("老板们，急单夹心不想等太久", prompt)
        self.assertIn("售价：几十块", prompt)
        self.assertIn("价格表达规则", prompt)
        self.assertNotIn("售价：46.94元", prompt)
        self.assertIn("只借鉴模板的成交结构", prompt)
        self.assertIn("最终只输出一段连续口播文案", prompt)
        self.assertIn("严禁输出“改写自”", prompt)
        self.assertIn("禁止复制模板示例脚本原文", prompt)
        self.assertNotIn("从以上", prompt)
        self.assertNotIn("爆款脚本 #", prompt)
        self.assertNotIn("完整脚本内容", prompt)
        self.assertNotIn("**保持**原脚本的结构", prompt)
        self.assertNotIn("时间标注", prompt)
        self.assertNotIn("镜头指令微调", prompt)
        self.assertNotIn("必须在开头标注你改写了第几条脚本", prompt)

        self.assertNotIn("\n", result)
        self.assertNotIn("---", result)
        self.assertNotIn("**", result)
        self.assertNotIn("改写自", result)
        self.assertNotIn("【", result)
        self.assertNotIn("】", result)
        self.assertNotIn("镜头", result)
        self.assertNotIn("前3秒", result)
        self.assertNotIn("姐妹们", result)
        self.assertIn("2024年了", result)
        self.assertIn("以前做个蛋糕夹心", result)

    def test_shot_design_library_rewrite_uses_unified_rewrite_prompt_and_keeps_shot_requirements(self):
        ai = CapturingAI("（主播半身站在烘焙台前开场，手边摆放慕斯粉包装）老板们看过来。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=make_template_context(),
            tone="活泼",
            include_shot_design=True,
        ))

        system_prompt = ai.messages[0]["content"]
        self.assertIn("专业的带货文案结构分析师与改写专家", system_prompt)
        self.assertIn("输出1条文案，500字以内", system_prompt)
        self.assertIn("当前输出模式：画面括号 + 口播文案", system_prompt)
        self.assertIn("拍摄主体、镜头/景别、动作或道具", system_prompt)
        self.assertIn("（主播半身站在烘焙台前开场", result)

    def test_plain_library_rewrite_removes_ai_preamble_and_format_scaffold(self):
        ai = CapturingAI(
            "好的，没问题！作为拥有5年抖音烘焙带货经验的脚本改写专家，我完全理解你的需求。"
            "根据你提供的3条爆款脚本和目标产品“袋装刀叉”，我选择**爆款脚本 #2**进行改写。"
            "这条脚本的“机制类”定位、活泼口语化的风格以及“大促囤货”的紧迫感，与刀叉卖点高度契合。\n\n"
            "以下是为你全新改写的带货脚本：\n\n"
            "---\n\n"
            "**改写自：爆款脚本 #2**\n\n"
            "【开场钩子-前3秒】\n"
            "（镜头快速扫过一堆法采袋装刀叉，然后定格在一套精美的纸袋包装上，语气急促）\n"
            "姐妹们，别等恢复原价了才后悔没多囤几单！法采这个袋装刀叉，价格真的太离谱了！\n\n"
            "【促销信息-第一波】\n"
            "（镜头展示不同角度堆叠的袋装刀叉，强调数量感）\n"
            "法采年终福利，力度搞这么大，确定不来看一下？拍下一单，直接到手50套袋装刀叉！"
        )
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product={
                "name": "袋装刀叉",
                "category": "烘焙配件",
                "price": 55.17,
                "brand": "法采",
                "selling_points": [
                    {"type": "包装", "content": "独立袋装，干净卫生，适合蛋糕配送", "priority": 1},
                ],
            },
            video_type="机制类",
            template=make_template_context(),
            tone="活泼",
            include_shot_design=False,
        ))

        self.assertNotIn("\n", result)
        self.assertNotIn("好的，没问题", result)
        self.assertNotIn("脚本改写专家", result)
        self.assertNotIn("以下是", result)
        self.assertNotIn("改写自", result)
        self.assertNotIn("---", result)
        self.assertNotIn("【", result)
        self.assertNotIn("】", result)
        self.assertNotIn("镜头", result)
        self.assertNotIn("！ 法采", result)
        self.assertNotIn("？ 拍下", result)
        self.assertIn("？拍下", result)
        self.assertNotIn("姐妹们", result)
        self.assertIn("别等恢复原价了", result)
        self.assertIn("法采年终福利", result)

    def test_shot_design_prompt_requires_camera_notes_for_each_sentence(self):
        ai = CapturingAI("（镜头展示慕斯粉）这是一句卖点。\n（成品特写）这是第二句。")
        generator = ScriptGenerator()
        generator.ai = ai

        result = asyncio.run(generator.generate_from_library(
            product=make_product(),
            video_type="需求类",
            template=make_template_context(),
            tone="活泼",
            include_shot_design=True,
        ))

        prompt = ai.messages[-1]["content"]
        self.assertIn("参考脚本模板库的画面节奏", prompt)
        self.assertIn("引用模板：机制类出单模板", prompt)
        self.assertIn("每句话添加镜头说明", prompt)
        self.assertIn("（镜头/画面说明）口播文案", prompt)
        self.assertIn("\n", result)
        self.assertIn("镜头展示慕斯粉", result)


if __name__ == "__main__":
    unittest.main()
