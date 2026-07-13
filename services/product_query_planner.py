"""Deterministic query planning for product knowledge retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Iterable


PRICE_TERMS = ("价格", "售价", "原价", "活动价", "优惠", "多少钱", "SKU", "sku")
COMPARE_TERMS = ("区别", "对比", "比较", "哪个好", "怎么选")
USAGE_TERMS = ("怎么用", "如何用", "用法", "用量", "怎么做", "如何做", "适合什么")
RECOMMENDATION_TERMS = ("有哪些", "哪些", "推荐", "适合", "有什么", "列出", "产品")
NEGATION_PATTERNS = (
    re.compile(r"(?:不要|排除|不含|不能用|不适合)([^，。；、\s]{2,12})"),
)
USE_CASE_PATTERN = re.compile(r"适合(?P<use>[^，。；？?]{1,24}?)(?:的)?产品")
ATTRIBUTE_FILTER_PATTERN = re.compile(r"(?:有哪些|哪些|推荐)(?P<attribute>[^，。；？?]{1,16})产品")
PRODUCT_TERM_EQUIVALENCE_GROUPS = (
    ("油性色素", "油溶色粉", "油溶性色粉"),
    ("水性色素", "水状色素", "水溶色粉"),
)


@dataclass(frozen=True)
class ProductEvidenceFacet:
    name: str
    query_terms: tuple[str, ...]
    desired_use: str
    query_type: str
    positive_patterns: tuple[str, ...]
    query_patterns: tuple[str, ...] = ()
    identity_patterns: tuple[str, ...] = ()
    negative_patterns: tuple[str, ...] = ()


PRODUCT_EVIDENCE_FACETS = (
    ProductEvidenceFacet(
        name="macaron",
        query_terms=("马卡龙",),
        desired_use="马卡龙",
        query_type="use_case_recommendation",
        positive_patterns=(r"马卡龙",),
    ),
    ProductEvidenceFacet(
        name="glaze",
        query_terms=("淋面",),
        desired_use="淋面",
        query_type="use_case_recommendation",
        positive_patterns=(
            r"蛋糕淋面",
            r"(?:制作|做|用于|适合|主要场景[:：]?|使用场景[:：]?).{0,16}淋面",
            r"[、，；:：]淋面(?:[、，；。:：]|$)",
        ),
        negative_patterns=(
            r"在.{0,6}淋面(?:上|中).{0,10}(?:绘|画|装饰|调色|调味)",
            r"淋面.{0,8}(?:图案|绘画|填充)",
            r"给.{0,6}淋面.{0,8}(?:调味|调色|装饰)",
        ),
    ),
    ProductEvidenceFacet(
        name="baked_texture",
        query_terms=("烤后还能保持口感", "烤后保持口感", "烤后口感不变"),
        desired_use="烤后保持口感",
        query_type="attribute_filter",
        positive_patterns=(
            r"烤后.{0,10}(?:口感|酥脆|脆度).{0,10}(?:保持|不变)",
            r"烤后.{0,10}(?:保持|不变).{0,10}(?:口感|酥脆|脆度)",
        ),
        negative_patterns=(
            r"(?:别|不可|不能|不宜|不适合).{0,6}(?:烘烤|烤制|进烤箱)",
        ),
    ),
    ProductEvidenceFacet(
        name="high_heat",
        query_terms=("耐高温", "进烤箱", "耐烤"),
        desired_use="耐高温烘烤",
        query_type="attribute_filter",
        positive_patterns=(
            r"耐高温",
            r"(?:烘焙|烘烤|烤制)后",
            r"(?:可以|可|能|能够|适合).{0,8}(?:进烤箱|烘烤|烤制)",
            r"切片烘烤",
        ),
        query_patterns=(
            r"高温烘烤",
            r"适合烤制的.{0,8}产品",
            r"需要经过烘烤的产品",
        ),
        negative_patterns=(
            r"(?:无需|不用|不需要).{0,6}烤箱",
            r"(?:别|不可|不能|不宜|不适合).{0,6}(?:烘烤|烤制|进烤箱)",
            r"高温消毒",
        ),
    ),
    ProductEvidenceFacet(
        name="low_sugar",
        query_terms=("低糖", "控糖", "降低甜度", "低甜度", "替代白砂糖", "零卡糖", "甜度更友好"),
        desired_use="低糖控糖",
        query_type="attribute_filter",
        positive_patterns=(
            r"低糖",
            r"控糖",
            r"零卡糖",
            r"0卡糖",
            r"代糖",
            r"替代白砂糖",
            r"降低甜度",
        ),
        identity_patterns=(r"低糖", r"控糖", r"零卡糖", r"0卡糖", r"代糖", r"海藻糖"),
    ),
)


@dataclass(frozen=True)
class ProductQueryPlan:
    query: str
    query_type: str
    entity_product_ids: tuple[int, ...] = ()
    entity_names: tuple[str, ...] = ()
    wants_price: bool = False
    broad: bool = False
    negative_terms: tuple[str, ...] = ()
    desired_use: str = ""
    facets: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "entity_product_ids": list(self.entity_product_ids),
            "entity_names": list(self.entity_names),
            "wants_price": self.wants_price,
            "broad": self.broad,
            "negative_terms": list(self.negative_terms),
            "desired_use": self.desired_use,
            "facets": list(self.facets),
        }


def matched_product_evidence_facets(query: str) -> tuple[ProductEvidenceFacet, ...]:
    clean = str(query or "")
    return tuple(
        facet for facet in PRODUCT_EVIDENCE_FACETS
        if any(term in clean for term in facet.query_terms)
        or any(re.search(pattern, clean) for pattern in facet.query_patterns)
    )


def score_product_facet_evidence(text: str, facet_names: Iterable[str]) -> int:
    """Score direct evidence while rejecting negated or auxiliary mentions."""
    value = str(text or "")
    names = set(facet_names)
    score = 0
    for facet in PRODUCT_EVIDENCE_FACETS:
        if facet.name not in names:
            continue
        if any(re.search(pattern, value) for pattern in facet.negative_patterns):
            continue
        matches = sum(1 for pattern in facet.positive_patterns if re.search(pattern, value))
        score += matches * 10
    return score


def score_product_facet_identity(text: str, facet_names: Iterable[str]) -> int:
    value = str(text or "")
    names = set(facet_names)
    score = 0
    for facet in PRODUCT_EVIDENCE_FACETS:
        if facet.name not in names:
            continue
        score += sum(20 for pattern in facet.identity_patterns if re.search(pattern, value))
    return score


def _normalize(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", str(text or "")).lower()


@lru_cache(maxsize=1)
def _knowledge_aliases() -> dict[str, set[str]]:
    try:
        from services.product_detail import _load_2026_aliases

        root = str(Path(__file__).resolve().parents[1])
        return _load_2026_aliases(root)
    except Exception:
        return {}


def product_names_and_aliases(product: Any) -> tuple[str, ...]:
    values = [str(getattr(product, "name", "") or "").strip()]
    aliases = _knowledge_aliases()
    values.extend(sorted(aliases.get(values[0], set())))
    for point in getattr(product, "selling_points", None) or []:
        point_type = str(getattr(point, "point_type", "") or "")
        if not any(term in point_type for term in ("命名", "别名", "旧称")):
            continue
        content = str(getattr(point, "content", "") or "")
        if "：" in content:
            content = content.split("：", 1)[1]
        elif ":" in content:
            content = content.split(":", 1)[1]
        values.extend(re.split(r"[、,，/；;]+", content))
    return tuple(dict.fromkeys(value.strip() for value in values if len(_normalize(value)) >= 2))


def _matched_products(query: str, products: Iterable[Any]) -> list[Any]:
    normalized_query = _normalize(query)
    matched: list[tuple[int, int, int, Any]] = []
    for product in products:
        product_matches = [
            (len(normalized_value), normalized_query.find(normalized_value))
            for value in product_names_and_aliases(product)
            if (normalized_value := _normalize(value))
            and normalized_query.find(normalized_value) >= 0
        ]
        if not product_matches:
            continue
        length, start = max(product_matches, key=lambda item: (item[0], -item[1]))
        matched.append((length, start, start + length, product))
    matched.sort(key=lambda item: (-item[0], item[1]))
    selected: list[tuple[int, int, Any]] = []
    for _, start, end, product in matched:
        if any(start < selected_end and end > selected_start for selected_start, selected_end, _ in selected):
            continue
        selected.append((start, end, product))
    selected.sort(key=lambda item: item[0])
    return [product for _, _, product in selected]


def _negative_terms(query: str) -> tuple[str, ...]:
    values: list[str] = []
    for pattern in NEGATION_PATTERNS:
        values.extend(match.group(1).strip() for match in pattern.finditer(query))
    expanded = [value for value in values if value]
    for value in list(expanded):
        normalized = _normalize(value)
        for group in PRODUCT_TERM_EQUIVALENCE_GROUPS:
            if normalized not in {_normalize(term) for term in group}:
                continue
            expanded.extend(group)
    return tuple(dict.fromkeys(expanded))


def build_product_query_plan(query: str, products: Iterable[Any]) -> ProductQueryPlan:
    clean = re.sub(r"\s+", " ", str(query or "").strip())
    matched = _matched_products(clean, products)
    wants_price = any(term in clean for term in PRICE_TERMS)
    recommendation_requested = any(term in clean for term in RECOMMENDATION_TERMS)
    broad = recommendation_requested and not bool(matched)
    facets = matched_product_evidence_facets(clean)
    use_case_match = USE_CASE_PATTERN.search(clean)
    desired_use = str(use_case_match.group("use") if use_case_match else "").strip(" 的")
    if not desired_use and facets:
        desired_use = facets[0].desired_use
    attribute_match = None if use_case_match else ATTRIBUTE_FILTER_PATTERN.search(clean)
    if wants_price:
        query_type = "price"
    elif any(term in clean for term in COMPARE_TERMS):
        query_type = "comparison"
    elif any(term in clean for term in USAGE_TERMS):
        query_type = "usage"
    elif facets:
        query_type = facets[0].query_type
    elif desired_use:
        query_type = "use_case_recommendation"
    elif attribute_match:
        query_type = "attribute_filter"
    elif recommendation_requested:
        query_type = "recommendation"
    else:
        query_type = "fact"
    return ProductQueryPlan(
        query=clean,
        query_type=query_type,
        entity_product_ids=tuple(int(product.id) for product in matched),
        entity_names=tuple(str(product.name) for product in matched),
        wants_price=wants_price,
        broad=broad,
        negative_terms=_negative_terms(clean),
        desired_use=desired_use,
        facets=tuple(facet.name for facet in facets),
    )
