import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import ReferenceScript, ViralScript
from routers.reference_scripts import list_reference_scripts
from routers.templates import list_viral_scripts
from schemas import ViralScriptOut, ViralScriptPageOut
from tests.frontend_source import read_page_source


ROOT = Path(__file__).resolve().parents[1]


class TemplateHighFilterPageTests(unittest.TestCase):
    def setUp(self):
        self.page = read_page_source("templates.html")

    def test_high_conversion_filter_is_a_standalone_checkbox(self):
        self.assertIn('class="high-filter"', self.page)
        self.assertIn('id="highOnlyFilter"', self.page)
        self.assertIn('type="checkbox"', self.page)
        self.assertIn('onchange="toggleHigh()"', self.page)
        self.assertNotIn('id="highBtn"', self.page)

    def test_high_conversion_filter_is_sent_to_list_and_search_requests(self):
        self.assertIn("function buildListUrl(base)", self.page)
        self.assertIn("high_only=1", self.page)
        self.assertIn("request(buildListUrl('/api/templates/viral/list'))", self.page)
        self.assertIn("request(buildReferenceUrl())", self.page)
        self.assertIn("if(highOnly)params+='&high_only=1';", self.page)


class TemplateHighFilterApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_viral_script_output_exposes_high_conversion_flag(self):
        self.assertIn("is_high_conversion", ViralScriptOut.model_fields)

    def test_viral_script_page_output_exposes_pagination_fields(self):
        for field in ["items", "total", "page", "per_page", "total_pages"]:
            self.assertIn(field, ViralScriptPageOut.model_fields)

    def test_viral_list_supports_search_and_pagination(self):
        self.db.add_all([
            ViralScript(category="decor", video_type="type-a", title="alpha match", script_content="first body", is_high_conversion=0),
            ViralScript(category="decor", video_type="type-a", title="beta match", script_content="second body", is_high_conversion=0),
            ViralScript(category="decor", video_type="type-a", title="gamma other", script_content="third body", is_high_conversion=0),
        ])
        self.db.commit()

        page = list_viral_scripts(
            category="decor",
            video_type="type-a",
            q="match",
            page=2,
            per_page=1,
            high_only=False,
            db=self.db,
        )

        self.assertEqual(page.total, 2)
        self.assertEqual(page.page, 2)
        self.assertEqual(page.per_page, 1)
        self.assertEqual(page.total_pages, 2)
        self.assertEqual(len(page.items), 1)

    def test_viral_list_can_return_only_high_conversion_scripts(self):
        self.db.add_all([
            ViralScript(category="烘焙调色", video_type="机制类", title="普通脚本", script_content="普通脚本内容", is_high_conversion=0),
            ViralScript(category="烘焙调色", video_type="机制类", title="高成交脚本", script_content="高成交脚本内容", is_high_conversion=1),
        ])
        self.db.commit()

        scripts = list_viral_scripts(category=None, video_type=None, high_only=True, db=self.db)

        self.assertEqual([script.title for script in scripts], ["高成交脚本"])

    def test_reference_list_can_return_only_high_conversion_scripts(self):
        self.db.add_all([
            ReferenceScript(title="普通参考", script_content="普通参考脚本内容", is_high_conversion=0),
            ReferenceScript(title="高成交参考", script_content="高成交参考脚本内容", is_high_conversion=1),
        ])
        self.db.commit()

        scripts = list_reference_scripts(high_only=True, db=self.db)

        self.assertEqual([script["title"] for script in scripts], ["高成交参考"])


if __name__ == "__main__":
    unittest.main()
