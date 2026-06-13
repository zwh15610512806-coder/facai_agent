import tempfile
import time
import unittest
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import search_local


class SearchLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "\u86cb\u7cd5\u89c6\u9891.mp4").write_bytes(b"video")
        (self.root / "\u4ea7\u54c1\u8d44\u6599.pdf").write_bytes(b"pdf")
        (self.root / "\u5b50\u76ee\u5f55").mkdir()
        (self.root / "\u5b50\u76ee\u5f55" / "\u56fe\u7247.png").write_bytes(b"png")

        self.original_roots = search_local.SEARCH_ROOTS
        self.original_index_path = search_local.INDEX_PATH
        search_local.SEARCH_ROOTS = [str(self.root)]
        search_local.INDEX_PATH = self.root / "search_index.json"
        self._reset_index_state()

        app = FastAPI()
        app.include_router(search_local.router, prefix="/api/search-proxy")
        self.client = TestClient(app)

    def tearDown(self):
        search_local.SEARCH_ROOTS = self.original_roots
        search_local.INDEX_PATH = self.original_index_path
        self._reset_index_state()
        self.tmp.cleanup()

    def _reset_index_state(self):
        search_local._loaded = False
        search_local._files = []
        search_local._files_by_id = {}
        search_local._state.update({
            "is_indexing": False,
            "last_indexed": None,
            "total_files": 0,
            "message": "",
        })

    def _start_and_wait_for_index(self):
        response = self.client.post("/api/search-proxy/index/start")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        deadline = time.time() + 5
        while time.time() < deadline:
            status = self.client.get("/api/search-proxy/index/status").json()
            if not status["is_indexing"]:
                return status
            time.sleep(0.05)
        self.fail("indexing did not finish")

    def test_index_status_and_keyword_search(self):
        status = self._start_and_wait_for_index()

        self.assertEqual(status["total_files"], 4)
        self.assertIsNotNone(status["last_indexed"])

        search = self.client.get(
            "/api/search-proxy/search",
            params={"q": "\u86cb\u7cd5", "type": "video"},
        ).json()

        self.assertTrue(search["success"])
        self.assertEqual(search["total"], 1)
        self.assertEqual(search["files"][0]["file_name"], "\u86cb\u7cd5\u89c6\u9891.mp4")

    def test_ai_search_extracts_video_type_and_keyword(self):
        self._start_and_wait_for_index()

        response = self.client.post(
            "/api/search-proxy/ai-search",
            json={"query": "\u86cb\u7cd5\u89c6\u9891\u6587\u4ef6", "page": 1, "per_page": 20},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["ai_understanding"]["file_type"], "video")
        self.assertEqual(payload["ai_understanding"]["keywords"], ["\u86cb\u7cd5"])

    def test_file_detail_uses_indexed_id(self):
        self._start_and_wait_for_index()

        search = self.client.get(
            "/api/search-proxy/search",
            params={"q": "\u4ea7\u54c1\u8d44\u6599"},
        ).json()
        file_id = search["files"][0]["id"]

        detail = self.client.get(f"/api/search-proxy/files/{file_id}").json()

        self.assertTrue(detail["success"])
        self.assertEqual(detail["file"]["file_name"], "\u4ea7\u54c1\u8d44\u6599.pdf")

    def test_cached_index_outside_search_roots_is_not_served(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            search_local.INDEX_PATH.write_text(
                json.dumps({
                    "last_indexed": "2026-06-13T00:00:00",
                    "files": [{
                        "id": 99,
                        "file_name": "secret.txt",
                        "file_path": str(outside),
                        "file_type": "document",
                        "file_extension": "txt",
                        "file_size": 6,
                        "file_modified": "2026-06-13T00:00:00",
                        "parent_folder": "outside",
                    }],
                }),
                encoding="utf-8",
            )
            self._reset_index_state()

            detail = self.client.get("/api/search-proxy/files/99")
            download = self.client.get("/api/search-proxy/files/99/download")

        self.assertEqual(detail.status_code, 404)
        self.assertEqual(download.status_code, 404)

    def test_allowed_indexed_file_can_still_be_downloaded(self):
        self._start_and_wait_for_index()
        search = self.client.get(
            "/api/search-proxy/search",
            params={"q": "\u4ea7\u54c1\u8d44\u6599"},
        ).json()
        file_id = search["files"][0]["id"]

        response = self.client.get(f"/api/search-proxy/files/{file_id}/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"pdf")


if __name__ == "__main__":
    unittest.main()
