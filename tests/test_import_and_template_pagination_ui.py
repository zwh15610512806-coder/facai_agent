import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ImportWorkspaceLayoutTests(unittest.TestCase):
    def test_import_page_uses_full_width_workspace_layout(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn('class="page-main import-main"', page)
        self.assertIn('class="import-workspace"', page)
        self.assertIn('id="productImportPanel"', page)
        self.assertIn('id="txtBatchPanel"', page)
        self.assertIn('id="singleScriptPanel"', page)
        self.assertIn("minmax(320px, 1fr)", page)


class TemplatePaginationUiTests(unittest.TestCase):
    def test_template_library_has_client_side_pagination_controls(self):
        page = (ROOT / "templates" / "templates.html").read_text(encoding="utf-8-sig")

        self.assertIn('id="paginationBar"', page)
        self.assertIn('id="pageInfo"', page)
        self.assertIn('id="pagePrev"', page)
        self.assertIn('id="pageNext"', page)
        self.assertIn('id="pageSize"', page)
        self.assertIn('id="pageJumpInput"', page)
        self.assertIn("var currentPage=1", page)
        self.assertIn("var pageSize=15", page)
        self.assertIn("function renderPagination", page)
        self.assertIn("function setPage", page)
        self.assertIn("function jumpToPage", page)
        self.assertIn("function getPagedItems", page)


if __name__ == "__main__":
    unittest.main()
