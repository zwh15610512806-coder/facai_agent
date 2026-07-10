"""Script vector store — semantic search over viral_scripts + reference_scripts."""
import logging
import os
import time
from sqlalchemy.orm import Session

from vector_store import VectorStoreError, get_chroma_store

logger = logging.getLogger("vector_store.scripts")


def _upsert_batch_size() -> int:
    try:
        value = int(os.getenv("VECTOR_UPSERT_BATCH_SIZE", "64"))
    except (TypeError, ValueError):
        value = 64
    return max(1, min(value, 256))


def _iter_slices(total: int, size: int):
    for start in range(0, total, size):
        yield start, min(start + size, total)


class ScriptVectorStore:
    """Manages script embeddings in ChromaDB 'scripts' collection."""

    def __init__(self):
        self.store = get_chroma_store()

    @property
    def collection(self):
        return self.store.get_script_collection()

    def _build_viral_doc(self, script) -> str:
        parts = []
        if script.title:
            parts.append(f"标题：{script.title}")
        if script.category:
            parts.append(f"品类：{script.category}")
        if script.video_type:
            parts.append(f"类型：{script.video_type}")
        if script.tags:
            parts.append(f"标签：{script.tags}")
        content = (script.script_content or "")[:2000]
        parts.append(f"脚本内容：{content}")
        return "\n".join(parts)

    def _build_reference_doc(self, script) -> str:
        parts = []
        if script.title:
            parts.append(f"标题：{script.title}")
        if script.video_type:
            parts.append(f"类型：{script.video_type}")
        if script.tags:
            parts.append(f"标签：{script.tags}")
        content = (script.script_content or "")[:2000]
        parts.append(f"脚本内容：{content}")
        return "\n".join(parts)

    def index_viral_script(self, script) -> str:
        doc_id = f"viral_{script.id}"
        doc_text = self._build_viral_doc(script)
        metadata = {
            "source": "viral",
            "db_id": script.id,
            "category": script.category or "",
            "video_type": script.video_type or "",
            "is_high_conversion": bool(script.is_high_conversion),
            "title": script.title or "",
        }
        try:
            self.collection.upsert(ids=[doc_id], documents=[doc_text], metadatas=[metadata])
            return doc_id
        except Exception as e:
            logger.warning(f"Failed to index viral script {script.id}: {e}")
            raise VectorStoreError(f"爆款脚本 {script.id} 向量写入失败: {e}") from e

    def index_reference_script(self, script) -> str:
        doc_id = f"ref_{script.id}"
        doc_text = self._build_reference_doc(script)
        metadata = {
            "source": "reference",
            "db_id": script.id,
            "category": "",
            "video_type": script.video_type or "",
            "is_high_conversion": bool(script.is_high_conversion),
            "title": script.title or "",
        }
        try:
            self.collection.upsert(ids=[doc_id], documents=[doc_text], metadatas=[metadata])
            return doc_id
        except Exception as e:
            logger.warning(f"Failed to index reference script {script.id}: {e}")
            raise VectorStoreError(f"参考脚本 {script.id} 向量写入失败: {e}") from e

    def delete_embedding(self, doc_id: str):
        try:
            self.collection.delete(ids=[doc_id])
        except Exception as e:
            logger.warning(f"Failed to delete script embedding {doc_id}: {e}")
            raise VectorStoreError(f"脚本向量 {doc_id} 删除失败: {e}") from e

    def search(self, query: str, limit: int = 10, video_type: str = None,
               high_conversion_only: bool = False) -> list:
        """Semantic search across scripts. Returns list of result dicts."""
        self.store.require_available()
        try:
            kwargs = {"query_texts": [query], "n_results": limit * 2}
            where_parts = []
            if video_type:
                where_parts.append({"video_type": video_type})
            if high_conversion_only:
                where_parts.append({"is_high_conversion": True})
            if len(where_parts) == 1:
                kwargs["where"] = where_parts[0]
            elif len(where_parts) > 1:
                kwargs["where"] = {"$and": where_parts}
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
                    "source": meta.get("source", ""),
                    "db_id": meta.get("db_id"),
                    "category": meta.get("category", ""),
                    "video_type": meta.get("video_type", ""),
                    "title": meta.get("title", ""),
                    "is_high_conversion": meta.get("is_high_conversion", False),
                    "distance": round(dist, 4),
                })
            out.sort(key=lambda x: x["distance"])
            return out[:limit]
        except VectorStoreError:
            raise
        except Exception as e:
            logger.warning(f"Semantic script search failed: {e}")
            raise VectorStoreError(f"脚本向量检索失败，请检查火山方舟 embedding 配置和索引维度: {e}") from e

    def find_similar_scripts(self, product_context: dict, video_type: str,
                              db: Session = None, limit: int = 5) -> list:
        """Vector search for scripts similar to product context."""
        self.store.require_available()

        query = f"{product_context.get('name','')} {product_context.get('category','')} {product_context.get('description','')}"
        selling_points = product_context.get("selling_points", [])
        if selling_points:
            sp_text = " ".join([f"[{sp.get('point_type','')}]{sp.get('content','')}" for sp in selling_points])
            query += " " + sp_text

        results = self.search(query, limit=limit, video_type=video_type)
        if results:
            return results

        return _keyword_find_similar(product_context, video_type, db, limit)

    def index_all_scripts(self, db: Session) -> int:
        """Batch index all viral_scripts + reference_scripts. Returns total indexed."""
        from models import ViralScript, ReferenceScript

        virals = db.query(ViralScript).all()
        refs = db.query(ReferenceScript).all()
        total = 0

        if virals:
            ids, docs, metas = [], [], []
            for s in virals:
                ids.append(f"viral_{s.id}")
                docs.append(self._build_viral_doc(s))
                metas.append({
                    "source": "viral", "db_id": s.id,
                    "category": s.category or "", "video_type": s.video_type or "",
                    "is_high_conversion": bool(s.is_high_conversion), "title": s.title or "",
                })
            try:
                self._upsert_batches(ids, docs, metas, label="viral scripts")
                total += len(ids)
                logger.info(f"Indexed {len(ids)} viral scripts")
            except Exception as e:
                logger.error(f"Batch viral script indexing failed: {e}")
                raise VectorStoreError(f"爆款脚本向量全量重建失败: {e}") from e

        if refs:
            ids, docs, metas = [], [], []
            for s in refs:
                ids.append(f"ref_{s.id}")
                docs.append(self._build_reference_doc(s))
                metas.append({
                    "source": "reference", "db_id": s.id,
                    "category": "", "video_type": s.video_type or "",
                    "is_high_conversion": bool(s.is_high_conversion), "title": s.title or "",
                })
                try:
                    s.embedding_id = f"ref_{s.id}"
                except Exception:
                    pass
            try:
                self._upsert_batches(ids, docs, metas, label="reference scripts")
                total += len(ids)
                logger.info(f"Indexed {len(ids)} reference scripts")
            except Exception as e:
                logger.error(f"Batch reference script indexing failed: {e}")
                raise VectorStoreError(f"参考脚本向量全量重建失败: {e}") from e

        return total

    def _upsert_batches(self, ids: list[str], documents: list[str], metadatas: list[dict], *, label: str):
        batch_size = _upsert_batch_size()
        for start, end in _iter_slices(len(ids), batch_size):
            self._upsert_with_retry(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
                label=f"{label} {start + 1}-{end}/{len(ids)}",
            )

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


