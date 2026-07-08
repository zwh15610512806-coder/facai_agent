"""ChromaDB vector store — singleton client + collection management."""
import os
import logging
from typing import Any
import chromadb
import httpx
from chromadb.errors import InvalidCollectionException, NotFoundError
from chromadb.config import Settings
from chromadb.telemetry.product import ProductTelemetryClient
from overrides import override

from config import (
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_PRODUCTS,
    CHROMA_COLLECTION_SCRIPTS,
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_PROVIDER,
)

logger = logging.getLogger("vector_store")


class NoopChromaTelemetry(ProductTelemetryClient):
    """Chroma telemetry client that intentionally drops all events."""

    @override
    def capture(self, *args: Any, **kwargs: Any) -> None:
        return None


def _make_chroma_settings() -> Settings:
    """Create Chroma settings without noisy third-party telemetry."""
    return Settings(
        anonymized_telemetry=False,
        chroma_product_telemetry_impl="vector_store.NoopChromaTelemetry",
        chroma_telemetry_impl="vector_store.NoopChromaTelemetry",
    )


class VectorStoreError(RuntimeError):
    """Base exception for explicit vector-store operations."""


class EmbeddingConfigurationError(VectorStoreError):
    """Raised when the Ark embedding provider is missing required config."""


class EmbeddingCallError(VectorStoreError):
    """Raised when the Ark embedding API call or response is invalid."""


