import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TemplatesPageTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "templates.html").read_text(encoding="utf-8-sig")

    def test_library_page_uses_wide_workspace_layout(self):
        self.assertIn('<main class="page-main library-main">', self.page)
        self.assertIn("max-width:1680px", self.page)
        self.assertIn('class="library-toolbar"', self.page)
        self.assertIn('class="script-board"', self.page)
        self.assertIn('class="script-grid"', self.page)
        self.assertNotIn('id="scriptList" class="product-grid"', self.page)

    def test_script_list_is_paginated(self):
        self.assertIn("var currentPage=1", self.page)
        self.assertIn("var pageSize=24", self.page)
        self.assertIn("var currentResults=[]", self.page)
        self.assertIn('id="topPagination"', self.page)
        self.assertIn('id="bottomPagination"', self.page)
        self.assertIn("function renderPagination", self.page)
        self.assertIn("function changePage", self.page)
        self.assertIn("function renderCurrentPage", self.page)
        self.assertIn("fetch(buildListUrl('/api/templates/viral/list'))", self.page)
        self.assertIn("page='+currentPage", self.page)
        self.assertIn("per_page='+pageSize", self.page)

        render_all = re.search(r"function renderAll\(\)\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        self.assertIsNotNone(render_all)
        self.assertIn("renderCurrentPage()", render_all.group("body"))

    def test_pagination_uses_requested_page_sizes_and_page_jump(self):
        self.assertIn('<option value="24">24 条/页</option>', self.page)
        self.assertNotIn('<option value="16">16 条/页</option>', self.page)
        self.assertIn('>24 条/页</option>', self.page)
        self.assertIn('>48 条/页</option>', self.page)
        self.assertIn('>96 条/页</option>', self.page)
        self.assertNotIn('>32 条/页</option>', self.page)
        self.assertNotIn('>64 条/页</option>', self.page)
        self.assertIn('id="pageJumpInput"', self.page)
        self.assertIn("function changePageSize", self.page)
        self.assertIn("function jumpToPage", self.page)
        self.assertIn("setPage(target)", self.page)
        self.assertIn("if(event.key==='Enter')jumpToPage()", self.page)

    def test_filters_and_semantic_search_reset_to_first_page(self):
        for function_name in ["setFilter", "toggleHigh", "toggleSort", "doSemSearch", "clearSemSearch"]:
            match = re.search(
                rf"(?:async\s+)?function {function_name}\([^)]*\)\{{(?P<body>.*?)\n\}}",
                self.page,
                flags=re.S,
            )
            self.assertIsNotNone(match)
            self.assertIn("currentPage=1", match.group("body"))

    def test_script_cards_have_delete_and_high_conversion_buttons(self):
        build_card = re.search(
            r"function buildScriptCard\(s\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(build_card)
        body = build_card.group("body")
        self.assertIn("script-card-actions", body)
        self.assertIn("toggleHighOne", body)
        self.assertIn("delOne", body)
        self.assertIn('data-lucide="badge-check"', body)
        self.assertIn('data-lucide="trash-2"', body)
        self.assertIn("标记高成交", body)
        self.assertIn("删除", body)
        self.assertIn("event.stopPropagation()", body)

    def test_script_card_action_icons_are_compact(self):
        self.assertIn(".script-card-actions .btn{", self.page)
        self.assertIn("min-height:30px", self.page)
        self.assertIn("padding:5px 8px", self.page)
        self.assertIn("gap:4px", self.page)
        self.assertIn(".script-card-actions i,.script-card-actions svg{width:12px;height:12px;flex:0 0 12px}", self.page)

    def test_script_card_badges_hide_brand_and_high_conversion_label(self):
        build_card = re.search(
            r"function buildScriptCard\(s\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(build_card)
        body = build_card.group("body")
        self.assertIn("cleanCardCategory(s.category)", body)
        self.assertNotIn(">法采", body)
        self.assertNotIn("&middot;", body)
        self.assertNotIn("badge-hi", body)
        self.assertNotIn("高成交</span>", body)

    def test_script_card_category_badge_strips_facai_prefix_from_data_category(self):
        helper = re.search(
            r"function cleanCardCategory\(category\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(helper)
        body = helper.group("body")
        self.assertIn("category||'未分类'", body)
        self.assertIn("replace(/^法采\\s*[-·:：／/|]*\\s*/,'')", body)
        self.assertIn("return value||'未分类'", body)

    def test_high_conversion_cards_use_deeper_green_surface(self):
        self.assertIn(
            ".script-grid .scard.hi{border-color:rgba(122,139,60,.42);background:rgba(122,139,60,.12)",
            self.page,
        )
        self.assertIn(
            ".script-grid .scard.hi:hover{border-color:rgba(122,139,60,.58)",
            self.page,
        )

    def test_view_modal_rewrite_panel_has_search_action_and_category_filter(self):
        self.assertIn('class="mo-box mo-wide script-detail-modal"', self.page)
        self.assertIn('class="script-detail-shell"', self.page)
        self.assertIn('class="script-preview-panel"', self.page)
        self.assertIn('class="rewrite-product-panel"', self.page)
        self.assertIn('class="modal-product-toolbar"', self.page)

        toolbar = re.search(
            r'<div class="modal-product-toolbar">(?P<body>.*?)</div>',
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(toolbar)
        toolbar_body = toolbar.group("body")
        self.assertIn('id="modalProductSearch"', toolbar_body)
        self.assertIn('id="btnModalRewrite"', toolbar_body)
        self.assertIn('id="modalProductCategory"', toolbar_body)
        self.assertLess(toolbar_body.find('id="modalProductSearch"'), toolbar_body.find('id="btnModalRewrite"'))
        self.assertLess(toolbar_body.find('id="btnModalRewrite"'), toolbar_body.find('id="modalProductCategory"'))

        self.assertIn("var modalProductCategory=''", self.page)
        self.assertIn("function renderModalProductCategories", self.page)
        self.assertIn("function setModalProductCategory", self.page)
        self.assertIn("p.category===modalProductCategory", self.page)
        self.assertIn('onchange="setModalProductCategory(this.value)"', self.page)

    def test_view_modal_category_select_has_enough_space(self):
        self.assertIn(
            ".modal-product-toolbar{display:grid;grid-template-columns:minmax(120px,1fr) auto minmax(150px,170px)",
            self.page,
        )
        self.assertIn(".modal-product-toolbar>*{min-width:0}", self.page)
        self.assertIn("#modalProductCategory{min-width:150px;height:40px;padding:0 36px 0 14px;line-height:40px}", self.page)


if __name__ == "__main__":
    unittest.main()
