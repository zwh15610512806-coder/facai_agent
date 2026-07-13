"""Structured product knowledge chunks for retrieval and indexing."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from collections import Counter, defaultdict
from typing import Any, Iterable
import re

from services.product_detail import build_product_detail_payload


INTENT_TAG_TERMS: dict[str, tuple[str, ...]] = {
    "coloring": (
        "调色", "上色", "着色", "色素", "色粉", "红丝绒", "果蔬粉", "果蔬色素",
        "竹炭粉", "红曲粉", "浅柔色素", "天然色素", "水性色素", "油性色素",
        "水状色素", "胶状色素", "油溶色粉", "水溶色粉", "配色", "颜色还原",
    ),
    "cake_filling": (
        "蛋糕夹心", "夹心", "夹层", "内馅", "内心", "奶冻", "慕斯", "布蕾",
        "果泥", "芋泥", "栗子泥", "夹心珠", "夹心脆", "脆馅", "脆珠", "薄脆",
    ),
    "flavoring": ("调味", "风味", "口味", "果酱", "茶酱", "糖浆", "酱料", "香精"),
    "decoration": ("装饰", "造型", "点缀", "翻糖", "糖珠", "拉线", "手绘", "插件"),
    "packaging": ("配件", "打包", "刀叉", "盒装", "餐盘", "包装", "纸盘"),
}

CATEGORY_INTENT_TAGS = {
    "烘焙调色": "coloring",
    "烘焙夹心": "cake_filling",
    "烘焙调味": "flavoring",
    "烘焙装饰": "decoration",
    "烘焙配件": "packaging",
}


@dataclass(frozen=True)
class ProductKnowledgeChunk:
    chunk_id: str
    product_id: int
    product_name: str
    category: str
    section: str
    text: str
    intent_tags: tuple[str, ...]
    source_name: str = ""
    priority: int = 0
    evidence_type: str = "direct_fact"
    source_ref: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            normalized = re.sub(r"\s+", " ", self.text.strip())
            object.__setattr__(self, "content_hash", hashlib.sha256(normalized.encode("utf-8")).hexdigest())

    def document(self) -> str:
        bits = [
            f"产品：{self.product_name}",
            f"品类：{self.category or '未分类'}",
            f"资料类型：{self.section}",
            self.text,
        ]
        if self.source_name:
            bits.append(f"来源：{self.source_name}")
        return "\n".join(bit for bit in bits if bit)

    def metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "product_id": int(self.product_id),
            "name": self.product_name,
            "category": self.category or "",
            "section": self.section,
            "source_name": self.source_name or "",
            "priority": int(self.priority or 0),
            "intent_tags": ",".join(self.intent_tags),
            "evidence_type": self.evidence_type,
            "source_ref": self.source_ref or "",
            "content_hash": self.content_hash,
        }
        for intent in INTENT_TAG_TERMS:
            metadata[f"intent_{intent}"] = intent in self.intent_tags
        return metadata


def product_chunk_index_metadata(chunk: ProductKnowledgeChunk, price: Any = None) -> dict[str, Any]:
    """Build Chroma metadata with a hash covering every retrieval-relevant value."""
    metadata = chunk.metadata()
    metadata["price"] = price or 0
    hash_payload = {
        "document": chunk.document(),
        "metadata": {
            key: value
            for key, value in metadata.items()
            if key != "content_hash"
        },
    }
    encoded = json.dumps(
        hash_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    metadata["content_hash"] = hashlib.sha256(encoded).hexdigest()
    return metadata


def infer_intent_tags(*texts: str, category: str = "") -> tuple[str, ...]:
    combined = " ".join(str(text or "") for text in texts)
    tags: list[str] = []
    category_tag = CATEGORY_INTENT_TAGS.get(category or "")
    if category_tag:
        tags.append(category_tag)
    for intent, terms in INTENT_TAG_TERMS.items():
        if any(term in combined for term in terms):
            tags.append(intent)
    return tuple(dict.fromkeys(tags))


def _safe_chunk_key(text: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", str(text or "").strip())
    return key[:48] or "chunk"


def _detail_sources(detail: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    if detail.get("manual_source"):
        sources.append(str(detail["manual_source"]))
    sources.extend(str(source) for source in (detail.get("knowledge_sources") or []) if source)
    return list(dict.fromkeys(sources))


def _selling_points_from_product(product: Any) -> Iterable[Any]:
    points = getattr(product, "selling_points", None) or []
    return sorted(points, key=lambda item: getattr(item, "priority", 0) or 0)


ASSOCIATION_LABELS = {"经营场景", "门店方案", "解决方案", "推荐搭配"}


def _evidence_type(label: str, item: dict[str, Any]) -> str:
    if item.get("generated"):
        return "generated"
    if item.get("evidence_type") in {"direct_fact", "association"}:
        return str(item["evidence_type"])
    return "association" if label in ASSOCIATION_LABELS else "direct_fact"


def _source_ref(source_name: str, section: str, index: int | str) -> str:
    return f"{source_name or '结构化产品资料'}#{section}:{index}"


def build_product_knowledge_chunks(product: Any, detail: dict[str, Any] | None = None) -> list[ProductKnowledgeChunk]:
    """Build searchable chunks from one product and its enriched detail payload."""
    if detail is None:
        try:
            detail = build_product_detail_payload(product)
        except Exception:
            detail = {
                "id": getattr(product, "id"),
                "name": getattr(product, "name", ""),
                "category": getattr(product, "category", ""),
                "price": getattr(product, "price", None),
                "brand": getattr(product, "brand", "法采"),
                "description": getattr(product, "description", ""),
                "selling_points": [
                    {
                        "point_type": getattr(point, "point_type", "卖点"),
                        "content": getattr(point, "content", ""),
                        "priority": getattr(point, "priority", index + 1),
                    }
                    for index, point in enumerate(_selling_points_from_product(product))
                ],
                "sku_prices": [],
                "profile_sections": [],
                "manual_source": "结构化产品资料",
                "knowledge_sources": [],
            }
    product_id = int(detail.get("id") or getattr(product, "id"))
    name = str(detail.get("name") or getattr(product, "name", "") or "")
    category = str(detail.get("category") or getattr(product, "category", "") or "")
    brand = str(detail.get("brand") or getattr(product, "brand", "") or "法采")
    description = str(detail.get("description") or getattr(product, "description", "") or "")
    sources = _detail_sources(detail)
    default_source = sources[0] if sources else "结构化产品资料"
    chunks: list[ProductKnowledgeChunk] = []

    info_text = "\n".join(
        bit for bit in [
            f"产品名称：{name}",
            f"品类：{category}",
            f"品牌：{brand}",
            f"描述：{description}" if description else "",
        ]
        if bit
    )
    chunks.append(ProductKnowledgeChunk(
        chunk_id=f"product_{product_id}:product_info",
        product_id=product_id,
        product_name=name,
        category=category,
        section="product_info",
        text=info_text,
        intent_tags=infer_intent_tags(name, category, description, category=category),
        source_name="结构化产品资料",
        priority=0,
        evidence_type="direct_fact",
        source_ref=f"products/{product_id}",
    ))

    detail_points = detail.get("selling_points") or []
    if detail_points:
        point_iterable = detail_points
    else:
        point_iterable = [
            {
                "point_type": getattr(point, "point_type", "卖点"),
                "content": getattr(point, "content", ""),
                "priority": getattr(point, "priority", index + 1),
            }
            for index, point in enumerate(_selling_points_from_product(product))
        ]
    for index, point in enumerate(point_iterable, start=1):
        content = str(point.get("content") or "").strip()
        if not content:
            continue
        point_type = str(point.get("point_type") or "卖点")
        priority = int(point.get("priority") or index)
        evidence_type = _evidence_type(point_type, point)
        if evidence_type == "generated":
            continue
        source_name = str(point.get("source") or default_source)
        text = f"[{point_type}] {content}"
        chunks.append(ProductKnowledgeChunk(
            chunk_id=f"product_{product_id}:selling_point_{priority}_{index}",
            product_id=product_id,
            product_name=name,
            category=category,
            section="selling_point",
            text=text,
            intent_tags=infer_intent_tags(name, point_type, content, category=category),
            source_name=source_name,
            priority=priority,
            evidence_type=evidence_type,
            source_ref=_source_ref(source_name, "selling_point", priority),
        ))

    for section in detail.get("profile_sections") or []:
        section_id = _safe_chunk_key(section.get("id") or section.get("title") or "profile")
        section_title = str(section.get("title") or "产品资料")
        for index, item in enumerate(section.get("items") or [], start=1):
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            label = str(item.get("label") or section_title)
            evidence_type = _evidence_type(label, item)
            if evidence_type == "generated" or label == "资料来源":
                continue
            source_name = str(item.get("source") or default_source)
            text = f"{section_title} - {label}：{content}"
            chunks.append(ProductKnowledgeChunk(
                chunk_id=f"product_{product_id}:profile_{section_id}_{index}",
                product_id=product_id,
                product_name=name,
                category=category,
                section="source_excerpt",
                text=text,
                intent_tags=infer_intent_tags(name, section_title, label, content, category=category),
                source_name=source_name,
                priority=100 + index,
                evidence_type=evidence_type,
                source_ref=_source_ref(source_name, section_id, index),
            ))
        for index, sku in enumerate(section.get("sku_prices") or [], start=1):
            name_bits = [sku.get("name"), sku.get("price"), sku.get("daily_price")]
            text = "；".join(str(bit) for bit in name_bits if bit)
            if not text:
                continue
            chunks.append(ProductKnowledgeChunk(
                chunk_id=f"product_{product_id}:sku_{section_id}_{index}",
                product_id=product_id,
                product_name=name,
                category=category,
                section="sku_price",
                text=f"{section_title} SKU/价格：{text}",
                intent_tags=infer_intent_tags(name, section_title, text, category=category),
                source_name=default_source,
                priority=200 + index,
                evidence_type="direct_fact",
                source_ref=_source_ref(default_source, f"sku_{section_id}", index),
            ))

    for index, sku in enumerate(detail.get("sku_prices") or [], start=1):
        parts = [
            sku.get("product"),
            sku.get("spec"),
            f"售价 {sku.get('price')}" if sku.get("price") is not None else "",
            f"日常价 {sku.get('daily_price')}" if sku.get("daily_price") is not None else "",
        ]
        text = "；".join(str(part) for part in parts if part)
        if not text:
            continue
        chunks.append(ProductKnowledgeChunk(
            chunk_id=f"product_{product_id}:sku_price_{index}",
            product_id=product_id,
            product_name=name,
            category=category,
            section="sku_price",
            text=f"SKU/价格：{text}",
            intent_tags=infer_intent_tags(name, text, category=category),
            source_name=default_source,
            priority=300 + index,
            evidence_type="direct_fact",
            source_ref=_source_ref(default_source, "sku_price", index),
        ))

    seen: set[str] = set()
    deduped: list[ProductKnowledgeChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen or not chunk.text.strip():
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def product_knowledge_quality_report(products: Iterable[Any]) -> dict[str, Any]:
    product_list = list(products)
    names = [
        str(getattr(product, "name", "") or "").strip()
        for product in product_list
        if len(str(getattr(product, "name", "") or "").strip()) >= 3
    ]
    evidence_counts: Counter[str] = Counter()
    hash_products: dict[str, set[int]] = defaultdict(set)
    missing_source_chunks = 0
    generated_chunks = 0
    cross_product_mention_chunks = 0
    chunk_count = 0
    for product in product_list:
        product_id = int(getattr(product, "id"))
        product_name = str(getattr(product, "name", "") or "")
        for chunk in build_product_knowledge_chunks(product):
            chunk_count += 1
            evidence_counts[chunk.evidence_type] += 1
            hash_products[chunk.content_hash].add(product_id)
            if not chunk.source_name or not chunk.source_ref:
                missing_source_chunks += 1
            if chunk.evidence_type == "generated":
                generated_chunks += 1
            if any(name != product_name and name in chunk.text for name in names):
                cross_product_mention_chunks += 1
    duplicate_groups = sum(
        1 for product_ids in hash_products.values()
        if len(product_ids) > 1
    )
    return {
        "product_count": len(product_list),
        "chunk_count": chunk_count,
        "evidence_counts": dict(evidence_counts),
        "duplicate_cross_product_groups": duplicate_groups,
        "cross_product_mention_chunks": cross_product_mention_chunks,
        "missing_source_chunks": missing_source_chunks,
        "generated_chunks": generated_chunks,
    }


def validate_product_knowledge_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    """Reject index activation when evidence quality crosses safety thresholds."""
    chunk_count = int(report.get("chunk_count") or 0)
    errors: list[str] = []
    if chunk_count <= 0:
        errors.append("知识块为空")
    if int(report.get("generated_chunks") or 0) > 0:
        errors.append("生成内容混入索引")
    if int(report.get("missing_source_chunks") or 0) > 0:
        errors.append("知识块缺少来源")
    try:
        duplicate_limit = float(os.getenv("PRODUCT_RAG_MAX_DUPLICATE_RATIO", "0.25"))
        cross_mention_limit = float(os.getenv("PRODUCT_RAG_MAX_CROSS_MENTION_RATIO", "0.35"))
    except (TypeError, ValueError):
        duplicate_limit, cross_mention_limit = 0.25, 0.35
    if chunk_count:
        duplicate_ratio = int(report.get("duplicate_cross_product_groups") or 0) / chunk_count
        cross_mention_ratio = int(report.get("cross_product_mention_chunks") or 0) / chunk_count
        if duplicate_ratio > duplicate_limit:
            errors.append(f"跨产品重复比例过高 {duplicate_ratio:.1%}")
        if cross_mention_ratio > cross_mention_limit:
            errors.append(f"跨产品提及比例过高 {cross_mention_ratio:.1%}")
    if errors:
        raise ValueError("；".join(errors))
    return report
