import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperationsNavigationSourceTests(unittest.TestCase):
    def test_every_application_navigation_places_operations_after_creators(self):
        templates = []
        for path in sorted((ROOT / "templates").glob("*.html")):
            source = path.read_text(encoding="utf-8-sig")
            if 'class="nav-links"' in source:
                templates.append(path)
                with self.subTest(template=path.name):
                    navigation = re.search(
                        r'<div class="nav-links">(?P<body>.*?)</div>',
                        source,
                        re.DOTALL,
                    )
                    self.assertIsNotNone(navigation)
                    body = navigation.group("body")
                    self.assertRegex(
                        body,
                        r'href="/app/creators"[^>]*>达人工作</a>\s*'
                        r'<a href="/app/operations"[^>]*>运营数据中台</a>',
                    )
                    self.assertNotIn('href="/app/api-connections"', body)

        self.assertGreaterEqual(len(templates), 10)

    def test_compact_desktop_and_mobile_navigation_contracts_are_present(self):
        css = (ROOT / "static" / "css" / "style.css").read_text(
            encoding="utf-8-sig"
        )
        common = (ROOT / "static" / "js" / "common.js").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("@media (min-width: 769px) and (max-width: 1599px)", css)
        self.assertIn(".nav-link", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn(
            "{label: 'API接入', href: '/app/api-connections', icon: 'plug-zap'}",
            common,
        )
        self.assertIn(
            "nav.appendChild(createToolLink(item, 'nav-link nav-mobile-utility'))",
            common,
        )


if __name__ == "__main__":
    unittest.main()
