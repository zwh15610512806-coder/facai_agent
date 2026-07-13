"""Standalone helpers for selecting and checking generated script openings."""

from __future__ import annotations

import math
import random
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


OPENING_SIMILARITY_THRESHOLD = 0.76

AI_OPENING_FAMILIES = {
    "action": "用具体制作动作开场，直接展示怎么做。",
    "scene_conflict": "用真实工作场景开场，让痛点当场发生。",
    "result_contrast": "用前后结果反差开场，突出变化。",
    "cognition": "用实用认知纠偏开场，点破常见误区。",
    "product_proof": "用产品事实或可见效果开场，先给证据。",
    "customer_feedback": "用具体顾客反馈或复购表现开场。",
    "cost_mechanism": "用真实价格、成本或优惠机制开场。",
}


@dataclass(frozen=True)
class OpeningBrief:
    family: str
    instruction: str


@dataclass(frozen=True)
class OpeningCheck:
    valid: bool
    opening: str
    reasons: tuple[str, ...]
    max_similarity: float


_FAMILY_COMPATIBILITY = {
    "机制类": ("cognition", "cost_mechanism", "result_contrast", "product_proof"),
    "成本低": ("cost_mechanism", "result_contrast", "scene_conflict", "product_proof"),
    "痛点类": ("scene_conflict", "result_contrast", "action", "cognition"),
    "需求类": ("scene_conflict", "action", "product_proof", "customer_feedback"),
    "认知类": ("cognition", "product_proof", "result_contrast", "action"),
    "达人分享类": ("customer_feedback", "action", "product_proof", "scene_conflict"),
    "制作方便": ("action", "result_contrast", "scene_conflict", "product_proof"),
    "对比类": ("result_contrast", "product_proof", "action", "cognition"),
    "情绪类": ("scene_conflict", "customer_feedback", "result_contrast", "action"),
    "场景类": ("action", "scene_conflict", "customer_feedback", "product_proof"),
}
_PRICE_VIDEO_TYPES = {"机制类", "成本低"}
_NON_PRICE_FAMILIES = tuple(family for family in AI_OPENING_FAMILIES if family != "cost_mechanism")
_AUDIENCE_PHRASE_RE = re.compile(
    r"^(?:(?:经常)?(?:做|开|经营|从事)[\u4e00-\u9fff]{0,24}的[\u4e00-\u9fff]{1,8}们"
    r"|[\u4e00-\u9fff]{0,8}(?:老板|姐妹|宝子|家人|朋友)们)"
)
_DIRECT_ADDRESS_CONTINUATION_RE = re.compile(
    r"^(?:今天看|先看|一定要看|记住|注意|听我说|别|快|赶紧|来看|看看|必须|千万|看过来)"
)
_AUDIENCE_PUNCTUATION_RE = re.compile(r"^[，,、：:；;！!。.?？]")
_EMPTY_AUDIENCE_CUE_RE = re.compile(r"^(?:快看过来|看过来|注意了|别划走)")
_PROMOTION_KEYS = {
    "activity_price",
    "final_price",
    "promotion_price",
    "promotional_price",
    "promotion",
    "discount",
    "优惠",
    "促销",
    "活动价",
    "到手价",
}
_PROMOTION_PRICE_KEYS = {
    "activity_price",
    "final_price",
    "promotion_price",
    "promotional_price",
    "活动价",
    "到手价",
}
_PROMOTION_MECHANISM_KEYS = _PROMOTION_KEYS - _PROMOTION_PRICE_KEYS
_PROMOTION_CONTEXT_KEYS = {"promotion", "activity_prices", "discount", "优惠", "促销"}
_PROMOTION_CONTEXT_SCALAR_KEYS = {"label", "mechanism", "value"}
_INVALID_PROMOTION_TEXTS = {
    "",
    "none",
    "null",
    "false",
    "nan",
    "暂无",
    "无",
    "待更新",
    "未配置",
}
_POSITIVE_NUMBER_RE = r"(?:[1-9]\d*(?:\.\d+)?|0?\.\d*[1-9]\d*)"
_REAL_PROMOTION_MECHANISM_RE = re.compile(
    rf"(?:买\s*(?:[1-9]\d*|[一二两三四五六七八九十]+)\s*送\s*(?:[1-9]\d*|[一二两三四五六七八九十]+))"
    rf"|(?:满\s*{_POSITIVE_NUMBER_RE}\s*(?:元)?\s*减\s*{_POSITIVE_NUMBER_RE})"
    rf"|(?:第(?:二|2)件(?:半价|{_POSITIVE_NUMBER_RE}折))"
    rf"|(?:立减\s*{_POSITIVE_NUMBER_RE})"
    rf"|(?:{_POSITIVE_NUMBER_RE}折)"
)


