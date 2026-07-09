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
        self.assertIn("var pageSize=25", self.page)
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
        self.assertIn('<option value="25">25 条/页</option>', self.page)
        self.assertNotIn('<option value="16">16 条/页</option>', self.page)
        self.assertNotIn('>24 条/页</option>', self.page)
        self.assertIn('>25 条/页</option>', self.page)
        self.assertIn('>50 条/页</option>', self.page)
        self.assertIn('>100 条/页</option>', self.page)
        self.assertNotIn('>32 条/页</option>', self.page)
        self.assertNotIn('>64 条/页</option>', self.page)
        self.assertIn('id="pageJumpInput"', self.page)
        self.assertIn("function changePageSize", self.page)
        self.assertIn("function jumpToPage", self.page)
        self.assertIn("setPage(target)", self.page)
        self.assertIn("if(event.key==='Enter')jumpToPage()", self.page)

    def test_semantic_search_uses_full_five_column_page_size(self):
        self.assertIn("var searchPageSize=25", self.page)
        self.assertIn("function getActivePageSize()", self.page)
        self.assertIn("return resultMode==='search'?searchPageSize:pageSize", self.page)
        self.assertIn("function buildPageSizeOptions(activePageSize)", self.page)

        render_current = re.search(
            r"function renderCurrentPage\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(render_current)
        self.assertIn("var activePageSize=getActivePageSize()", render_current.group("body"))
        self.assertIn("currentResults.slice(start,start+activePageSize)", self.page)

        semantic_search = re.search(
            r"async function doSemSearch\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(semantic_search)
        self.assertIn("limit=50", semantic_search.group("body"))

    def test_semantic_search_falls_back_to_keyword_list_when_embedding_fails(self):
        self.assertIn("async function fallbackKeywordSearch(q)", self.page)
        self.assertIn("fetch(buildKeywordSearchUrl(q))", self.page)
        self.assertIn("renderKeywordSearchResults(data.items||data||[])", self.page)
        self.assertIn("await fallbackKeywordSearch(q)", self.page)
        self.assertNotIn("搜索失败</div>';updateResultMeta(0,0,0);renderPagination();", self.page)

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

    def test_script_card_shows_reference_image_in_top_right_and_moves_time_to_actions(self):
        build_card = re.search(
            r"function buildScriptCard\(s\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(build_card)
        body = build_card.group("body")
        self.assertIn("script-card-image-area", body)
        self.assertIn("script-card-image-count", body)
        self.assertIn("script-card-image-placeholder", body)
        self.assertIn("script-card-time", body)
        self.assertIn("cakeImages[0].url", body)
        self.assertIn("script-card-top", body)
        self.assertLess(body.index("script-card-top"), body.index("script-card-image-area"))
        self.assertLess(body.index("script-card-image-area"), body.index("<p style="))
        self.assertLess(body.index("script-card-time"), body.index("toggleHighOne"))
        self.assertNotIn("else if(time)html+='<span style=\"margin-left:auto", body)

    def test_script_card_action_icons_are_compact(self):
        self.assertIn(".script-card-actions .btn{", self.page)
        self.assertIn("min-height:30px", self.page)
        self.assertIn("padding:5px 8px", self.page)
        self.assertIn("gap:4px", self.page)
        self.assertIn(".script-card-actions i,.script-card-actions svg{width:12px;height:12px;flex:0 0 12px}", self.page)
        self.assertIn(".script-card-time{", self.page)

    def test_script_card_shows_cake_reference_preview_in_top_right(self):
        build_card = re.search(
            r"function buildScriptCard\(s\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(build_card)
        body = build_card.group("body")
        self.assertIn("getScriptCakeImages(s)", body)
        self.assertIn("script-card-reference-preview", body)
        self.assertIn("cakeImages[0].url", body)
        self.assertIn("共 '+cakeImages.length+' 张", body)
        self.assertIn("onerror=\"this.onerror=null;this.closest", body)
        self.assertIn("script-card-reference-preview", body)
        self.assertIn("classList.add", body)
        self.assertIn("is-fallback", body)
        self.assertIn(".script-card-top{display:grid;grid-template-columns:minmax(0,1fr) 112px", self.page)
        self.assertIn(".script-card-reference-preview{position:relative", self.page)
        self.assertRegex(
            body,
            r"<div class=\"script-card-top[\s\S]*if\(cakeImages\.length\)html\+='<div class=\"script-card-reference-preview[^\"]*\"",
        )

    def test_script_card_date_moves_to_actions_before_high_button(self):
        build_card = re.search(
            r"function buildScriptCard\(s\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(build_card)
        body = build_card.group("body")
        self.assertNotIn("else if(time)html+='<span style=\"margin-left:auto;font-size:12px;color:var(--text-3)\">'+time+'</span>'", body)
        self.assertIn("script-card-date", body)
        self.assertRegex(
            body,
            r"<div class=\"script-card-actions\">'\+\(time\?'<span class=\"script-card-date script-card-time\">'\+time\+'</span>':''\)\+'<button class=\"btn btn-soft btn-sm\"",
        )

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

    def test_view_modal_has_qianchuan_panel_and_bottom_rewrite_bar(self):
        self.assertIn('class="mo-box mo-wide script-detail-modal"', self.page)
        self.assertIn('class="script-detail-shell"', self.page)
        self.assertIn('class="script-preview-panel"', self.page)
        self.assertIn('class="qianchuan-performance-panel"', self.page)
        self.assertIn('id="qianchuanFileInput"', self.page)
        self.assertIn('新增千川数据表', self.page)
        self.assertIn('id="qianchuanBoundSource"', self.page)
        self.assertIn('id="qianchuanSummary"', self.page)
        self.assertIn('id="qianchuanBoundSection"', self.page)
        self.assertIn('id="qianchuanCandidateList"', self.page)
        self.assertIn('id="qianchuanCandidateSection"', self.page)
        self.assertIn('class="rewrite-product-bar"', self.page)
        self.assertIn('class="modal-product-toolbar"', self.page)
        self.assertNotIn('class="modal-product-action"', self.page)
        self.assertNotIn('id="modalRewriteButton"', self.page)
        self.assertNotIn('class="rewrite-panel-head"', self.page)
        self.assertNotIn('id="modalProductCount"', self.page)
        self.assertNotIn('id="modalProductCategory"', self.page)
        self.assertNotIn('id="btnModalRewrite"', self.page)
        self.assertNotIn('onchange="setModalProductCategory(this.value)"', self.page)

        toolbar = re.search(
            r'<div class="modal-product-toolbar">(?P<body>.*?)</div>',
            self.page,
            flags=re.S,
        )
        self.assertIsNotNone(toolbar)
        toolbar_body = toolbar.group("body")
        self.assertIn('id="modalProductSearch"', toolbar_body)
        self.assertNotIn('<select', toolbar_body)
        self.assertNotIn('<button', toolbar_body)

        self.assertRegex(
            self.page,
            r'<section class="rewrite-product-bar">\s*'
            r'<div class="modal-product-toolbar">[\s\S]*?id="modalProductSearch"[\s\S]*?</div>\s*'
            r'<div id="modalProductList" class="modal-product-list"></div>\s*'
            r'<div id="modalRewriteResult"',
        )
        self.assertNotIn("var modalProductCategory=''", self.page)
        self.assertNotIn("function renderModalProductCategories", self.page)
        self.assertNotIn("function setModalProductCategory", self.page)
        self.assertNotIn("p.category===modalProductCategory", self.page)
        self.assertIn("if(!q){modalProduct=null;listEl.innerHTML='';listEl.classList.remove('has-results');return;}", self.page)
        self.assertNotIn("'<button class=\"btn btn-pri btn-sm modal-product-card-action\" onclick=\"event.stopPropagation();doRewrite()\">改写</button>'", self.page)
        self.assertIn("onclick=\"rewriteWithModalProduct('+p.id+')\"", self.page)
        self.assertIn("async function rewriteWithModalProduct(id)", self.page)
        self.assertIn("if(modalRewriting)return;", self.page)
        self.assertIn("function loadQianchuanPerformance", self.page)
        self.assertIn("/api/templates/qianchuan/import", self.page)
        self.assertIn("/performance/bind", self.page)

    def test_qianchuan_panel_uses_average_order_value_and_compact_bound_source(self):
        self.assertIn("function renderQianchuanBoundSource", self.page)
        self.assertIn("qianchuanMetric('成交客单价'", self.page)
        self.assertIn("'成交金额 / 成交订单数'", self.page)
        self.assertNotIn("qianchuanMetric('素材数量'", self.page)
        self.assertIn("var hasBindings=bindings.length>0", self.page)
        self.assertIn("boundSection.style.display='none'", self.page)
        self.assertIn("candidateSection.style.display=hasBindings?'none':''", self.page)
        self.assertIn("可从候选素材中绑定", self.page)
        self.assertIn("+' 条</span>'", self.page)

    def test_view_modal_product_search_uses_two_slot_click_to_rewrite_layout(self):
        self.assertIn(".modal-product-toolbar{display:flex;align-items:stretch;margin-bottom:0;min-width:0;height:60px}", self.page)
        self.assertIn(".modal-product-toolbar .input{width:100%;height:60px;font-size:13px}", self.page)
        self.assertIn(".modal-product-list{display:none;gap:10px;overflow-x:auto;overflow-y:hidden;min-height:0;max-height:60px;padding:0 2px;min-width:0;align-items:stretch}", self.page)
        self.assertIn(".modal-product-list .modal-product-card{flex:0 0 184px;min-height:60px;height:60px}", self.page)
        self.assertIn(".modal-product-card{border-radius:var(--r);border:1px solid var(--border);padding:8px 10px;cursor:pointer;background:var(--surface);transition:all var(--normal) var(--ease);position:relative;display:grid;grid-template-columns:auto minmax(0,1fr);grid-template-rows:auto auto;column-gap:8px;row-gap:2px;align-content:center;align-items:center}", self.page)
        self.assertIn(".modal-product-card .pcat{grid-row:1/3;grid-column:1;display:inline-flex;align-items:center;justify-content:center;min-height:20px;max-width:68px;padding:2px 8px;border-radius:var(--r-pill);background:var(--facai-soft);color:var(--facai);font-size:11px;line-height:1.2;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}", self.page)
        self.assertIn(".modal-product-card .pname{grid-column:2;font-size:13px;font-weight:700;margin:0;line-height:1.2;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}", self.page)
        self.assertIn(".modal-product-card .ppoints{grid-column:2;font-size:12px;line-height:1.2;color:var(--text-3);margin:0}", self.page)
        self.assertIn("function productSellingPointLabel(p)", self.page)
        self.assertIn("selling_point_count", self.page)
        self.assertIn(".modal-product-card.rewriting{border-color:var(--facai);background:var(--facai-soft);box-shadow:0 0 0 2px var(--facai-subtle)}", self.page)
        self.assertIn(".modal-product-card.rewriting:after{content:'改写中...';position:absolute;right:8px;bottom:8px;font-size:11px;font-weight:800;color:var(--facai)}", self.page)
        self.assertNotIn(".modal-product-action", self.page)
        self.assertNotIn(".modal-product-card-action", self.page)
        self.assertNotIn(".modal-product-card.sel .modal-product-card-action", self.page)
        self.assertNotIn('class="pprice"', self.page)

    def test_view_modal_uses_fixed_layout_and_locks_background_scroll(self):
        self.assertIn(
            ".script-detail-modal{max-width:1180px;height:min(860px,calc(100dvh - 32px));max-height:calc(100dvh - 32px);overflow:hidden;display:flex;flex-direction:column}",
            self.page,
        )
        self.assertIn(
            ".script-detail-modal .mo-body{padding:0;display:flex;flex-direction:column;flex:1;min-height:0;overflow:hidden}",
            self.page,
        )
        self.assertIn(
            ".script-detail-shell{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));flex:1;min-height:0;min-width:0;overflow:hidden}",
            self.page,
        )
        self.assertIn(".qianchuan-scroll{flex:1;min-height:0;overflow-y:auto", self.page)
        self.assertIn(
            ".rewrite-product-bar{border-top:1px solid var(--border-soft);padding:10px 24px;background:var(--muted);min-width:0;flex:0 0 82px;height:82px;min-height:82px;max-height:82px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;align-items:center;overflow:hidden}",
            self.page,
        )
        self.assertIn(".rewrite-product-bar { display:grid; grid-template-columns:1fr; flex:initial; height:auto; min-height:0; max-height:none; overflow:visible; padding:16px; gap:10px; }", self.page)
        self.assertNotIn(".rewrite-product-bar:before", self.page)
        self.assertNotIn(".rewrite-product-bar{position:absolute", self.page)
        self.assertIn("html.modal-scroll-locked,body.modal-scroll-locked{overflow:hidden;overscroll-behavior:none}", self.page)
        self.assertIn("var modalScrollY=0", self.page)
        self.assertIn("function lockViewModalScroll", self.page)
        self.assertIn("function unlockViewModalScroll", self.page)
        self.assertIn("document.documentElement.classList.add('modal-scroll-locked')", self.page)
        self.assertIn("document.documentElement.classList.remove('modal-scroll-locked')", self.page)
        self.assertIn("document.body.classList.add('modal-scroll-locked')", self.page)
        self.assertIn("document.body.classList.remove('modal-scroll-locked')", self.page)
        self.assertNotIn("document.body.style.top='-'", self.page)
        self.assertIn("lockViewModalScroll();document.getElementById('viewModal').style.display=''", self.page)
        self.assertIn("document.getElementById('viewModal').style.display='none';unlockViewModalScroll()", self.page)

    def test_global_modal_layer_sits_above_floating_action_buttons(self):
        style = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8-sig")
        self.assertIn(".ai-config-fab,.data-import-fab {\n  position: fixed; right: 28px; z-index: 90;", style)
        self.assertIn(".ai-config-fab { bottom: 28px; }", style)
        self.assertIn(".data-import-fab { bottom: 88px; }", style)
        self.assertIn("z-index: 900; display: flex; align-items: center;", style)
        self.assertIn("z-index: 1000; box-shadow: var(--s-3);", style)


if __name__ == "__main__":
    unittest.main()
