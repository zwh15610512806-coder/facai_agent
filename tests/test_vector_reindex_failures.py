import unittest
import json
import tempfile
from pathlib import Path

from fastapi import HTTPException


class _DeleteFailsClient:
    def __init__(self):
        self.created_after_failure = False

    def delete_collection(self, name):
        raise RuntimeError(f"{name} delete failed")

    def get_or_create_collection(self, **kwargs):
        self.created_after_failure = True
        return object()


class VectorResetFailureTests(unittest.TestCase):
    def test_corrupt_product_manifest_fails_closed(self):
        from vector_store import ChromaStore, VectorStoreError

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "product_index_manifest.json"
            manifest.write_text("{not-json", encoding="utf-8")
            store = ChromaStore(persist_dir=temp_dir)

            with self.assertRaisesRegex(VectorStoreError, "manifest|清单"):
                store.active_product_collection_name()

    def test_manifest_missing_collection_fails_closed_without_creating_empty_index(self):
        from vector_store import ChromaStore, VectorStoreError

        class MissingCollectionClient:
            created = False

            def get_collection(self, **kwargs):
                raise RuntimeError("collection missing")

            def get_or_create_collection(self, **kwargs):
                self.created = True
                return object()

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "product_index_manifest.json"
            manifest.write_text(
                json.dumps({"active_collection": "products_v_missing"}),
                encoding="utf-8",
            )
            store = ChromaStore(persist_dir=temp_dir)
            store._client = MissingCollectionClient()
            store._embedding_fn = object()

            with self.assertRaisesRegex(VectorStoreError, "products_v_missing"):
                store.get_product_collection()

            self.assertFalse(store._client.created)

    def test_product_build_lock_rejects_concurrent_builder(self):
        from vector_store import VectorStoreError, product_index_build_lock

        with tempfile.TemporaryDirectory() as temp_dir:
            with product_index_build_lock(temp_dir, blocking=False):
                with self.assertRaisesRegex(VectorStoreError, "正在重建"):
                    with product_index_build_lock(temp_dir, blocking=False):
                        pass

    def _store_with_delete_failure(self):
        from vector_store import ChromaStore

        store = ChromaStore(persist_dir="unused")
        store._client = _DeleteFailsClient()
        store._embedding_fn = object()
        return store

    def test_reset_product_collection_surfaces_delete_failure_without_recreating_collection(self):
        from vector_store import VectorStoreError

        store = self._store_with_delete_failure()

        with self.assertRaisesRegex(VectorStoreError, "删除产品向量集合失败.*delete failed"):
            store.reset_product_collection()

        self.assertFalse(store._client.created_after_failure)

    def test_reset_script_collection_surfaces_delete_failure_without_recreating_collection(self):
        from vector_store import VectorStoreError

        store = self._store_with_delete_failure()

        with self.assertRaisesRegex(VectorStoreError, "删除脚本向量集合失败.*delete failed"):
            store.reset_script_collection()

        self.assertFalse(store._client.created_after_failure)

    def test_product_reindex_failure_keeps_previous_active_collection(self):
        from routers import products as products_router
        from vector_store import VectorStoreError
        from vector_store import product_store

        class FailingProductVectorStore:
            activated = []

            def __init__(self):
                self.store = self

            def active_product_collection_name(self):
                return "products_v_old"

            def create_product_collection(self, name):
                return object()

            def index_all_products(self, db, collection=None):
                raise VectorStoreError("new version write failed")

            def activate_product_collection(self, name):
                self.activated.append(name)

            def delete_product_collection(self, name):
                return None

        original = product_store.ProductVectorStore
        product_store.ProductVectorStore = FailingProductVectorStore
        try:
            with self.assertRaises(HTTPException) as caught:
                products_router.reindex_products(db=None)
        finally:
            product_store.ProductVectorStore = original

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("new version write failed", caught.exception.detail)
        self.assertIn("未重建", caught.exception.detail)
        self.assertEqual(FailingProductVectorStore.activated, [])

    def test_product_reindex_activates_only_after_count_validation(self):
        from routers import products as products_router
        from vector_store import product_store

        events = []

        class TargetCollection:
            def count(self):
                events.append("count")
                return 12

            def get(self, limit, include):
                events.append("get")
                return {
                    "ids": ["product_1:info"],
                    "documents": ["产品：测试"],
                    "metadatas": [{
                        "product_id": 1,
                        "content_hash": "hash",
                        "source_name": "结构化产品资料",
                    }],
                }

            def query(self, query_texts, n_results):
                events.append("query")
                return {"ids": [["product_1:info"]]}

            def upsert(self, ids, documents, metadatas):
                events.append("upsert")

        class SuccessfulProductVectorStore:
            def __init__(self):
                self.store = self

            def active_product_collection_name(self):
                return "products_v_old"

            def create_product_collection(self, name):
                events.append("create")
                return TargetCollection()

            def index_all_products(self, db, collection=None):
                events.append("index")
                return 12

            def activate_product_collection(self, name, **kwargs):
                events.append("activate")

            def delete_product_collection(self, name):
                events.append("delete")

        original = product_store.ProductVectorStore
        product_store.ProductVectorStore = SuccessfulProductVectorStore
        try:
            response = products_router.reindex_products(db=None)
        finally:
            product_store.ProductVectorStore = original

        self.assertEqual(
            events,
            [
                "create", "index",
                "count", "get", "query", "upsert",
                "count", "count", "get", "query", "upsert",
                "activate",
            ],
        )
        self.assertIn("12", response.message)

    def test_script_reindex_reports_reset_failure_as_service_error(self):
        from routers import templates as templates_router
        from vector_store import VectorStoreError
        from vector_store import script_store

        class FailingScriptVectorStore:
            def __init__(self):
                self.store = self

            def reset_script_collection(self):
                raise VectorStoreError("script delete failed")

            def index_all_scripts(self, db):
                raise AssertionError("index_all_scripts should not run after reset failure")

        original = script_store.ScriptVectorStore
        script_store.ScriptVectorStore = FailingScriptVectorStore
        try:
            with self.assertRaises(HTTPException) as caught:
                templates_router.reindex_scripts(db=None)
        finally:
            script_store.ScriptVectorStore = original

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("script delete failed", caught.exception.detail)
        self.assertIn("未重建", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