def _strip_opening_prefix(script: str) -> str:
    text = script.strip()
    while text:
        original = text
        text = re.sub(
            r"^【\s*(?:开场|开头|hook|口播|文案|opening)[^】]{0,40}】\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"^(?:[#>*-]+\s*)?(?:\*{1,2}\s*)?"
            r"(?:开场白|开场|开头|hook|口播|文案|opening)"
            r"(?:\s*[（(][^）)]{0,40}[）)])?"
            r"(?:\s*[:：-]\s*(?:\*{1,2})?|\s*\*{1,2}\s*[:：-]?)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"^(?:\[\s*)?\d{1,2}:\d{2}(?:\s*[-~至]\s*\d{1,2}:\d{2})?(?:\s*\])?\s*",
            "",
            text,
        )
        text = re.sub(
            r"^(?:"
            r"\[\s*\d+(?:\.\d+)?\s*(?:秒|s)?\s*[-~至]\s*\d+(?:\.\d+)?\s*(?:秒|s)\s*\]"
            r"|【\s*\d+(?:\.\d+)?\s*(?:秒|s)?\s*[-~至]\s*\d+(?:\.\d+)?\s*(?:秒|s)\s*】"
            r"|\d+(?:\.\d+)?\s*(?:秒|s)?\s*[-~至]\s*\d+(?:\.\d+)?\s*(?:秒|s)"
            r")\s*[:：]?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"^[（(][^）)]{0,120}[）)]\s*", "", text)
        if text == original:
            break
    return text.strip()


def extract_spoken_opening(script: str, limit: int = 80) -> str:
    """Return the first spoken clause after common script metadata."""
    text = _strip_opening_prefix(script)
    if limit <= 0:
        return ""
    candidate = text[:limit]
    match = re.search(r"[，,。！？!?]", candidate)
    return candidate[: match.end()] if match else candidate


def has_generic_audience_opening(text: str) -> bool:
    opening = _strip_opening_prefix(text)
    audience = _AUDIENCE_PHRASE_RE.match(opening)
    if audience is None:
        return False
    continuation = opening[audience.end() :].lstrip()
    if not continuation:
        return True
    if _AUDIENCE_PUNCTUATION_RE.match(continuation):
        return True
    return _DIRECT_ADDRESS_CONTINUATION_RE.match(continuation) is not None


def extract_normalized_leading_audience_phrase(text: str) -> str | None:
    """Return the canonical direct audience phrase at the spoken opening."""
    opening = _strip_opening_prefix(text)
    audience = _AUDIENCE_PHRASE_RE.match(opening)
    if audience is None or not has_generic_audience_opening(opening):
        return None
    return re.sub(
        r"\s+",
        "",
        unicodedata.normalize("NFKC", audience.group(0)).strip(),
    )


def extract_normalized_leading_audience_signature(text: str) -> str | None:
    """Return the audience phrase plus its immediate generic attention cue."""
    opening = _strip_opening_prefix(text)
    audience = _AUDIENCE_PHRASE_RE.match(opening)
    if audience is None or not has_generic_audience_opening(opening):
        return None

    phrase = re.sub(
        r"\s+",
        "",
        unicodedata.normalize("NFKC", audience.group(0)).strip(),
    )
    continuation = opening[audience.end() :]
    continuation = re.sub(r"^[，,、：:；;！!。.?？\s]*", "", continuation)
    cue = _EMPTY_AUDIENCE_CUE_RE.match(continuation)
    if cue is None:
        return phrase
    normalized_cue = re.sub(
        r"\s+",
        "",
        unicodedata.normalize("NFKC", cue.group(0)).strip(),
    )
    return f"{phrase}{normalized_cue}"


def strip_generic_audience_opening(text: str) -> str:
    """Remove a direct audience-call prefix while retaining leading shot notes."""
    if not text:
        return ""

    prefix_match = re.match(r"^(\s*(?:[（(][^（）()]{0,120}[）)]\s*)*)", text)
    prefix = prefix_match.group(1) if prefix_match else ""
    spoken = text[len(prefix) :]
    audience = _AUDIENCE_PHRASE_RE.match(spoken)
    if audience is None or not has_generic_audience_opening(spoken):
        return text

    remainder = spoken[audience.end() :]
    while remainder:
        remainder = re.sub(r"^[，,、：:；;！!。.?？\s]*", "", remainder)
        cue = _EMPTY_AUDIENCE_CUE_RE.match(remainder)
        if cue is None:
            break
        remainder = remainder[cue.end() :]
    return f"{prefix}{remainder.lstrip()}".strip()


def _has_concrete_detail(text: str, product_name: str = "") -> bool:
    category = r"奶油|蛋糕|黄油|面粉|原料|配料|食材|糖珠|刀叉|餐叉|慕斯|果酱|色素|翻糖|夹心|烤盘|模具|包装|餐盘|打包盒|裱花袋|刮刀|抹刀"
    observable_state = r"打发过头|打过头|开裂|掉色|褪色|染色|结块|不稳定|稳定|纹路|质地|塌腰|塌陷|融化|变色|凝固|承托"
    action = r"拿起|摆上|摆到|摆好|放到|拆开|翻找|凑齐|囤货|备货|倒入|挤入|挤好|撒上|淋上|打发|抹面|搅拌|烘烤|切开|制作|加入|出炉|装饰|打包|配送|揪|揉|擀|按|捏|搓|拉伸|铺开|刮平|卷起|压平|剪开|刻出|包住|刷上|涂开|做|用"
    scene = r"后厨|高峰期|订单|急单|赶单|节日单|备货|出品|配送|打包|工作台|操作台|冷藏"
    product_fact = r"乳脂含量|配料|成分|规格|克重|保质期|质地|颜色|稳定性|独立包装|尺寸|效率|成本|复购|顾客反馈|客户反馈|价格待更新|活动价|到手价"
    numeric_fact = r"\d+(?:\.\d+)?\s*(?:%|％|g|kg|ml|L|克|千克|公斤|斤|毫升|升|元|种|个|个月|天|秒|分钟|小时|寸|mm|cm)"
    normalized_product = re.sub(r"[（）()\s]", "", product_name or "")
    normalized_text = re.sub(r"[（）()\s]", "", text)
    has_category = bool(re.search(category, text))
    has_action = bool(re.search(action, text))
    has_scene = bool(re.search(scene, text))
    has_product_fact = bool(re.search(product_fact, text))
    has_numeric_fact = bool(re.search(numeric_fact, text))
    feedback_subject = r"(?:顾客|客户)"
    feedback_detail = r"(?:口感|味道|甜度|颜色|包装|切面|成品|配送|干净|稳定|省事|方便|好吃|不甜|不腻|更轻|更脆|更香)"
    feedback = bool(
        re.search(rf"{feedback_subject}.{{0,12}}(?:回购|复购)", text)
        or re.search(rf"{feedback_subject}.{{0,12}}(?:试吃|反馈|都说|夸).{{0,14}}{feedback_detail}", text)
    )
    result_contrast = bool(
        re.search(r"以前|现在|成品|总是|容易|经常|一到", text)
        and re.search(rf"{observable_state}|立住|省时|省事|更快|更稳", text)
    )
    scene_conflict = bool(
        re.search(r"最怕|来不及|一多|忙乱|手忙脚乱|缺货|卡住|太慢|不够|麻烦|问题|正愁", text)
    )
    product_with_fact = bool(
        normalized_product
        and normalized_product in normalized_text
        and re.search(r"适合|用于|能|可以|更(?:稳|快|省|干净|清晰|亮|脆|细腻|方便|耐用)|不易|不会|只需|需要|冷藏|稳定|包装|配送|装饰|打包|凝固|承托|口感|尺寸|规格", text)
    )
    return bool(
        feedback
        or result_contrast
        or product_with_fact
        or has_product_fact
        or (has_category and has_numeric_fact)
        or (has_category and re.search(observable_state, text))
        or (has_action and has_category)
        or (has_scene and (has_category or has_product_fact or scene_conflict))
    )


def has_empty_attention_hook(text: str) -> bool:
    spoken = _strip_opening_prefix(text)
    attention_match = re.match(r"^(?:你们知道吗|有没有这种困扰|别划走)", spoken)
    if attention_match:
        remainder = spoken[attention_match.end() :].lstrip()
        if not remainder or remainder[0] not in "，,:：":
            return True
        remainder = remainder[1:].lstrip()
        immediate_clause = re.split(r"[，,。！？!?]", remainder, maxsplit=1)[0].strip()
        return not _has_concrete_detail(immediate_clause)
    first_clause = re.split(r"[，,。！？!?]", spoken, maxsplit=1)[0].strip()
    vague_starter = re.match(
        r"^(?:(?:今天)?(?:给|跟)?大家(?:分享|推荐|安利)|(?:今天)?推荐|这个|这款)",
        first_clause,
    )
    if vague_starter and not _has_concrete_detail(first_clause):
        return True
    return False


def _canonicalize_opening_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"(?:法采|法彩|发彩|facai)", "facai", normalized)
    return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)


def normalize_opening(text: str, product_name: str = "") -> str:
    normalized = _canonicalize_opening_text(text)
    product = _canonicalize_opening_text(product_name)
    return normalized.replace(product, "") if product else normalized


def opening_similarity(left: str, right: str, product_name: str = "") -> float:
    normalized_left = normalize_opening(left, product_name)
    normalized_right = normalize_opening(right, product_name)
    if len(normalized_left) < 12 or len(normalized_right) < 12:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right, autojunk=False).ratio()


def classify_opening_family(text: str) -> str | None:
    opening = _strip_opening_prefix(text)
    rules = (
        ("cost_mechanism", r"活动价|促销|省下|成本|毛利|到手价|价格"),
        ("customer_feedback", r"顾客|客户|回购|反馈|试吃|都说"),
        ("result_contrast", r"以前.*现在|从.*到|前后对比|不再.*而是"),
        ("cognition", r"别再|别以为|误以为|真相|很多人以为"),
        ("scene_conflict", r"每次|高峰期|后厨|赶单|订单|一团乱|来不及|困扰|翻车"),
        ("product_proof", r"乳脂|含量|配料|检测|实测|打发后|纹路|成分"),
        ("action", r"先把|打发|抹面|搅拌|切开|加入|倒入|制作"),
    )
    for family, pattern in rules:
        if re.search(pattern, opening):
            return family
    return None


