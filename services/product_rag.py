"""RAG-style product question answering helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging
import re
import time

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import Product, ProductRagQueryLog, SellingPoint
from services.ai_service import ai_service
from services.product_knowledge_chunks import build_product_knowledge_chunks
from services.product_detail import build_product_detail_payload


logger = logging.getLogger("services.product_rag")


PRODUCT_CHAT_SYSTEM_PROMPT = """你是法采产品资料助手。
只根据给定的产品资料回答，不编造资料外的信息。
回答要简洁、可执行，优先说明产品名、适用场景、核心卖点、SKU/价格/活动机制。
必须先用“简要回答：”给一句概况，再用“具体信息：”列产品依据，不要单独列“来源：”段落。
如果用户问“有哪些/推荐哪些”这类宽泛选品问题，要尽量覆盖检索到的相关产品，不只挑少数 Top 推荐。
如果资料不足，直接说明没有查到；不要把来源文件列表当作答案。"""


BROAD_QUERY_WORDS = ("有哪些", "哪些", "推荐", "适合", "有什么", "列出", "找")
PRODUCT_QUERY_WORDS = ("产品", "款", "品", "材料", "原料")
FILLING_SCENE_TERMS = ("蛋糕夹心", "夹心", "夹层", "内馅", "内心", "奶冻", "慕斯", "布蕾")
FILLING_PRODUCT_TERMS = (
    "夹心", "夹层", "内馅", "内心", "奶冻", "慕斯", "布蕾", "果泥", "芋泥",
    "栗子泥", "夹心珠", "夹心脆", "脆馅", "脆珠", "薄脆", "成品奶冻",
)
PRIMARY_FILLING_NAME_TERMS = (
    "夹心", "奶冻", "慕斯", "布蕾", "果泥", "芋泥", "栗子泥", "脆馅", "脆珠", "薄脆",
)
COLORING_NAME_TERMS = (
    "色素", "色粉", "红丝绒", "果蔬粉", "果蔬色素", "竹炭粉", "红曲粉", "浅柔色素",
    "天然色素", "水性色素", "油性色素", "水状色素", "胶状色素", "油溶色粉", "水溶色粉",
)


@dataclass(frozen=True)
class ProductIntentRule:
    intent: str
    category: str
    query_terms: tuple[str, ...]
    name_terms: tuple[str, ...] = ()
    allow_uncategorized_name_match: bool = False


PRODUCT_INTENT_RULES = (
    ProductIntentRule(
        intent="coloring",
        category="烘焙调色",
        query_terms=("调色", "上色", "色素", "色粉", "红丝绒", "颜色还原", "配色"),
        name_terms=COLORING_NAME_TERMS,
        allow_uncategorized_name_match=True,
    ),
    ProductIntentRule(
        intent="cake_filling",
        category="烘焙夹心",
        query_terms=FILLING_SCENE_TERMS,
        name_terms=PRIMARY_FILLING_NAME_TERMS,
        allow_uncategorized_name_match=True,
    ),
    ProductIntentRule(
        intent="flavoring",
        category="烘焙调味",
        query_terms=("调味", "风味", "口味", "果酱", "茶酱", "糖浆", "酱料", "香精"),
    ),
    ProductIntentRule(
        intent="decoration",
        category="烘焙装饰",
        query_terms=("装饰", "造型", "点缀", "翻糖", "糖珠", "拉线", "手绘", "插件"),
    ),
    ProductIntentRule(
        intent="packaging",
        category="烘焙配件",
        query_terms=("配件", "打包", "刀叉", "盒装", "餐盘", "包装", "纸盘"),
    ),
)


@dataclass(frozen=True)
class ProductQueryPolicy:
    intent: str
    broad: bool
    strict_primary_filter: bool = False
    intents: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


@dataclass
class ProductRetrievalSelection:
    products: list[Product]
    policy: ProductQueryPolicy
    hit_chunks: list[dict[str, Any]]
    excluded_product_ids: list[int]
    retrieval_mode: str
    degraded_reason: str = ""


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


def _is_filling_query(query: str) -> bool:
    return any(term in query for term in FILLING_SCENE_TERMS)


def _matched_intent_rules(query: str) -> tuple[ProductIntentRule, ...]:
    clean = _clean_query(query)
    return tuple(
        rule for rule in PRODUCT_INTENT_RULES
        if any(term in clean for term in rule.query_terms)
    )


def _is_broad_product_query(query: str) -> bool:
    clean = _clean_query(query)
    if not clean:
        return False
    has_broad_word = any(word in clean for word in BROAD_QUERY_WORDS)
    has_product_word = any(word in clean for word in PRODUCT_QUERY_WORDS)
    has_known_intent = bool(_matched_intent_rules(clean))
    return (
        has_broad_word and (has_product_word or has_known_intent)
    ) or (
        has_product_word and has_known_intent
    )


def _product_query_policy(query: str) -> ProductQueryPolicy:
    clean = _clean_query(query)
    broad = _is_broad_product_query(clean)
    rules = _matched_intent_rules(clean)
    if rules:
        intents = tuple(rule.intent for rule in rules)
        categories = tuple(rule.category for rule in rules)
        intent = intents[0] if len(intents) == 1 else "multi"
        return ProductQueryPolicy(
            intent=intent,
            broad=broad,
            strict_primary_filter=True,
            intents=intents,
            categories=categories,
        )
    if broad:
        return ProductQueryPolicy(intent="broad_product", broad=True)
    return ProductQueryPolicy(intent="default", broad=False)


def _product_search_text(product: Product) -> str:
    point_text = " ".join(
        f"{point.point_type or ''} {point.content or ''}"
        for point in (product.selling_points or [])
    )
    return " ".join([
        product.name or "",
        product.category or "",
        product.brand or "",
        product.description or "",
        point_text,
    ])


def _is_primary_filling_product(product: Product) -> bool:
    if (product.category or "") == "烘焙夹心":
        return True
    name = product.name or ""
    return any(term in name for term in PRIMARY_FILLING_NAME_TERMS)


def _is_primary_product_for_policy(product: Product, policy: ProductQueryPolicy) -> bool:
    if not policy.strict_primary_filter:
        return True
    category = product.category or ""
    name = product.name or ""
    if category in policy.categories:
        return True
    if category:
        return False
    rules = [rule for rule in PRODUCT_INTENT_RULES if rule.intent in policy.intents]
    return any(
        rule.allow_uncategorized_name_match
        and any(term in name for term in rule.name_terms)
        for rule in rules
    )


def _scenario_relevance_score(product: Product, query: str, policy: ProductQueryPolicy | None = None) -> int:
    policy = policy or _product_query_policy(query)
    text = _product_search_text(product)
    terms = _query_terms(query)
    score = _text_score(text, terms)
    if policy.strict_primary_filter:
        if product.category in policy.categories:
            score += 80
        if product.name:
            rules = [rule for rule in PRODUCT_INTENT_RULES if rule.intent in policy.intents]
            for rule in rules:
                if any(term in product.name for term in rule.name_terms):
                    score += 30
                if any(term in text for term in rule.query_terms):
                    score += 12
    if "cake_filling" in policy.intents:
        if "蛋糕夹心" in text:
            score += 35
        if "夹心" in text:
            score += 20
        for term in FILLING_PRODUCT_TERMS:
            if term in (product.name or ""):
                score += 25
            elif term in text:
                score += 10
    return score


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


def _detail_to_result(
    detail: dict[str, Any],
    query: str,
    *,
    scoped: bool = False,
    hit_chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
        "retrieval_chunks": hit_chunks or [],
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


def _vector_category_filter(policy: ProductQueryPolicy, category: str | None) -> str | None:
    if category:
        return category
    if policy.strict_primary_filter and len(policy.categories) == 1:
        return policy.categories[0]
    return None


def _hit_trace(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": hit.get("chunk_id") or "",
        "product_id": hit.get("product_id"),
        "name": hit.get("name", ""),
        "category": hit.get("category", ""),
        "section": hit.get("section", ""),
        "source_name": hit.get("source_name", ""),
        "document": hit.get("document", ""),
        "distance": hit.get("distance"),
    }


def _unique_ints(values: list[Any]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number in seen:
            continue
        seen.add(number)
        out.append(number)
    return out


def _retrieve_product_selection(query: str, db: Session, limit: int, category: str | None = None) -> ProductRetrievalSelection:
    policy = _product_query_policy(query)
    pool_limit = max(limit, 30) if (policy.broad or policy.strict_primary_filter) else max(limit, 12)
    product_ids: list[int] = []
    vector_hits: list[dict[str, Any]] = []
    degraded_reason = ""
    try:
        from vector_store.product_store import ProductVectorStore

        hits = ProductVectorStore().hybrid_search(
            query=query,
            db=db,
            limit=max(pool_limit, pool_limit * 2),
            category_filter=_vector_category_filter(policy, category),
            intent_filter=policy.intents if policy.strict_primary_filter else None,
        )
        vector_hits = [_hit_trace(hit) for hit in hits]
        product_ids = _unique_ints([hit.get("product_id") for hit in hits])
    except Exception as exc:
        degraded_reason = str(exc)
        logger.warning("Product vector retrieval degraded to keyword/category search: %s", exc)
        product_ids = []

    ordered: list[Product] = []
    if product_ids:
        products = db.query(Product).filter(Product.id.in_(product_ids), Product.status == "active").all()
        by_id = {product.id: product for product in products}
        ordered = [by_id[product_id] for product_id in product_ids if product_id in by_id]

    keyword_matches = _keyword_products(query, db, pool_limit, category)
    category_matches: list[Product] = []
    if policy.categories:
        category_values = [
            category_value
            for category_value in policy.categories
            if not category or category == category_value
        ]
        if category_values:
            category_matches = (
                db.query(Product)
                .filter(Product.status == "active", Product.category.in_(category_values))
                .limit(max(pool_limit, pool_limit * len(category_values)))
                .all()
            )
    merged: list[Product] = []
    seen: set[int] = set()
    for product in [*ordered, *keyword_matches, *category_matches]:
        if product.id in seen:
            continue
        seen.add(product.id)
        merged.append(product)
    before_filter_ids = [product.id for product in merged]
    if policy.strict_primary_filter:
        merged = [product for product in merged if _is_primary_product_for_policy(product, policy)]
    if policy.broad or policy.strict_primary_filter:
        scored = [(_scenario_relevance_score(product, query, policy), index, product) for index, product in enumerate(merged)]
        minimum_score = 20 if policy.strict_primary_filter else 1
        relevant = [item for item in scored if item[0] >= minimum_score]
        scored = relevant or scored
        scored.sort(key=lambda item: (-item[0], item[1]))
        merged = [product for _, _, product in scored]
    selected = merged[:limit]
    selected_ids = {product.id for product in selected}
    excluded_product_ids = [
        product_id for product_id in before_filter_ids
        if product_id not in selected_ids
    ]
    modes = []
    if vector_hits:
        modes.append("vector")
    modes.append("keyword")
    if policy.categories:
        modes.append("category")
    if degraded_reason:
        modes.append("degraded")
    return ProductRetrievalSelection(
        products=selected,
        policy=policy,
        hit_chunks=vector_hits,
        excluded_product_ids=_unique_ints(excluded_product_ids),
        retrieval_mode="+".join(dict.fromkeys(modes)),
        degraded_reason=degraded_reason,
    )


def _candidate_products(query: str, db: Session, limit: int, category: str | None = None) -> list[Product]:
    return _retrieve_product_selection(query, db, limit, category).products


def _context_for_ai(results: list[dict[str, Any]]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        lines = [
            f"{index}. 产品：{result['name']}",
            f"品类：{result.get('category') or '未分类'}",
        ]
        if result.get("price") is not None:
            lines.append(f"售价：¥{_format_price(result.get('price'))}")
        if result.get("retrieval_chunks"):
            lines.append("命中资料块：")
            for chunk in result["retrieval_chunks"][:6]:
                parts = [
                    chunk.get("section", ""),
                    chunk.get("source_name", ""),
                    chunk.get("document", ""),
                ]
                text = "；".join(str(part) for part in parts if part)
                if text:
                    lines.append(f"- {text[:500]}")
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


def _reference_product(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": result.get("product_id"),
        "name": result.get("name", ""),
        "category": result.get("category", ""),
        "price": result.get("price"),
    }


def find_product_context_for_inspiration(query: str, db: Session, *, limit: int = 6, force: bool = False) -> dict[str, Any]:
    """Return product context for creative chat without generating a product answer."""
    clean = _clean_query(query)
    if not clean:
        return {"used": False, "context": "", "results": [], "products": []}

    requested_limit = max(1, min(limit, 6))
    policy = _product_query_policy(clean)
    candidates = _candidate_products(clean, db, max(requested_limit, 12))
    if not policy.broad and not force:
        candidates = [
            product for product in candidates
            if _scenario_relevance_score(product, clean, policy) > 0
        ]
    candidates = candidates[:requested_limit]
    results = [
        _detail_to_result(build_product_detail_payload(product), clean)
        for product in candidates
    ]
    products = [_reference_product(result) for result in results]
    return {
        "used": bool(results),
        "context": _context_for_ai(results) if results else "",
        "results": results,
        "products": products,
    }


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


def _result_reason(result: dict[str, Any]) -> str:
    if result.get("selling_points"):
        return result["selling_points"][0].get("content", "")
    if result.get("description"):
        return result["description"]
    if result.get("sku_prices"):
        return result["sku_prices"][0].get("line", "")
    return ""


def _result_source_label(result: dict[str, Any]) -> str:
    if result.get("sources"):
        return "、".join(result["sources"][:5])
    labels = ["结构化产品资料", "卖点资料"]
    if result.get("sku_prices"):
        labels.append("SKU/价格资料")
    return "、".join(labels)


def _fallback_answer(query: str, results: list[dict[str, Any]], scope: str) -> str:
    if not results:
        return "\n".join([
            f"简要回答：没有在产品资料里检索到与“{query}”直接相关的内容。",
            "",
            "具体信息：暂无可引用的匹配产品。",
        ])

    if scope == "product":
        result = results[0]
        lines = [
            f"简要回答：根据「{result['name']}」的产品资料，可以围绕它的适用场景、卖点和价格来回答。",
            "",
            "具体信息：",
        ]
        points = result.get("selling_points", [])[:4]
        if points:
            for point in points:
                lines.append(f"- {point.get('content', '')}")
        elif result.get("description"):
            lines.append(f"- {result['description']}")
        if result.get("price") is not None:
            lines.append(f"- 参考售价：¥{_format_price(result.get('price'))}")
        for sku in result.get("sku_prices", [])[:3]:
            if sku.get("line"):
                lines.append(f"- {sku['line']}")
        return "\n".join(line for line in lines if line.strip())

    policy = _product_query_policy(query)
    name_limit = 30 if policy.broad else 8
    names = "、".join(result["name"] for result in results[:name_limit])
    if len(results) > name_limit:
        names += f"等 {len(results)} 款"
    lines = [
        f"简要回答：根据产品资料，适合“{query}”的法采产品包括 {names}。",
        "",
        "具体信息：",
    ]
    wants_price = _wants_price(query)
    for result in results:
        meta = []
        if result.get("category"):
            meta.append(result["category"])
        if result.get("price") is not None:
            meta.append(f"¥{_format_price(result.get('price'))}")
        suffix = f"（{'，'.join(meta)}）" if meta else ""
        reason = _result_reason(result)
        lines.append(f"- {result['name']}{suffix}" + (f"：{reason}" if reason else ""))
        if wants_price:
            for sku in result.get("sku_prices", [])[:1]:
                if sku.get("line"):
                    lines.append(f"  · {sku['line']}")
    return "\n".join(lines)


def _strip_answer_sources(answer: str) -> str:
    return re.sub(r"(^|\n)\s*来源：[\s\S]*$", "", answer or "").strip()


def _policy_log_dict(policy: ProductQueryPolicy) -> dict[str, Any]:
    return {
        "intent": policy.intent,
        "broad": policy.broad,
        "strict_primary_filter": policy.strict_primary_filter,
        "intents": list(policy.intents),
        "categories": list(policy.categories),
    }


def _chunks_for_log_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for result in results:
        for chunk in result.get("retrieval_chunks") or []:
            chunks.append(_hit_trace(chunk))
    return chunks


def _record_rag_query_log(
    db: Session,
    *,
    query: str,
    answer: str,
    scope: str,
    product_id: int | None,
    policy: ProductQueryPolicy,
    retrieval_mode: str,
    hit_chunks: list[dict[str, Any]],
    final_product_ids: list[int],
    excluded_product_ids: list[int],
    degraded_reason: str = "",
    latency_ms: int = 0,
    error_summary: str = "",
) -> None:
    try:
        db.add(ProductRagQueryLog(
            query=query,
            answer=answer or "",
            scope=scope,
            product_id=product_id,
            policy=_policy_log_dict(policy),
            retrieval_mode=retrieval_mode or "unknown",
            hit_chunks=hit_chunks or [],
            final_product_ids=final_product_ids or [],
            excluded_product_ids=excluded_product_ids or [],
            degraded_reason=degraded_reason or "",
            latency_ms=max(0, int(latency_ms or 0)),
            error_summary=error_summary or "",
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to record product RAG query log: %s", exc)


async def _summarize_answer(query: str, results: list[dict[str, Any]], scope_label: str, db: Session) -> tuple[str, str]:
    if not results:
        return _fallback_answer(query, results, scope_label), "fallback"
    policy = _product_query_policy(query)
    if scope_label == "global" and policy.broad:
        return _fallback_answer(query, results, scope_label), "fallback"

    context = _context_for_ai(results)
    messages = [
        {"role": "system", "content": PRODUCT_CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"用户问题：{query}\n检索范围：{scope_label}\n\n产品资料：\n{context}",
        },
    ]
    interface_key = "product_rag_scoped" if scope_label == "product" else "product_rag_global"
    answer = await ai_service.chat(
        messages,
        temperature=0.2,
        allow_fallback=False,
        interface_key=interface_key,
        db=db,
    )
    answer = _strip_answer_sources(answer or "")
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
    start_time = time.perf_counter()
    clean = _clean_query(query)
    requested_limit = max(1, min(limit, 30))
    policy = _product_query_policy(clean)
    candidate_limit = 30 if policy.broad else requested_limit
    selection = _retrieve_product_selection(clean, db, candidate_limit, category)
    products = selection.products
    chunks_by_product: dict[int, list[dict[str, Any]]] = {}
    for chunk in selection.hit_chunks:
        product_id = chunk.get("product_id")
        if product_id is None:
            continue
        try:
            product_key = int(product_id)
        except (TypeError, ValueError):
            continue
        chunks_by_product.setdefault(product_key, []).append(chunk)
    results = [
        _detail_to_result(
            build_product_detail_payload(product),
            clean,
            hit_chunks=chunks_by_product.get(product.id, []),
        )
        for product in products
    ]
    sources = _unique([source for result in results for source in result.get("sources", [])])
    answer, mode = await _summarize_answer(clean, results, "global", db)
    _record_rag_query_log(
        db,
        query=clean,
        answer=answer,
        scope="global",
        product_id=None,
        policy=selection.policy,
        retrieval_mode=selection.retrieval_mode,
        hit_chunks=selection.hit_chunks,
        final_product_ids=[int(product.id) for product in products],
        excluded_product_ids=selection.excluded_product_ids,
        degraded_reason=selection.degraded_reason,
        latency_ms=int((time.perf_counter() - start_time) * 1000),
    )
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
    start_time = time.perf_counter()
    product = db.query(Product).filter(Product.id == product_id, Product.status == "active").first()
    if not product:
        raise ValueError("产品不存在")
    clean = _clean_query(query)
    detail = build_product_detail_payload(product)
    chunks = [
        {
            "chunk_id": chunk.chunk_id,
            "product_id": chunk.product_id,
            "name": chunk.product_name,
            "category": chunk.category,
            "section": chunk.section,
            "source_name": chunk.source_name,
            "document": chunk.document(),
            "distance": 0,
        }
        for chunk in build_product_knowledge_chunks(product, detail)[:12]
    ]
    result = _detail_to_result(detail, clean, scoped=True, hit_chunks=chunks)
    sources = result.get("sources", [])
    answer, mode = await _summarize_answer(clean, [result], "product", db)
    policy = _product_query_policy(clean)
    _record_rag_query_log(
        db,
        query=clean,
        answer=answer,
        scope="product",
        product_id=product_id,
        policy=policy,
        retrieval_mode="scoped_product",
        hit_chunks=chunks,
        final_product_ids=[product_id],
        excluded_product_ids=[],
        latency_ms=int((time.perf_counter() - start_time) * 1000),
    )
    return {
        "answer": answer,
        "mode": mode,
        "scope": "product",
        "product_id": product_id,
        "results": [result],
        "sources": sources,
    }
