import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ARK_EMBEDDING_MODEL = "ark-4e8d208b-a896-43b4-9b77-eda0ceac0370-0a2ef"


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
    def test_calls_openai_compatible_embeddings_create(self):
        from vector_store import VolcengineArkEmbeddingFunction

        captured = {}

        class FakeEmbeddings:
            def create(self, model, input):
                captured["model"] = model
                captured["input"] = input
                return SimpleNamespace(data=[
                    SimpleNamespace(index=1, embedding=[3, 4.5]),
                    SimpleNamespace(index=0, embedding=[1, 2]),
                ])

        class FakeClient:
            def __init__(self, api_key, base_url):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.embeddings = FakeEmbeddings()

        fn = VolcengineArkEmbeddingFunction(
            api_key="key",
            base_url="https://ark.example/v3",
            model=ARK_EMBEDDING_MODEL,
            client_factory=FakeClient,
        )

        embeddings = fn(["产品资料", "脚本资料"])

        self.assertEqual(captured["api_key"], "key")
        self.assertEqual(captured["base_url"], "https://ark.example/v3")
        self.assertEqual(captured["model"], ARK_EMBEDDING_MODEL)
        self.assertEqual(captured["input"], ["产品资料", "脚本资料"])
        self.assertEqual(embeddings, [[1.0, 2.0], [3.0, 4.5]])

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

        class FakeEmbeddings:
            def create(self, model, input):
                raise RuntimeError("endpoint forbidden")

        class FakeClient:
            def __init__(self, api_key, base_url):
                self.embeddings = FakeEmbeddings()

        fn = VolcengineArkEmbeddingFunction(
            api_key="key",
            base_url="https://ark.example/v3",
            model=ARK_EMBEDDING_MODEL,
            client_factory=FakeClient,
        )

        with self.assertRaisesRegex(EmbeddingCallError, "火山方舟 embedding 调用失败"):
            fn(["产品资料"])


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


if __name__ == "__main__":
    unittest.main()
