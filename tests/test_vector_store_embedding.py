import importlib
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ARK_EMBEDDING_MODEL = "ep-20260703164659-v5sh5"


class VectorStoreEmbeddingConfigTests(unittest.TestCase):
    def test_default_embedding_config_uses_volcengine_ark_endpoint(self):
        with patch.dict(os.environ, {
            "ARK_API_KEY": "",
            "DOUBAO_API_KEY": "",
            "ARK_BASE_URL": "",
            "DOUBAO_BASE_URL": "",
            "EMBEDDING_PROVIDER": "",
            "EMBEDDING_MODEL_NAME": "",
            "EMBEDDING_API_KEY": "",
            "EMBEDDING_BASE_URL": "",
        }, clear=False):
            for key in [
                "EMBEDDING_PROVIDER",
                "EMBEDDING_MODEL_NAME",
                "EMBEDDING_API_KEY",
                "EMBEDDING_BASE_URL",
            ]:
                os.environ.pop(key, None)
            config = importlib.reload(importlib.import_module("config"))
            values = (
                config.EMBEDDING_PROVIDER,
                config.EMBEDDING_MODEL_NAME,
                config.EMBEDDING_BASE_URL,
            )
        importlib.reload(config)

        self.assertEqual(values[0], "volcengine_ark")
        self.assertEqual(values[1], ARK_EMBEDDING_MODEL)
        self.assertEqual(values[2], "https://ark.cn-beijing.volces.com/api/v3")

    def test_embedding_api_key_and_base_url_reuse_ark_or_doubao_config(self):
        with patch.dict(os.environ, {
            "ARK_API_KEY": "ark-key",
            "ARK_BASE_URL": "https://ark.example/v3",
            "DOUBAO_API_KEY": "doubao-key",
            "DOUBAO_BASE_URL": "https://doubao.example/v3",
        }, clear=False):
            for key in ["EMBEDDING_API_KEY", "EMBEDDING_BASE_URL"]:
                os.environ.pop(key, None)
            config = importlib.reload(importlib.import_module("config"))
            values = (config.EMBEDDING_API_KEY, config.EMBEDDING_BASE_URL)
        importlib.reload(config)

        self.assertEqual(values[0], "ark-key")
        self.assertEqual(values[1], "https://ark.example/v3")


