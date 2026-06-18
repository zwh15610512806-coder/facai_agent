import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import GeneratedScript, Product
from routers.scripts import get_history, list_history
from schemas import GeneratedScriptOut, GeneratedScriptPageOut


ROOT = Path(__file__).resolve().parents[1]


class HistoryPageTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "history.html").read_text(encoding="utf-8-sig")

    def test_history_page_has_expand_and_collapse_controls(self):
        self.assertIn("toggleScriptExpanded", self.page)
        self.assertIn("查看全文", self.page)
        self.assertIn("收起", self.page)
        self.assertIn("script-preview-expanded", self.page)

    def test_history_script_preview_box_can_toggle_long_script(self):
        self.assertIn("script-preview-clickable", self.page)
        self.assertIn("onclick=\"toggleScriptExpanded('+s.id+')\"", self.page)
        self.assertIn("onkeydown=\"handlePreviewKey(event," + "'+s.id+'" + ")\"", self.page)

    def test_history_page_escapes_script_content_before_rendering(self):
        self.assertIn("function escHtml", self.page)
        self.assertIn("var content=s.script_content||''", self.page)
        self.assertIn("escHtml(preview)", self.page)

    def test_history_preview_keeps_full_content_available_for_copy(self):
        self.assertIn("copyText(s.script_content)", self.page)
        self.assertIn("fallbackCopyText", self.page)
        self.assertIn("已成功复制到剪贴板", self.page)
        self.assertIn("expandedScripts", self.page)
        self.assertNotIn("substring(0,400)+(s.script_content&&s.script_content.length>400?'...':'')", self.page)


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        product = Product(name="测试产品", category="烘焙调色", price=12.5)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self.product = product

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _add_history_record(self, is_high_conversion=1):
        record = GeneratedScript(
            product_id=self.product.id,
            script_content="完整脚本内容",
            video_type="痛点类",
            ai_model="DeepSeek AI",
            is_high_conversion=is_high_conversion,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def test_generated_script_output_exposes_high_conversion_flag(self):
        self.assertIn("is_high_conversion", GeneratedScriptOut.model_fields)

    def test_generated_script_page_output_exposes_pagination_fields(self):
        for field in ["items", "total", "page", "per_page", "total_pages"]:
            self.assertIn(field, GeneratedScriptPageOut.model_fields)

    def test_history_list_returns_paginated_records_in_desc_order(self):
        first = self._add_history_record(is_high_conversion=0)
        second = self._add_history_record(is_high_conversion=1)

        page = list_history(product_id=None, page=1, per_page=1, db=self.db)

        self.assertEqual(page.total, 2)
        self.assertEqual(page.page, 1)
        self.assertEqual(page.per_page, 1)
        self.assertEqual(page.total_pages, 2)
        self.assertEqual([item.id for item in page.items], [second.id])
        self.assertNotEqual(page.items[0].id, first.id)

    def test_history_list_empty_page_is_valid(self):
        page = list_history(product_id=None, page=3, per_page=20, db=self.db)

        self.assertEqual(page.total, 0)
        self.assertEqual(page.total_pages, 1)
        self.assertEqual(page.items, [])

    def test_history_list_returns_high_conversion_flag(self):
        self._add_history_record(is_high_conversion=1)

        scripts = list_history(product_id=None, db=self.db)

        self.assertEqual(len(scripts.items), 1)
        self.assertTrue(scripts.items[0].is_high_conversion)

    def test_history_detail_returns_high_conversion_flag(self):
        record = self._add_history_record(is_high_conversion=0)

        script = get_history(record.id, db=self.db)

        self.assertFalse(script.is_high_conversion)


if __name__ == "__main__":
    unittest.main()
