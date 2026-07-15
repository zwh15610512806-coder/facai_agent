import re
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _local_materials_available():
    import import_materials

    try:
        import_materials.get_material_paths(ROOT)
    except (OSError, FileNotFoundError):
        return False
    return True


class ProductDetailDataTests(unittest.TestCase):
    MATERIAL_DATA_TESTS = {
        "test_detail_data_uses_manual_points_and_sku_prices",
        "test_detail_data_exposes_activity_mechanism_prices",
        "test_detail_data_reads_knife_price_workbook_for_cutlery",
        "test_detail_data_matches_legacy_product_names",
        "test_detail_data_enriches_points_from_2026_knowledge_base",
        "test_detail_data_reads_2026_single_product_archive",
        "test_detail_data_merges_2026_sku_knowledge_to_parent_product",
        "test_detail_data_uses_2026_naming_aliases_for_legacy_products",
        "test_detail_data_adds_2026_solution_context",
        "test_detail_data_removes_useless_material_metadata",
        "test_detail_data_merges_repeated_selling_point_sections",
        "test_detail_payload_prefers_editable_database_selling_points",
        "test_detail_payload_hides_deleted_material_selling_points",
        "test_detail_payload_builds_five_profile_sections",
        "test_sparse_named_products_get_profile_fallbacks_without_metadata_as_selling_point",
        "test_profile_sections_keep_all_activity_prices_without_useless_metadata",
    }

    def setUp(self):
        if self._testMethodName in self.MATERIAL_DATA_TESTS and not _local_materials_available():
            self.skipTest("requires local material files")

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

    def test_detail_data_removes_useless_material_metadata(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("多肉果酱", ROOT)
        point_types = {point["point_type"] for point in detail["selling_points"]}
        contents = [point["content"] for point in detail["selling_points"]]

        self.assertNotIn("资料标题", point_types)
        self.assertNotIn("产品名称", point_types)
        self.assertFalse(any("手卡" in content or "一页纸" in content for content in contents))
        self.assertFalse(any("代表产品：" in content for content in contents))

    def test_detail_data_merges_repeated_selling_point_sections(self):
        from services.product_detail import build_material_product_detail

        detail = build_material_product_detail("茶酱", ROOT)
        point_types = [point["point_type"] for point in detail["selling_points"]]
        contents = [point["content"] for point in detail["selling_points"]]

        self.assertLessEqual(point_types.count("门店方案"), 1)
        self.assertEqual(len(contents), len({content.strip() for content in contents}))
        self.assertFalse(any("打印预览尺寸" in content for content in contents))

    def test_detail_payload_prefers_editable_database_selling_points(self):
        from services.product_detail import build_product_detail_payload

        point = SimpleNamespace(
            id=77,
            product_id=5,
            point_type="基础卖点",
            content="编辑后的卖点内容",
            priority=1,
        )
        product = SimpleNamespace(
            id=5,
            name="水性色素",
            category="烘焙调色",
            price=18.8,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[point],
        )

        detail = build_product_detail_payload(product, ROOT)

        self.assertEqual(detail["selling_points"][0]["id"], 77)
        self.assertEqual(detail["selling_points"][0]["content"], "编辑后的卖点内容")
        self.assertEqual(detail["selling_points"][0]["point_type"], "基础卖点")
        self.assertGreater(len(detail["selling_points"]), 1)

    def test_detail_payload_hides_deleted_material_selling_points(self):
        from services.product_detail import HIDDEN_SELLING_POINT_TYPE, build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="水性色素",
            category="烘焙调色",
            price=18.8,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[
                SimpleNamespace(
                    id=88,
                    product_id=5,
                    point_type=HIDDEN_SELLING_POINT_TYPE,
                    content="hidden",
                    priority=1,
                )
            ],
        )

        material_detail = build_product_detail_payload(
            SimpleNamespace(**{**product.__dict__, "selling_points": []}), ROOT
        )
        hidden_detail = build_product_detail_payload(product, ROOT)

        self.assertNotEqual(
            hidden_detail["selling_points"][0]["content"],
            material_detail["selling_points"][0]["content"],
        )
        self.assertFalse(
            any(point["point_type"] == HIDDEN_SELLING_POINT_TYPE for point in hidden_detail["selling_points"])
        )

    def test_detail_payload_filters_saved_useless_metadata_points(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="多肉果酱",
            category="烘焙调味",
            price=28,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[
                SimpleNamespace(
                    id=91,
                    product_id=5,
                    point_type="资料标题",
                    content="法采·多肉果酱产品——手卡；0.86",
                    priority=1,
                ),
                SimpleNamespace(
                    id=92,
                    product_id=5,
                    point_type="核心亮点",
                    content="大果粒、减甜、果肉含量高。",
                    priority=2,
                ),
            ],
        )

        detail = build_product_detail_payload(product, ROOT)

        self.assertFalse(any(point["point_type"] == "资料标题" for point in detail["selling_points"]))
        self.assertTrue(any(point["content"] == "大果粒、减甜、果肉含量高。" for point in detail["selling_points"]))

    def test_detail_payload_strips_saved_garbled_placeholder_text(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="调味果酱",
            category="烘焙调味",
            price=28,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[
                SimpleNamespace(
                    id=93,
                    product_id=5,
                    point_type="主要场景",
                    content="调奶油、慕斯、淋面、巴斯克。 ????",
                    priority=1,
                )
            ],
        )

        detail = build_product_detail_payload(product, ROOT)

        self.assertEqual(detail["selling_points"][0]["content"], "调奶油、慕斯、淋面、巴斯克。")

    def test_detail_payload_merges_saved_and_material_sections(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="茶酱",
            category="烘焙调味",
            price=54,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[
                SimpleNamespace(
                    id=94,
                    product_id=5,
                    point_type="门店方案",
                    content="B. 口味蛋糕与趋势上新：茶酱",
                    priority=1,
                ),
                SimpleNamespace(
                    id=95,
                    product_id=5,
                    point_type="门店方案",
                    content="解决方案：提供果酱、茶酱与坚果酱等配套产品。",
                    priority=2,
                )
            ],
        )

        detail = build_product_detail_payload(product, ROOT)
        point_types = [point["point_type"] for point in detail["selling_points"]]

        self.assertLessEqual(point_types.count("门店方案"), 1)

    def test_detail_payload_builds_five_profile_sections(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="水性色素",
            category="烘焙调色",
            price=18.59,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[],
        )

        detail = build_product_detail_payload(product, ROOT)
        sections = detail["profile_sections"]
        by_id = {section["id"]: section for section in sections}

        self.assertEqual(
            [section["title"] for section in sections],
            ["产品信息", "产品价格", "产品用途", "使用场景", "主要卖点"],
        )
        self.assertTrue(by_id["product_price"]["sku_prices"])
        self.assertTrue(any("水性色素" in item["content"] for item in by_id["product_info"]["items"]))
        self.assertTrue(by_id["usage_scenarios"]["items"])
        self.assertTrue(by_id["main_selling_points"]["items"])

    def test_detail_payload_marks_product_price_as_editable_product_field(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="浅柔色素",
            category="烘焙调色",
            price=38.6,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[],
        )

        detail = build_product_detail_payload(product, ROOT / "__missing_material_root__")
        by_id = {section["id"]: section for section in detail["profile_sections"]}
        price_item = next(item for item in by_id["product_price"]["items"] if item["label"] == "产品售价")

        self.assertEqual(price_item["field"], "price")
        self.assertTrue(price_item["editable"])

    def test_sparse_named_products_get_profile_fallbacks_without_metadata_as_selling_point(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=47,
            name="巧克力脆馅",
            category="烘焙夹心",
            price=42.2,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[],
        )

        detail = build_product_detail_payload(product, ROOT)
        by_id = {section["id"]: section for section in detail["profile_sections"]}
        selling_labels = {item["label"] for item in by_id["main_selling_points"]["items"]}

        self.assertTrue(by_id["product_usage"]["items"])
        self.assertTrue(by_id["usage_scenarios"]["items"])
        self.assertTrue(by_id["main_selling_points"]["items"])
        self.assertGreaterEqual(len(by_id["product_usage"]["items"]), 3)
        self.assertGreaterEqual(len(by_id["usage_scenarios"]["items"]), 3)
        self.assertGreaterEqual(len(by_id["main_selling_points"]["items"]), 3)
        self.assertTrue(any(item["label"] == "标准命名" for item in by_id["product_info"]["items"]))
        self.assertNotIn("标准命名", selling_labels)
        self.assertTrue(
            any("巧克力" in item["content"] or "夹心" in item["content"] for item in by_id["main_selling_points"]["items"])
        )

    def test_sparse_pistachio_bits_profile_is_detailed_enough(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=46,
            name="开心果碎",
            category="烘焙夹心",
            price=37.65,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[],
        )

        detail = build_product_detail_payload(product, ROOT)
        by_id = {section["id"]: section for section in detail["profile_sections"]}
        combined = str(by_id["main_selling_points"]["items"])

        self.assertGreaterEqual(len(by_id["product_usage"]["items"]), 3)
        self.assertGreaterEqual(len(by_id["usage_scenarios"]["items"]), 3)
        self.assertGreaterEqual(len(by_id["main_selling_points"]["items"]), 3)
        self.assertIn("开心果", combined)
        self.assertTrue(all(item.get("priority") for item in by_id["main_selling_points"]["items"]))

    def test_existing_sparse_sections_are_enriched_to_minimum_detail(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=42,
            name="夹心芋泥",
            category="烘焙夹心",
            price=49.29,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[],
        )

        detail = build_product_detail_payload(product, ROOT)
        by_id = {section["id"]: section for section in detail["profile_sections"]}

        self.assertGreaterEqual(len(by_id["product_usage"]["items"]), 3)
        self.assertGreaterEqual(len(by_id["usage_scenarios"]["items"]), 3)
        self.assertGreaterEqual(len(by_id["main_selling_points"]["items"]), 3)
        self.assertTrue(any("夹心" in item["content"] for item in by_id["product_usage"]["items"]))

    def test_hidden_generated_profile_item_does_not_reappear(self):
        from services.product_detail import HIDDEN_SELLING_POINT_TYPE, build_product_detail_payload

        product = SimpleNamespace(
            id=46,
            name="开心果碎",
            category="烘焙夹心",
            price=37.65,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[
                SimpleNamespace(
                    id=120,
                    product_id=46,
                    point_type=HIDDEN_SELLING_POINT_TYPE,
                    content="hidden",
                    priority=9201,
                )
            ],
        )

        detail = build_product_detail_payload(product, ROOT)
        by_id = {section["id"]: section for section in detail["profile_sections"]}
        contents = [item["content"] for item in by_id["main_selling_points"]["items"]]

        self.assertFalse(any(content.startswith("为蛋糕和甜品增加开心果风味") for content in contents))
        self.assertGreaterEqual(len(contents), 2)

    def test_profile_sections_keep_all_activity_prices_without_useless_metadata(self):
        from services.product_detail import build_product_detail_payload

        product = SimpleNamespace(
            id=5,
            name="盒装刀叉",
            category="烘焙配件",
            price=32.21,
            original_price=None,
            commission_rate=0,
            brand="法采",
            description="",
            info_file=None,
            pending_fields=[],
            status="active",
            selling_points=[],
        )

        detail = build_product_detail_payload(product, ROOT)
        by_id = {section["id"]: section for section in detail["profile_sections"]}
        price_section = by_id["product_price"]
        all_text = str(detail["profile_sections"])

        self.assertGreaterEqual(len(price_section["sku_prices"]), 5)
        self.assertTrue(any(sku["activity_prices"] for sku in price_section["sku_prices"]))
        self.assertIn("产品信息", [section["title"] for section in detail["profile_sections"]])
        self.assertNotIn("打印预览尺寸", all_text)
        self.assertNotIn("产品——手卡", all_text)


class ProductDetailTemplateTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "products.html").read_text(encoding="utf-8-sig")

    def test_products_page_uses_three_panel_chatbot_workspace(self):
        self.assertIn('class="products-chat-shell"', self.page)
        self.assertIn('id="categoryTree"', self.page)
        self.assertIn('id="globalChatThread"', self.page)
        self.assertIn('id="detailPanelBody"', self.page)
        self.assertIn("async function selectProduct(id)", self.page)
        self.assertIn("'/api/products/'+id+'/detail'", self.page)
        self.assertIn("renderProductSkuRows", self.page)
        self.assertIn("renderProfileSectionEditor", self.page)
        self.assertIn("活动价", self.page)
        self.assertIn("renderPriceSkuCard", self.page)
        self.assertNotIn('id="productDetailModal"', self.page)

    def test_products_page_has_single_main_rag_chat_that_switches_scope(self):
        self.assertIn("function sendGlobalChat(event)", self.page)
        self.assertNotIn("function sendScopedChat(event)", self.page)
        self.assertIn("'/api/products/rag-chat'", self.page)
        self.assertIn("'/api/products/'+productId+'/rag-chat'", self.page)
        self.assertIn("const scoped=!!productId", self.page)
        self.assertIn("const payload=scoped?{query:query}:{query:query,limit:30}", self.page)
        self.assertIn('id="globalChatInput"', self.page)
        self.assertIn('id="globalChatSubtitle"', self.page)
        self.assertNotIn('id="scopedChatInput"', self.page)
        self.assertNotIn('id="scopedChatThread"', self.page)
        self.assertIn("renderRagResults", self.page)

    def test_products_page_mobile_workspace_switches_between_list_detail_and_chat(self):
        self.assertIn("let mobileProductView='list'", self.page)
        self.assertIn("function setMobileProductView(view)", self.page)
        self.assertIn("function syncMobileProductView()", self.page)
        self.assertIn("document.querySelector('.products-page')", self.page)
        self.assertIn("root.setAttribute('data-mobile-view',mobileProductView)", self.page)
        self.assertIn("document.querySelectorAll('.mobile-product-tab')", self.page)
        self.assertIn("button.classList.toggle('on',button.getAttribute('data-view')===mobileProductView)", self.page)

    def test_product_mobile_workspace_moves_to_expected_panel_after_user_actions(self):
        select_body = re.search(r"async function selectProduct\(id\)\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        clear_body = re.search(r"function clearSelectedProduct\(\)\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        chat_body = re.search(r"async function sendGlobalChat\(event\)\{(?P<body>.*?)\n\}", self.page, flags=re.S)

        self.assertIsNotNone(select_body)
        self.assertIsNotNone(clear_body)
        self.assertIsNotNone(chat_body)
        self.assertIn("setMobileProductView('detail');", select_body.group("body"))
        self.assertIn("setMobileProductView('list');", clear_body.group("body"))
        self.assertIn("setMobileProductView('chat');", chat_body.group("body"))

    def test_selecting_product_resets_main_chat_to_product_scope(self):
        self.assertIn("function renderProductChatWelcome(product)", self.page)
        self.assertIn("renderProductChatWelcome(product);", self.page)
        self.assertIn("只检索「'+name+'」的产品资料", self.page)
        self.assertIn("现在只检索「'+esc(name)+'」的资料。", self.page)
        self.assertNotIn('class="scoped-chat"', self.page)

    def test_product_detail_selling_points_are_editable_and_savable(self):
        self.assertIn("function editProfileSection(sectionId)", self.page)
        self.assertIn("function saveProfileSection(sectionId,button)", self.page)
        self.assertIn('class="profile-section-edit"', self.page)
        self.assertIn('class="profile-section-save"', self.page)
        self.assertIn('class="profile-section-editor"', self.page)
        self.assertIn("textarea", self.page)
        self.assertIn("'/api/products/'+selectedProductId+'/selling-points/'+pointId", self.page)
        self.assertIn("method:'PUT'", self.page)
        self.assertIn("JSON.stringify(payload)", self.page)
        self.assertIn("onclick=\"saveProfileSection", self.page)

    def test_product_detail_price_section_is_editable_and_saves_product_fields(self):
        self.assertNotIn("if(section.id==='product_price'||!editableItems.length)return ''", self.page)
        self.assertNotIn("if(sectionId==='product_price')return false", self.page)
        self.assertNotIn("if(!section||section.id==='product_price')return;", self.page)
        self.assertIn("saveProductFieldUpdates(productFieldUpdates)", self.page)
        self.assertIn("'/api/products/'+selectedProductId", self.page)

    def test_product_detail_profile_sections_do_not_render_delete_buttons(self):
        self.assertNotIn("function deleteSellingPoint(pointId,button)", self.page)
        self.assertNotIn('class="detail-point-delete"', self.page)
        self.assertNotIn("onclick=\"deleteSellingPoint", self.page)
        self.assertNotIn("'/api/products/'+productId+'/selling-points/'+pointId", self.page)
        self.assertIn(".profile-section-actions", self.page)

    def test_product_actions_use_busy_buttons_and_api_error_messages(self):
        self.assertIn("function getApiErrorMessage", self.page)
        self.assertIn("function formatApiErrorMessage", self.page)
        self.assertIn('/static/js/common.js?v=tools-20260714-all-pages', self.page)
        self.assertIn("function withBusyButton", self.page)
        self.assertIn("withBusyButton(button", self.page)
        self.assertIn("btnExtractAllPoints", self.page)
        self.assertIn("btnDeleteFile", self.page)
        self.assertIn("btnExtractPoints", self.page)

    def test_three_panel_workspace_uses_independent_scrolling(self):
        self.assertIn("body{overflow:hidden}", self.page)
        self.assertIn(".products-page{max-width:min(1600px,calc(100vw - 32px));height:calc(100dvh - 68px)", self.page)
        self.assertIn(".products-chat-shell{flex:1;min-height:0;display:grid;grid-template-columns:300px 500px minmax(420px,1fr)", self.page)
        self.assertIn(".sidebar-panel{grid-column:1;order:1}", self.page)
        self.assertIn(".detail-panel{grid-column:2;order:2}", self.page)
        self.assertIn(".chat-panel{grid-column:3;order:3}", self.page)
        self.assertIn(".category-tree{flex:1;min-height:0;overflow:auto", self.page)
        self.assertIn(".chat-thread{flex:1;min-height:0;overflow:auto", self.page)
        self.assertIn(".selected-detail{flex:1;min-height:0;overflow:auto", self.page)
        self.assertIn("display:flex;flex-direction:column;gap:14px", self.page)
        self.assertIn(".selected-detail .profile-section{flex:0 0 auto}", self.page)
        self.assertNotIn(".scoped-thread{max-height:220px;overflow:auto", self.page)
        self.assertNotIn("function lockBodyScroll()", self.page)
        self.assertNotIn("function scrollProductsToTop()", self.page)

    def test_detail_panel_renders_five_profile_sections_without_horizontal_price_table(self):
        self.assertIn("function renderProfileSections(sections)", self.page)
        self.assertIn("product_info:'产品信息'", self.page)
        self.assertIn("product_price:'产品价格'", self.page)
        self.assertIn("product_usage:'产品用途'", self.page)
        self.assertIn("usage_scenarios:'使用场景'", self.page)
        self.assertIn("main_selling_points:'主要卖点'", self.page)
        self.assertIn("body+=editingProfileSections[section.id]?renderProfileSectionEditor(section,editableItems):renderProfileItems(items,section.id);", self.page)
        self.assertIn("function isEditableProfileItem(item,sectionId)", self.page)
        self.assertIn("function editableProfileItems(items,sectionId)", self.page)
        self.assertIn("function renderProfileSectionActions(section,editableItems)", self.page)
        self.assertIn("function parseProfileSectionEditor(text,items)", self.page)
        self.assertNotIn("renderEditableProfileItem", self.page)
        self.assertNotIn('.profile-section .detail-point{border:0', self.page)
        self.assertNotIn("detail-point-editor", self.page)
        self.assertIn('.profile-section[data-section-id="main_selling_points"] .profile-section-body{gap:12px}', self.page)
        self.assertNotIn('.profile-section[data-section-id="main_selling_points"] .profile-section-body{gap:12px;max-height', self.page)
        self.assertIn("price-sku-card", self.page)
        self.assertIn("展开全部 '+skus.length+' 个 SKU", self.page)
        self.assertIn("skus.slice(0,5)", self.page)
        self.assertNotIn("detail-sku-table", self.page)
        self.assertNotIn("min-width:720px", self.page)

    def test_right_panel_keeps_product_management_actions(self):
        self.assertIn("selectedProductActions", self.page)
        self.assertIn('data-lucide="file-up"', self.page)
        self.assertIn('data-lucide="download"', self.page)
        self.assertIn('data-lucide="trash-2"', self.page)
        self.assertIn("openUploadModal('+d.id+')", self.page)
        self.assertIn("deleteProduct('+d.id+',this)", self.page)
        self.assertIn("lucide.createIcons()", self.page)

    def test_left_sidebar_uses_category_tree_instead_of_select_filter(self):
        self.assertIn("function renderSidebar()", self.page)
        self.assertIn("function toggleCategory(category)", self.page)
        self.assertIn("expandedCategories", self.page)
        self.assertIn('class="category-toggle"', self.page)
        self.assertIn('class="product-list-item', self.page)
        self.assertNotIn('<select id="categoryFilter"', self.page)
        self.assertNotIn('class="product-filter-sticky"', self.page)

    def test_left_sidebar_can_clear_selected_product(self):
        self.assertIn('id="btnClearProductSelection"', self.page)
        self.assertIn('onclick="clearSelectedProduct()"', self.page)
        self.assertIn('class="sidebar-clear-selection"', self.page)
        self.assertIn('data-lucide="x"', self.page)
        self.assertIn("function updateClearSelectionButton()", self.page)

        clear_body = re.search(r"function clearSelectedProduct\(\)\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        self.assertIsNotNone(clear_body)
        self.assertIn("renderGlobalWelcome();", clear_body.group("body"))
        self.assertIn("renderSidebar();", clear_body.group("body"))

    def test_rag_chat_prioritizes_answer_over_retrieval_artifacts(self):
        self.assertIn('id="sourceModal"', self.page)
        self.assertIn("function openSourceViewer(source,productId)", self.page)
        self.assertIn("function closeSourceModal()", self.page)
        self.assertNotIn("function hasRagResults(data)", self.page)
        self.assertIn(".answer-summary{display:block;font-size:16px", self.page)
        self.assertNotIn(".answer-summary{display:block;font-size:16px;font-weight:900", self.page)
        self.assertIn("function stripAnswerSources(text)", self.page)
        self.assertIn("function formatAssistantAnswer(text)", self.page)
        self.assertIn("const answerText=formatApiErrorMessage(text||(data&&data.answer)||'','')", self.page)
        self.assertIn("formatAssistantAnswer(answerText)", self.page)
        self.assertNotIn("esc(answerText).replace(/\\n/g,'<br>')+(data?renderRagResults(data):'')", self.page)
        self.assertNotIn("hasRagResults(data)?renderRagResults(data)", self.page)
        self.assertIn("formatApiErrorMessage(data.detail||data.message||data,'检索失败')", self.page)
        self.assertNotIn("appendMessage('globalChatThread','assistant',data.detail||'检索失败')", self.page)

        render_body = re.search(r"function renderRagResults\(data\)\{(?P<body>.*?)\n\}", self.page, flags=re.S)
        self.assertIsNotNone(render_body)
        body = render_body.group("body")
        self.assertIn("参考产品", body)
        self.assertIn("rag-result-row", body)
        self.assertIn("result.product_id", body)
        self.assertIn("selectProduct", body)
        self.assertNotIn("results.slice(0,5)", body)
        self.assertNotIn("result.sources", body)
        self.assertNotIn("rag-source-chip", body)
        self.assertNotIn("openSourceViewer", body)
        self.assertNotIn("selling_points", body)
        self.assertNotIn("sku_prices", body)
        self.assertNotIn("rag-result-card", body)
        self.assertIn("function renderRagFeedback(queryId)", self.page)
        self.assertIn("function submitRagFeedback(queryId,rating,reason)", self.page)
        self.assertIn("'/api/products/rag-feedback'", self.page)
        self.assertIn("data-rag-feedback", self.page)

    def test_product_workspace_uses_confirmed_reading_type_scale(self):
        self.assertIn(".products-panel-title{font-family:var(--font-ui);font-size:15px", self.page)
        self.assertIn(".products-panel-subtitle{font-size:12px", self.page)
        self.assertIn(".sidebar-clear-selection{height:30px", self.page)
        self.assertIn("font-size:12px;font-weight:800;white-space:nowrap", self.page)
        self.assertIn(".sidebar-search{height:36px;font-size:14px}", self.page)
        self.assertIn(".sidebar-actions .btn{height:32px;padding:0 10px;font-size:12px}", self.page)
        self.assertIn(".category-toggle{width:100%;border:0;background:transparent", self.page)
        self.assertIn("font-size:13px;font-weight:800;cursor:pointer", self.page)
        self.assertIn(".category-count{font-size:11px", self.page)
        self.assertIn(".product-list-name{font-size:15px", self.page)
        self.assertIn(".product-list-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px", self.page)
        self.assertIn(".profile-section-title{font-family:var(--font-ui);font-size:13px", self.page)
        self.assertIn(".profile-section-count{font-size:11px", self.page)
        self.assertIn(".profile-section-edit,.profile-section-save{height:28px", self.page)
        self.assertIn("font-family:var(--font-ui);font-size:12px;font-weight:800;cursor:pointer", self.page)
        self.assertIn(".profile-item-label{font-size:13px", self.page)
        self.assertIn(".profile-item-content{font-size:15px", self.page)
        self.assertIn(".profile-section-editor{width:100%;min-height:260px", self.page)
        self.assertIn("font-size:15px;line-height:1.75", self.page)
        self.assertIn(".profile-source-chip{max-width:100%;padding:4px 8px", self.page)
        self.assertIn("font-size:13px;font-weight:700", self.page)
        self.assertIn(".price-sku-name{font-size:15px", self.page)
        self.assertIn(".price-chip{display:inline-flex;align-items:center;gap:4px;min-height:24px", self.page)
        self.assertIn("font-size:13px;color:var(--text-2);font-weight:800", self.page)
        self.assertIn(".price-activity-line{display:grid;grid-template-columns:minmax(72px,auto) 1fr;gap:6px;font-size:13px", self.page)
        self.assertIn(".chat-bubble{max-width:min(760px,86%);border:1px solid var(--border-soft)", self.page)
        self.assertIn("font-size:14px;line-height:1.75", self.page)
        self.assertIn(".chat-input{flex:1;min-height:42px;max-height:110px", self.page)
        self.assertIn("font-size:14px;line-height:1.55", self.page)
        self.assertNotIn(".scoped-thread .chat-bubble{max-width:94%;font-size:14px", self.page)


if __name__ == "__main__":
    unittest.main()
