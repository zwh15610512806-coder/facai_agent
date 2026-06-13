import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import ReferenceScript, ViralScript
from routers.reference_scripts import list_reference_scripts
from routers.templates import list_viral_scripts
from schemas import ViralScriptOut


ROOT = Path(__file__).resolve().parents[1]


class TemplateHighFilterPageTests(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "templates" / "templates.html").read_text(encoding="utf-8-sig")

    def test_high_conversion_filter_is_a_standalone_checkbox(self):
        self.assertIn('class="high-filter"', self.page)
        self.assertIn('id="highOnlyFilter"', self.page)
        self.assertIn('type="checkbox"', self.page)
        self.assertIn('onchange="toggleHigh()"', self.page)
        self.assertNotIn('id="highBtn"', self.page)

    def test_high_conversion_filter_is_sent_to_list_and_search_requests(self):
        self.assertIn("function buildListUrl(base)", self.page)
        self.assertIn("high_only=1", self.page)
        self.assertIn("fetch(buildListUrl('/api/templates/viral/list'))", self.page)
        self.assertIn("fetch(buildListUrl('/api/reference/list'))", self.page)
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
