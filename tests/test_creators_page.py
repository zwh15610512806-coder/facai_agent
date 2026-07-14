import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = [
    "index.html",
    "rewrite.html",
    "products.html",
    "import.html",
    "templates.html",
    "history.html",
    "search.html",
    "inspiration.html",
    "ai_config.html",
    "creators.html",
]


class CreatorPageContractTests(unittest.TestCase):
    def test_main_registers_creator_page(self):
        from main import app

        self.assertIn("/app/creators", app.openapi()["paths"])

    def test_all_templates_place_creator_work_after_product_knowledge(self):
        pattern = re.compile(
            r'href="/app/products"[^>]*>产品知识库</a>\s*'
            r'<a href="/app/creators"[^>]*>达人工作</a>\s*'
            r'<a href="/app/operations"[^>]*>运营数据中台</a>\s*'
            r'<a href="/app/templates"[^>]*>脚本模板库</a>',
            re.S,
        )
        for name in TEMPLATES:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertRegex(page, pattern, name)
            if name == "creators.html":
                self.assertIn('<a href="/app/creators" class="nav-link on">达人工作</a>', page)
            else:
                self.assertNotIn('<a href="/app/creators" class="nav-link on">', page, name)

    def test_creator_page_is_externalized_three_column_workbench(self):
        page = (ROOT / "templates" / "creators.html").read_text(encoding="utf-8-sig")
        self.assertIn('/static/css/creators.css?v=20260713-creators-v2', page)
        self.assertIn('/static/js/common.js?v=tools-20260713', page)
        self.assertIn('/static/js/creators.js?v=20260713-creators-v2', page)
        self.assertNotIn("<style", page.lower())
        self.assertNotRegex(page.lower(), r"<script(?![^>]+src=)")
        for marker in (
            'id="creatorWorkbench"',
            'class="creator-panel creator-sidebar"',
            'class="creator-panel creator-detail-panel"',
            'class="creator-panel creator-activity-panel"',
            'data-mobile-view="list"',
            'data-mobile-target="detail"',
            'data-mobile-target="activity"',
        ):
            self.assertIn(marker, page)

    def test_creator_page_exposes_required_controls_and_dialogs(self):
        page = (ROOT / "templates" / "creators.html").read_text(encoding="utf-8-sig")
        for control in (
            "creatorSearch",
            "creatorStageFilter",
            "creatorOwnerFilter",
            "creatorCategoryFilter",
            "creatorFollowerFilter",
            "creatorSort",
            "creatorList",
            "creatorDetailBody",
            "creatorActivityList",
            "creatorForm",
            "portraitForm",
            "followupForm",
            "collaborationForm",
            "addressForm",
            "sampleOrderForm",
            "creatorImportForm",
            "privateContactBody",
        ):
            self.assertIn(f'id="{control}"', page)
        for label in (
            "新建达人",
            "Excel 导入",
            "记录合作",
            "添加跟进",
            "一键寄样",
            "累计实付",
            "合作记录",
            "寄样记录",
            "查看联系方式",
        ):
            self.assertIn(label, page)

    def test_creator_javascript_uses_real_api_and_common_safety_helpers(self):
        script = (ROOT / "static" / "js" / "creators.js").read_text(encoding="utf-8-sig")
        for endpoint in (
            "/api/creators",
            "/bd-members",
            "/portrait",
            "/followups",
            "/collaborations",
            "/sample-orders",
            "/private-contact",
            "/import/preview",
            "/export",
            "/api/products/",
        ):
            self.assertIn(endpoint, script)
        for behavior in (
            "loadCreators",
            "selectCreator",
            "saveCreator",
            "savePortrait",
            "saveFollowup",
            "saveCollaboration",
            "saveAddress",
            "saveSampleOrder",
            "previewImport",
            "validateImport",
            "commitImport",
            "setMobileCreatorView",
            "openPrivateContact",
        ):
            self.assertIn(f"function {behavior}", script)
        self.assertIn("FacaiUI.escHtml", script)
        self.assertIn("FacaiUI.fetchWithTimeout", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("sessionStorage", script)
        for safety_contract in (
            "listRequestId",
            "selectionRequestId",
            "privateContactRequestId",
            "sampleIdempotencyKey",
            "edit-collaboration",
            "cancel-collaboration",
            "data-export-filtered-entity",
            'params.set("category"',
            'params.set("follower_tier"',
        ):
            self.assertIn(safety_contract, script)
        self.assertIn("var requestedCreatorId = state.selectedId;", script)
        self.assertIn(
            "privateContactRequestId !== state.privateContactRequestId || requestedCreatorId !== state.selectedId",
            script,
        )
        self.assertGreaterEqual(script.count("privateContactRequestId !== state.privateContactRequestId"), 2)
        for import_field in (
            "audience_profile",
            "recipient_name",
            "recipient_phone",
            "province",
            "city",
            "district",
            "address_detail",
        ):
            self.assertIn(f'["{import_field}",', script)
        self.assertNotIn('["creator_nickname",', script)

        page = (ROOT / "templates" / "creators.html").read_text(encoding="utf-8-sig")
        for entity in ("creators", "collaborations", "sample_orders"):
            self.assertIn(f'data-export-filtered-entity="{entity}"', page)
        self.assertIn('id="collaborationEditId"', page)

        result = subprocess.run(
            ["node", "--check", str(ROOT / "static" / "js" / "creators.js")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_creator_css_has_desktop_and_mobile_view_contracts(self):
        css = (ROOT / "static" / "css" / "creators.css").read_text(encoding="utf-8-sig")
        self.assertIn("grid-template-columns:300pxminmax(420px,.95fr)minmax(440px,1.1fr)", css.replace(" ", ""))
        self.assertIn("@media (max-width: 980px)", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn('[data-mobile-view="list"] .creator-sidebar', css)
        self.assertIn('[data-mobile-view="detail"] .creator-detail-panel', css)
        self.assertIn('[data-mobile-view="activity"] .creator-activity-panel', css)
        self.assertIn("min-height:42px", css.replace(" ", ""))
        self.assertIn("prefers-reduced-motion: reduce", css)


if __name__ == "__main__":
    unittest.main()
