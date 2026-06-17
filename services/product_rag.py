"""RAG-style product question answering helpers."""
from __future__ import annotations

from typing import Any
import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import Product, SellingPoint
from services.ai_service import ai_service
from services.product_detail import build_product_detail_payload


PRODUCT_CHAT_SYSTEM_PROMPT = """你是法采产品资料助手。
只根据给定的产品资料回答，不编造资料外的信息。
回答要简洁、可执行，优先说明产品名、适用场景、核心卖点、SKU/价格/活动机制。
如果资料不足，直接说明没有查到，并列出已检索到的相关资料。"""


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _query_terms(query: str) -> list[str]:
    query = _clean_query(query)
    terms = [query] if query else []
    terms.extend(re.findall(r"[A-Za-z0-9.]+|[\u4e00-\u9fff]{2,}", query))
    for chinese_run in re.findall(r"[\u4e00-\u9fff]{3,}", query):
        terms.extend(chinese_run[index:index + 2] for index in range(0, len(chinese_run) - 1))
    stop_words = {"这个产品", "哪些", "什么", "怎么", "适合", "有没有", "产品", "信息"}
    return [
        term for term in _unique(terms)
        if len(term) > 1 and term not in stop_words
    ]


def _text_score(text: str, terms: list[str]) -> int:
    text = str(text or "")
    score = 0
    for term in terms:
        if term and term in text:
            score += len(term)
    return score


def _wants_price(query: str) -> bool:
    return any(word in query for word in ("价格", "售价", "活动", "优惠", "SKU", "sku", "日常价", "机制", "多少钱"))


