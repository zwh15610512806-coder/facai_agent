import unittest
from pathlib import Path

from fastapi import FastAPI

from routers import templates


class TemplateRouterDomainTests(unittest.TestCase):
    def test_composite_router_keeps_urls_but_declarations_live_in_domain_modules(self):
        app = FastAPI()
        app.include_router(templates.router)
        paths = app.openapi()["paths"]

        self.assertIn("post", paths["/viral/import-workbook"])
        self.assertIn("post", paths["/viral/scan-local-txt"])
        self.assertIn("post", paths["/qianchuan/import"])
        self.assertIn("get", paths["/viral/list"])

        source = (Path(__file__).resolve().parents[1] / "routers" / "templates.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('@router.post("/qianchuan/import")', source)
        self.assertNotIn('@router.post("/viral/import-workbook")', source)
        self.assertIn("template_qianchuan", source)
        self.assertIn("template_workbook_import", source)


if __name__ == "__main__":
    unittest.main()
