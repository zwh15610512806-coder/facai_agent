import unittest

from services.script_price import abstract_script_price, sanitize_script_price_text


class ScriptPriceLanguageTests(unittest.TestCase):
    def test_abstract_script_price_uses_short_price_bands(self):
        cases = [
            (0.64, "几毛钱"),
            (5.2, "几块钱"),
            (9.18, "十块以内"),
            (12.71, "十来块"),
            (23.29, "一杯奶茶钱"),
            (46.94, "几十块"),
            (128.0, "一百出头"),
            (388.0, "三位数"),
            (1288.0, "千元级"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(abstract_script_price(value), expected)

    def test_sanitize_script_price_text_replaces_precise_money_without_touching_specs(self):
        text = "糖珠 500g 售价¥9.18，活动到手8.26元，袋装刀叉0.64元一套，6寸蛋糕用，12个月保质，30秒搞定。"

        sanitized = sanitize_script_price_text(text)

        self.assertIn("500g", sanitized)
        self.assertIn("6寸", sanitized)
        self.assertIn("12个月", sanitized)
        self.assertIn("30秒", sanitized)
        self.assertIn("售价十块以内", sanitized)
        self.assertIn("活动到手十块以内", sanitized)
        self.assertIn("袋装刀叉几毛钱一套", sanitized)
        self.assertNotIn("¥9.18", sanitized)
        self.assertNotIn("8.26元", sanitized)
        self.assertNotIn("0.64元", sanitized)


if __name__ == "__main__":
    unittest.main()
