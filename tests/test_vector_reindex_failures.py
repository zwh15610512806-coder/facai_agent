import unittest

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

    def test_product_reindex_reports_reset_failure_as_service_error(self):
        from routers import products as products_router
        from vector_store import VectorStoreError
        from vector_store import product_store

        class FailingProductVectorStore:
            def __init__(self):
                self.store = self

            def reset_product_collection(self):
                raise VectorStoreError("product delete failed")

            def index_all_products(self, db):
                raise AssertionError("index_all_products should not run after reset failure")

        original = product_store.ProductVectorStore
        product_store.ProductVectorStore = FailingProductVectorStore
        try:
            with self.assertRaises(HTTPException) as caught:
                products_router.reindex_products(db=None)
        finally:
            product_store.ProductVectorStore = original

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("product delete failed", caught.exception.detail)
        self.assertIn("未重建", caught.exception.detail)

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