def _format_price(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _format_sku_line(sku: dict[str, Any]) -> str:
    name = " · ".join([part for part in [sku.get("product"), sku.get("spec")] if part]) or "默认规格"
    price_bits = []
    if sku.get("price") is not None:
        price_bits.append(f"售价 ¥{_format_price(sku.get('price'))}")
    if sku.get("daily_price") is not None:
        price_bits.append(f"日常价 ¥{_format_price(sku.get('daily_price'))}")
    activities = []
    for activity in sku.get("activity_prices", [])[:3]:
        activity_price = activity.get("final_price") or activity.get("activity_price") or activity.get("tag_price")
        if activity_price is None:
            continue
        mechanism = activity.get("mechanism") or "活动价"
        meta = []
        if activity.get("discount"):
            meta.append(activity["discount"])
        if activity.get("coupon") and activity.get("coupon") != "0":
            meta.append(f"券{activity['coupon']}")
        activities.append(f"{mechanism} ¥{_format_price(activity_price)}" + (f"（{' / '.join(meta)}）" if meta else ""))
    if activities:
        price_bits.append("；".join(activities))
    return f"{name}：" + "；".join(price_bits)


def _detail_sources(detail: dict[str, Any]) -> list[str]:
    sources = []
    if detail.get("manual_source"):
        sources.append(detail["manual_source"])
    sources.extend(detail.get("knowledge_sources") or [])
    return _unique(sources)


def _detail_to_result(detail: dict[str, Any], query: str, *, scoped: bool = False) -> dict[str, Any]:
    terms = _query_terms(query)
    selling_points = detail.get("selling_points") or []
    scored_points = []
    for point in selling_points:
        text = f"{point.get('point_type', '')} {point.get('content', '')}"
        scored_points.append((_text_score(text, terms), point))
    scored_points.sort(key=lambda item: item[0], reverse=True)
    matched_points = [point for score, point in scored_points if score > 0]
    if not matched_points:
        matched_points = [point for _, point in scored_points[: (6 if scoped else 3)]]

    skus = detail.get("sku_prices") or []
    sku_rows = skus[:6 if _wants_price(query) or scoped else 3]
    sku_matches = []
    for sku in sku_rows:
        sku_matches.append({
            "product": sku.get("product", ""),
            "spec": sku.get("spec", ""),
            "price": sku.get("price"),
            "daily_price": sku.get("daily_price"),
            "activity_prices": (sku.get("activity_prices") or [])[:4],
            "line": _format_sku_line(sku),
        })

    return {
        "product_id": detail.get("id"),
        "name": detail.get("name", ""),
        "category": detail.get("category", ""),
        "price": detail.get("price"),
        "original_price": detail.get("original_price"),
        "description": detail.get("description") or "",
        "sources": _detail_sources(detail),
        "profile_sections": detail.get("profile_sections") or [],
        "selling_points": [
            {
                "point_type": point.get("point_type", "卖点"),
                "content": point.get("content", ""),
                "priority": point.get("priority"),
            }
            for point in matched_points[: (6 if scoped else 4)]
            if point.get("content")
        ],
        "sku_prices": sku_matches,
    }


def _keyword_products(query: str, db: Session, limit: int, category: str | None = None) -> list[Product]:
    q = db.query(Product).filter(Product.status == "active")
    if category:
        q = q.filter(Product.category == category)
    terms = _query_terms(query)
    if terms:
        conditions = []
        for term in terms[:8]:
            like = f"%{term}%"
            conditions.extend([
                Product.name.like(like),
                Product.category.like(like),
                Product.brand.like(like),
                Product.description.like(like),
                Product.selling_points.any(SellingPoint.content.like(like)),
                Product.selling_points.any(SellingPoint.point_type.like(like)),
            ])
        q = q.filter(or_(*conditions))
    return q.order_by(Product.created_at.desc()).limit(limit).all()


def _candidate_products(query: str, db: Session, limit: int, category: str | None = None) -> list[Product]:
    product_ids: list[int] = []
    try:
        from vector_store.product_store import ProductVectorStore

        hits = ProductVectorStore().hybrid_search(
            query=query,
            db=db,
            limit=limit,
            category_filter=category,
        )
        product_ids = [int(hit["product_id"]) for hit in hits if hit.get("product_id")]
    except Exception:
        product_ids = []

    ordered: list[Product] = []
    if product_ids:
        products = db.query(Product).filter(Product.id.in_(product_ids), Product.status == "active").all()
        by_id = {product.id: product for product in products}
        ordered = [by_id[product_id] for product_id in product_ids if product_id in by_id]

    keyword_matches = _keyword_products(query, db, limit, category)
    merged: list[Product] = []
    seen: set[int] = set()
    for product in [*ordered, *keyword_matches]:
        if product.id in seen:
            continue
        seen.add(product.id)
        merged.append(product)
    return merged[:limit]


def _context_for_ai(results: list[dict[str, Any]]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        lines = [
            f"{index}. 产品：{result['name']}",
            f"品类：{result.get('category') or '未分类'}",
        ]
        if result.get("price") is not None:
            lines.append(f"售价：¥{_format_price(result.get('price'))}")
        if result.get("profile_sections"):
            lines.append("五维资料：")
            for section in result["profile_sections"]:
                section_title = section.get("title") or "产品资料"
                lines.append(f"【{section_title}】")
                for item in (section.get("items") or [])[:5]:
                    if item.get("content"):
                        lines.append(f"- {item.get('label', '资料')}：{item.get('content')}")
                if section.get("sku_prices"):
                    for sku in (section.get("sku_prices") or [])[:5]:
                        lines.append(f"- {_format_profile_sku_line(sku)}")
        if result.get("selling_points"):
            lines.append("卖点：")
            for point in result["selling_points"][:5]:
                lines.append(f"- [{point.get('point_type', '卖点')}] {point.get('content', '')}")
        if result.get("sku_prices"):
            lines.append("SKU/价格：")
            for sku in result["sku_prices"][:5]:
                lines.append(f"- {sku.get('line', '')}")
        if result.get("sources"):
            lines.append(f"来源：{'、'.join(result['sources'][:5])}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)[:9000]


def _format_profile_sku_line(sku: dict[str, Any]) -> str:
    name = sku.get("name") or "默认规格"
    bits = []
    if sku.get("price"):
        bits.append(f"售价 ¥{sku['price']}")
    if sku.get("daily_price"):
        bits.append(f"日常价 ¥{sku['daily_price']}")
    for activity in (sku.get("activity_prices") or [])[:3]:
        price = activity.get("price")
        if not price:
            continue
        meta = f"（{activity.get('meta')}）" if activity.get("meta") else ""
        bits.append(f"{activity.get('mechanism', '活动价')} ¥{price}{meta}")
    return f"{name}：" + "；".join(bits)


def _fallback_answer(query: str, results: list[dict[str, Any]], scope: str) -> str:
    if not results:
        return f"没有在产品资料里检索到与“{query}”直接相关的内容。"

    if scope == "product":
        result = results[0]
        lines = [f"已在「{result['name']}」资料中找到以下信息："]
    else:
        lines = [f"已检索到 {len(results)} 个相关产品："]

    for result in results[:5]:
        if scope != "product":
            price = f" ¥{_format_price(result.get('price'))}" if result.get("price") is not None else ""
            lines.append(f"- {result['name']}（{result.get('category') or '未分类'}{price}）")
        for point in result.get("selling_points", [])[:2]:
            lines.append(f"  · [{point.get('point_type', '卖点')}] {point.get('content', '')}")
        for sku in result.get("sku_prices", [])[:2]:
            if sku.get("line"):
                lines.append(f"  · {sku['line']}")
    return "\n".join(lines)


async def _summarize_answer(query: str, results: list[dict[str, Any]], scope_label: str) -> tuple[str, str]:
    if not results:
        return _fallback_answer(query, results, scope_label), "fallback"

    context = _context_for_ai(results)
    messages = [
        {"role": "system", "content": PRODUCT_CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"用户问题：{query}\n检索范围：{scope_label}\n\n产品资料：\n{context}",
        },
    ]
    answer = await ai_service.chat(messages, temperature=0.2, allow_fallback=False)
    answer = (answer or "").strip()
    if answer:
        return answer, "ai"
    return _fallback_answer(query, results, scope_label), "fallback"


async def answer_global_product_question(
    query: str,
    db: Session,
    *,
    category: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    clean = _clean_query(query)
    products = _candidate_products(clean, db, max(1, min(limit, 10)), category)
    results = [
        _detail_to_result(build_product_detail_payload(product), clean)
        for product in products
    ]
    sources = _unique([source for result in results for source in result.get("sources", [])])
    answer, mode = await _summarize_answer(clean, results, "global")
    return {
        "answer": answer,
        "mode": mode,
        "scope": "global",
        "results": results,
        "sources": sources,
    }


async def answer_product_question(
    product_id: int,
    query: str,
    db: Session,
) -> dict[str, Any]:
    product = db.query(Product).filter(Product.id == product_id, Product.status == "active").first()
    if not product:
        raise ValueError("产品不存在")
    clean = _clean_query(query)
    detail = build_product_detail_payload(product)
    result = _detail_to_result(detail, clean, scoped=True)
    sources = result.get("sources", [])
    answer, mode = await _summarize_answer(clean, [result], "product")
    return {
        "answer": answer,
        "mode": mode,
        "scope": "product",
        "product_id": product_id,
        "results": [result],
        "sources": sources,
    }