def _is_real_promotion_scalar(key: str, value: object) -> bool:
    if isinstance(value, (dict, list, tuple)):
        return False
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        text = unicodedata.normalize("NFKC", value).casefold().strip()
        if text in _INVALID_PROMOTION_TEXTS:
            return False
        numeric_text = re.sub(r"^[¥￥]\s*", "", text)
        numeric_text = re.sub(r"\s*元$", "", numeric_text).replace(",", "")
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", numeric_text):
            number = float(numeric_text)
            return math.isfinite(number) and number > 0
        mechanism_keys = _PROMOTION_MECHANISM_KEYS | _PROMOTION_CONTEXT_SCALAR_KEYS
        return bool(key in mechanism_keys and _REAL_PROMOTION_MECHANISM_RE.search(text))
    if isinstance(value, (int, float)):
        return math.isfinite(float(value)) and value > 0
    return False


def _has_real_promotion(product: object, in_promotion_context: bool = False) -> bool:
    if isinstance(product, dict):
        for key, value in product.items():
            normalized_key = str(key).casefold().replace(" ", "_")
            is_context_scalar = (
                in_promotion_context
                and normalized_key in _PROMOTION_CONTEXT_SCALAR_KEYS
            )
            if (
                normalized_key in _PROMOTION_KEYS or is_context_scalar
            ) and _is_real_promotion_scalar(normalized_key, value):
                return True
            child_context = (
                in_promotion_context or normalized_key in _PROMOTION_CONTEXT_KEYS
            )
            if isinstance(value, (dict, list, tuple)) and _has_real_promotion(
                value, child_context
            ):
                return True
    elif isinstance(product, (list, tuple)):
        return any(_has_real_promotion(item, in_promotion_context) for item in product)
    return False


