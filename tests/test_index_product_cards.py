import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexProductCardTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_generator_product_cards_do_not_render_prices(self):
        render_products = re.search(
            r"function renderProducts\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(render_products)
        body = render_products.group("body")
        self.assertNotIn("pprice", body)
        self.assertNotIn("formatPrice(p.price)", body)
        self.assertNotIn("original_price", body)

    def test_generator_product_grid_uses_compact_cards(self):
        self.assertRegex(
            self.page,
            r"#productGrid\s*\{\s*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(190px,\s*1fr\)\);",
        )
        self.assertIn("#productGrid .product-card", self.page)
        self.assertIn("padding: 16px", self.page)
        self.assertIn("min-height: 116px", self.page)

    def test_generator_product_name_is_slightly_larger_and_bolder(self):
        product_name_css = re.search(
            r"#productGrid \.product-card \.pname\s*\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(product_name_css)
        body = product_name_css.group("body")
        self.assertIn("font-size: 16px", body)
        self.assertIn("font-weight: 700", body)


if __name__ == "__main__":
    unittest.main()
