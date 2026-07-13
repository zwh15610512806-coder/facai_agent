import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import import_materials


ROOT = Path(__file__).resolve().parents[1]
REQUESTED_VIDEO_TYPES = [
    "机制类",
    "痛点类",
    "需求类",
    "认知类",
    "达人分享类",
    "制作方便",
    "成本低",
    "对比类",
    "情绪类",
    "场景类",
]


class MaterialsImportParsingTests(unittest.TestCase):
    MATERIAL_DATA_TESTS = {
        "test_parse_product_knowledge_extracts_expected_products",
        "test_parse_product_manual_extracts_missing_products",
        "test_parse_2026_product_knowledge_extracts_standard_and_card_products",
        "test_parse_2026_product_knowledge_excludes_removed_unpriced_products",
        "test_product_sources_merge_and_price_products",
        "test_2026_products_get_prices_from_price_system",
        "test_material_paths_find_knife_price_workbook",
        "test_parse_excel_scripts_extracts_expected_script_count",
        "test_script_dedupe_key_uses_category_and_title",
    }

    @classmethod
    def setUpClass(cls):
        try:
            cls.paths = import_materials.get_material_paths(ROOT)
        except (OSError, FileNotFoundError):
            cls.paths = None

    def setUp(self):
        if self._testMethodName in self.MATERIAL_DATA_TESTS and self.paths is None:
            self.skipTest("requires local material files")

    def test_parse_product_knowledge_extracts_expected_products(self):
        products = import_materials.parse_product_knowledge(self.paths.product_knowledge_md)

        self.assertEqual(len(products), 11)
        self.assertEqual(products[0].name, "袋装刀叉")
        self.assertEqual(products[0].category, "烘焙配件")
        self.assertGreaterEqual(len(products[0].selling_points), 3)
        self.assertTrue(products[0].section_text.startswith("## 产品名称：袋装刀叉"))

    def test_parse_product_manual_extracts_missing_products(self):
        products = import_materials.parse_product_manual(self.paths.product_manual_md)
        names = {product.name for product in products}

        self.assertEqual(len(products), 25)
        self.assertIn("水性色素", names)
        self.assertIn("高浓果蔬色素", names)
        self.assertIn("香草荚", names)
        self.assertIn("豆沙奶油霜", names)
        self.assertNotIn("胶状色素", names)

    def test_parse_2026_product_knowledge_extracts_standard_and_card_products(self):
        products = import_materials.parse_2026_product_knowledge(self.paths.product_2026_dir)
        by_name = {product.name: product for product in products}

        for name in ["调味果酱", "夹心脆", "茶酱", "夹心果泥", "多肉果酱", "夹心珠", "夹心芋泥"]:
            self.assertIn(name, by_name)

        self.assertEqual(by_name["调味果酱"].category, "烘焙调味")
        self.assertEqual(by_name["夹心脆"].category, "烘焙夹心")
        self.assertTrue(any("调味" in point["content"] for point in by_name["调味果酱"].selling_points))
        self.assertTrue(any("酥脆" in point["content"] for point in by_name["夹心脆"].selling_points))

    def test_parse_2026_product_knowledge_excludes_removed_unpriced_products(self):
        products = import_materials.parse_2026_product_knowledge(self.paths.product_2026_dir)
        names = {product.name for product in products}

        for removed_name in ["调味奶酱", "调味花酱", "巧克力酱"]:
            self.assertNotIn(removed_name, names)

    def test_product_sources_merge_and_price_products(self):
        products = import_materials.merge_product_inputs(
            import_materials.parse_product_knowledge(self.paths.product_knowledge_md)
            + import_materials.parse_product_manual(self.paths.product_manual_md)
            + import_materials.parse_2026_product_knowledge(self.paths.product_2026_dir)
        )
        import_materials.apply_product_prices(
            products,
            self.paths.price_system_xlsx,
            self.paths.knife_price_xlsx,
        )
        by_name = {product.name: product for product in products}

        self.assertGreater(len(products), 31)
        self.assertEqual(by_name["袋装刀叉"].price, 0.64)
        self.assertEqual(by_name["盒装刀叉"].price, 2.03)
        self.assertEqual(by_name["水性色素"].price, 17.41)
        self.assertGreaterEqual(len(by_name["水性色素"].selling_points), 6)
        self.assertIn("调味果酱", by_name)
        self.assertIn("夹心脆", by_name)
        self.assertGreaterEqual(len(by_name["调味果酱"].selling_points), 3)
        self.assertGreaterEqual(len(by_name["夹心脆"].selling_points), 3)

    def test_2026_products_get_prices_from_price_system(self):
        products = import_materials.merge_product_inputs(
            import_materials.parse_product_knowledge(self.paths.product_knowledge_md)
            + import_materials.parse_product_manual(self.paths.product_manual_md)
            + import_materials.parse_2026_product_knowledge(self.paths.product_2026_dir)
        )
        import_materials.apply_product_prices(
            products,
            self.paths.price_system_xlsx,
            self.paths.knife_price_xlsx,
        )
        by_name = {product.name: product for product in products}

        expected_prices = {
            "调味果酱": 27.06,
            "多肉果酱": 28.0,
            "茶酱": 46.94,
            "夹心脆": 24.47,
            "巧克力脆皮酱": 55.17,
            "黄油薄脆": 23.11,
            "巧克力脆珠": 15.06,
            "夹心芋泥": 49.29,
            "调味糖浆": 11.64,
            "手绘膏": 16.7,
            "1.1浆纸盘": 1.08,
            "2元盒装": 2.03,
            "2.5元盒装": 3.21,
        }
        for name, price in expected_prices.items():
            self.assertEqual(by_name[name].price, price, name)

    def test_material_paths_find_knife_price_workbook(self):
        self.assertIsNotNone(self.paths.knife_price_xlsx)
        self.assertEqual(self.paths.knife_price_xlsx.name, "刀叉价格资料.xlsx")

    def test_material_paths_ignore_office_temp_workbooks(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials_dir = root / "资料"
            materials_dir.mkdir()
            (materials_dir / "法采产品知识库 - AI调用营销极简版.md").write_text("", encoding="utf-8")
            (materials_dir / "FC法采产品手册24年5月6日更新版.md").write_text("", encoding="utf-8")
            (materials_dir / "脚本生成.xlsx").write_bytes(b"placeholder")
            real_price = materials_dir / "法采公司产品价格体系（26年3月10日更新）.xlsx"
            knife_price = materials_dir / "刀叉价格资料.xlsx"
            temp_price = materials_dir / "~$法采公司产品价格体系（26年3月10日更新）.xlsx"
            real_price.write_bytes(b"real workbook placeholder")
            knife_price.write_bytes(b"knife workbook placeholder")
            temp_price.write_bytes(b"")

            paths = import_materials.get_material_paths(root)

            self.assertEqual(paths.price_system_xlsx, real_price)
            self.assertEqual(paths.knife_price_xlsx, knife_price)

    def test_parse_excel_scripts_extracts_expected_script_count(self):
        scripts = import_materials.parse_excel_scripts(self.paths.scripts_xlsx)

        self.assertEqual(len(scripts), 445)
        self.assertEqual(scripts[0].product_name, "袋装刀叉")
        self.assertEqual(scripts[0].category, "法采-袋装刀叉")
        self.assertIn("需求", scripts[0].title)
        self.assertIn("刀叉", scripts[0].script_content)

    def test_script_type_mapping_normalizes_known_and_unknown_types(self):
        self.assertEqual(import_materials.REQUESTED_VIDEO_TYPES, REQUESTED_VIDEO_TYPES)
        self.assertEqual(import_materials.map_script_type("需求"), "需求类")
        self.assertEqual(import_materials.map_script_type("痛点"), "痛点类")
        self.assertEqual(import_materials.map_script_type("机制"), "机制类")
        self.assertEqual(import_materials.map_script_type("爆款翻拍"), "达人分享类")
        self.assertEqual(import_materials.map_script_type("对比"), "对比类")
        self.assertEqual(import_materials.map_script_type("创意"), "情绪类")
        self.assertEqual(import_materials.map_script_type("认知类"), "认知类")
        self.assertEqual(import_materials.map_script_type("制作简单"), "制作方便")
        self.assertEqual(import_materials.map_script_type("省成本"), "成本低")
        self.assertEqual(import_materials.map_script_type("场景"), "场景类")
        self.assertEqual(import_materials.map_script_type("没有映射"), "机制类")

    def test_high_conversion_detection_uses_only_high_conversion_columns(self):
        self.assertFalse(import_materials.is_high_conversion_marker(""))
        self.assertFalse(import_materials.is_high_conversion_marker(None))
        self.assertFalse(import_materials.is_high_conversion_marker("已拍"))
        self.assertTrue(import_materials.is_high_conversion_marker("高成交2000+"))
        self.assertTrue(import_materials.is_high_conversion_marker("是"))
        self.assertTrue(import_materials.is_high_conversion_marker(1))

    def test_script_dedupe_key_uses_category_and_title(self):
        scripts = import_materials.parse_excel_scripts(self.paths.scripts_xlsx)
        first = scripts[0]

        self.assertEqual(import_materials.build_script_dedupe_key(first), (first.category, first.title))
        self.assertEqual(len({import_materials.build_script_dedupe_key(s) for s in scripts}), 445)
        self.assertEqual(
            import_materials.build_script_source_key(first),
            ("资料/脚本生成.xlsx", first.sheet_name, first.source_row),
        )
        self.assertEqual(len({import_materials.build_script_source_key(s) for s in scripts}), 445)

    def test_import_page_uses_existing_csv_and_excel_endpoints(self):
        import_page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertNotIn("/api/import/products", import_page)
        self.assertIn("/api/import/excel", import_page)
        self.assertIn("/api/import/csv", import_page)

    def test_index_reset_is_needed_when_rebuild_indexes_zero_rows(self):
        self.assertTrue(import_materials.needs_index_reset(
            expected_products=88,
            expected_scripts=445,
            product_indexed=0,
            script_indexed=0,
        ))
        self.assertFalse(import_materials.needs_index_reset(
            expected_products=88,
            expected_scripts=445,
            product_indexed=88,
            script_indexed=445,
        ))

    def test_vector_store_startup_does_not_reset_existing_indexes(self):
        source = (ROOT / "vector_store" / "__init__.py").read_text(encoding="utf-8-sig")
        init_body = source.split("def init_vector_store():", 1)[1]

        self.assertNotIn("reset_product_collection()", init_body)
        self.assertNotIn("reset_script_collection()", init_body)

    def test_product_reindex_builds_version_before_activation(self):
        products_source = (ROOT / "routers" / "products.py").read_text(encoding="utf-8-sig")
        product_body = products_source.split("def reindex_products", 1)[1].split("\n\n@router", 1)[0]
        self.assertNotIn("reset_product_collection()", product_body)
        self.assertIn("create_product_collection", product_body)
        self.assertIn("activate_product_collection", product_body)
        self.assertLess(product_body.index("index_all_products"), product_body.index("activate_product_collection"))

    def test_product_reindex_reconciles_database_without_consuming_sync_jobs(self):
        products_source = (ROOT / "routers" / "products.py").read_text(encoding="utf-8-sig")
        product_body = products_source.split("def _reindex_products_locked", 1)[1].split("\n\n@router", 1)[0]

        self.assertIn("reconcile_collection_to_database", product_body)
        self.assertIn("final_db = SessionLocal()", product_body)
        self.assertRegex(product_body, r"reconcile_collection_to_database\(\s+final_db,")
        self.assertGreater(
            product_body.rindex("product_knowledge_quality_report"),
            product_body.index("final_db = SessionLocal()"),
        )
        self.assertLess(
            product_body.index("reconcile_collection_to_database"),
            product_body.index("activate_product_collection"),
        )
        self.assertNotIn("VectorSyncJob.status: \"succeeded\"", product_body)

    def test_script_reindex_still_resets_before_full_indexing(self):
        templates_source = (ROOT / "routers" / "templates.py").read_text(encoding="utf-8-sig")
        script_body = templates_source.split("def reindex_scripts", 1)[1].split("\n\n@router", 1)[0]
        self.assertIn("reset_script_collection()", script_body)
        self.assertLess(script_body.index("reset_script_collection()"), script_body.index("index_all_scripts"))

    def test_reindex_failure_message_mentions_ark_embedding_configuration(self):
        for path, func_name in [
            (ROOT / "routers" / "products.py", "def reindex_products"),
            (ROOT / "routers" / "templates.py", "def reindex_scripts"),
        ]:
            source = path.read_text(encoding="utf-8-sig")
            body = source.split(func_name, 1)[1].split("\n\n@router", 1)[0]
            self.assertIn("ARK_API_KEY", body)
            self.assertIn("ARK_BASE_URL", body)
            self.assertIn("EMBEDDING_MODEL_NAME", body)
            self.assertIn("火山方舟", body)

    def test_vector_store_disables_chromadb_telemetry(self):
        source = (ROOT / "vector_store" / "__init__.py").read_text(encoding="utf-8-sig")

        self.assertIn("class NoopChromaTelemetry(ProductTelemetryClient):", source)
        self.assertIn("def capture(self, *args: Any, **kwargs: Any) -> None:", source)
        self.assertIn("anonymized_telemetry=False", source)
        self.assertIn('chroma_product_telemetry_impl="vector_store.NoopChromaTelemetry"', source)
        self.assertIn("settings=_make_chroma_settings()", source)

    def test_generator_page_uses_requested_video_types(self):
        index_page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8-sig")
        video_types_block = index_page.split("const VIDEO_TYPES=", 1)[1].split("];", 1)[0]

        for video_type in REQUESTED_VIDEO_TYPES:
            self.assertIn(f'v:"{video_type}"', video_types_block)
        for old_type in ["黄金3秒种草", "测评对比", "痛点激发", "限时优惠", "剧情带货", "专家口播", "开箱体验", "源头工厂", "纯产品展示", "真实需求"]:
            self.assertNotIn(old_type, video_types_block)

    def test_script_generator_has_requested_type_strategies(self):
        generator_source = (ROOT / "services" / "script_generator.py").read_text(encoding="utf-8-sig")

        for video_type in REQUESTED_VIDEO_TYPES:
            self.assertIn(f'"{video_type}"', generator_source)
        self.assertIn('self.TYPE_STRATEGIES["机制类"]', generator_source)


if __name__ == "__main__":
    unittest.main()
