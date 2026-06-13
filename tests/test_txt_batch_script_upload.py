import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import ViralScript
from routers import templates as templates_router


ROOT = Path(__file__).resolve().parents[1]


class ImportPageTxtBatchUploadTests(unittest.TestCase):
    def test_import_page_exposes_batch_txt_upload(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn('id="txtScriptFiles"', page)
        self.assertIn('accept=".txt,text/plain"', page)
        self.assertIn("multiple", page)
        self.assertIn("uploadTxtScriptFiles", page)
        self.assertIn("/api/templates/viral/upload-txt-batch", page)


class TxtBatchScriptUploadTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.original_analyze_script_ai = templates_router.analyze_script_ai
        self.original_sync_viral_index = templates_router._sync_viral_index

        async def no_ai_analysis(text: str, user_type: str = ""):
            return {}

        templates_router.analyze_script_ai = no_ai_analysis
        templates_router._sync_viral_index = lambda viral, db: None

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[templates_router.get_db] = override_db
        app.include_router(templates_router.router, prefix="/api/templates")
        self.client = TestClient(app)

    def tearDown(self):
        templates_router.analyze_script_ai = self.original_analyze_script_ai
        templates_router._sync_viral_index = self.original_sync_viral_index
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_batch_upload_txt_files_creates_viral_scripts_from_file_names(self):
        files = [
            (
                "files",
                (
                    "first-hook.txt",
                    "First imported script has enough text for saving into the viral script library.",
                    "text/plain",
                ),
            ),
            (
                "files",
                (
                    "second-offer.txt",
                    "Second imported script also has enough text and should be saved as another item.",
                    "text/plain",
                ),
            ),
        ]

        response = self.client.post(
            "/api/templates/viral/upload-txt-batch",
            data={"category": "烘焙配件", "video_type": "机制类", "tags": "本地txt"},
            files=files,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["total"], 2)
        self.assertEqual(data["data"]["success"], 2)
        self.assertEqual(data["data"]["skipped"], 0)

        scripts = self.db.query(ViralScript).order_by(ViralScript.id).all()
        self.assertEqual([script.title for script in scripts], ["first-hook", "second-offer"])
        self.assertEqual([script.category for script in scripts], ["烘焙配件", "烘焙配件"])
        self.assertEqual([script.video_type for script in scripts], ["机制类", "机制类"])
        self.assertIn("First imported script", scripts[0].script_content)
        self.assertEqual(scripts[0].performance_data["source"], "批量TXT上传")


if __name__ == "__main__":
    unittest.main()
