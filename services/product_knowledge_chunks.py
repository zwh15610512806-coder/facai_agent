"""Structured product knowledge chunks for retrieval and indexing."""
from __future__ import annotations

from dataclasses import dataclass
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
        }
        for intent in INTENT_TAG_TERMS:
            metadata[f"intent_{intent}"] = intent in self.intent_tags
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
        source_name=default_source,
        priority=0,
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
        text = f"[{point_type}] {content}"
        chunks.append(ProductKnowledgeChunk(
            chunk_id=f"product_{product_id}:selling_point_{priority}_{index}",
            product_id=product_id,
            product_name=name,
            category=category,
            section="selling_point",
            text=text,
            intent_tags=infer_intent_tags(name, point_type, content, category=category),
            source_name=default_source,
            priority=priority,
        ))

    for section in detail.get("profile_sections") or []:
        section_id = _safe_chunk_key(section.get("id") or section.get("title") or "profile")
        section_title = str(section.get("title") or "产品资料")
        for index, item in enumerate(section.get("items") or [], start=1):
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            label = str(item.get("label") or section_title)
            text = f"{section_title} - {label}：{content}"
            chunks.append(ProductKnowledgeChunk(
                chunk_id=f"product_{product_id}:profile_{section_id}_{index}",
                product_id=product_id,
                product_name=name,
                category=category,
                section="source_excerpt",
                text=text,
                intent_tags=infer_intent_tags(name, section_title, label, content, category=category),
                source_name=default_source,
                priority=100 + index,
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
        ))

    seen: set[str] = set()
    deduped: list[ProductKnowledgeChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen or not chunk.text.strip():
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped
