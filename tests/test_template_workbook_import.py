import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import ViralScript
from routers import templates as templates_router


ROOT = Path(__file__).resolve().parents[1]


class TemplateWorkbookImportUiTests(unittest.TestCase):
    def test_template_page_exposes_workbook_import_and_image_gallery(self):
        page = (ROOT / "templates" / "templates.html").read_text(encoding="utf-8-sig")

        self.assertIn('id="workbookImportFile"', page)
        self.assertIn("importTemplateWorkbook", page)
        self.assertIn("pollTemplateWorkbookImportStatus", page)
        self.assertIn("renderTemplateWorkbookImportState", page)
        self.assertIn("/api/templates/viral/import-workbook", page)
        self.assertIn("/api/templates/viral/import-workbook/status", page)
        self.assertIn("renderScriptCakeImages", page)
        self.assertIn("script-cake-gallery", page)
        self.assertIn("script-card-image-area", page)
        self.assertIn("script-card-time", page)
        self.assertIn("cakeImages[0].url", page)
        self.assertIn("onclick=\"openCakeImage(\\''+escJsArg(img.url)+'\\')\"", page)
        self.assertNotIn("onclick=\"openCakeImage(\\\\''+escJsArg(img.url)+'\\\\')\"", page)


class TemplateWorkbookImportApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.image_dir = Path(self.tmp.name) / "script_images"
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.original_sync_viral_index = templates_router._sync_viral_index
        self.original_session_factory = getattr(templates_router, "WORKBOOK_IMPORT_SESSION_FACTORY", None)
        self.had_session_factory = hasattr(templates_router, "WORKBOOK_IMPORT_SESSION_FACTORY")
        self.original_image_dir = getattr(templates_router, "VIRAL_SCRIPT_IMAGE_DIR", None)
        self.had_image_dir = hasattr(templates_router, "VIRAL_SCRIPT_IMAGE_DIR")
        self.original_limit = getattr(templates_router, "SCRIPT_WORKBOOK_IMPORT_MAX_SIZE", None)
        self.had_limit = hasattr(templates_router, "SCRIPT_WORKBOOK_IMPORT_MAX_SIZE")

        templates_router.WORKBOOK_IMPORT_SESSION_FACTORY = self.Session
        templates_router.VIRAL_SCRIPT_IMAGE_DIR = self.image_dir
        templates_router._sync_viral_index = lambda viral, db: None
        if hasattr(templates_router, "_reset_workbook_import_state"):
            templates_router._reset_workbook_import_state()

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
        templates_router._sync_viral_index = self.original_sync_viral_index
        if self.had_session_factory:
            templates_router.WORKBOOK_IMPORT_SESSION_FACTORY = self.original_session_factory
        elif hasattr(templates_router, "WORKBOOK_IMPORT_SESSION_FACTORY"):
            delattr(templates_router, "WORKBOOK_IMPORT_SESSION_FACTORY")
        if self.had_image_dir:
            templates_router.VIRAL_SCRIPT_IMAGE_DIR = self.original_image_dir
        elif hasattr(templates_router, "VIRAL_SCRIPT_IMAGE_DIR"):
            delattr(templates_router, "VIRAL_SCRIPT_IMAGE_DIR")
        if self.had_limit:
            templates_router.SCRIPT_WORKBOOK_IMPORT_MAX_SIZE = self.original_limit
        elif hasattr(templates_router, "SCRIPT_WORKBOOK_IMPORT_MAX_SIZE"):
            delattr(templates_router, "SCRIPT_WORKBOOK_IMPORT_MAX_SIZE")
        if hasattr(templates_router, "_reset_workbook_import_state"):
            templates_router._reset_workbook_import_state()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    def _make_png(self, color=(120, 139, 60)):
        path = Path(self.tmp.name) / f"cake_{color[0]}_{color[1]}_{color[2]}.png"
        Image.new("RGB", (18, 18), color).save(path, format="PNG")
        return path

    def _make_workbook(self, *, duplicate_script=False):
        wb = Workbook()
        ws = wb.active
        ws.title = "翻糖"
        ws.append(["编号", "是否高成交", "类型", "视频脚本", "蛋糕参考图"])
        script = "【开场-0-3s】翻糖蛋糕参考图脚本，内容足够长，用来验证导入排版和图片保存。"
        ws.append(["FT-001", "是", "痛点", script, ""])
        ws.add_image(ExcelImage(str(self._make_png())), "E2")

        ws2 = wb.create_sheet("水性色素")
        ws2.append(["编号", "高成交", "类型", "视频脚本", "蛋糕参考图"])
        second_script = script if duplicate_script else "水性色素脚本内容足够长，用来验证品类映射到烘焙调色和机制类型。"
        ws2.append(["SS-001", "", "机制", second_script, ""])

        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue(), script

    def _post_workbook(self, content, filename="scripts.xlsx"):
        return self.client.post(
            "/api/templates/viral/import-workbook",
            files={
                "file": (
                    filename,
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    def _wait_for_import(self):
        deadline = time.time() + 10
        last_status = None
        while time.time() < deadline:
            response = self.client.get("/api/templates/viral/import-workbook/status")
            self.assertEqual(response.status_code, 200)
            last_status = response.json()["data"]
            if not last_status["is_running"]:
                return last_status
            time.sleep(0.05)
        self.fail(f"workbook import did not finish: {last_status}")

    def test_import_workbook_creates_scripts_and_serves_cake_images(self):
        workbook, _script = self._make_workbook()

        response = self._post_workbook(workbook)
        self.assertEqual(response.status_code, 200)
        status = self._wait_for_import()

        self.assertEqual(status["total"], 2)
        self.assertEqual(status["created"], 2)
        self.assertEqual(status["skipped"], 0)
        scripts = self.db.query(ViralScript).order_by(ViralScript.title).all()
        self.assertEqual(len(scripts), 2)

        first = next(script for script in scripts if script.title.startswith("翻糖 / FT-001"))
        self.assertEqual(first.category, "烘焙装饰")
        self.assertEqual(first.video_type, "痛点类")
        self.assertEqual(first.is_high_conversion, 1)
        self.assertNotIn("【开场-0-3s】", first.script_content)
        self.assertEqual(first.performance_data["source"], "Excel脚本表导入")
        self.assertEqual(first.performance_data["sheet_name"], "翻糖")
        self.assertEqual(first.performance_data["script_code"], "FT-001")
        self.assertEqual(first.performance_data["original_type"], "痛点")
        self.assertEqual(len(first.performance_data["cake_images"]), 1)

        detail = self.client.get(f"/api/templates/viral/{first.id}")
        self.assertEqual(detail.status_code, 200)
        image_url = detail.json()["performance_data"]["cake_images"][0]["url"]
        image_response = self.client.get(image_url)
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.headers["content-type"], "image/png")
        self.assertTrue(image_response.content.startswith(b"\x89PNG"))

        listing = self.client.get("/api/templates/viral/list")
        self.assertEqual(listing.status_code, 200)
        listed = next(item for item in listing.json()["items"] if item["id"] == first.id)
        self.assertEqual(listed["performance_data"]["cake_images"][0]["url"], image_url)
        self.assertEqual(listed["performance_data"]["cake_images"][0]["content_type"], "image/png")
        self.assertTrue(listed["performance_data"]["cake_images"][0]["relative_path"])

        second = next(script for script in scripts if script.title.startswith("水性色素 / SS-001"))
        self.assertEqual(second.category, "烘焙调色")
        self.assertEqual(second.video_type, "机制类")

    def test_reimport_skips_duplicate_scripts_without_new_records(self):
        workbook, _script = self._make_workbook()
        first = self._post_workbook(workbook)
        self.assertEqual(first.status_code, 200)
        first_status = self._wait_for_import()
        self.assertEqual(first_status["created"], 2)

        second = self._post_workbook(workbook)
        self.assertEqual(second.status_code, 200)
        second_status = self._wait_for_import()

        self.assertEqual(second_status["created"], 0)
        self.assertEqual(second_status["skipped"], 2)
        self.assertEqual(self.db.query(ViralScript).count(), 2)

    def test_duplicate_content_updates_existing_script_with_missing_images(self):
        workbook, script = self._make_workbook(duplicate_script=True)
        existing = ViralScript(
            category="烘焙装饰",
            video_type="痛点类",
            title="旧脚本",
            script_content=templates_router.format_script(script),
            performance_data={},
        )
        self.db.add(existing)
        self.db.commit()

        response = self._post_workbook(workbook)
        self.assertEqual(response.status_code, 200)
        status = self._wait_for_import()

        self.assertEqual(status["created"], 0)
        self.assertEqual(status["updated"], 1)
        self.assertEqual(status["skipped"], 1)
        self.assertEqual(self.db.query(ViralScript).count(), 1)
        self.db.refresh(existing)
        self.assertEqual(existing.performance_data["source"], "Excel脚本表导入")
        self.assertEqual(existing.performance_data["sheet_name"], "翻糖")
        self.assertEqual(len(existing.performance_data["cake_images"]), 1)

    def test_workbook_import_uses_dedicated_large_file_limit(self):
        templates_router.SCRIPT_WORKBOOK_IMPORT_MAX_SIZE = 32

        response = self._post_workbook(b"x" * 40)

        self.assertEqual(response.status_code, 413)

    def test_workbook_import_records_index_failures_without_rollback(self):
        templates_router._sync_viral_index = lambda viral, db: False
        workbook, _script = self._make_workbook()

        response = self._post_workbook(workbook)
        self.assertEqual(response.status_code, 200)
        status = self._wait_for_import()

        self.assertEqual(status["created"], 2)
        self.assertEqual(status["index_error_count"], 2)
        self.assertEqual(self.db.query(ViralScript).count(), 2)

    def test_semantic_search_returns_cake_image_metadata_for_cards(self):
        script = ViralScript(
            category="烘焙调色",
            video_type="需求类",
            title="果蔬粉 / 参考图脚本",
            script_content="果蔬粉蛋糕参考图脚本。",
            performance_data={
                "cake_images": [{
                    "filename": "cake.png",
                    "relative_path": "sample/cake.png",
                    "url": "/api/templates/viral/1/cake-images/cake.png",
                    "content_type": "image/png",
                }]
            },
        )
        self.db.add(script)
        self.db.commit()

        with patch("vector_store.script_store.ScriptVectorStore") as store_class:
            store_class.return_value.search.return_value = [{
                "source": "viral",
                "db_id": script.id,
                "distance": 0.12,
            }]
            response = self.client.get("/api/templates/viral/search?q=果蔬粉&limit=5")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], script.id)
        self.assertEqual(data[0]["performance_data"]["cake_images"][0]["filename"], "cake.png")


if __name__ == "__main__":
    unittest.main()
