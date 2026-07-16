import asyncio
import unittest

from services.script_generator import ScriptGenerationError, ScriptGenerator
from services.script_structure import extract_script_beats


class SequencedAI:
    is_available = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages, temperature=0.75, **kwargs):
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "kwargs": kwargs,
        })
        return self.responses.pop(0)


def make_product(*, pending_price=False):
    product = {
        "name": "慕斯粉",
        "category": "烘焙夹心",
        "price": 18.6,
        "brand": "法采",
        "selling_points": [
            {"type": "操作", "content": "开水搅匀后加入淡奶油，操作简单", "priority": 1},
            {"type": "稳定", "content": "冷藏后不易出水塌陷", "priority": 2},
            {"type": "口感", "content": "入口细腻，微甜不腻", "priority": 3},
        ],
    }
    if pending_price:
        product["pending_fields"] = ["price"]
    return product


def make_template():
    return {
        "id": 7,
        "name": "成本低模板",
        "video_type": "成本低",
        "structure": {
            "segments": [
                {"name": "成本钩子", "goal": "先谈价格"},
                {"name": "价格证明", "goal": "强调优惠"},
                {"name": "促单收口", "goal": "引导下单"},
            ],
        },
        "hook_templates": ["老板们看过来，做烘焙别只看单价。"],
        "cta_templates": ["想省成本就点左下角。"],
        "example_script": "老板们看过来，先讲价格，再讲优惠，最后点左下角。",
    }


def make_source(content=None):
    return {
        "id": 948,
        "source": "facai",
        "title": "夹心脆 / 脚本参考 / 口感和使用体验 / 文案",
        "video_type": "成本低",
        "content": content or (
            "真正的好夹心，先看入口的层次（捧起一把夹心给镜头看）\n"
            "颗颗都能吃到酥脆和清爽（成品切面近景展示）\n"
            "做蛋糕夹心时不用反复搭配，出品更省心（用户体验夹馅）\n"
            "适合想把口感做丰富的门店"
        ),
    }


def valid_plain_response():
    return (
        "[[BEAT_1]]真正好用的慕斯粉，先看做出来的细腻口感。"
        "[[BEAT_2]]入口微甜不腻，冷藏后的切面也很稳定。"
        "[[BEAT_3]]做蛋糕夹心不用反复试配方，操作更省心。"
        "[[BEAT_4]]适合想把夹心口感做丰富的烘焙门店。"
    )


class ScriptStructureExtractionTests(unittest.TestCase):
    def test_extracts_ordered_beats_and_removes_visual_parentheses(self):
        beats = extract_script_beats(make_source()["content"])

        self.assertEqual(len(beats), 4)
        self.assertEqual(beats[0]["text"], "真正的好夹心，先看入口的层次")
        self.assertEqual(beats[1]["text"], "颗颗都能吃到酥脆和清爽")
        self.assertNotIn("镜头", "".join(beat["text"] for beat in beats))
        self.assertNotIn("成品切面", "".join(beat["text"] for beat in beats))


