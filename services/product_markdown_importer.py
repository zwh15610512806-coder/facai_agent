"""Parse uploaded Markdown product files into normalized product data."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any


PENDING_LABEL = "待更新"


@dataclass
class ParsedSellingPoint:
    point_type: str
    content: str
    priority: int = 0


@dataclass
class ParsedProductMarkdown:
    name: str
    category: str
    price: float
    original_price: float | None = None
    commission_rate: float | None = None
    brand: str | None = None
    description: str | None = None
    image_url: str | None = None
    selling_points: list[ParsedSellingPoint] = field(default_factory=list)
    pending_fields: list[str] = field(default_factory=list)
    provided_fields: set[str] = field(default_factory=set)


FIELD_ALIASES = {
    "name": {"name", "product", "product_name", "title", "产品名称", "产品名", "商品名称", "名称"},
    "category": {"category", "品类", "类目", "分类", "产品分类"},
    "price": {"price", "售价", "价格", "活动价", "到手价", "吊牌价"},
    "original_price": {"original_price", "原价", "划线价", "日常价"},
    "commission_rate": {"commission_rate", "佣金", "佣金比例", "佣金率"},
    "brand": {"brand", "品牌"},
    "description": {"description", "产品描述", "描述", "简介", "介绍"},
    "image_url": {"image_url", "image", "图片", "图片链接", "主图"},
}

CANONICAL_BY_ALIAS = {
    alias.casefold(): canonical
    for canonical, aliases in FIELD_ALIASES.items()
    for alias in aliases
}

SELLING_POINT_HEADINGS = {
    "selling points",
    "selling point",
    "卖点",
    "核心卖点",
    "产品卖点",
    "产品亮点",
    "亮点",
    "优势",
}


def parse_product_markdown(text: str, filename: str = "product.md") -> ParsedProductMarkdown:
    """Parse a product Markdown document.

    Missing category and price are represented as usable defaults plus
    pending_fields so the UI can show "待更新" instead of treating them as real values.
    """
    raw = (text or "").replace("\ufeff", "").strip()
    frontmatter, body = _split_frontmatter(raw)
    fields: dict[str, str] = {}
    provided_fields: set[str] = set()

    for key, value in frontmatter.items():
        _put_field(fields, provided_fields, key, value)

    for key, value in _extract_inline_fields(body).items():
        _put_field(fields, provided_fields, key, value)

    h1 = _first_h1(body)
    fallback_name = _title_from_filename(filename)
    name = _clean_text(fields.get("name")) or h1 or fallback_name
    provided_fields.add("name")

    category = _clean_text(fields.get("category"))
    price_value = _parse_float(fields.get("price"))
    pending_fields: list[str] = []

    if not category:
        category = PENDING_LABEL
        pending_fields.append("category")
        provided_fields.discard("category")

    if price_value is None:
        price_value = 0.0
        pending_fields.append("price")
        provided_fields.discard("price")

    description = _clean_text(fields.get("description")) or _extract_description(body)

    return ParsedProductMarkdown(
        name=name,
        category=category,
        price=price_value,
        original_price=_parse_float(fields.get("original_price")),
        commission_rate=_parse_float(fields.get("commission_rate")),
        brand=_clean_text(fields.get("brand")) or None,
        description=description or None,
        image_url=_clean_text(fields.get("image_url")) or None,
        selling_points=_extract_selling_points(body),
        pending_fields=pending_fields,
        provided_fields=provided_fields,
    )


def normalize_product_name(name: str) -> str:
    value = (name or "").casefold()
    value = re.sub(r"[\s\-_·•:：/\\|（）()\[\]【】{}《》<>]+", "", value)
    return value


def decode_markdown_bytes(content: bytes) -> str | None:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(?P<front>.*?)\n---\s*\n?(?P<body>.*)$", text, re.S)
    if not match:
        return {}, text
    fields = {}
    for line in match.group("front").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() and value.strip():
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields, match.group("body")


def _extract_inline_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        table_pair = _parse_two_column_table_row(line)
        if table_pair:
            fields[table_pair[0]] = table_pair[1]
            continue
        match = re.match(r"^(?:[-*]\s*)?([^:：|#]{1,30})\s*[:：]\s*(.+?)\s*$", line)
        if match:
            key = match.group(1).strip().strip("*")
            value = match.group(2).strip()
            if key and value:
                fields[key] = value
    return fields


def _parse_two_column_table_row(line: str) -> tuple[str, str] | None:
    if "|" not in line:
        return None
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) != 2:
        return None
    if not cells[0] or not cells[1] or set(cells[0]) <= {"-", ":"}:
        return None
    if set(cells[1]) <= {"-", ":"}:
        return None
    return cells[0], cells[1]


def _put_field(fields: dict[str, str], provided_fields: set[str], key: str, value: Any) -> None:
    canonical = CANONICAL_BY_ALIAS.get(str(key).strip().casefold())
    if not canonical:
        return
    cleaned = _clean_text(str(value))
    if not cleaned:
        return
    fields[canonical] = cleaned
    provided_fields.add(canonical)


def _first_h1(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if match:
            return _clean_text(match.group(1))
    return ""


def _title_from_filename(filename: str) -> str:
    stem = Path(filename or "product").stem
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return stem or "未命名产品"


def _extract_description(text: str) -> str:
    in_selling_points = False
    paragraphs: list[str] = []
    current: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("---") or line.startswith("|") or _is_inline_field(line):
            continue
        heading = _heading_text(line)
        if heading:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            in_selling_points = _is_selling_heading(heading)
            continue
        if in_selling_points or re.match(r"^[-*+]\s+", line) or re.match(r"^\d+[.)、]\s+", line):
            continue
        current.append(line)

    if current:
        paragraphs.append(" ".join(current))
    return paragraphs[0].strip() if paragraphs else ""


def _extract_selling_points(text: str) -> list[ParsedSellingPoint]:
    points: list[ParsedSellingPoint] = []
    in_section = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _heading_text(line)
        if heading:
            was_in_section = in_section
            in_section = _is_selling_heading(heading)
            if was_in_section and not in_section and points:
                break
            continue

        explicit = _extract_explicit_selling_point(line)
        if explicit:
            points.extend(explicit)
            continue

        if not in_section:
            continue

        bullet = re.match(r"^(?:[-*+]\s+|\d+[.)、]\s+)(.+?)\s*$", line)
        if bullet:
            content = _clean_text(bullet.group(1))
            if content:
                points.append(ParsedSellingPoint(point_type="卖点", content=content, priority=len(points) + 1))

    deduped: list[ParsedSellingPoint] = []
    seen = set()
    for point in points:
        key = point.content
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ParsedSellingPoint(point_type=point.point_type, content=point.content, priority=len(deduped) + 1))
    return deduped


def _extract_explicit_selling_point(line: str) -> list[ParsedSellingPoint]:
    match = re.match(r"^(?:卖点|核心卖点|产品卖点|selling points?)\s*[:：]\s*(.+)$", line, re.I)
    if not match:
        return []
    parts = re.split(r"[；;]\s*|(?<!\d)、", match.group(1))
    return [
        ParsedSellingPoint(point_type="卖点", content=content, priority=index + 1)
        for index, content in enumerate(_clean_text(part) for part in parts)
        if content
    ]


def _heading_text(line: str) -> str:
    match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    return _clean_text(match.group(2)) if match else ""


def _is_selling_heading(heading: str) -> bool:
    normalized = heading.casefold().strip()
    return any(alias in normalized for alias in SELLING_POINT_HEADINGS)


def _is_inline_field(line: str) -> bool:
    match = re.match(r"^(?:[-*]\s*)?([^:：|#]{1,30})\s*[:：]\s*(.+?)\s*$", line)
    return bool(match and CANONICAL_BY_ALIAS.get(match.group(1).strip().casefold()))


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"^\*\*(.+)\*\*$", r"\1", text)
    return text.strip()
