"""ChromaDB vector store — singleton client + collection management."""
import os
import logging
import chromadb
from chromadb.config import Settings
from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent
from overrides import override

from config import (
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_PRODUCTS,
    CHROMA_COLLECTION_SCRIPTS,
    EMBEDDING_MODEL_NAME,
)

logger = logging.getLogger("vector_store")

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class NoopChromaTelemetry(ProductTelemetryClient):
    """Chroma telemetry client that intentionally drops all events."""

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        return None


def _make_chroma_settings() -> Settings:
    """Create Chroma settings without noisy third-party telemetry."""
    return Settings(
        anonymized_telemetry=False,
        chroma_product_telemetry_impl="vector_store.NoopChromaTelemetry",
        chroma_telemetry_impl="vector_store.NoopChromaTelemetry",
    )


class ChromaStore:
    """Singleton wrapper around ChromaDB persistent client.

    Tries BGE Chinese embeddings first (if sentence-transformers installed),
    falls back to ChromaDB's built-in ONNX embedding (all-MiniLM-L6-v2),
    or marks itself unavailable (keyword search used as fallback).
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

    def _ensure_client(self):
        if self._client is not None:
            return
        os.makedirs(self._persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._persist_dir, settings=_make_chroma_settings())
        try:
            from chromadb.utils import embedding_functions
            model_dir = os.path.join(os.path.dirname(self._persist_dir), "models", "BAAI", "bge-small-zh-v1___5")
            if os.path.isdir(model_dir):
                self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=model_dir,
                )
                logger.info(f"Using local BGE Chinese embedding: {model_dir}")
            else:
                self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=EMBEDDING_MODEL_NAME,
                )
                logger.info(f"Using remote BGE Chinese embedding: {EMBEDDING_MODEL_NAME}")
        except Exception as e:
            logger.warning(f"SentenceTransformerEmbeddingFunction failed ({e}), using keyword fallback")
            self._embedding_fn = None

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
        except Exception:
            pass
        self._product_col = None
        return self.get_product_collection()

    def reset_script_collection(self):
        self._ensure_client()
        try:
            self._client.delete_collection(CHROMA_COLLECTION_SCRIPTS)
        except Exception:
            pass
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
            logger.info(f"ChromaDB not available (keyword search active): {store.init_error}")
    except Exception as e:
        logger.warning(f"ChromaDB init deferred: {e}")
