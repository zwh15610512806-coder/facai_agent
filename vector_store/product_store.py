"""Product vector store — semantic search over products + selling points."""
import logging
import os
import re
import time
from threading import Lock
from sqlalchemy.orm import Session
from rank_bm25 import BM25Okapi

from contextlib import nullcontext

from vector_store import VectorStoreError, get_chroma_store, product_index_write_lock
from services.product_knowledge_chunks import (
    build_product_knowledge_chunks,
    product_chunk_index_metadata,
)

logger = logging.getLogger("vector_store.products")
_keyword_cache_lock = Lock()
_keyword_cache: dict = {}


def _search_tokens(text: str) -> list[str]:
    text = str(text or "").lower()
    tokens = re.findall(r"[a-z0-9.]+", text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run)
        tokens.extend(run[index:index + 2] for index in range(max(0, len(run) - 1)))
        tokens.extend(run[index:index + 3] for index in range(max(0, len(run) - 2)))
    return [token for token in tokens if token.strip()]


def _clear_keyword_cache() -> None:
    with _keyword_cache_lock:
        _keyword_cache.clear()


def _upsert_batch_size() -> int:
    try:
        value = int(os.getenv("VECTOR_UPSERT_BATCH_SIZE", "64"))
    except (TypeError, ValueError):
        value = 64
    return max(1, min(value, 256))


def _iter_slices(total: int, size: int):
    for start in range(0, total, size):
        yield start, min(start + size, total)


def _filter_pending_chunks(collection, ids: list[str], documents: list[str], metadatas: list[dict]):
    """Return only missing or changed chunks so interrupted builds can resume."""
    try:
        existing = collection.get(include=["metadatas"])
        existing_hashes = {
            str(chunk_id): str((metadata or {}).get("content_hash") or "")
            for chunk_id, metadata in zip(
                existing.get("ids") or [],
                existing.get("metadatas") or [],
            )
        }
    except Exception as exc:
        logger.warning(f"Could not inspect partial product index; rebuilding all chunks: {exc}")
        return ids, documents, metadatas

    pending_ids = []
    pending_documents = []
    pending_metadatas = []
    for chunk_id, document, metadata in zip(ids, documents, metadatas):
        content_hash = str((metadata or {}).get("content_hash") or "")
        if content_hash and existing_hashes.get(str(chunk_id)) == content_hash:
            continue
        pending_ids.append(chunk_id)
        pending_documents.append(document)
        pending_metadatas.append(metadata)
    return pending_ids, pending_documents, pending_metadatas


def _existing_product_chunk_hashes(collection, product_id: int) -> dict[str, str] | None:
    try:
        existing = collection.get(
            where={"product_id": int(product_id)},
            include=["metadatas"],
        )
    except Exception as exc:
        logger.warning(f"Could not inspect product {product_id} chunks; replacing the product index: {exc}")
        return None
    return {
        str(chunk_id): str((metadata or {}).get("content_hash") or "")
        for chunk_id, metadata in zip(
            existing.get("ids") or [],
            existing.get("metadatas") or [],
        )
    }


def validate_product_collection_for_activation(collection, expected_count: int) -> dict:
    """Exercise read, ANN query and update paths before an index becomes active."""
    actual_count = int(collection.count())
    if actual_count != int(expected_count):
        raise VectorStoreError(
            f"产品知识块数量校验失败: expected {expected_count}, actual {actual_count}"
        )
    if actual_count <= 0:
        raise VectorStoreError("产品知识块索引为空，拒绝激活")

    sample = collection.get(limit=1, include=["documents", "metadatas"])
    sample_ids = sample.get("ids") or []
    sample_documents = sample.get("documents") or []
    sample_metadatas = sample.get("metadatas") or []
    if not sample_ids or not sample_documents or not sample_metadatas:
        raise VectorStoreError("产品知识块索引读取冒烟失败")
    sample_metadata = sample_metadatas[0] or {}
    if not sample_metadata.get("content_hash") or not sample_metadata.get("source_name"):
        raise VectorStoreError("产品知识块索引缺少内容哈希或来源 metadata")

    query_result = collection.query(query_texts=["产品资料"], n_results=1)
    query_hits = len((query_result.get("ids") or [[]])[0])
    if query_hits <= 0:
        raise VectorStoreError("产品知识块向量查询冒烟失败")

    collection.upsert(
        ids=[sample_ids[0]],
        documents=[sample_documents[0]],
        metadatas=[sample_metadata],
    )
    return {"count": actual_count, "query_hits": query_hits, "reupserted_chunk_id": sample_ids[0]}


