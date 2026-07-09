"""ChromaDB vector store — singleton client + collection management."""
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor
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
_last_embedding_degraded_reason = ""
_last_embedding_degraded_at = 0.0


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


def _record_embedding_degraded_reason(reason: str) -> None:
    global _last_embedding_degraded_reason, _last_embedding_degraded_at
    text = str(reason or "").strip()
    if not text:
        return
    _last_embedding_degraded_reason = text
    _last_embedding_degraded_at = time.monotonic()


def get_embedding_degraded_reason(*, max_age_seconds: float = 30.0, since_monotonic: float | None = None) -> str:
    """Return the most recent embedding failure reason if it is still fresh."""
    if not _last_embedding_degraded_reason:
        return ""
    if since_monotonic is not None and _last_embedding_degraded_at < since_monotonic:
        return ""
    if time.monotonic() - _last_embedding_degraded_at > max(0.0, float(max_age_seconds)):
        return ""
    return _last_embedding_degraded_reason


def _env_or_config(name: str, fallback: str | None = "") -> str:
    if name in os.environ:
        return os.environ.get(name, "")
    return fallback or ""


def _embedding_runtime_config() -> dict[str, str]:
    import config as config_module

    provider = _env_or_config("EMBEDDING_PROVIDER", config_module.EMBEDDING_PROVIDER).strip()
    model = _env_or_config("EMBEDDING_MODEL_NAME", config_module.EMBEDDING_MODEL_NAME).strip()
    api_key_env_names = ("EMBEDDING_API_KEY", "ARK_API_KEY", "DOUBAO_API_KEY")
    if any(name in os.environ for name in api_key_env_names):
        api_key = next((os.getenv(name, "").strip() for name in api_key_env_names if os.getenv(name, "").strip()), "")
    else:
        api_key = (config_module.EMBEDDING_API_KEY or "").strip()
    base_url_env_names = ("EMBEDDING_BASE_URL", "ARK_BASE_URL", "DOUBAO_BASE_URL")
    if any(name in os.environ for name in base_url_env_names):
        base_url = next((os.getenv(name, "").strip() for name in base_url_env_names if os.getenv(name, "").strip()), "")
    else:
        base_url = (config_module.EMBEDDING_BASE_URL or "").strip()
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }


def _sanitize_embedding_error(message: str, api_key: str) -> str:
    text = str(message or "").strip()
    secret = (api_key or "").strip()
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


def _embedding_max_concurrency() -> int:
    try:
        value = int(os.getenv("EMBEDDING_CONCURRENCY", "6"))
    except (TypeError, ValueError):
        value = 6
    return max(1, min(value, 16))


def embedding_health_check(probe_text: str = "vector health check") -> dict[str, Any]:
    """Perform a lightweight text embedding probe and return sanitized health details."""
    config = _embedding_runtime_config()
    provider = config["provider"]
    model = config["model"]
    base_url = config["base_url"]
    api_key = config["api_key"]
    configured = bool(provider and model and base_url and api_key)
    result: dict[str, Any] = {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "configured": configured,
        "healthy": False,
        "dimension": None,
        "error": "",
    }
    try:
        if (provider or "").strip().lower() != "volcengine_ark":
            raise EmbeddingConfigurationError(
                f"不支持的 EMBEDDING_PROVIDER: {provider}；当前仅支持 volcengine_ark"
            )
        embedding_fn = VolcengineArkEmbeddingFunction(api_key=api_key, base_url=base_url, model=model)
        vectors = embedding_fn([probe_text])
        vector = vectors[0] if vectors else []
        result["dimension"] = len(vector)
        result["healthy"] = bool(vector)
        if not vector:
            raise EmbeddingCallError("火山方舟 embedding 健康检查未返回向量")
    except Exception as exc:
        error = _sanitize_embedding_error(str(exc), api_key)
        result["error"] = error
        result["configured"] = configured
        result["healthy"] = False
        result["dimension"] = None
        _record_embedding_degraded_reason(error)
    return result


class VolcengineArkEmbeddingFunction:
    """Chroma embedding function backed by Volcengine Ark multimodal embeddings."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        http_client_factory=httpx.Client,
        max_concurrency: int | None = None,
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
        self._max_concurrency = max(1, int(max_concurrency or _embedding_max_concurrency()))

    @staticmethod
    def name() -> str:
        return "volcengine_ark"

    def __call__(self, input):
        texts = [str(item) for item in input]
        if not texts:
            return []
        try:
            if len(texts) == 1 or self._max_concurrency <= 1:
                with self._http_client_factory(timeout=60) as client:
                    embeddings = [self._embed_text(client, text) for text in texts]
            else:
                workers = min(self._max_concurrency, len(texts))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    embeddings = list(executor.map(self._embed_text_with_new_client, texts))
        except EmbeddingCallError as exc:
            _record_embedding_degraded_reason(str(exc))
            raise
        except Exception as exc:
            error = EmbeddingCallError(f"火山方舟 embedding 调用失败: {exc}")
            _record_embedding_degraded_reason(str(error))
            raise error from exc

        if len(embeddings) != len(texts):
            raise EmbeddingCallError(
                f"火山方舟 embedding 响应数量不匹配: 请求 {len(texts)} 条，返回 {len(embeddings)} 条"
            )
        dimensions = {len(vector) for vector in embeddings}
        if len(dimensions) > 1:
            raise EmbeddingCallError("火山方舟 embedding 响应维度不一致")
        return embeddings

    def _embed_text_with_new_client(self, text: str) -> list[float]:
        with self._http_client_factory(timeout=60) as client:
            return self._embed_text(client, text)

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
                _record_embedding_degraded_reason(self._init_error)
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
