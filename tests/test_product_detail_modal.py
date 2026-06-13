import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductDetailDataTests(unittest.TestCase):
    def test_detail_data_uses_manual_points_and_sku_prices(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("水性色素", ROOT)

        self.assertEqual(detail["source_name"], "水性色素")
        self.assertEqual(detail["manual_source"], "FC法采产品手册24年5月6日更新版.md")
        self.assertGreaterEqual(len(detail["selling_points"]), 6)
        self.assertTrue(
            any("着色" in point["content"] for point in detail["selling_points"])
        )

        specs = {sku["spec"] for sku in detail["sku_prices"]}
        self.assertIn("23g-所有颜色", specs)
        self.assertIn("66色套装", specs)
        self.assertEqual(detail["sku_prices"][0]["price"], 17.41)

    def test_detail_data_exposes_activity_mechanism_prices(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("水性色素", ROOT)

        first_sku = detail["sku_prices"][0]
        activities = {
            activity["mechanism"]: activity
            for activity in first_sku["activity_prices"]
        }
        self.assertIn("淘宝-现有", activities)
        self.assertIn("淘宝-调整202603", activities)
        self.assertIn("淘宝A级-调整202507", activities)
        self.assertIn("淘宝S级-调整202507", activities)
        self.assertEqual(activities["淘宝-调整202603"]["discount"], "1件85折")
        self.assertEqual(activities["淘宝-调整202603"]["final_price"], 14.8)
        self.assertEqual(activities["淘宝A级-调整202507"]["activity_price"], 14.45)
        self.assertEqual(activities["淘宝S级-调整202507"]["final_price"], 14.45)

    def test_detail_data_reads_knife_price_workbook_for_cutlery(self):
        from services.product_detail import build_material_product_detail

        bag_detail = build_material_product_detail("袋装刀叉", ROOT)
        box_detail = build_material_product_detail("盒装刀叉", ROOT)

        self.assertEqual(len(bag_detail["sku_prices"]), 12)
        self.assertEqual(bag_detail["sku_prices"][0]["product"], "0.7元款刀叉")
        self.assertEqual(bag_detail["sku_prices"][0]["spec"], "【5叉5盘】60套")
        self.assertEqual(bag_detail["sku_prices"][0]["price"], 44.53)
        self.assertEqual(bag_detail["sku_prices"][0]["daily_price"], 37.85)
        bag_activities = {
            activity["mechanism"]: activity
            for activity in bag_detail["sku_prices"][0]["activity_prices"]
        }
        self.assertEqual(bag_activities["现在价格"]["final_price"], 37.85)
        self.assertEqual(bag_activities["线上A级-调整202603"]["final_price"], 35.63)

        box_specs = {sku["spec"]: sku for sku in box_detail["sku_prices"]}
        self.assertIn("【5叉5盘1刀】16套", box_specs)
        self.assertEqual(box_specs["【5叉5盘1刀】16套"]["product"], "2元盒装")
        self.assertEqual(box_specs["【5叉5盘1刀】16套"]["daily_price"], 27.6)
        box_activities = {
            activity["mechanism"]: activity
            for activity in box_specs["【5叉5盘1刀】16套"]["activity_prices"]
        }
        self.assertEqual(box_activities["线上-日常涨价"]["final_price"], 27.6)
        self.assertEqual(box_activities["线上S级-调整202603"]["activity_price"], 26.95)

    def test_detail_data_matches_legacy_product_names(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("水性色素（胶状）", ROOT)

        self.assertEqual(detail["source_name"], "水性色素")
        self.assertGreaterEqual(len(detail["sku_prices"]), 6)

    def test_detail_data_enriches_points_from_2026_knowledge_base(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("布蕾粉", ROOT)

        contents = [point["content"] for point in detail["selling_points"]]
        self.assertTrue(any("夹心稳定" in content for content in contents))
        self.assertTrue(any("茶系应用" in content for content in contents))
        self.assertTrue(any("1：4：4" in content or "1:4:4" in content for content in contents))
        self.assertTrue(any("创新抹茶味" in content for content in contents))
        self.assertIn("04_产品常见问题精选.md", detail["knowledge_sources"])
        self.assertIn("【法采】2026年产品手卡.xlsx", detail["knowledge_sources"])
        self.assertIn("02_核心产品卖点速览.md", detail["knowledge_sources"])

    def test_detail_data_reads_2026_single_product_archive(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("浅柔色素", ROOT)

        contents = [point["content"] for point in detail["selling_points"]]
        self.assertTrue(any("低饱和" in content for content in contents))
        self.assertTrue(any("反复复配调色" in content for content in contents))
        self.assertTrue(any("120ml" in content for content in contents))
        self.assertIn("06_浅柔色素产品档案.md", detail["knowledge_sources"])
        self.assertIn("【法采浅柔色素】产品一页纸.xlsx", detail["knowledge_sources"])

    def test_detail_data_merges_2026_sku_knowledge_to_parent_product(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("奶冻粉", ROOT)

        contents = [point["content"] for point in detail["selling_points"]]
        self.assertTrue(any("Q弹果冻" in content for content in contents))
        self.assertTrue(any("创意水晶蛋糕" in content for content in contents))
        self.assertTrue(any("200g/包" in content or "200g" in content for content in contents))
        self.assertIn("【法采】2026年产品手卡.xlsx", detail["knowledge_sources"])

    def test_detail_data_uses_2026_naming_aliases_for_legacy_products(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("拉线膏", ROOT)

        contents = [point["content"] for point in detail["selling_points"]]
        self.assertTrue(any("防晕染彩色拉线膏" in content for content in contents))
        self.assertTrue(any("顺滑不晕色" in content for content in contents))
        self.assertIn("05_产品命名主数据与旧称对照.md", detail["knowledge_sources"])

    def test_detail_data_adds_2026_solution_context(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("水性色素", ROOT)

        contents = [point["content"] for point in detail["selling_points"]]
        self.assertTrue(any("网红蛋糕颜色还原" in content for content in contents))
        self.assertTrue(any("360款热门蛋糕颜色调色卡" in content for content in contents))
        self.assertIn("00_产品知识总索引.md", detail["knowledge_sources"])
        self.assertIn("01_五大门店解决方案.md", detail["knowledge_sources"])


class ProductDetailTemplateTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "products.html").read_text(encoding="utf-8-sig")

    def test_product_cards_open_detail_modal(self):
        self.assertIn('id="productDetailModal"', self.page)
        self.assertRegex(self.page, r'class="product-card"[^\n]+openProduct(?:Card)?Detail\(')
        self.assertIn("function openProductDetail(id)", self.page)
        self.assertIn("'/api/products/'+id+'/detail'", self.page)
        self.assertIn("renderProductSkuRows", self.page)
        self.assertIn("renderProductSellingPoints", self.page)
        self.assertIn("活动价", self.page)
        self.assertIn("renderActivityPriceCells", self.page)

    def test_product_detail_modal_uses_large_workspace_layout(self):
        self.assertIn("#productDetailModal{align-items:flex-start;padding:84px 28px 24px}", self.page)
        self.assertIn("max-width:min(1280px,calc(100vw - 56px))", self.page)
        self.assertIn("max-height:calc(100dvh - 108px)", self.page)
        self.assertIn(".detail-box .mo-body{flex:1;min-height:0;overflow:hidden", self.page)
        self.assertIn(".detail-grid>section{display:flex;flex-direction:column;min-height:0;overflow:hidden}", self.page)
        self.assertIn(".detail-point-list{display:grid;gap:10px;overflow:auto", self.page)
        self.assertIn(".detail-sku-wrap{border:1px solid var(--border);border-radius:var(--r);overflow:auto;background:var(--surface);max-height:100%;flex:1}", self.page)

    def test_card_action_buttons_do_not_trigger_detail_modal(self):
        upload_button_start = self.page.index("openUploadModal(")
        button_slice = self.page[upload_button_start - 120:upload_button_start + 220]

        self.assertIn("event.stopPropagation()", button_slice)

    def test_product_card_footer_uses_text_lucide_actions_without_file_status(self):
        render_grid = re.search(
            r"function renderGrid\(\)\{(?P<body>.*?)\n\}",
            self.page,
            flags=re.S,
        )

        self.assertIsNotNone(render_grid)
        body = render_grid.group("body")
        self.assertNotIn("fd-has", body)
        self.assertNotIn("fd-none", body)
        self.assertNotIn("product_material_", body)
        self.assertIn("product-card-actions", body)
        self.assertIn("product-card-action", body)
        self.assertIn('data-lucide="file-up"', body)
        self.assertIn('data-lucide="download"', body)
        self.assertIn('data-lucide="trash-2"', body)
        self.assertIn(">资料<", body)
        self.assertIn(">下载<", body)
        self.assertIn(">删除<", body)
        self.assertIn("lucide.createIcons()", body)

    def test_product_card_action_icons_use_compact_sizing(self):
        self.assertIn(".product-card-action{height:30px", self.page)
        self.assertIn("font-size:11px", self.page)
        self.assertIn(".product-card-action svg,.product-card-action i{width:10px;height:10px", self.page)
        self.assertIn(".product-card-action { height: 30px", self.page)


if __name__ == "__main__":
    unittest.main()
