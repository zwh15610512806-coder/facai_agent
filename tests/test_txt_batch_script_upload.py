import unittest
import tempfile
import time
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

    def test_import_page_exposes_local_txt_scan(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn('id="btnScanLocalTxtScripts"', page)
        self.assertIn("扫码本地脚本", page)
        self.assertIn("scanLocalTxtScripts", page)
        self.assertIn("pollLocalTxtScanStatus", page)
        self.assertIn("renderLocalTxtScanState", page)
        self.assertIn("/api/templates/viral/scan-local-txt", page)
        self.assertIn("/api/templates/viral/scan-local-txt/status", page)
        self.assertIn('id="txtScriptResult"', page)

    def test_local_txt_scan_polling_handles_non_json_responses(self):
        page = (ROOT / "templates" / "import.html").read_text(encoding="utf-8-sig")

        self.assertIn("function readJsonResponse", page)
        self.assertIn("response.headers.get('content-type')", page)
        self.assertIn("服务返回了页面内容", page)
        self.assertIn("localTxtScanFailures<5", page)
        self.assertIn("服务连接不稳定，稍后自动重试", page)


class TxtBatchScriptUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local_source = Path(self.tmp.name) / "source"
        self.local_source.mkdir()
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
        self.original_local_source_dir = getattr(templates_router, "LOCAL_TXT_SCRIPT_SOURCE_DIR", None)
        self.had_local_source_dir = hasattr(templates_router, "LOCAL_TXT_SCRIPT_SOURCE_DIR")
        self.original_local_session_factory = getattr(templates_router, "LOCAL_TXT_SCAN_SESSION_FACTORY", None)
        self.had_local_session_factory = hasattr(templates_router, "LOCAL_TXT_SCAN_SESSION_FACTORY")
        templates_router.LOCAL_TXT_SCRIPT_SOURCE_DIR = str(self.local_source)
        templates_router.LOCAL_TXT_SCAN_SESSION_FACTORY = self.Session
        if hasattr(templates_router, "_reset_local_txt_scan_state"):
            templates_router._reset_local_txt_scan_state()

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
        if self.had_local_source_dir:
            templates_router.LOCAL_TXT_SCRIPT_SOURCE_DIR = self.original_local_source_dir
        elif hasattr(templates_router, "LOCAL_TXT_SCRIPT_SOURCE_DIR"):
            delattr(templates_router, "LOCAL_TXT_SCRIPT_SOURCE_DIR")
        if self.had_local_session_factory:
            templates_router.LOCAL_TXT_SCAN_SESSION_FACTORY = self.original_local_session_factory
        elif hasattr(templates_router, "LOCAL_TXT_SCAN_SESSION_FACTORY"):
            delattr(templates_router, "LOCAL_TXT_SCAN_SESSION_FACTORY")
        if hasattr(templates_router, "_reset_local_txt_scan_state"):
            templates_router._reset_local_txt_scan_state()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    def _wait_for_local_scan(self):
        deadline = time.time() + 10
        last_status = None
        while time.time() < deadline:
            response = self.client.get("/api/templates/viral/scan-local-txt/status")
            self.assertEqual(response.status_code, 200)
            last_status = response.json()
            data = last_status["data"]
            if not data["is_running"]:
                return data
            time.sleep(0.05)
        self.fail(f"local TXT scan did not finish: {last_status}")

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

    def test_batch_upload_rejects_files_over_configured_limit(self):
        had_limit = hasattr(templates_router, "MAX_UPLOAD_SIZE")
        original_limit = getattr(templates_router, "MAX_UPLOAD_SIZE", None)
        templates_router.MAX_UPLOAD_SIZE = 4
        try:
            response = self.client.post(
                "/api/templates/viral/upload-txt-batch",
                data={"category": "烘焙配件"},
                files=[("files", ("too-large.txt", "12345", "text/plain"))],
            )
        finally:
            if had_limit:
                templates_router.MAX_UPLOAD_SIZE = original_limit
            else:
                delattr(templates_router, "MAX_UPLOAD_SIZE")

        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.db.query(ViralScript).count(), 0)

    def test_local_txt_scan_recursively_imports_txt_files_with_relative_titles_and_metadata(self):
        nested = self.local_source / "夹心珠" / "脚本" / "4.10体验"
        nested.mkdir(parents=True)
        script_path = nested / "文案.txt"
        script_path.write_text("这是一条递归扫描导入的脚本文案，长度足够保存进模板库，并且需要用于测试。", encoding="utf-8")
        (nested / "忽略.md").write_text("not txt", encoding="utf-8")

        async def fake_ai_analysis(text: str, user_type: str = ""):
            return {
                "video_type": "情绪类",
                "structure": "钩子→展示→成交",
                "viral_points": "情绪利益点清晰",
                "tags": "夹心珠,本地扫描",
            }

        templates_router.analyze_script_ai = fake_ai_analysis

        response = self.client.post(
            "/api/templates/viral/scan-local-txt",
            data={"category": "烘焙夹心", "video_type": "情绪类", "tags": "本地txt"},
        )
        self.assertEqual(response.status_code, 200)

        status = self._wait_for_local_scan()
        self.assertEqual(status["total"], 1)
        self.assertEqual(status["success"], 1)
        self.assertEqual(status["skipped"], 0)
        self.assertEqual(status["error_count"], 0)

        scripts = self.db.query(ViralScript).order_by(ViralScript.id).all()
        self.assertEqual(len(scripts), 1)
        script = scripts[0]
        self.assertEqual(script.title, "夹心珠 / 脚本 / 4.10体验 / 文案")
        self.assertEqual(script.category, "烘焙夹心")
        self.assertEqual(script.video_type, "情绪类")
        self.assertIn("递归扫描导入", script.script_content)
        self.assertEqual(script.performance_data["source"], "本地TXT扫描")
        self.assertEqual(script.performance_data["filename"], "文案.txt")
        self.assertEqual(script.performance_data["relative_path"], "夹心珠/脚本/4.10体验/文案.txt")
        self.assertEqual(script.performance_data["local_path"], str(script_path))
        self.assertEqual(len(script.performance_data["content_sha256"]), 64)
        self.assertGreater(script.performance_data["file_size"], 0)
        self.assertEqual(script.performance_data["ai_structure"], "钩子→展示→成交")
        self.assertEqual(script.performance_data["ai_viral_points"], "情绪利益点清晰")

    def test_local_txt_scan_skips_duplicate_path_or_content_without_calling_ai_again(self):
        source_file = self.local_source / "first.txt"
        duplicate_content_file = self.local_source / "copy.txt"
        body = "这是一条会被重复扫描识别的脚本内容，文本长度足够保存，并且第二次扫描不能重复导入。"
        source_file.write_text(body, encoding="utf-8")

        calls = []

        async def fake_ai_analysis(text: str, user_type: str = ""):
            calls.append(text)
            return {"video_type": "机制类"}

        templates_router.analyze_script_ai = fake_ai_analysis

        first = self.client.post("/api/templates/viral/scan-local-txt", data={"category": "烘焙配件"})
        self.assertEqual(first.status_code, 200)
        first_status = self._wait_for_local_scan()
        self.assertEqual(first_status["success"], 1)
        self.assertEqual(len(calls), 1)

        duplicate_content_file.write_text(body, encoding="utf-8")
        second = self.client.post("/api/templates/viral/scan-local-txt", data={"category": "烘焙配件"})
        self.assertEqual(second.status_code, 200)
        second_status = self._wait_for_local_scan()

        self.assertEqual(second_status["total"], 2)
        self.assertEqual(second_status["success"], 0)
        self.assertEqual(second_status["skipped"], 2)
        self.assertEqual(self.db.query(ViralScript).count(), 1)
        self.assertEqual(len(calls), 1)

    def test_local_txt_scan_rejects_inaccessible_source_directory(self):
        missing = self.local_source / "missing"
        templates_router.LOCAL_TXT_SCRIPT_SOURCE_DIR = str(missing)

        response = self.client.post("/api/templates/viral/scan-local-txt", data={"category": "烘焙配件"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.db.query(ViralScript).count(), 0)


if __name__ == "__main__":
    unittest.main()
