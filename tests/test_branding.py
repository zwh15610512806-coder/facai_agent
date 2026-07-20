import unittest
from pathlib import Path

import config


ROOT = Path(__file__).resolve().parents[1]
NEW_BRAND = "抖音运营agent"
OLD_BRAND = "法采新媒体运营 Agent"


class BrandingTests(unittest.TestCase):
    def test_app_title_uses_new_media_operations_name(self):
        self.assertEqual(config.APP_TITLE, NEW_BRAND)

    def test_templates_use_new_brand_name(self):
        template_paths = sorted((ROOT / "templates").glob("*.html"))
        self.assertGreater(len(template_paths), 0)

        for path in template_paths:
            with self.subTest(path=path.name):
                page = path.read_text(encoding="utf-8-sig")
                self.assertIn(NEW_BRAND, page)
                self.assertNotIn(OLD_BRAND, page)


if __name__ == "__main__":
    unittest.main()