class TemplateRewriteStructureFidelityTests(unittest.TestCase):
    def _generate(self, responses, **kwargs):
        ai = SequencedAI(responses)
        generator = ScriptGenerator()
        generator.ai = ai
        result = asyncio.run(generator.generate_from_library(
            product=kwargs.pop("product", make_product()),
            video_type="成本低",
            template=make_template(),
            source_script=kwargs.pop("source_script", make_source()),
            **kwargs,
        ))
        return result, ai

    def test_concrete_source_is_primary_skeleton_and_markers_are_removed(self):
        result, ai = self._generate([valid_plain_response()])

        prompt = ai.calls[0]["messages"][-1]["content"]
        self.assertIn("具体引用脚本是唯一主结构", prompt)
        self.assertIn("通用结构模板不得新增、删除或重排表达点", prompt)
        self.assertIn("[[BEAT_1]]", prompt)
        self.assertIn("[[BEAT_4]]", prompt)
        self.assertIn("同功能的真实卖点或证明", prompt)
        self.assertEqual(ai.calls[0]["temperature"], 0.45)
        self.assertNotIn("[[BEAT_", result)
        self.assertNotIn("\n", result)
        self.assertTrue(result.startswith("真正好用的慕斯粉"))
        self.assertTrue(result.endswith("烘焙门店。"))

    def test_shot_design_keeps_one_output_line_per_source_beat(self):
        response = (
            "[[BEAT_1]]（慕斯切面近景，镜头缓慢推近）先看做出来的细腻口感。"
            "[[BEAT_2]]（勺子挖起慕斯特写）入口微甜不腻。"
            "[[BEAT_3]]（俯拍操作台，手部搅拌原料）操作不用反复试配方。"
            "[[BEAT_4]]（门店冷柜中景，展示成品蛋糕）适合烘焙门店日常出品。"
        )
        result, _ai = self._generate([response], include_shot_design=True)

        self.assertNotIn("[[BEAT_", result)
        self.assertEqual(len(result.splitlines()), 4)
        self.assertTrue(all(line.startswith("（") for line in result.splitlines()))

    def test_invalid_order_repairs_once_with_original_skeleton_and_reason(self):
        first = "[[BEAT_2]]先写第二条。[[BEAT_1]]再写第一条。"
        result, ai = self._generate([first, valid_plain_response()])

        self.assertEqual(len(ai.calls), 2)
        repair_prompt = ai.calls[1]["messages"][-1]["content"]
        self.assertIn("表达点序号缺失、重复或顺序错误", repair_prompt)
        self.assertIn("[[BEAT_1]]", repair_prompt)
        self.assertIn(first, repair_prompt)
        self.assertNotIn("[[BEAT_", result)

    def test_second_invalid_result_raises_structure_error(self):
        invalid = "没有任何内部表达点序号。"
        with self.assertRaisesRegex(
            ScriptGenerationError,
            "模板库改写结构未通过，请重新生成",
        ) as raised:
            self._generate([invalid, invalid])

        self.assertEqual(raised.exception.status_code, 502)

    def test_empty_first_result_repairs_once(self):
        result, ai = self._generate(["", valid_plain_response()])

        self.assertEqual(len(ai.calls), 2)
        self.assertIn("表达点序号缺失、重复或顺序错误", ai.calls[1]["messages"][-1]["content"])
        self.assertNotIn("[[BEAT_", result)

    def test_source_length_rule_overrides_default_500_character_limit(self):
        _result, ai = self._generate([valid_plain_response()])

        system_prompt = ai.calls[0]["messages"][0]["content"]
        self.assertIn("原稿超过500字时允许改写稿超过500字", system_prompt)
        self.assertIn("结构完整性优先于默认500字限制", system_prompt)

    def test_preparing_materials_is_not_mistaken_for_cta(self):
        source = make_source(
            "开店每天都要先备料\n"
            "操作步骤越简单越省心\n"
            "冷藏后切面依旧稳定\n"
            "适合门店日常出品"
        )
        response = (
            "[[BEAT_1]]开店每天都要先备料。"
            "[[BEAT_2]]这款慕斯粉操作简单更省心。"
            "[[BEAT_3]]冷藏后切面依旧稳定。"
            "[[BEAT_4]]适合烘焙门店日常出品。"
        )
        result, ai = self._generate([response], source_script=source)

        self.assertEqual(len(ai.calls), 1)
        self.assertIn("先备料", result)

    def test_template_price_and_cta_cannot_override_source_without_them(self):
        first = (
            "[[BEAT_1]]老板们看过来，这款慕斯粉十来块。"
            "[[BEAT_2]]入口微甜不腻。"
            "[[BEAT_3]]操作更省心。"
            "[[BEAT_4]]想要的点左下角。"
        )
        result, ai = self._generate([first, valid_plain_response()])

        first_prompt = ai.calls[0]["messages"][-1]["content"]
        self.assertIn("原脚本没有价格或促销表达，禁止通用结构模板新增", first_prompt)
        self.assertIn("原脚本没有 CTA，禁止通用结构模板新增", first_prompt)
        self.assertIn("原脚本没有泛人群召唤，禁止新增", first_prompt)
        repair_prompt = ai.calls[1]["messages"][-1]["content"]
        self.assertIn("价格或促销出现在原脚本没有的位置", repair_prompt)
        self.assertIn("CTA 出现在原脚本没有的位置", repair_prompt)
        self.assertIn("新增了原脚本没有的泛人群召唤", repair_prompt)
        self.assertNotIn("十来块", result)
        self.assertNotIn("左下角", result)
        self.assertNotIn("老板们", result)

    def test_price_and_cta_must_remain_in_their_source_beats(self):
        source = make_source(
            "先看这份夹心做出来的口感\n"
            "现在十来块就能备一份\n"
            "冷藏后切面依旧稳定\n"
            "需要的点左下角看看"
        )
        wrong = (
            "[[BEAT_1]]这份慕斯粉十来块，先看口感。"
            "[[BEAT_2]]备一份很省心。"
            "[[BEAT_3]]冷藏后切面稳定，点左下角看看。"
            "[[BEAT_4]]适合门店使用。"
        )
        repaired = (
            "[[BEAT_1]]先看这份慕斯粉做出来的细腻口感。"
            "[[BEAT_2]]现在十来块就能备一份。"
            "[[BEAT_3]]冷藏后切面依旧稳定。"
            "[[BEAT_4]]需要的点左下角看看。"
        )
        result, ai = self._generate([wrong, repaired], source_script=source)

        self.assertEqual(len(ai.calls), 2)
        repair_prompt = ai.calls[1]["messages"][-1]["content"]
        self.assertIn("价格或促销位置与原脚本不一致", repair_prompt)
        self.assertIn("CTA 位置与原脚本不一致", repair_prompt)
        self.assertIn("十来块", result)
        self.assertTrue(result.endswith("点左下角看看。"))

    def test_pending_price_replaces_price_beat_with_verified_value(self):
        source = make_source(
            "先看这份夹心做出来的口感\n"
            "现在十来块就能备一份\n"
            "冷藏后切面依旧稳定\n"
            "需要的点左下角看看"
        )
        response = (
            "[[BEAT_1]]先看这份慕斯粉做出来的细腻口感。"
            "[[BEAT_2]]操作步骤简单，日常出品更省心。"
            "[[BEAT_3]]冷藏后切面依旧稳定。"
            "[[BEAT_4]]需要的点左下角看看。"
        )
        result, ai = self._generate(
            [response],
            source_script=source,
            product=make_product(pending_price=True),
        )

        prompt = ai.calls[0]["messages"][-1]["content"]
        self.assertIn("价格待更新", prompt)
        self.assertIn("在原价格表达点的位置改写为真实价值证明", prompt)
        self.assertNotIn("十来块", result)

    def test_length_outside_allowed_ratio_repairs_once(self):
        too_short = (
            "[[BEAT_1]]好用。[[BEAT_2]]稳定。[[BEAT_3]]省心。[[BEAT_4]]适合门店。"
        )
        _result, ai = self._generate([too_short, valid_plain_response()])

        self.assertEqual(len(ai.calls), 2)
        self.assertIn("总口播长度不在原脚本的 65%-140% 范围内", ai.calls[1]["messages"][-1]["content"])

    def test_blank_explicit_source_fails_before_model_call(self):
        ai = SequencedAI([valid_plain_response()])
        generator = ScriptGenerator()
        generator.ai = ai

        with self.assertRaisesRegex(ScriptGenerationError, "引用脚本正文为空") as raised:
            asyncio.run(generator.generate_from_library(
                product=make_product(),
                video_type="成本低",
                template=make_template(),
                source_script=make_source("   "),
            ))

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(ai.calls, [])


if __name__ == "__main__":
    unittest.main()