def _keyword_find_similar(product_context: dict, video_type: str, db: Session, limit: int = 5) -> list:
    """Fallback: keyword-based similar script search (original logic)."""
    from models import ViralScript
    if db is None:
        return []

    name = product_context.get("name", "")
    category = product_context.get("category", "")

    keywords = _extract_keywords(name)
    scripts = []
    for kw in keywords:
        if category:
            matches = db.query(ViralScript).filter(
                ViralScript.video_type == video_type,
                ViralScript.category.contains(category)
            ).order_by(ViralScript.is_high_conversion.desc()).limit(limit * 2).all()
        else:
            matches = db.query(ViralScript).filter(
                ViralScript.video_type == video_type
            ).order_by(ViralScript.is_high_conversion.desc()).limit(limit * 2).all()
        scripts.extend(matches)
        if len(scripts) >= limit:
            break

    if len(scripts) < limit and category:
        extra = db.query(ViralScript).filter(
            ViralScript.video_type == video_type
        ).order_by(ViralScript.is_high_conversion.desc()).limit(limit - len(scripts)).all()
        scripts.extend(extra)

    seen = set()
    out = []
    for s in scripts[:limit]:
        if s.id not in seen:
            seen.add(s.id)
            out.append({
                "source": "viral", "db_id": s.id,
                "category": s.category or "", "video_type": s.video_type or "",
                "title": s.title or "", "is_high_conversion": bool(s.is_high_conversion),
                "distance": 0.0,
            })
    return out


def _extract_keywords(name: str) -> list:
    """Extract core keywords from product name for fallback search."""
    prefixes = ["防潮", "彩色", "水性", "油性", "高浓", "果蔬", "水状", "水溶", "油溶"]
    suffixes = ["膏", "粉", "片", "珠", "酱", "粉", "液", "笔", "盘", "囊"]
    kw = name
    for p in prefixes:
        if kw.startswith(p):
            kw = kw[len(p):]
            break
    if kw and kw[-1] in suffixes and len(kw) > 2:
        kw = kw[:-1]
    return [kw, name[:4], name[:3], name[:2]]
