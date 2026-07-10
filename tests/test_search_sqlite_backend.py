import json
import tempfile
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


class SqliteSearchIndexTests(unittest.TestCase):
    def setUp(self):
        from services.search_index import SQLiteSearchIndex

        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.index = SQLiteSearchIndex(self.root / "search_index.db")
        self.entries = [
            {
                "id": 1,
                "file_name": "奶冻粉活动方案.docx",
                "file_path": str(self.root / "营销" / "奶冻粉活动方案.docx"),
                "file_type": "document",
                "file_extension": "docx",
                "file_size": 120,
                "file_modified": "2026-07-09T09:00:00",
                "parent_folder": "营销",
                "_parent_path": str(self.root / "营销"),
                "_search_text": f"奶冻粉活动方案.docx {self.root / '营销' / '奶冻粉活动方案.docx'}".lower(),
            },
            {
                "id": 2,
                "file_name": "奶冻粉拍摄",
                "file_path": str(self.root / "视频" / "奶冻粉拍摄"),
                "file_type": "folder",
                "file_extension": "",
                "file_size": 0,
                "file_modified": "2026-07-08T08:00:00",
                "parent_folder": "视频",
                "_parent_path": str(self.root / "视频"),
                "_search_text": f"奶冻粉拍摄 {self.root / '视频' / '奶冻粉拍摄'}".lower(),
            },
            {
                "id": 3,
                "file_name": "色素海报.png",
                "file_path": str(self.root / "设计" / "色素海报.png"),
                "file_type": "image",
                "file_extension": "png",
                "file_size": 220,
                "file_modified": "2026-07-07T07:00:00",
                "parent_folder": "设计",
                "_parent_path": str(self.root / "设计"),
                "_search_text": f"色素海报.png {self.root / '设计' / '色素海报.png'}".lower(),
            },
        ]
        self.index.replace_from_entries(self.entries, "2026-07-10T10:00:00")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_trigram_and_short_like_search_preserve_chinese_substring_semantics(self):
        trigram = self.index.search(q="奶冻粉")
        short = self.index.search(q="奶冻")

        self.assertEqual([item["id"] for item in trigram], [1, 2])
        self.assertEqual([item["id"] for item in short], [1, 2])

    def test_type_extension_date_folder_and_pagination_filters_are_compatible(self):
        documents = self.index.search(file_type="document", ext="docx")
        dated = self.index.search(date_from="2026-07-08", date_to="2026-07-09")
        folder = self.index.search(folder=str(self.root / "设计"))
        page = self.index.search_page(q="奶冻粉", page=2, per_page=1)

        self.assertEqual([item["id"] for item in documents], [1])
        self.assertEqual([item["id"] for item in dated], [1, 2])
        self.assertEqual([item["id"] for item in folder], [3])
        self.assertEqual(page["total"], 2)
        self.assertEqual([item["id"] for item in page["files"]], [2])

    def test_status_does_not_load_all_rows_into_memory(self):
        started = time.perf_counter()
        status = self.index.status()
        elapsed = time.perf_counter() - started

        self.assertEqual(status["total_files"], 3)
        self.assertEqual(status["last_indexed"], "2026-07-10T10:00:00")
        self.assertLess(elapsed, 0.3)

    def test_json_import_is_atomic_and_preserves_public_fields(self):
        json_path = self.root / "search_index.json"
        json_path.write_text(
            json.dumps({"last_indexed": "2026-07-10T11:00:00", "files": self.entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        imported = self.index.import_json(json_path, allowed_path=lambda _path: True)

        self.assertEqual(imported, 3)
        self.assertEqual(self.index.status()["last_indexed"], "2026-07-10T11:00:00")
        self.assertEqual(self.index.get(1)["file_name"], "奶冻粉活动方案.docx")


class SqliteSearchRouterMigrationTests(unittest.TestCase):
    def setUp(self):
        from routers import search_local

        self.search_local = search_local
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        target = self.root / "奶冻粉方案.docx"
        target.write_bytes(b"docx")
        self.json_path = self.root / "search_index.json"
        self.db_path = self.root / "search_index.db"
        self.json_path.write_text(
            json.dumps(
                {
                    "last_indexed": "2026-07-10T12:00:00",
                    "files": [
                        {
                            "id": 1,
                            "file_name": target.name,
                            "file_path": str(target),
                            "file_type": "document",
                            "file_extension": "docx",
                            "file_size": 4,
                            "file_modified": "2026-07-10T12:00:00",
                            "parent_folder": self.root.name,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.original = (
            search_local.SEARCH_ROOTS,
            search_local.SEARCH_INDEX_BACKEND,
            search_local.INDEX_PATH,
            search_local.INDEX_DB_PATH,
        )
        search_local.SEARCH_ROOTS = [str(self.root)]
        search_local.SEARCH_INDEX_BACKEND = "sqlite"
        search_local.INDEX_PATH = self.json_path
        search_local.INDEX_DB_PATH = self.db_path
        search_local._loaded = False
        search_local._state.update({
            "is_indexing": False,
            "last_indexed": None,
            "total_files": 0,
            "message": "",
            "migration_status": "not_started",
            "last_error": "",
        })
        app = FastAPI()
        app.include_router(search_local.router, prefix="/api/search-proxy")
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        (
            self.search_local.SEARCH_ROOTS,
            self.search_local.SEARCH_INDEX_BACKEND,
            self.search_local.INDEX_PATH,
            self.search_local.INDEX_DB_PATH,
        ) = self.original
        self.search_local._loaded = False
        self.temp_dir.cleanup()

    def test_first_status_imports_json_and_exposes_backend_migration_fields(self):
        status = self.client.get("/api/search-proxy/index/status")
        search = self.client.get("/api/search-proxy/search", params={"q": "奶冻粉"})

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["backend"], "sqlite")
        self.assertEqual(status.json()["migration_status"], "imported_json")
        self.assertEqual(status.json()["last_error"], "")
        self.assertTrue(self.db_path.exists())
        self.assertEqual(search.json()["files"][0]["file_name"], "奶冻粉方案.docx")


if __name__ == "__main__":
    unittest.main()