class VolcengineArkEmbeddingFunction:
    """Chroma embedding function backed by Volcengine Ark multimodal embeddings."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        http_client_factory=httpx.Client,
    ):
        if not (api_key or "").strip():
            raise EmbeddingConfigurationError(
                "EMBEDDING_API_KEY 未配置；请设置 EMBEDDING_API_KEY，或复用 ARK_API_KEY / DOUBAO_API_KEY"
            )
        if not (base_url or "").strip():
            raise EmbeddingConfigurationError(
                "EMBEDDING_BASE_URL 未配置；请设置 EMBEDDING_BASE_URL，或复用 ARK_BASE_URL / DOUBAO_BASE_URL"
            )
        if not (model or "").strip():
            raise EmbeddingConfigurationError("EMBEDDING_MODEL_NAME 未配置")
        self.model = model.strip()
        self.base_url = base_url.strip()
        self.api_key = api_key.strip()
        self._http_client_factory = http_client_factory

    @staticmethod
    def name() -> str:
        return "volcengine_ark"

    def __call__(self, input):
        texts = [str(item) for item in input]
        if not texts:
            return []
        embeddings = []
        try:
            with self._http_client_factory(timeout=60) as client:
                for text in texts:
                    embeddings.append(self._embed_text(client, text))
        except EmbeddingCallError:
            raise
        except Exception as exc:
            raise EmbeddingCallError(f"火山方舟 embedding 调用失败: {exc}") from exc

        if len(embeddings) != len(texts):
            raise EmbeddingCallError(
                f"火山方舟 embedding 响应数量不匹配: 请求 {len(texts)} 条，返回 {len(embeddings)} 条"
            )
        dimensions = {len(vector) for vector in embeddings}
        if len(dimensions) > 1:
            raise EmbeddingCallError("火山方舟 embedding 响应维度不一致")
        return embeddings

    def _embed_text(self, client, text: str) -> list[float]:
        url = self.base_url.rstrip("/") + "/embeddings/multimodal"
        payload = {
            "model": self.model,
            "input": [{"type": "text", "text": text}],
        }
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if getattr(response, "status_code", 200) >= 400:
            detail = getattr(response, "text", "")
            try:
                detail = response.json()
            except Exception:
                pass
            raise EmbeddingCallError(f"火山方舟 embedding 调用失败: HTTP {response.status_code} - {detail}")
        try:
            data = response.json()
        except Exception as exc:
            raise EmbeddingCallError(f"火山方舟 embedding 响应不是合法 JSON: {exc}") from exc
        vector = None
        payload_data = data.get("data") if isinstance(data, dict) else None
        if isinstance(payload_data, dict):
            vector = payload_data.get("embedding")
        elif isinstance(payload_data, list) and payload_data:
            first = payload_data[0]
            if isinstance(first, dict):
                vector = first.get("embedding")
            else:
                vector = getattr(first, "embedding", None)
        if vector is None:
            raise EmbeddingCallError("火山方舟 embedding 响应缺少 data.embedding 字段")
        return [float(value) for value in vector]


class ChromaStore:
    """Singleton wrapper around ChromaDB persistent client.

    Uses the configured Volcengine Ark OpenAI-compatible embedding endpoint.
    Explicit vector operations raise clear errors when the endpoint is unavailable.
    """

    _instance = None

    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR):
        self._persist_dir = os.path.abspath(persist_dir)
        self._client = None
        self._embedding_fn = None
        self._product_col = None
        self._script_col = None
        self._available = None
        self._init_error = None

    @property
    def is_available(self) -> bool:
        if self._available is None:
            try:
                self._ensure_client()
                self._available = True
            except Exception as e:
                self._init_error = str(e)
                self._available = False
                logger.warning(f"ChromaDB embedding init failed: {e}")
        return self._available

    @property
    def init_error(self) -> str:
        return self._init_error or ""

    def require_available(self) -> None:
        if not self.is_available:
            detail = self.init_error or "未知错误"
            raise VectorStoreError(f"火山方舟 embedding 不可用: {detail}")
        if self._embedding_fn is None:
            raise VectorStoreError(
                "火山方舟 embedding 未初始化；请检查 ARK_API_KEY、ARK_BASE_URL、EMBEDDING_MODEL_NAME 和 endpoint 权限"
            )

    def _make_embedding_function(self):
        provider = (EMBEDDING_PROVIDER or "").strip().lower()
        if provider != "volcengine_ark":
            raise EmbeddingConfigurationError(
                f"不支持的 EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}；当前仅支持 volcengine_ark"
            )
        return VolcengineArkEmbeddingFunction(
            api_key=EMBEDDING_API_KEY,
            base_url=EMBEDDING_BASE_URL,
            model=EMBEDDING_MODEL_NAME,
        )

    def _ensure_client(self):
        if self._client is not None:
            return
        embedding_fn = self._make_embedding_function()
        os.makedirs(self._persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._persist_dir, settings=_make_chroma_settings())
        self._embedding_fn = embedding_fn
        logger.info(f"Using Volcengine Ark embedding model: {EMBEDDING_MODEL_NAME}")

    def get_product_collection(self):
        if self._product_col is None:
            self._ensure_client()
            self._product_col = self._client.get_or_create_collection(
                name=CHROMA_COLLECTION_PRODUCTS,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        return self._product_col

    def get_script_collection(self):
        if self._script_col is None:
            self._ensure_client()
            self._script_col = self._client.get_or_create_collection(
                name=CHROMA_COLLECTION_SCRIPTS,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        return self._script_col

    def reset_product_collection(self):
        self._ensure_client()
        try:
            self._client.delete_collection(CHROMA_COLLECTION_PRODUCTS)
        except (InvalidCollectionException, NotFoundError):
            logger.info("Product vector collection did not exist before reset")
        except Exception as exc:
            raise VectorStoreError(f"删除产品向量集合失败，已停止重建以避免混用旧索引: {exc}") from exc
        self._product_col = None
        return self.get_product_collection()

    def reset_script_collection(self):
        self._ensure_client()
        try:
            self._client.delete_collection(CHROMA_COLLECTION_SCRIPTS)
        except (InvalidCollectionException, NotFoundError):
            logger.info("Script vector collection did not exist before reset")
        except Exception as exc:
            raise VectorStoreError(f"删除脚本向量集合失败，已停止重建以避免混用旧索引: {exc}") from exc
        self._script_col = None
        return self.get_script_collection()


_store = None


def get_chroma_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store


def init_vector_store():
    """Pre-warm the ChromaDB client at app startup."""
    try:
        store = get_chroma_store()
        if store.is_available:
            logger.info(f"ChromaDB ready at {store._persist_dir}")
            try:
                n_products = store.get_product_collection().count()
                n_scripts = store.get_script_collection().count()
                logger.info(f"  products: {n_products} docs, scripts: {n_scripts} docs")
            except Exception:
                pass
        else:
            logger.info(f"ChromaDB vector search unavailable: {store.init_error}")
    except Exception as e:
        logger.warning(f"ChromaDB init deferred: {e}")
