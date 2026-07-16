"""Parse natural-language instructions for selecting template rewrite sources."""

from dataclasses import dataclass
import re
from typing import Iterable, Optional


DEFAULT_VIDEO_TYPES = (
    "达人分享类",
    "制作方便",
    "机制类",
    "痛点类",
    "需求类",
    "认知类",
    "成本低",
    "对比类",
    "情绪类",
    "场景类",
)

_REQUEST_LABEL_RE = re.compile(r"(?:^|\n)\s*用户(?:需求|优化建议)：?\s*")
_COMMAND_BOUNDARY = r"(?=$|[，。；;、\n])"
_DIRECT_RESOURCE_RE = re.compile(
    r"(?:找(?:一个|一条)?|选(?:一个|一条)?|选择(?:一个|一条)?|"
    r"挑(?:一个|一条)?|用|使用|参考|调用)\s*"
    r"(?P<subject>.{1,120}?)\s*"
    r"(?:脚本模板库|脚本库|模板库|脚本模板|脚本|模板)"
    r"(?:\s*(?:来|进行|用于)?\s*(?:参考)?\s*(?:改写|生成|创作))?"
    + _COMMAND_BOUNDARY
)
_FROM_LIBRARY_RE = re.compile(
    r"从\s*(?P<subject>.{1,120}?)\s*(?:脚本模板库|脚本库|模板库)"
    r"(?:中|里)?\s*(?:选(?:一个|一条)?|选择(?:一个|一条)?|找(?:一个|一条)?|"
    r"挑(?:一个|一条)?|使用|参考|调用)?\s*(?:来|进行|用于)?\s*(?:参考)?\s*"
    r"(?:改写|生成|创作)?"
    + _COMMAND_BOUNDARY
)
_SHORT_REWRITE_RE = re.compile(
    r"(?:找(?:一个|一条)?|选(?:一个|一条)?|选择(?:一个|一条)?|"
    r"挑(?:一个|一条)?|用|使用|参考|调用)\s*"
    r"(?P<subject>.{1,100}?)\s*(?:的\s*)?(?:参考)?改写"
    + _COMMAND_BOUNDARY
)
_GENERIC_NON_PRODUCT_TERMS = (
    "产品资料",
    "产品知识库",
    "产品卖点",
    "当前产品",
    "所选产品",
    "这个产品",
    "目标产品",
    "模板结构",
)


@dataclass(frozen=True)
class ReferenceSelectionIntent:
    product_query: Optional[str]
    explicit_video_type: Optional[str]
    remaining_requirements: Optional[str]


def _clean_product_subject(subject: str, video_types: Iterable[str]) -> tuple[str, Optional[str]]:
    value = " ".join((subject or "").strip().split()).strip(" ，。；;、")
    value = re.sub(r"(?:的\s*)?同类型(?:的)?$", "", value).strip()
    explicit_video_type = None
    for video_type in sorted({item.strip() for item in video_types if item and item.strip()}, key=len, reverse=True):
        match = re.search(rf"(?:的\s*)?{re.escape(video_type)}(?:的)?$", value)
        if match:
            explicit_video_type = video_type
            value = value[:match.start()].strip()
            break
    value = re.sub(r"(?:的\s*)?(?:产品)?(?:的)?$", "", value).strip(" ，。；;、")
    return value, explicit_video_type


def _remaining_text(body: str, start: int, end: int) -> Optional[str]:
    remaining = (body[:start] + body[end:]).strip(" ，。；;、\n")
    remaining = _REQUEST_LABEL_RE.sub("", remaining).strip(" ，。；;、\n")
    return remaining or None


def _is_specific_product_query(value: str) -> bool:
    compact = re.sub(r"\s+", "", value or "")
    if not compact or any(term in compact for term in _GENERIC_NON_PRODUCT_TERMS):
        return False
    return not re.search(r"(?:生成|创作|改写|参考)$", compact)


def parse_reference_selection_intent(
    requirements: str | None,
    video_types: Iterable[str] = DEFAULT_VIDEO_TYPES,
) -> ReferenceSelectionIntent:
    raw = (requirements or "").strip()
    if not raw:
        return ReferenceSelectionIntent(None, None, None)

    body = _REQUEST_LABEL_RE.sub("", raw).strip()
    for pattern in (_FROM_LIBRARY_RE, _DIRECT_RESOURCE_RE, _SHORT_REWRITE_RE):
        match = pattern.search(body)
        if not match:
            continue
        product_query, explicit_video_type = _clean_product_subject(
            match.group("subject"),
            video_types,
        )
        if not _is_specific_product_query(product_query):
            continue
        return ReferenceSelectionIntent(
            product_query=product_query,
            explicit_video_type=explicit_video_type,
            remaining_requirements=_remaining_text(body, match.start(), match.end()),
        )

    return ReferenceSelectionIntent(None, None, raw)
