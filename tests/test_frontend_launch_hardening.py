import unittest
from pathlib import Path

from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]


class FrontendLaunchHardeningTests(unittest.TestCase):
    def setUp(self):
        self.import_page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")
        self.products_page = (ROOT / "templates" / "products.html").read_text(encoding="utf-8-sig")
        self.templates_page = read_page_source("templates.html")
        self.common_js = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8-sig")

    def test_excel_upload_surfaces_only_xlsx(self):
        self.assertIn('id="productFile"', self.import_page)
        self.assertIn('accept=".csv,.xlsx,.md,.markdown"', self.import_page)
        self.assertNotIn(".xlsx,.xls", self.import_page)
        self.assertIn("name.endsWith('.xlsx')?'/api/import/excel':'/api/import/csv'", self.import_page)
        self.assertIn('id="qianchuanFileInput" type="file" accept=".xlsx"', self.templates_page)
        self.assertIn('id="workbookImportFile" type="file" accept=".xlsx"', self.templates_page)
        self.assertIn("支持 .xlsx，带蛋糕参考图会同步到脚本详情。", self.templates_page)
        self.assertNotIn("支持 .xlsx/.xls", self.templates_page)
        self.assertNotIn('accept=".pdf,.doc,.docx,.xlsx,.xls', self.products_page)

    def test_upload_dropzones_are_keyboard_accessible(self):
        self.assertIn('id="productDrop" class="drop" role="button" tabindex="0" aria-controls="productFile"', self.import_page)
        self.assertIn('id="txtScriptDrop" class="drop" role="button" tabindex="0" aria-controls="txtScriptFiles"', self.import_page)
        self.assertIn("activateDropZoneFileInput(e, 'productFile')", self.import_page)
        self.assertIn("activateDropZoneFileInput(e, 'txtScriptFiles')", self.import_page)
        self.assertIn('id="dropZone" class="drop" role="button" tabindex="0" aria-controls="fileInput"', self.products_page)
        self.assertIn("activateDropZoneFileInput(e, 'fileInput')", self.products_page)

    def test_template_inline_dynamic_arguments_use_js_literals(self):
        self.assertIn("function jsStringLiteral", self.templates_page)
        self.assertNotIn("function escJsArg", self.templates_page)
        self.assertIn("onclick=\"openCakeImage('+jsStringLiteral(img.url)+')\"", self.templates_page)
        self.assertIn("onclick=\"bindQianchuanMaterial('+jsStringLiteral(item.material_id)+')\"", self.templates_page)

    def test_shared_mobile_nav_scrolls_active_link_into_view(self):
        self.assertIn("function scrollActiveNavIntoView", self.common_js)
        self.assertIn("document.querySelector('.nav-links .nav-link.on, .nav-links .nav-link[aria-current=\"page\"]')", self.common_js)
        self.assertIn("active.scrollIntoView({block:'nearest',inline:'center'})", self.common_js)
        self.assertIn("document.addEventListener('DOMContentLoaded', scrollActiveNavIntoView)", self.common_js)


if __name__ == "__main__":
    unittest.main()
