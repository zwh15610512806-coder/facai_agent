"""Price wording helpers for short-video scripts.

Product data keeps exact prices elsewhere. These helpers are only for script
prompts and final script copy, where abstract price bands perform better.
"""
from __future__ import annotations

import re
from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("¥", "").replace("￥", "").strip())
    except (TypeError, ValueError):
        return None


def abstract_script_price(value: Any, pending: bool = False) -> str:
    """Return a concise Douyin-friendly price band for script copy."""
    if pending:
        return "价格待更新"

    number = _to_float(value)
    if number is None:
        return ""

    if number < 1:
        return "几毛钱"
    if number < 8:
        return "几块钱"
    if number < 10:
        return "十块以内"
    if number < 20:
        return "十来块"
    if number < 40:
        return "一杯奶茶钱"
    if number < 100:
        return "几十块"
    if number < 150:
        return "一百出头"
    if number < 1000:
        return "三位数"
    return "千元级"


_CURRENCY_PATTERN = re.compile(
    r"(?P<currency>[¥￥])\s*(?P<currency_num>\d+(?:\.\d+)?)"
    r"|(?P<unit_num>\d+(?:\.\d+)?)\s*(?P<unit>元|块钱|块)"
)

_BARE_DECIMAL_PATTERN = re.compile(
    r"(?<![\w.])(?P<num>\d+\.\d{1,2})(?![\w.])"
    r"(?!\s*(?:g|G|kg|KG|克|斤|寸|秒|分钟|小时|天|个月|月|年|%|％|折|倍|cm|CM|mm|MM|ml|ML|l|L))"
)


def sanitize_script_price_text(text: Any) -> str:
    """Replace exact money mentions in script-facing text with price bands.

    The sanitizer intentionally targets currency signs, yuan/kuai suffixes, and
    standalone decimal money-like values. It does not rewrite specification
    numbers such as 500g, 6寸, 12个月, or 30秒.
    """
    value = str(text or "")
    if not value:
        return ""

    def replace_currency(match: re.Match) -> str:
        number = match.group("currency_num") or match.group("unit_num")
        return abstract_script_price(number)

    value = _CURRENCY_PATTERN.sub(replace_currency, value)
    value = _BARE_DECIMAL_PATTERN.sub(
        lambda match: abstract_script_price(match.group("num")),
        value,
    )
    return value
