"""E2E-only vector surface that never imports ChromaDB or its ONNX dependency."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator


class VectorStoreError(RuntimeError):
    """Match the production boundary used by lazy router error handling."""


class _InMemoryCollection:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, tuple[str, dict[str, Any]]] = {}

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def get(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, list[Any]]:
        del include
        requested = None if ids is None else {str(item) for item in ids}
        with self._lock:
            rows = [
                (record_id, document, dict(metadata))
                for record_id, (document, metadata) in self._records.items()
                if (requested is None or record_id in requested)
                and (
                    where is None
                    or all(metadata.get(key) == value for key, value in where.items())
                )
            ]
        if limit is not None:
            rows = rows[:limit]
        return {
            "ids": [record_id for record_id, _, _ in rows],
            "documents": [document for _, document, _ in rows],
            "metadatas": [metadata for _, _, metadata in rows],
        }

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        with self._lock:
            for record_id, document, metadata in zip(ids, documents, metadatas):
                self._records[str(record_id)] = (str(document), dict(metadata))

    def delete(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        requested = None if ids is None else {str(item) for item in ids}
        with self._lock:
            removed = [
                record_id
                for record_id, (_, metadata) in self._records.items()
                if (requested is not None and record_id in requested)
                or (
                    where is not None
                    and all(metadata.get(key) == value for key, value in where.items())
                )
            ]
            for record_id in removed:
                self._records.pop(record_id, None)

    def query(self, **kwargs: Any) -> dict[str, list[list[Any]]]:
        del kwargs
        return {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }


class _UnavailableVectorStore:
    is_available = False

    def __init__(self) -> None:
        self._persist_dir = None
        self._product_collection = _InMemoryCollection()
        self._script_collection = _InMemoryCollection()

    def get_product_collection(self) -> _InMemoryCollection:
        return self._product_collection

    def get_script_collection(self) -> _InMemoryCollection:
        return self._script_collection


_STORE = _UnavailableVectorStore()


def init_vector_store() -> None:
    return None


def get_chroma_store() -> _UnavailableVectorStore:
    return _STORE


def get_embedding_degraded_reason(
    *,
    max_age_seconds: float = 30.0,
    since_monotonic: float | None = None,
) -> str:
    del max_age_seconds, since_monotonic
    return "isolated E2E vector store is disabled"


def embedding_health_check(probe_text: str = "vector health check") -> dict[str, Any]:
    del probe_text
    return {
        "provider": "",
        "base_url": "",
        "model": "",
        "configured": False,
        "healthy": False,
        "dimension": None,
        "error": "isolated E2E vector store is disabled",
    }


@contextmanager
def product_index_build_lock(
    persist_dir: str | None = None,
    *,
    blocking: bool = True,
) -> Iterator[None]:
    del persist_dir, blocking
    yield


@contextmanager
def product_index_write_lock(
    persist_dir: str | None = None,
    *,
    blocking: bool = True,
) -> Iterator[None]:
    del persist_dir, blocking
    yield