def select_opening_brief(
    video_type: str,
    product: dict,
    recent_openings: list[str] | None = None,
    rng=None,
) -> OpeningBrief:
    allow_price = video_type in _PRICE_VIDEO_TYPES or _has_real_promotion(product)
    fallback_families = AI_OPENING_FAMILIES if allow_price else _NON_PRICE_FAMILIES
    candidates = list(_FAMILY_COMPATIBILITY.get(video_type, fallback_families))
    if not allow_price:
        candidates = [family for family in candidates if family != "cost_mechanism"]

    recent_families: list[str] = []
    for opening in recent_openings or []:
        family = classify_opening_family(opening)
        if family and family not in recent_families:
            recent_families.append(family)
        if len(recent_families) == 2:
            break
    alternatives = [family for family in candidates if family not in recent_families]
    if alternatives:
        candidates = alternatives

    chooser = rng if rng is not None else random
    family = chooser.choice(candidates)
    return OpeningBrief(family=family, instruction=AI_OPENING_FAMILIES[family])


def validate_opening(
    script: str,
    recent_openings: list[str] | None = None,
    product_name: str = "",
    allow_audience_call: bool = False,
) -> OpeningCheck:
    opening = extract_spoken_opening(script)
    reasons: list[str] = []
    generic_audience = not allow_audience_call and has_generic_audience_opening(opening)
    empty_attention = has_empty_attention_hook(script)
    if generic_audience:
        reasons.append("generic_audience_call")
    if empty_attention:
        reasons.append("empty_attention_hook")
    if (
        not allow_audience_call
        and not generic_audience
        and not empty_attention
        and not _has_concrete_detail(opening, product_name)
    ):
        reasons.append("non_specific_opening")

    similarities = [
        opening_similarity(opening, recent, product_name) for recent in recent_openings or []
    ]
    max_similarity = max(similarities, default=0.0)
    if max_similarity >= OPENING_SIMILARITY_THRESHOLD:
        reasons.append("recent_opening_similarity")
    return OpeningCheck(
        valid=not reasons,
        opening=opening,
        reasons=tuple(reasons),
        max_similarity=max_similarity,
    )


def _template_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, str)]
    if isinstance(value, (list, tuple)):
        return [item for entry in value for item in _template_strings(entry)]
    return []


def collect_template_audience_phrases(template: dict) -> set[str]:
    """Collect complete normalized direct-call signatures from template openings."""
    phrases: set[str] = set()
    candidates = _template_strings(template.get("hook_templates", []))
    example_script = template.get("example_script", "")
    if isinstance(example_script, str):
        candidates.append(extract_spoken_opening(example_script))
    for candidate in candidates:
        phrase = extract_normalized_leading_audience_signature(candidate)
        if phrase:
            phrases.add(phrase)
    return phrases


def template_allows_audience_call(template: dict) -> bool:
    return bool(collect_template_audience_phrases(template))
