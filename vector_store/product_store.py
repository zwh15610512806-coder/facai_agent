"""Product vector store — semantic search over products + selling points."""
import logging
from sqlalchemy.orm import Session

from vector_store import get_chroma_store

logger = logging.getLogger("vector_store.products")


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

    def index_product(self, product, db: Session = None) -> str:
        """Index a single product. Returns the ChromaDB document ID."""
        doc_id = f"product_{product.id}"
        doc_text = self.build_document(product)
        metadata = {
            "product_id": product.id,
            "name": product.name,
            "category": product.category or "",
            "price": product.price or 0,
        }
        try:
            self.collection.upsert(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[metadata],
            )
            return doc_id
        except Exception as e:
            logger.warning(f"Failed to index product {product.id}: {e}")
            return None

    def delete_embedding(self, product_id: int):
        try:
            self.collection.delete(ids=[f"product_{product_id}"])
        except Exception as e:
            logger.warning(f"Failed to delete embedding for product {product_id}: {e}")

    def search(self, query: str, limit: int = 10, category_filter: str = None) -> list:
        """Semantic search. Returns [{product_id, name, category, price, distance}, ...]."""
        if self.store._embedding_fn is None:
            return []
        try:
            kwargs = {"query_texts": [query], "n_results": limit * 2}
            if category_filter:
                kwargs["where"] = {"category": category_filter}
            results = self.collection.query(**kwargs)
            if not results or not results.get("ids") or not results["ids"][0]:
                return []
            out = []
            ids = results["ids"][0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            for i, doc_id in enumerate(ids):
                meta = metadatas[i] if i < len(metadatas) else {}
                dist = distances[i] if i < len(distances) else 1.0
                out.append({
                    "product_id": meta.get("product_id"),
                    "name": meta.get("name", ""),
                    "category": meta.get("category", ""),
                    "price": meta.get("price", 0),
                    "distance": round(dist, 4),
                })
            out.sort(key=lambda x: x["distance"])
            return out[:limit]
        except Exception as e:
            logger.warning(f"Semantic product search failed: {e}")
            return []

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
            ids.append(f"product_{p.id}")
            docs.append(self.build_document(p))
            metas.append({
                "product_id": p.id,
                "name": p.name,
                "category": p.category or "",
                "price": p.price or 0,
            })

        try:
            self.collection.upsert(ids=ids, documents=docs, metadatas=metas)
            logger.info(f"Indexed {len(ids)} products")
            return len(ids)
        except Exception as e:
            logger.error(f"Batch product indexing failed: {e}")
            return 0

    def hybrid_search(self, query: str, db: Session, limit: int = 10, category_filter: str = None) -> list:
        """Vector search + keyword fallback, deduplicated."""
        if not self.store.is_available:
            return self._keyword_search(query, db, limit, category_filter)

        results = self.search(query, limit=limit, category_filter=category_filter)
        if results:
            return results

        return self._keyword_search(query, db, limit, category_filter)

    def _keyword_search(self, query: str, db: Session, limit: int = 10, category_filter: str = None) -> list:
        from models import Product
        q = db.query(Product).filter(Product.status == "active")
        if category_filter:
            q = q.filter(Product.category == category_filter)
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
            "distance": 0.0,
        } for p in products]
