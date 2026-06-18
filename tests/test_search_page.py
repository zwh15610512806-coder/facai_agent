import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SearchPageTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "search.html").read_text(encoding="utf-8-sig")

    def test_search_page_uses_library_style_workspace(self):
        self.assertIn('class="page-main search-page"', self.page)
        self.assertIn('class="search-command"', self.page)
        self.assertIn('class="search-results search-board"', self.page)
        self.assertIn('id="topPagination"', self.page)
        self.assertIn('id="bottomPagination"', self.page)

    def test_search_pagination_supports_page_size_and_jump(self):
        self.assertIn("let currentPage = 1, totalPages = 1, pageSize = 15, totalResults = 0", self.page)
        self.assertIn("per_page: pageSize", self.page)
        self.assertIn("changePageSize(this.value)", self.page)
        self.assertIn("jumpToPage()", self.page)
        self.assertIn("15 条/页", self.page)
        self.assertIn("30 条/页", self.page)
        self.assertIn("60 条/页", self.page)

    def test_clear_states_do_not_reference_removed_pagination_node(self):
        script = self.page.split("<script>", 1)[1]
        self.assertNotIn("$('pagination')", script)
        self.assertRegex(script, re.compile(r"function renderPagination\(\).*topPagination.*bottomPagination", re.S))

    def test_ai_banner_fields_are_escaped_before_inner_html(self):
        self.assertIn("escHtml(ai.keywords.join('、'))", self.page)
        self.assertIn("escHtml(ai.file_type)", self.page)
        self.assertIn("escHtml(ai.extension)", self.page)
        self.assertIn("escHtml(ai.date_from)", self.page)

    def test_ai_summary_escapes_server_text_before_markdown_rendering(self):
        self.assertIn("simpleMD(escHtml(d.summary))", self.page)
        self.assertIn("escHtml(d.message||'生成失败')", self.page)


if __name__ == "__main__":
    unittest.main()