class ProductVectorStore:
    """Manages product embeddings in ChromaDB 'products' collection."""

    def __init__(self):
        self.store = get_chroma_store()

    @property
    def collection(self):
        return self.store.get_product_collection()

    def build_document(self, product) -> str:
        """Build the searchable text document from a Product ORM object or dict."""
        if isinstance(product, dict):
            name = product.get("name", "")
            category = product.get("category", "")
            brand = product.get("brand", "法采")
            desc = product.get("description", "")
            selling_points = product.get("selling_points", [])
        else:
            name = product.name
            category = product.category or ""
            brand = product.brand or "法采"
            desc = product.description or ""
            selling_points = sorted(product.selling_points, key=lambda sp: sp.priority) if product.selling_points else []

        parts = [f"产品名称：{name}", f"品类：{category}", f"品牌：{brand}"]
        if desc:
            parts.append(f"描述：{desc}")
        if selling_points:
            sp_texts = [f"[{sp.point_type}]{sp.content}" for sp in selling_points]
            parts.append(f"核心卖点：{'；'.join(sp_texts)}")
        return "\n".join(parts)

    def build_chunks(self, product) -> list:
        """Build structured searchable chunks for a Product ORM object."""
        return build_product_knowledge_chunks(product)

    def _build_where(
        self,
        category_filter: str = None,
        intent_filter: tuple[str, ...] | list[str] | None = None,
        product_id_filter: int | None = None,
    ) -> dict | None:
        conditions = []
        if category_filter:
            conditions.append({"category": category_filter})
        intents = [intent for intent in (intent_filter or []) if intent]
        if len(intents) == 1:
            conditions.append({f"intent_{intents[0]}": True})
        elif len(intents) > 1:
            conditions.append({"$or": [{f"intent_{intent}": True} for intent in intents]})
        if product_id_filter is not None:
            conditions.append({"product_id": int(product_id_filter)})
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def index_product(
        self,
        product,
        db: Session = None,
        *,
        collection=None,
        lock_held: bool = False,
    ) -> list[str]:
        """Index a single product. Returns the ChromaDB chunk document IDs."""
        chunks = self.build_chunks(product)
        if not chunks:
            return []
        ids = [chunk.chunk_id for chunk in chunks]
        docs = [chunk.document() for chunk in chunks]
        metas = []
        for chunk in chunks:
            metas.append(product_chunk_index_metadata(chunk, product.price))
        try:
            lock_context = nullcontext() if lock_held else product_index_write_lock(
                getattr(self.store, "_persist_dir", None)
            )
            with lock_context:
                target_collection = collection or self.collection
                existing_hashes = _existing_product_chunk_hashes(target_collection, int(product.id))
                if existing_hashes is None:
                    raise VectorStoreError(
                        f"无法读取产品 {product.id} 的现有向量状态，已停止更新以保留旧索引"
                    )
                desired_ids = set(ids)
                removed_ids = sorted(set(existing_hashes) - desired_ids)
                pending_ids = []
                pending_docs = []
                pending_metas = []
                for chunk_id, document, metadata in zip(ids, docs, metas):
                    if existing_hashes.get(chunk_id) == str(metadata.get("content_hash") or ""):
                        continue
                    pending_ids.append(chunk_id)
                    pending_docs.append(document)
                    pending_metas.append(metadata)
                if pending_ids:
                    target_collection.upsert(
                        ids=pending_ids,
                        documents=pending_docs,
                        metadatas=pending_metas,
                    )
                if removed_ids:
                    target_collection.delete(ids=removed_ids)
            _clear_keyword_cache()
            return ids
        except Exception as e:
            logger.warning(f"Failed to index product {product.id}: {e}")
            raise VectorStoreError(f"产品 {product.id} 向量写入失败: {e}") from e

    def delete_embedding(self, product_id: int, *, collection=None, lock_held: bool = False):
        try:
            lock_context = nullcontext() if lock_held else product_index_write_lock(
                getattr(self.store, "_persist_dir", None)
            )
            with lock_context:
                target_collection = collection or self.collection
                target_collection.delete(where={"product_id": int(product_id)})
            _clear_keyword_cache()
        except Exception as e:
            logger.warning(f"Failed to delete embedding for product {product_id}: {e}")
            raise VectorStoreError(f"产品 {product_id} 向量删除失败: {e}") from e

    def search(
        self,
        query: str,
        limit: int = 10,
        category_filter: str = None,
        intent_filter: tuple[str, ...] | list[str] | None = None,
        product_id_filter: int | None = None,
    ) -> list:
        """Semantic chunk search. Returns chunk hits with product metadata."""
        self.store.require_available()
        try:
            kwargs = {"query_texts": [query], "n_results": limit * 2}
            where = self._build_where(category_filter, intent_filter, product_id_filter)
            if where:
                kwargs["where"] = where
            results = self.collection.query(**kwargs)
            if not results or not results.get("ids") or not results["ids"][0]:
                return []
            out = []
            ids = results["ids"][0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            documents = results.get("documents", [[]])[0]
            for i, doc_id in enumerate(ids):
                meta = metadatas[i] if i < len(metadatas) else {}
                dist = distances[i] if i < len(distances) else 1.0
                document = documents[i] if i < len(documents) else ""
                out.append({
                    "chunk_id": doc_id,
                    "product_id": meta.get("product_id"),
                    "name": meta.get("name", ""),
                    "category": meta.get("category", ""),
                    "price": meta.get("price", 0),
                    "section": meta.get("section", ""),
                    "source_name": meta.get("source_name", ""),
                    "source_ref": meta.get("source_ref", ""),
                    "evidence_type": meta.get("evidence_type", "direct_fact"),
                    "content_hash": meta.get("content_hash", ""),
                    "intent_tags": meta.get("intent_tags", ""),
                    "document": document,
                    "distance": round(dist, 4),
                })
            out.sort(key=lambda x: x["distance"])
            return out[:limit]
        except VectorStoreError:
            raise
        except Exception as e:
            logger.warning(f"Semantic product search failed: {e}")
            raise VectorStoreError(f"产品向量检索失败，请检查火山方舟 embedding 配置和索引维度: {e}") from e

    def index_all_products(self, db: Session, collection=None) -> int:
        """Batch index all products from SQLite. Returns count indexed."""
        from models import Product

        products = db.query(Product).filter(Product.status == "active").all()
        if not products:
            return 0

        docs = []
        ids = []
        metas = []
        for p in products:
            for chunk in self.build_chunks(p):
                ids.append(chunk.chunk_id)
                docs.append(chunk.document())
                metas.append(product_chunk_index_metadata(chunk, p.price))

        target_collection = collection or self.collection
        total_chunks = len(ids)
        ids, docs, metas = _filter_pending_chunks(target_collection, ids, docs, metas)
        if len(ids) != total_chunks:
            logger.info(
                f"Resuming product index: {total_chunks - len(ids)} unchanged chunks already present, "
                f"{len(ids)} remaining"
            )
        batch_size = _upsert_batch_size()
        try:
            for start, end in _iter_slices(len(ids), batch_size):
                self._upsert_with_retry(
                    collection=target_collection,
                    ids=ids[start:end],
                    documents=docs[start:end],
                    metadatas=metas[start:end],
                    label=f"product chunks {start + 1}-{end}/{len(ids)}",
                )
            logger.info(f"Indexed {total_chunks} product knowledge chunks ({len(ids)} written in this run)")
            _clear_keyword_cache()
            return total_chunks
        except Exception as e:
            logger.error(f"Batch product indexing failed: {e}")
            raise VectorStoreError(f"产品向量全量重建失败: {e}") from e

    def reconcile_collection_to_database(self, db: Session, collection, *, lock_held: bool = False) -> dict:
        """Make a target collection exactly match current active SQLite products."""
        from models import Product

        rows = collection.get(include=["metadatas"])
        actual_by_product: dict[int, dict[str, str]] = {}
        for chunk_id, metadata in zip(rows.get("ids") or [], rows.get("metadatas") or []):
            if not isinstance(metadata, dict):
                continue
            try:
                product_id = int(metadata.get("product_id"))
            except (TypeError, ValueError):
                continue
            actual_by_product.setdefault(product_id, {})[str(chunk_id)] = str(
                metadata.get("content_hash") or ""
            )

        products = db.query(Product).filter(Product.status == "active").all()
        active_ids = {int(product.id) for product in products}
        repaired = 0
        for product in products:
            chunks = self.build_chunks(product)
            expected = {
                chunk.chunk_id: product_chunk_index_metadata(chunk, product.price)["content_hash"]
                for chunk in chunks
            }
            if actual_by_product.get(int(product.id)) == expected:
                continue
            self.index_product(
                product,
                db,
                collection=collection,
                lock_held=lock_held,
            )
            repaired += 1
        deleted = 0
        for product_id in actual_by_product:
            if product_id in active_ids:
                continue
            self.delete_embedding(
                product_id,
                collection=collection,
                lock_held=lock_held,
            )
            deleted += 1
        return {
            "active_products": len(products),
            "repaired_products": repaired,
            "deleted_products": deleted,
        }

    def _upsert_with_retry(self, *, collection, ids: list[str], documents: list[str], metadatas: list[dict], label: str):
        last_error = None
        for attempt in range(1, 4):
            try:
                collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= 3:
                    break
                logger.warning(f"Retrying {label} after vector upsert failure ({attempt}/3): {exc}")
                time.sleep(attempt * 2)
        raise last_error

    def hybrid_search(
        self,
        query: str,
        db: Session,
        limit: int = 10,
        category_filter: str = None,
        intent_filter: tuple[str, ...] | list[str] | None = None,
        product_id_filter: int | None = None,
    ) -> list:
        """Fuse semantic and BM25 chunk rankings with reciprocal-rank fusion."""
        vector_results = []
        vector_error = ""
        try:
            vector_results = self.search(
                query,
                limit=limit,
                category_filter=category_filter,
                intent_filter=intent_filter,
                product_id_filter=product_id_filter,
            )
        except Exception as exc:
            vector_error = str(exc)[:500]
            logger.warning("Vector branch degraded; continuing with BM25: %s", exc)
        try:
            keyword_results = self._keyword_search(
                query,
                db,
                limit,
                category_filter,
                intent_filter,
                product_id_filter,
            )
        except Exception as exc:
            if vector_error:
                raise VectorStoreError(
                    f"产品向量与 BM25 检索均失败: vector={vector_error}; bm25={exc}"
                ) from exc
            raise
        if vector_error:
            keyword_results = [
                {**item, "vector_degraded_reason": vector_error}
                for item in keyword_results
            ]
        fused: dict[str, dict] = {}
        for source, results in (("vector", vector_results), ("keyword", keyword_results)):
            for rank, item in enumerate(results, start=1):
                key = str(item.get("chunk_id") or f"product_{item.get('product_id')}:{source}:{rank}")
                evidence_weight = 0.35 if item.get("evidence_type") == "association" else 1.0
                existing = fused.setdefault(key, {
                    **item,
                    "rrf_score": 0.0,
                    "retrieval_sources": [],
                    "evidence_weight": evidence_weight,
                })
                existing["rrf_score"] += evidence_weight / (60 + rank)
                existing["retrieval_sources"].append(source)
                existing[f"{source}_rank"] = rank
                if source == "vector":
                    existing.update({key_name: value for key_name, value in item.items() if value is not None})
        ordered = sorted(fused.values(), key=lambda item: (-item["rrf_score"], item.get("distance") or 999))
        capped = []
        product_chunk_counts: dict[int, int] = {}
        for item in ordered:
            try:
                product_id = int(item.get("product_id"))
            except (TypeError, ValueError):
                product_id = 0
            if product_id and product_chunk_counts.get(product_id, 0) >= 3:
                continue
            capped.append(item)
            if product_id:
                product_chunk_counts[product_id] = product_chunk_counts.get(product_id, 0) + 1
            if len(capped) >= limit:
                break
        return capped

    def _keyword_search(
        self,
        query: str,
        db: Session,
        limit: int = 10,
        category_filter: str = None,
        intent_filter: tuple[str, ...] | list[str] | None = None,
        product_id_filter: int | None = None,
    ) -> list:
        del db
        cache_key = (id(self.collection), self.collection.count())
        with _keyword_cache_lock:
            cached = _keyword_cache.get(cache_key)
        if cached is None:
            rows = self.collection.get(include=["documents", "metadatas"])
            ids = rows.get("ids") or []
            documents = rows.get("documents") or []
            metadatas = rows.get("metadatas") or []
            corpus = [_search_tokens(document) for document in documents]
            cached = (ids, documents, metadatas, BM25Okapi(corpus) if corpus else None)
            with _keyword_cache_lock:
                _keyword_cache.clear()
                _keyword_cache[cache_key] = cached
        ids, documents, metadatas, bm25 = cached
        if bm25 is None:
            return []
        scores = bm25.get_scores(_search_tokens(query))
        intents = set(intent_filter or [])
        ranked = []
        for index, score in enumerate(scores):
            if score <= 0:
                continue
            meta = metadatas[index] if index < len(metadatas) else {}
            if category_filter and meta.get("category") != category_filter:
                continue
            if product_id_filter is not None and int(meta.get("product_id") or 0) != int(product_id_filter):
                continue
            if intents and not any(meta.get(f"intent_{intent}") is True for intent in intents):
                continue
            ranked.append((float(score), index, meta))
        ranked.sort(key=lambda item: -item[0])
        return [{
            "chunk_id": ids[index],
            "product_id": meta.get("product_id"),
            "name": meta.get("name", ""),
            "category": meta.get("category", ""),
            "price": meta.get("price", 0),
            "section": meta.get("section", ""),
            "source_name": meta.get("source_name", ""),
            "source_ref": meta.get("source_ref", ""),
            "evidence_type": meta.get("evidence_type", "direct_fact"),
            "intent_tags": meta.get("intent_tags", ""),
            "document": documents[index],
            "distance": None,
            "keyword_score": round(score, 6),
        } for score, index, meta in ranked[:limit]]
