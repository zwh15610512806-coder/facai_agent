"""Product vector store — semantic search over products + selling points."""
import logging
import os
import time
from sqlalchemy.orm import Session

from vector_store import VectorStoreError, get_chroma_store
from services.product_knowledge_chunks import build_product_knowledge_chunks

logger = logging.getLogger("vector_store.products")


def _upsert_batch_size() -> int:
    try:
        value = int(os.getenv("VECTOR_UPSERT_BATCH_SIZE", "64"))
    except (TypeError, ValueError):
        value = 64
    return max(1, min(value, 256))


def _iter_slices(total: int, size: int):
    for start in range(0, total, size):
        yield start, min(start + size, total)


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

    def index_product(self, product, db: Session = None) -> list[str]:
        """Index a single product. Returns the ChromaDB chunk document IDs."""
        chunks = self.build_chunks(product)
        if not chunks:
            return []
        ids = [chunk.chunk_id for chunk in chunks]
        docs = [chunk.document() for chunk in chunks]
        metas = []
        for chunk in chunks:
            metadata = chunk.metadata()
            metadata["price"] = product.price or 0
            metas.append(metadata)
        try:
            self.collection.delete(where={"product_id": int(product.id)})
            self.collection.upsert(
                ids=ids,
                documents=docs,
                metadatas=metas,
            )
            return ids
        except Exception as e:
            logger.warning(f"Failed to index product {product.id}: {e}")
            raise VectorStoreError(f"产品 {product.id} 向量写入失败: {e}") from e

    def delete_embedding(self, product_id: int):
        try:
            self.collection.delete(where={"product_id": int(product_id)})
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

    def index_all_products(self, db: Session) -> int:
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
                metadata = chunk.metadata()
                metadata["price"] = p.price or 0
                metas.append(metadata)

        batch_size = _upsert_batch_size()
        try:
            for start, end in _iter_slices(len(ids), batch_size):
                self._upsert_with_retry(
                    ids=ids[start:end],
                    documents=docs[start:end],
                    metadatas=metas[start:end],
                    label=f"product chunks {start + 1}-{end}/{len(ids)}",
                )
            logger.info(f"Indexed {len(ids)} product knowledge chunks")
            return len(ids)
        except Exception as e:
            logger.error(f"Batch product indexing failed: {e}")
            raise VectorStoreError(f"产品向量全量重建失败: {e}") from e

    def _upsert_with_retry(self, *, ids: list[str], documents: list[str], metadatas: list[dict], label: str):
        last_error = None
        for attempt in range(1, 4):
            try:
                self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
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
        """Vector search + keyword fallback, deduplicated."""
        self.store.require_available()

        results = self.search(
            query,
            limit=limit,
            category_filter=category_filter,
            intent_filter=intent_filter,
            product_id_filter=product_id_filter,
        )
        if results:
            return results

        return self._keyword_search(query, db, limit, category_filter, intent_filter, product_id_filter)

    def _keyword_search(
        self,
        query: str,
        db: Session,
        limit: int = 10,
        category_filter: str = None,
        intent_filter: tuple[str, ...] | list[str] | None = None,
        product_id_filter: int | None = None,
    ) -> list:
        from models import Product
        q = db.query(Product).filter(Product.status == "active")
        if category_filter:
            q = q.filter(Product.category == category_filter)
        if product_id_filter is not None:
            q = q.filter(Product.id == int(product_id_filter))
        if query:
            like = f"%{query}%"
            q = q.filter(
                Product.name.contains(query) |
                Product.brand.contains(query) |
                Product.description.contains(query)
            )
        products = q.limit(limit).all()
        return [{
            "product_id": p.id,
            "name": p.name,
            "category": p.category or "",
            "price": p.price or 0,
            "section": "keyword",
            "source_name": "",
            "intent_tags": ",".join(intent_filter or []),
            "document": self.build_document(p),
            "distance": 0.0,
        } for p in products]
