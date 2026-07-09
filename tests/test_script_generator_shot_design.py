import asyncio
import unittest

from services.script_generator import ScriptGenerator


class CapturingAI:
    is_available = True

    def __init__(self, response):
        self.response = response
        self.messages = None

    def get_model_name(self):
        return "fake-model"

    async def chat(self, messages, temperature=0.75):
        self.messages = messages
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


class ScriptGeneratorShotDesignTests(unittest.TestCase):
    def test_plain_copy_prompt_and_post_process_remove_shot_design(self):
        ai = CapturingAI("【痛点】\n0-3s\n（镜头推进展示产品）这是一句卖点。\n慕斯粉（液）口感细腻，3秒凝固也没问题。")
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
        self.assertIn("这是一句卖点。", result)
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
        self.assertIn("姐妹们！2024年了", result)
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
        self.assertIn("姐妹们，别等恢复原价了", result)
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
