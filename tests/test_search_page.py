import re
import unittest
from pathlib import Path

from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]


class SearchPageTests(unittest.TestCase):
    def setUp(self):
        self.page = read_page_source("search.html")

    def test_search_page_uses_library_style_workspace(self):
        self.assertIn('class="page-main search-page"', self.page)
        self.assertIn('class="search-workbench"', self.page)
        self.assertIn('class="search-command"', self.page)
        self.assertIn('class="search-sidebar search-panel"', self.page)
        self.assertIn('class="search-results search-board search-panel"', self.page)
        self.assertIn('class="search-panel-hd search-board-hd"', self.page)
        self.assertIn('id="bottomPagination"', self.page)

    def test_ai_understanding_lives_in_sidebar_to_expand_results(self):
        sidebar = re.search(
            r'<aside class="search-sidebar search-panel">(?P<body>.*?)</aside>',
            self.page,
            flags=re.S,
        )
        command = re.search(
            r'<section class="search-command">(?P<body>.*?)</section>',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(sidebar)
        self.assertIsNotNone(command)
        self.assertIn('id="aiBanner"', sidebar.group("body"))
        self.assertNotIn('id="aiBanner"', command.group("body"))
        self.assertIn('class="filter-ai-title"', self.page)

    def test_result_header_uses_single_footer_pagination_area(self):
        board_header = re.search(
            r'<div class="search-panel-hd search-board-hd">(?P<body>.*?)</div>\s*</div>',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(board_header)
        self.assertNotIn('topPagination', board_header.group("body"))
        self.assertIn('class="search-board-footer"', self.page)
        self.assertIn('id="bottomPagination"', self.page)
        self.assertNotIn('id="topPagination"', self.page)

    def test_result_header_is_compact_to_give_list_more_height(self):
        self.assertIn(".search-board-hd{align-items:center;padding:8px 14px}", self.page)
        self.assertIn(".list-title{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;min-width:0}", self.page)

    def test_index_status_moves_from_results_to_command_header(self):
        command_header = re.search(
            r'<div class="search-command-hd">(?P<body>.*?)</div>\s*<div class="search-bar-wrap">',
            self.page,
            flags=re.S,
        )
        results_panel = re.search(
            r'<section class="search-results search-board search-panel">(?P<body>.*?)</section>',
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(command_header)
        self.assertIsNotNone(results_panel)
        self.assertIn('class="search-command-index"', command_header.group("body"))
        self.assertIn('id="indexBadge"', command_header.group("body"))
        self.assertIn('id="indexInfo"', command_header.group("body"))
        self.assertIn('id="refreshIndexBtn"', command_header.group("body"))
        self.assertIn('id="totalFiles"', command_header.group("body"))
        self.assertNotIn('class="index-bar"', results_panel.group("body"))
        self.assertNotIn('id="refreshIndexBtn"', results_panel.group("body"))

    def test_command_index_status_uses_compact_header_layout(self):
        self.assertIn(".search-command-index{display:flex;align-items:center;justify-content:flex-end", self.page)
        self.assertIn(".search-command-index .index-refresh{height:30px", self.page)

    def test_video_preview_preloads_metadata_when_modal_opens(self):
        self.assertIn('<video class="vid-preview" controls preload="metadata">', self.page)
        self.assertIn("const media = $('modalBody').querySelector('video,audio');", self.page)
        self.assertIn("if (media) media.load();", self.page)

    def test_search_page_matches_workbench_typography_and_spacing(self):
        self.assertIn("body{overflow:hidden}", self.page)
        self.assertIn(".search-page{max-width:min(1600px,calc(100vw - 32px));height:calc(100dvh - 68px)", self.page)
        self.assertIn(".search-workbench{flex:1;min-height:0;display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px}", self.page)
        self.assertIn(".search-panel{min-width:0;min-height:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--s-2);display:flex;flex-direction:column;overflow:hidden}", self.page)
        self.assertIn(".search-panel-title{font-family:var(--font-ui);font-size:15px;font-weight:800", self.page)

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
        self.assertNotIn("$('topPagination')", script)
        self.assertRegex(script, re.compile(r"function renderPagination\(\).*bottomPagination", re.S))

    def test_ai_banner_fields_are_escaped_before_inner_html(self):
        self.assertIn("escHtml(ai.keywords.join('、'))", self.page)
        self.assertIn("escHtml(ai.file_type)", self.page)
        self.assertIn("escHtml(ai.extension)", self.page)
        self.assertIn("escHtml(ai.date_from)", self.page)

    def test_ai_summary_escapes_server_text_before_markdown_rendering(self):
        self.assertIn("simpleMD(escHtml(d.summary))", self.page)
        self.assertIn("escHtml(d.message||'生成失败')", self.page)

    def test_inline_actions_use_js_string_literal_escaping(self):
        self.assertIn("function jsStringLiteral", self.page)
        self.assertIn("const folderNameArg = jsStringLiteral(f.file_name);", self.page)
        self.assertIn("const folderPathArg = jsStringLiteral(f.parent_folder||'');", self.page)
        self.assertIn("const typeArg = jsStringLiteral(f.file_type);", self.page)
        self.assertIn("const extArg = jsStringLiteral(f.file_extension||'');", self.page)
        self.assertIn("filterByFolder(${fileId},${folderNameArg},${folderPathArg})", self.page)
        self.assertIn("previewFile(${fileId},${typeArg},${extArg})", self.page)
        self.assertNotIn("f.file_path", self.page)
        self.assertNotIn("escPath(f.file_path)", self.page)
        self.assertNotIn("escAttr(f.file_type)", self.page)
        self.assertNotIn("escAttr(f.file_extension||'')", self.page)


if __name__ == "__main__":
    unittest.main()
