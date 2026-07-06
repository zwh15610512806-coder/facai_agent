import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexCategorySidebarTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")

    def test_category_sidebar_sticks_while_scrolling_products(self):
        self.assertIn('id="categorySidebar" class="category-sidebar"', self.page)

        css = re.search(r"\.category-sidebar\s*\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        self.assertIsNotNone(css)
        body = css.group("body")

        self.assertIn("position: sticky", body)
        self.assertIn("top:", body)
        self.assertIn("align-self: flex-start", body)

    def test_category_sidebar_does_not_stick_on_small_screens(self):
        mobile = re.search(
            r"@media \(max-width: 760px\)\s*\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(mobile)
        body = mobile.group("body")
        self.assertIn(".category-sidebar", body)
        self.assertIn("position: static", body)

    def test_category_sidebar_shows_real_product_counts(self):
        self.assertIn('class="cat-label">全部品类</span>', self.page)
        self.assertIn('class="cat-count"', self.page)
        self.assertIn("function updateCategoryCountsFromProducts(products)", self.page)
        self.assertIn("function categoryProductCount(category)", self.page)
        self.assertIn("d.innerHTML=categoryItemHtml(c,c)", self.page)

    def test_category_counts_update_only_from_unfiltered_product_load(self):
        load_products = re.search(
            r"async function loadProducts\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(load_products)
        body = load_products.group("body")
        self.assertIn("if(!currentCategory&&!s)updateCategoryCountsFromProducts(state.products)", body)


if __name__ == "__main__":
    unittest.main()
