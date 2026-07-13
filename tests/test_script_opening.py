import random
import unittest
from dataclasses import FrozenInstanceError

from services.script_opening import (
    AI_OPENING_FAMILIES,
    OPENING_SIMILARITY_THRESHOLD,
    OpeningBrief,
    OpeningCheck,
    classify_opening_family,
    collect_template_audience_phrases,
    extract_normalized_leading_audience_phrase,
    extract_spoken_opening,
    has_empty_attention_hook,
    has_generic_audience_opening,
    normalize_opening,
    opening_similarity,
    select_opening_brief,
    strip_generic_audience_opening,
    template_allows_audience_call,
    validate_opening,
)


class FirstChoice:
    def choice(self, values):
        return values[0]


class CostChoice:
    def choice(self, values):
        return "cost_mechanism" if "cost_mechanism" in values else values[0]


class ScriptOpeningTests(unittest.TestCase):
    def test_extracts_and_normalizes_leading_generic_audience_phrase(self):
        cases = (
            ("老板们看过来，先看凝固速度。", "老板们"),
            ("（镜头推近） 姐妹们！别划走。", "姐妹们"),
            ("经营烘焙店的朋友们先看这个切面。", "经营烘焙店的朋友们"),
            ("急单夹心来不及等，就先看凝固速度。", None),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    extract_normalized_leading_audience_phrase(text),
                    expected,
                )

    def test_collects_only_explicit_template_leading_audience_phrases(self):
        template = {
            "hook_templates": [
                "老板们看过来，急单先看凝固速度。",
                {"alternate": "姐妹们，先看这个切面。"},
                "急单夹心来不及等，就先展示凝固速度。",
            ],
            "example_script": "（镜头推近）老板们，先看成品稳定性。",
        }

        self.assertEqual(
            collect_template_audience_phrases(template),
            {"老板们看过来", "老板们", "姐妹们"},
        )

    def test_strip_generic_audience_opening_preserves_shot_note_and_removes_empty_call_cue(self):
        cases = (
            (
                "（镜头：推近产品包装）姐妹们，快看过来！这款奶油打发更稳。",
                "（镜头：推近产品包装）这款奶油打发更稳。",
            ),
            (
                "(近景展示切面)做蛋糕的宝子们、注意了，这个切面更细腻。",
                "(近景展示切面)这个切面更细腻。",
            ),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(strip_generic_audience_opening(text), expected)

    def test_strip_generic_audience_opening_leaves_declarative_audience_subject_unchanged(self):
        text = "做蛋糕的姐妹们通常会提前备料。"

        self.assertEqual(strip_generic_audience_opening(text), text)

    def test_strip_generic_audience_opening_removes_consecutive_empty_cues(self):
        cases = (
            ("姐妹们，看过来，别划走！这款奶油更稳。", "这款奶油更稳。"),
            (
                "（镜头推近奶油切面）开烘焙店的朋友们，快看过来，注意了！这款奶油更稳。",
                "（镜头推近奶油切面）这款奶油更稳。",
            ),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(strip_generic_audience_opening(text), expected)

    def test_public_constants_and_value_objects_are_immutable(self):
        self.assertEqual(OPENING_SIMILARITY_THRESHOLD, 0.76)
        self.assertEqual(
            set(AI_OPENING_FAMILIES),
            {
                "action",
                "scene_conflict",
                "result_contrast",
                "cognition",
                "product_proof",
                "customer_feedback",
                "cost_mechanism",
            },
        )
        for instruction in AI_OPENING_FAMILIES.values():
            with self.subTest(instruction=instruction):
                self.assertRegex(instruction, r"[\u4e00-\u9fff]")
                self.assertNotRegex(instruction, r"[A-Za-z]")
                self.assertLessEqual(len(instruction), 40)
        brief = OpeningBrief("action", "用具体制作动作开场。")
        check = OpeningCheck(True, "先看奶油状态", (), 0.0)
        with self.assertRaises(FrozenInstanceError):
            brief.family = "cognition"
        with self.assertRaises(FrozenInstanceError):
            check.valid = False

    def test_extract_spoken_opening_removes_labels_timing_and_shot_notes(self):
        script = "**开场（0-3秒）**\n00:00-00:03\n（镜头：展示切面）先看这款奶油的状态，打发到七分就能抹面。"
        self.assertEqual(extract_spoken_opening(script), "先看这款奶油的状态，")

    def test_extract_spoken_opening_removes_chinese_bracket_label_before_shot_note(self):
        script = "【开场钩子-前3秒】\n（镜头：快速推近产品）先看这款奶油的纹路，七分发刚刚好。"
        self.assertEqual(extract_spoken_opening(script), "先看这款奶油的纹路，")

    def test_extract_spoken_opening_removes_bold_label_and_bracketed_time_range(self):
        script = "**开场白：**\n[00:00-00:03]\n这款奶油乳脂含量是38%，打发更稳定。"
        self.assertEqual(extract_spoken_opening(script), "这款奶油乳脂含量是38%，")

    def test_extract_spoken_opening_removes_leading_second_range_labels(self):
        cases = (
            ("0-3秒：先看这款奶油的状态，后面讲原因。", "先看这款奶油的状态，"),
            ("3-10s\n先看这款奶油的状态，后面讲原因。", "先看这款奶油的状态，"),
            ("[0-3秒]\n先看这款奶油的状态，后面讲原因。", "先看这款奶油的状态，"),
            ("【0-3s】先看这款奶油的状态，后面讲原因。", "先看这款奶油的状态，"),
            ("[00:00-00:03]\n先看这款奶油的状态，后面讲原因。", "先看这款奶油的状态，"),
        )
        for script, expected in cases:
            with self.subTest(script=script):
                self.assertEqual(extract_spoken_opening(script), expected)

    def test_extract_spoken_opening_obeys_limit_without_clause(self):
        self.assertEqual(extract_spoken_opening("这是一段没有标点的连续开场", limit=8), "这是一段没有标点")

    def test_detects_generic_audience_openings_without_flagging_declarative_sentence(self):
        self.assertTrue(has_generic_audience_opening("烘焙姐妹们，今天看奶油。"))
        self.assertTrue(has_generic_audience_opening("老板们看过来，这个成本要算清。"))
        self.assertFalse(has_generic_audience_opening("很多烘焙店老板选材料只看价格。"))

    def test_detects_variable_anchored_audience_openings(self):
        openings = (
            "经常做烘焙的姐妹们，今天看奶油。",
            "做烘焙调色总翻车的姐妹们快看过来，这个方法更稳。",
            "开私房的宝子们，这个出品细节要记住。",
            "做蛋糕的家人们，先看打发状态。",
            "开烘焙店的朋友们，今天看奶油。",
            "经营社区面包房的店主们，记住这个比例。",
            "从事甜品外卖的创业者们，注意打发状态。",
        )
        for opening in openings:
            with self.subTest(opening=opening):
                self.assertTrue(has_generic_audience_opening(opening))
        self.assertFalse(has_generic_audience_opening("很多烘焙店老板选材料只看价格。"))

    def test_generalized_audience_opening_requires_punctuation_or_call_cue(self):
        self.assertFalse(has_generic_audience_opening("做蛋糕的姐妹们通常会提前备料。"))
        self.assertTrue(has_generic_audience_opening("做蛋糕的姐妹们，先看这个切面。"))
        self.assertTrue(has_generic_audience_opening("做蛋糕的姐妹们快看过来！"))
        self.assertTrue(has_generic_audience_opening("做蛋糕的姐妹们今天看奶油。"))
        self.assertTrue(has_generic_audience_opening("做蛋糕的姐妹们先看这个切面。"))
        self.assertTrue(has_generic_audience_opening("做蛋糕的姐妹们一定要看。"))

    def test_audience_phrase_boundary_distinguishes_direct_calls_from_declarations(self):
        direct_calls = (
            "做烘焙的宝子们",
            "开烘焙店的姐妹们",
            "做烘焙的宝子们：先看这款奶油。",
            "开烘焙店的姐妹们快看过来！",
        )
        for opening in direct_calls:
            with self.subTest(opening=opening):
                self.assertTrue(has_generic_audience_opening(opening))

        declarations = (
            "姐妹们通常会提前备料。",
            "烘焙姐妹们更重视稳定性。",
            "做蛋糕的姐妹们通常会提前备料。",
        )
        for opening in declarations:
            with self.subTest(opening=opening):
                self.assertFalse(has_generic_audience_opening(opening))

    def test_audience_phrase_is_direct_only_for_bounded_address_continuations(self):
        direct_calls = (
            "姐妹们",
            "做蛋糕的姐妹们，通常会提前备料。",
        )
        direct_markers = (
            "今天看",
            "先看",
            "一定要看",
            "记住",
            "注意",
            "听我说",
            "别",
            "快",
            "赶紧",
            "来看",
            "看看",
            "必须",
            "千万",
        )
        direct_calls += tuple(
            f"经营烘焙店的朋友们{marker}这个打发状态。"
            for marker in direct_markers
        )
        for opening in direct_calls:
            with self.subTest(opening=opening):
                self.assertTrue(has_generic_audience_opening(opening))

        declarative_markers = (
            "每天",
            "平时",
            "通常",
            "一般",
            "都会",
            "经常",
            "往往",
            "更",
            "也",
            "最",
            "需要",
            "习惯",
            "在",
            "旺季",
            "做",
            "开",
        )
        for marker in declarative_markers:
            opening = f"做蛋糕的姐妹们{marker}提前备料。"
            with self.subTest(opening=opening):
                self.assertFalse(has_generic_audience_opening(opening))

        unknown_continuations = (
            "开烘焙店的老板们核对一下成本。",
            "经营私房烘焙的朋友们偏爱稳定的奶油。",
        )
        for opening in unknown_continuations:
            with self.subTest(opening=opening):
                self.assertFalse(has_generic_audience_opening(opening))

    def test_detects_only_empty_attention_hooks(self):
        self.assertTrue(has_empty_attention_hook("你们知道吗？"))
        self.assertTrue(has_empty_attention_hook("别划走！"))
        self.assertTrue(has_empty_attention_hook("这个真的太好用了。"))
        self.assertTrue(has_empty_attention_hook("今天给大家分享一个好东西。"))
        self.assertTrue(has_empty_attention_hook("今天推荐一款神器。"))
        self.assertTrue(has_empty_attention_hook("给大家安利一个好物。"))
        self.assertTrue(has_empty_attention_hook("这款产品真的值得入手。"))
        self.assertTrue(has_empty_attention_hook("这个效果真的太绝了。"))
        self.assertFalse(has_empty_attention_hook("你们知道吗，今天这款动物奶油打发到七分就能直接抹面。"))

    def test_prefixed_bakery_owner_call_is_detected_but_declarative_subject_is_not(self):
        self.assertTrue(has_generic_audience_opening("烘焙店老板们，先看这个。"))
        self.assertFalse(has_generic_audience_opening("很多烘焙店老板们每天都会提前备料。"))

    def test_quality_gate_rejects_non_specific_opening_beyond_known_empty_phrases(self):
        check = validate_opening("今天来聊一个特别值得关注的选择。")
        self.assertFalse(check.valid)
        self.assertIn("non_specific_opening", check.reasons)

    def test_quality_gate_accepts_concrete_action_scene_and_product_fact(self):
        concrete_openings = (
            "先把独立袋装刀叉摆到打包台上，配送更干净。",
            "每次赶节日单翻糖珠都要拆三四瓶不同尺寸的，",
            "糖珠适合门店做节日蛋糕装饰。",
            "这款慕斯粉冷藏后更稳定。",
            "顾客试吃后都说这口感更轻。",
            "以前总是塌腰，现在成品能立住一整天。",
            "直接揪一块翻糖膏随便揉两下就能擀开。",
            "揪一块法采翻糖膏往揉面垫上一按就擀成薄皮。",
            "之前冬天做翻糖配件硬得像石头。",
            "昨天我徒弟用这款翻糖膏做的蝴蝶结。",
        )
        for opening in concrete_openings:
            with self.subTest(opening=opening):
                self.assertTrue(validate_opening(opening, product_name="糖珠").valid)

    def test_quality_gate_rejects_action_and_scene_shells_without_product_detail(self):
        vague_openings = (
            "先把这个记下来，后面你会用到。",
            "门店一定要看这个，真的很实用。",
            "后厨拿起这个看一下，真的很实用。",
            "糖珠更好，今天就用它。",
            "顾客都说好。",
        )
        for opening in vague_openings:
            with self.subTest(opening=opening):
                check = validate_opening(opening, product_name="糖珠")
                self.assertFalse(check.valid)
                self.assertIn("non_specific_opening", check.reasons)

    def test_empty_attention_hook_only_evaluates_immediate_clause(self):
        self.assertTrue(has_empty_attention_hook("别划走，先听我说，后面讲奶油为什么不稳定。"))
        self.assertFalse(has_empty_attention_hook("别划走，今天这款动物奶油打发到七分就能抹面。"))

    def test_empty_attention_hook_rejects_detail_after_sentence_ending_punctuation(self):
        self.assertTrue(has_empty_attention_hook("你们知道吗？奶油打发到七分最稳。"))
        self.assertTrue(has_empty_attention_hook("别划走！这款奶油不稳定。"))
        self.assertFalse(has_empty_attention_hook("你们知道吗：奶油打发到七分最稳。"))

    def test_empty_attention_hook_allows_immediate_concrete_detail_after困扰(self):
        self.assertFalse(has_empty_attention_hook("有没有这种困扰，奶油总是打过头？"))
        self.assertFalse(has_empty_attention_hook("有没有这种困扰，高峰期订单一多就来不及出品？"))

    def test_empty_attention_hook_rejects_unspecified困扰(self):
        self.assertTrue(has_empty_attention_hook("有没有这种困扰，怎么做都不对？"))
        self.assertTrue(has_empty_attention_hook("有没有这种困扰，产品总是不对？"))
        self.assertFalse(has_empty_attention_hook("有没有这种困扰，奶油总是结块？"))

    def test_empty_attention_hook_allows_immediate_product_proof_facts(self):
        facts = (
            "你们知道吗，这款奶油乳脂含量是38%。",
            "别划走，这款奶油配料只有五种。",
            "你们知道吗：这款奶油成分只有乳脂和水。",
            "别划走，这款奶油规格是1千克。",
            "你们知道吗，这款奶油克重是500克。",
            "别划走，这款奶油保质期是12个月。",
            "你们知道吗，这款奶油质地细腻。",
            "别划走，这款奶油颜色是乳白色。",
            "你们知道吗，这款奶油稳定性提升了20%。",
            "别划走，这款奶油售价是19.9元。",
        )
        for opening in facts:
            with self.subTest(opening=opening):
                self.assertFalse(has_empty_attention_hook(opening))

    def test_normalize_opening_removes_product_and_punctuation_noise(self):
        normalized = normalize_opening(" 【Facai】 轻乳酪蛋糕，真的不用烤箱！ ", "轻乳酪蛋糕")
        self.assertNotIn("轻乳酪蛋糕", normalized)
        self.assertNotIn(" ", normalized)
        self.assertNotIn("！", normalized)
        self.assertIn("facai", normalized)
        self.assertEqual(
            normalize_opening("【法采】轻乳酪蛋糕，真的不用烤箱！", "轻乳酪蛋糕"),
            normalized,
        )
        self.assertEqual(
            normalize_opening("法采轻乳酪蛋糕，真的不用烤箱！", "Facai轻乳酪蛋糕"),
            "真的不用烤箱",
        )

    def test_opening_similarity_uses_normalized_text_and_ignores_short_values(self):
        self.assertGreaterEqual(
            opening_similarity(
                "轻乳酪蛋糕今天不用烤箱也能稳定成型不塌腰",
                "轻乳酪蛋糕今天不用烤箱照样稳定成型不塌腰",
                "轻乳酪蛋糕",
            ),
            OPENING_SIMILARITY_THRESHOLD,
        )
        self.assertEqual(opening_similarity("太好吃了", "太好吃了"), 0.0)

    def test_classifies_each_opening_family_conservatively(self):
        examples = {
            "action": "先把奶油打发到七分，再直接抹面。",
            "scene_conflict": "每次高峰期奶油都来不及打发，后厨一团乱。",
            "result_contrast": "以前总是塌腰，现在成品能立住一整天。",
            "cognition": "别再以为奶油越贵越稳定。",
            "product_proof": "这款奶油乳脂含量高，打发后纹路很清楚。",
            "customer_feedback": "顾客试吃后都说这口感更轻。",
            "cost_mechanism": "一盒省下三块钱，成本就能算明白。",
        }
        for family, opening in examples.items():
            with self.subTest(family=family):
                self.assertEqual(classify_opening_family(opening), family)
        self.assertIsNone(classify_opening_family("今天分享一个小技巧。"))

    def test_select_opening_brief_uses_compatible_family_and_avoids_two_recent_families(self):
        brief = select_opening_brief(
            "痛点类",
            {},
            recent_openings=["每次高峰期后厨都一团乱。", "别再以为奶油越贵越稳定。"],
            rng=FirstChoice(),
        )
        self.assertIn(brief.family, {"result_contrast", "action"})
        self.assertNotIn(brief.family, {"scene_conflict", "cognition"})
        self.assertTrue(brief.instruction)

    def test_select_opening_brief_only_allows_price_family_for_real_price_context(self):
        no_promotion = select_opening_brief("AI智能生成", {}, rng=CostChoice())
        with_promotion = select_opening_brief(
            "AI智能生成", {"activity_price": 9.9}, rng=CostChoice()
        )
        self.assertNotEqual(no_promotion.family, "cost_mechanism")
        self.assertEqual(with_promotion.family, "cost_mechanism")

    def test_select_opening_brief_finds_nested_activity_price(self):
        product = {
            "sku_prices": [
                {
                    "spec": "500g",
                    "activity_prices": [
                        {"mechanism": "淘宝A级-调整202603", "final_price": 8.26}
                    ],
                }
            ]
        }
        brief = select_opening_brief("AI智能生成", product, rng=CostChoice())
        self.assertEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_propagates_nested_discount_context(self):
        with_discount = select_opening_brief(
            "AI智能生成", {"discount": {"value": 10}}, rng=CostChoice()
        )
        zero_discount = select_opening_brief(
            "AI智能生成", {"discount": {"value": 0}}, rng=CostChoice()
        )
        self.assertEqual(with_discount.family, "cost_mechanism")
        self.assertNotEqual(zero_discount.family, "cost_mechanism")

    def test_select_opening_brief_rejects_promotion_containers_without_positive_price(self):
        products = (
            {"promotion": {"final_price": 0}},
            {"promotion": [{"final_price": 0}]},
            {"promotion": {}},
            {"activity_price": []},
            {"discount": ({"label": "none"},)},
        )
        for product in products:
            with self.subTest(product=product):
                brief = select_opening_brief("AI智能生成", product, rng=CostChoice())
                self.assertNotEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_accepts_positive_numeric_price_strings(self):
        for value in ("8.26", "8.26元"):
            with self.subTest(value=value):
                brief = select_opening_brief(
                    "AI智能生成", {"activity_price": value}, rng=CostChoice()
                )
                self.assertEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_rejects_invalid_promotion_scalars(self):
        values = (
            "0",
            "0.0",
            "0.00",
            "0元",
            "none",
            "null",
            "false",
            "nan",
            "暂无",
            "无",
            "待更新",
            "未配置",
            "",
            "   ",
        )
        for value in values:
            with self.subTest(value=value):
                brief = select_opening_brief(
                    "AI智能生成", {"activity_price": value}, rng=CostChoice()
                )
                self.assertNotEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_accepts_only_real_promotion_mechanism_text(self):
        for value in ("买一送一", "满200减30"):
            with self.subTest(value=value):
                brief = select_opening_brief(
                    "AI智能生成", {"promotion": value}, rng=CostChoice()
                )
                self.assertEqual(brief.family, "cost_mechanism")
        arbitrary = select_opening_brief(
            "AI智能生成", {"promotion": "none"}, rng=CostChoice()
        )
        self.assertNotEqual(arbitrary.family, "cost_mechanism")

    def test_select_opening_brief_requires_positive_promotion_mechanism_numbers(self):
        for value in ("满0减0", "立减0", "0折", "买0送0"):
            with self.subTest(value=value):
                brief = select_opening_brief(
                    "AI智能生成", {"promotion": value}, rng=CostChoice()
                )
                self.assertNotEqual(brief.family, "cost_mechanism")
        for value in ("满200减30", "立减10", "8折", "买1送1"):
            with self.subTest(value=value):
                brief = select_opening_brief(
                    "AI智能生成", {"promotion": value}, rng=CostChoice()
                )
                self.assertEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_validates_scalars_inside_promotion_context(self):
        qualifying = (
            {"promotion": {"label": "买一送一"}},
            {"promotion": {"mechanism": "满200减30"}},
            {"activity_prices": [{"value": "8.26元"}]},
            {"优惠": {"value": 10}},
        )
        for product in qualifying:
            with self.subTest(product=product):
                brief = select_opening_brief("AI智能生成", product, rng=CostChoice())
                self.assertEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_rejects_invalid_or_unrelated_nested_scalars(self):
        non_qualifying = (
            {"promotion": {"label": "none", "mechanism": "满0减0", "value": 0}},
            {"促销": {"label": "暂无", "mechanism": "买0送0", "value": "0元"}},
            {"metadata": {"label": "买一送一"}},
            {"metadata": {"mechanism": "满200减30", "value": 10}},
        )
        for product in non_qualifying:
            with self.subTest(product=product):
                brief = select_opening_brief("AI智能生成", product, rng=CostChoice())
                self.assertNotEqual(brief.family, "cost_mechanism")

    def test_select_opening_brief_treats_recent_openings_as_newest_first(self):
        brief = select_opening_brief(
            "痛点类",
            {},
            recent_openings=[
                "每次高峰期后厨都一团乱。",
                "订单一多就来不及出品。",
                "以前总是塌腰，现在成品能立住一整天。",
                "别再以为奶油越贵越稳定。",
            ],
            rng=FirstChoice(),
        )
        self.assertEqual(brief.family, "action")

    def test_select_opening_brief_accepts_random_compatible_rng(self):
        brief = select_opening_brief("机制类", {}, rng=random.Random(7))
        self.assertIn(
            brief.family,
            {"cognition", "cost_mechanism", "result_contrast", "product_proof"},
        )

    def test_validate_opening_reports_machine_readable_reasons_and_similarity(self):
        script = "姐妹们今天看这款奶油不用烤箱也能做好。"
        check = validate_opening(
            script,
            recent_openings=["今天看这款奶油不用烤箱照样做好。"],
            product_name="轻乳酪蛋糕",
        )
        self.assertFalse(check.valid)
        self.assertEqual(check.opening, "姐妹们今天看这款奶油不用烤箱也能做好。")
        self.assertIn("generic_audience_call", check.reasons)
        self.assertIn("recent_opening_similarity", check.reasons)
        self.assertGreaterEqual(check.max_similarity, OPENING_SIMILARITY_THRESHOLD)

    def test_validate_opening_can_allow_audience_call_but_rejects_empty_hook(self):
        allowed = validate_opening("家人们，今天看奶油的打发状态。", allow_audience_call=True)
        empty = validate_opening("别划走！")
        self.assertTrue(allowed.valid)
        self.assertFalse(empty.valid)
        self.assertEqual(empty.reasons, ("empty_attention_hook",))

    def test_template_allows_audience_call_only_for_explicit_opening(self):
        self.assertTrue(template_allows_audience_call({"hook_templates": ["姐妹们，今天看奶油。"]}))
        self.assertTrue(template_allows_audience_call({"example_script": "老板们看过来，这个成本要算清。"}))
        self.assertTrue(template_allows_audience_call({"hook_templates": ["开烘焙店的朋友们先看凝固速度。"]}))
        self.assertTrue(template_allows_audience_call({"example_script": "从事甜品外卖的店主们，记住这个比例。"}))
        self.assertFalse(template_allows_audience_call({"hook_templates": ["很多烘焙店老板选材料只看价格。"]}))
        self.assertFalse(template_allows_audience_call({"hook_templates": ["做蛋糕的姐妹们每天都会提前备料。"]}))
        self.assertFalse(template_allows_audience_call({"example_script": "经营烘焙店的朋友们偏爱稳定的奶油。"}))


if __name__ == "__main__":
    unittest.main()