class VolcengineArkEmbeddingFunctionTests(unittest.TestCase):
    def test_calls_multimodal_embedding_endpoint_once_per_text(self):
        from vector_store import VolcengineArkEmbeddingFunction

        captured = {"requests": []}

        class FakeResponse:
            status_code = 200

            def __init__(self, embedding):
                self._embedding = embedding
                self.text = "ok"

            def json(self):
                return {"data": {"embedding": self._embedding, "object": "embedding"}}

        class FakeHttpClient:
            def __init__(self, timeout):
                captured["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url, headers, json):
                captured["requests"].append({"url": url, "headers": headers, "json": json})
                if json["input"][0]["text"] == "产品资料":
                    return FakeResponse([1, 2])
                return FakeResponse([3, 4.5])

        fn = VolcengineArkEmbeddingFunction(
            api_key="key",
            base_url="https://ark.example/v3",
            model=ARK_EMBEDDING_MODEL,
            http_client_factory=FakeHttpClient,
        )

        embeddings = fn(["产品资料", "脚本资料"])

        self.assertEqual(captured["timeout"], 60)
        self.assertEqual(len(captured["requests"]), 2)
        self.assertEqual(captured["requests"][0]["url"], "https://ark.example/v3/embeddings/multimodal")
        self.assertEqual(captured["requests"][0]["headers"]["Authorization"], "Bearer key")
        self.assertEqual(captured["requests"][0]["json"], {
            "model": ARK_EMBEDDING_MODEL,
            "input": [{"type": "text", "text": "产品资料"}],
        })
        self.assertEqual(embeddings, [[1.0, 2.0], [3.0, 4.5]])

    def test_multiple_embedding_calls_preserve_input_order_when_parallel(self):
        from vector_store import VolcengineArkEmbeddingFunction

        captured = {"texts": []}

        class FakeResponse:
            status_code = 200

            def __init__(self, embedding):
                self._embedding = embedding
                self.text = "ok"

            def json(self):
                return {"data": {"embedding": self._embedding}}

        class FakeHttpClient:
            def __init__(self, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url, headers, json):
                text = json["input"][0]["text"]
                captured["texts"].append(text)
                if text == "慢请求":
                    time.sleep(0.05)
                    return FakeResponse([1, 1])
                return FakeResponse([2, 2])

        fn = VolcengineArkEmbeddingFunction(
            api_key="key",
            base_url="https://ark.example/v3",
            model=ARK_EMBEDDING_MODEL,
            http_client_factory=FakeHttpClient,
            max_concurrency=2,
        )

        self.assertEqual(fn(["慢请求", "快请求"]), [[1.0, 1.0], [2.0, 2.0]])
        self.assertEqual(set(captured["texts"]), {"慢请求", "快请求"})

    def test_missing_api_key_base_url_or_model_raises_clear_configuration_error(self):
        from vector_store import EmbeddingConfigurationError, VolcengineArkEmbeddingFunction

        with self.assertRaisesRegex(EmbeddingConfigurationError, "EMBEDDING_API_KEY"):
            VolcengineArkEmbeddingFunction(api_key="", base_url="https://ark.example/v3", model=ARK_EMBEDDING_MODEL)
        with self.assertRaisesRegex(EmbeddingConfigurationError, "EMBEDDING_BASE_URL"):
            VolcengineArkEmbeddingFunction(api_key="key", base_url="", model=ARK_EMBEDDING_MODEL)
        with self.assertRaisesRegex(EmbeddingConfigurationError, "EMBEDDING_MODEL_NAME"):
            VolcengineArkEmbeddingFunction(api_key="key", base_url="https://ark.example/v3", model="")

    def test_embedding_call_failure_raises_clear_runtime_error(self):
        from vector_store import EmbeddingCallError, VolcengineArkEmbeddingFunction

        class FakeHttpClient:
            def __init__(self, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url, headers, json):
                raise RuntimeError("endpoint forbidden")

        fn = VolcengineArkEmbeddingFunction(
            api_key="key",
            base_url="https://ark.example/v3",
            model=ARK_EMBEDDING_MODEL,
            http_client_factory=FakeHttpClient,
        )

        with self.assertRaisesRegex(EmbeddingCallError, "火山方舟 embedding 调用失败"):
            fn(["产品资料"])

    def test_embedding_call_failure_records_recent_degraded_reason(self):
        from vector_store import (
            EmbeddingCallError,
            VolcengineArkEmbeddingFunction,
            get_embedding_degraded_reason,
        )

        class FakeHttpClient:
            def __init__(self, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url, headers, json):
                raise RuntimeError("endpoint forbidden for health trace")

        fn = VolcengineArkEmbeddingFunction(
            api_key="key",
            base_url="https://ark.example/v3",
            model=ARK_EMBEDDING_MODEL,
            http_client_factory=FakeHttpClient,
        )

        with self.assertRaises(EmbeddingCallError):
            fn(["产品资料"])

        self.assertIn("endpoint forbidden for health trace", get_embedding_degraded_reason(max_age_seconds=60))


class ExplicitVectorOperationTests(unittest.TestCase):
    def test_product_search_raises_when_embedding_is_unavailable(self):
        from vector_store.product_store import ProductVectorStore

        class FakeStore:
            def require_available(self):
                raise RuntimeError("火山方舟 embedding 不可用")

        store = ProductVectorStore()
        store.store = FakeStore()

        with self.assertRaisesRegex(RuntimeError, "火山方舟 embedding 不可用"):
            store.search("色素")

    def test_script_search_raises_when_embedding_is_unavailable(self):
        from vector_store.script_store import ScriptVectorStore

        class FakeStore:
            def require_available(self):
                raise RuntimeError("火山方舟 embedding 不可用")

        store = ScriptVectorStore()
        store.store = FakeStore()

        with self.assertRaisesRegex(RuntimeError, "火山方舟 embedding 不可用"):
            store.search("口播")


class ProductChunkIndexingTests(unittest.TestCase):
    def test_index_hash_changes_when_source_or_price_metadata_changes(self):
        from services.product_knowledge_chunks import (
            ProductKnowledgeChunk,
            product_chunk_index_metadata,
        )

        base = ProductKnowledgeChunk(
            chunk_id="product_7:info",
            product_id=7,
            product_name="水性色素",
            category="烘焙调色",
            section="product_info",
            text="适合奶油调色。",
            intent_tags=("coloring",),
            source_name="资料A.md",
        )
        changed_source = ProductKnowledgeChunk(
            **{**base.__dict__, "source_name": "资料B.md", "content_hash": ""}
        )

        first = product_chunk_index_metadata(base, 18.59)
        source_changed = product_chunk_index_metadata(changed_source, 18.59)
        price_changed = product_chunk_index_metadata(base, 20.0)

        self.assertNotEqual(first["content_hash"], source_changed["content_hash"])
        self.assertNotEqual(first["content_hash"], price_changed["content_hash"])

    def test_activation_smoke_test_reads_queries_and_reupserts_one_chunk(self):
        from vector_store.product_store import validate_product_collection_for_activation

        captured = {}

        class FakeCollection:
            def count(self):
                return 1

            def get(self, limit, include):
                captured["get"] = (limit, include)
                return {
                    "ids": ["product_7:info"],
                    "documents": ["产品：水性色素"],
                    "metadatas": [{
                        "product_id": 7,
                        "content_hash": "hash",
                        "source_name": "结构化产品资料",
                    }],
                }

            def query(self, query_texts, n_results):
                captured["query"] = (query_texts, n_results)
                return {"ids": [["product_7:info"]]}

            def upsert(self, ids, documents, metadatas):
                captured["upsert"] = (ids, documents, metadatas)

        result = validate_product_collection_for_activation(FakeCollection(), expected_count=1)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["query_hits"], 1)
        self.assertEqual(captured["upsert"][0], ["product_7:info"])

    def test_resume_filter_skips_chunks_with_matching_content_hash(self):
        from vector_store.product_store import _filter_pending_chunks

        class FakeCollection:
            def get(self, include):
                self.include = include
                return {
                    "ids": ["product_7:info", "product_7:price"],
                    "metadatas": [
                        {"content_hash": "same"},
                        {"content_hash": "old"},
                    ],
                }

        collection = FakeCollection()
        ids, documents, metadatas = _filter_pending_chunks(
            FakeCollection(),
            ["product_7:info", "product_7:price", "product_7:usage"],
            ["info", "price", "usage"],
            [
                {"content_hash": "same"},
                {"content_hash": "new"},
                {"content_hash": "usage"},
            ],
        )

        self.assertEqual(ids, ["product_7:price", "product_7:usage"])
        self.assertEqual(documents, ["price", "usage"])
        self.assertEqual([item["content_hash"] for item in metadatas], ["new", "usage"])

    def test_index_product_writes_multiple_metadata_chunks(self):
        from vector_store.product_store import ProductVectorStore

        captured = {}

        class FakeCollection:
            def get(self, where, include):
                return {"ids": [], "metadatas": []}

            def upsert(self, ids, documents, metadatas):
                captured["ids"] = ids
                captured["documents"] = documents
                captured["metadatas"] = metadatas

        class FakeStore:
            def get_product_collection(self):
                return FakeCollection()

        product = SimpleNamespace(
            id=7,
            name="水性色素",
            category="烘焙调色",
            brand="法采",
            description="适合蛋糕调色和翻糖上色。",
            price=18.59,
            selling_points=[
                SimpleNamespace(point_type="核心卖点", content="少量即可上色，适合调色备货。", priority=1),
                SimpleNamespace(point_type="使用场景", content="适合奶油、蛋糕胚和翻糖调色。", priority=2),
            ],
        )
        store = ProductVectorStore()
        store.store = FakeStore()

        doc_ids = store.index_product(product)

        self.assertGreaterEqual(len(doc_ids), 3)
        self.assertTrue(all(doc_id.startswith("product_7:") for doc_id in captured["ids"]))
        sections = {meta["section"] for meta in captured["metadatas"]}
        self.assertGreaterEqual(sections, {"product_info", "selling_point"})
        self.assertTrue(all(meta["product_id"] == 7 for meta in captured["metadatas"]))
        self.assertTrue(any(meta.get("intent_coloring") is True for meta in captured["metadatas"]))
        self.assertTrue(any("少量即可上色" in document for document in captured["documents"]))

    def test_index_product_only_reembeds_changed_chunks(self):
        from vector_store.product_store import ProductVectorStore

        captured = {"deleted_ids": [], "events": []}

        class FakeCollection:
            def get(self, where, include):
                captured["get_where"] = where
                return {
                    "ids": ["keep", "change", "remove"],
                    "metadatas": [
                        {"content_hash": captured["keep_hash"]},
                        {"content_hash": "old"},
                        {"content_hash": "removed"},
                    ],
                }

            def delete(self, ids=None, where=None):
                captured["events"].append("delete")
                captured["deleted_ids"] = ids
                captured["delete_where"] = where

            def upsert(self, ids, documents, metadatas):
                captured["events"].append("upsert")
                captured["upsert_ids"] = ids

        class FakeStore:
            def get_product_collection(self):
                return FakeCollection()

        chunks = [
            SimpleNamespace(
                chunk_id="keep",
                document=lambda: "keep",
                metadata=lambda: {"content_hash": "same"},
            ),
            SimpleNamespace(
                chunk_id="change",
                document=lambda: "change",
                metadata=lambda: {"content_hash": "new"},
            ),
            SimpleNamespace(
                chunk_id="add",
                document=lambda: "add",
                metadata=lambda: {"content_hash": "added"},
            ),
        ]
        product = SimpleNamespace(id=7, price=18.59)
        store = ProductVectorStore()
        store.store = FakeStore()
        store.build_chunks = lambda _product: chunks
        from services.product_knowledge_chunks import product_chunk_index_metadata

        captured["keep_hash"] = product_chunk_index_metadata(chunks[0], product.price)["content_hash"]

        indexed_ids = store.index_product(product)

        self.assertEqual(indexed_ids, ["keep", "change", "add"])
        self.assertEqual(captured["get_where"], {"product_id": 7})
        self.assertEqual(captured["deleted_ids"], ["remove"])
        self.assertIsNone(captured["delete_where"])
        self.assertEqual(captured["upsert_ids"], ["change", "add"])
        self.assertEqual(captured["events"], ["upsert", "delete"])

    def test_search_passes_category_intent_and_product_metadata_filters(self):
        from vector_store.product_store import ProductVectorStore

        captured = {}

        class FakeCollection:
            def query(self, **kwargs):
                captured["query"] = kwargs
                return {
                    "ids": [["product_7:info"]],
                    "distances": [[0.12]],
                    "metadatas": [[{
                        "product_id": 7,
                        "name": "水性色素",
                        "category": "烘焙调色",
                        "price": 18.59,
                        "section": "product_info",
                        "intent_tags": "coloring",
                    }]],
                    "documents": [["产品名称：水性色素\n适合调色"]],
                }

        class FakeStore:
            def require_available(self):
                return None

            def get_product_collection(self):
                return FakeCollection()

        store = ProductVectorStore()
        store.store = FakeStore()

        results = store.search(
            "调色怎么用",
            limit=5,
            category_filter="烘焙调色",
            intent_filter=("coloring",),
            product_id_filter=7,
        )

        where = captured["query"]["where"]
        self.assertIn("$and", where)
        self.assertIn({"category": "烘焙调色"}, where["$and"])
        self.assertIn({"intent_coloring": True}, where["$and"])
        self.assertIn({"product_id": 7}, where["$and"])
        self.assertEqual(results[0]["product_id"], 7)
        self.assertEqual(results[0]["chunk_id"], "product_7:info")
        self.assertEqual(results[0]["section"], "product_info")


if __name__ == "__main__":
    unittest.main()
