"""Deterministic product price extraction from uploaded product materials."""
from __future__ import annotations

from pathlib import Path
import logging
import re
from typing import Any


logger = logging.getLogger(__name__)

PRICE_LABELS = {"价格", "售价", "产品售价", "吊牌价"}
SKU_PRICE_LABELS = {"sku售价", "sku价格", "sku售价格"}
ORIGINAL_PRICE_LABELS = {"原价", "划线价", "日常价"}
PRICE_SKIP_MARKERS = ("活动", "到手", "折", "券", "优惠", "满减", "机制")


def extract_product_price_metadata(file_path: str | Path) -> dict[str, float]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return _extract_xlsx_price_metadata(path)
    if suffix in {".md", ".markdown", ".txt", ".csv"}:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        return _extract_text_price_metadata(text)
    return {}


def apply_product_price_metadata(product: Any, metadata: dict[str, float]) -> list[str]:
    updated: list[str] = []
    pending_fields = set(_normalize_pending_fields(getattr(product, "pending_fields", [])))

    price = metadata.get("price")
    if price is not None and price > 0:
        if _different_price(getattr(product, "price", None), price):
            product.price = price
            updated.append("price")
        if "price" in pending_fields:
            pending_fields.discard("price")
            if "price" not in updated:
                updated.append("price")

    original_price = metadata.get("original_price")
    if original_price is not None and original_price > 0:
        if _different_price(getattr(product, "original_price", None), original_price):
            product.original_price = original_price
            updated.append("original_price")
        pending_fields.discard("original_price")

    if updated:
        product.pending_fields = sorted(pending_fields)
    return updated


def _extract_xlsx_price_metadata(path: Path) -> dict[str, float]:
    try:
        import pandas as pd
    except ImportError:
        logger.warning("Cannot extract product price from %s: pandas/openpyxl unavailable", path)
        return {}

    try:
        sheets = pd.read_excel(path, header=None, sheet_name=None)
    except Exception as exc:
        logger.warning("Cannot read product price workbook %s: %s", path, exc)
        return {}

    rows: list[list[Any]] = []
    for frame in sheets.values():
        rows.extend(frame.fillna("").values.tolist())
    return _extract_rows_price_metadata(rows)


def _extract_text_price_metadata(text: str) -> dict[str, float]:
    rows = [[part.strip() for part in re.split(r"[,\t|，]+", line)] for line in text.splitlines()]
    return _extract_rows_price_metadata(rows)


def _extract_rows_price_metadata(rows: list[list[Any]]) -> dict[str, float]:
    metadata: dict[str, float] = {}
    sku_fallback: float | None = None

    for row in rows:
        cells = [_cell_text(cell) for cell in row]
        for index, cell in enumerate(cells):
            if not cell:
                continue
            key = _label_key(cell)
            inline_number = _number_after_inline_label(cell)
            if _is_original_price_label(cell, key):
                value = inline_number or _first_price_after(cells, index)
                if value is not None and "original_price" not in metadata:
                    metadata["original_price"] = value
                continue
            if _is_primary_price_label(cell, key):
                value = inline_number or _first_price_after(cells, index)
                if value is not None and "price" not in metadata:
                    metadata["price"] = value
                continue
            if _is_sku_price_label(key) and sku_fallback is None:
                sku_fallback = inline_number or _first_price_after(cells, index)

    if "price" not in metadata and sku_fallback is not None:
        metadata["price"] = sku_fallback
    return metadata


def _is_primary_price_label(cell: str, key: str) -> bool:
    if any(marker in cell for marker in PRICE_SKIP_MARKERS):
        return False
    return key in {_label_key(label) for label in PRICE_LABELS}


def _is_original_price_label(cell: str, key: str) -> bool:
    if any(marker in cell for marker in PRICE_SKIP_MARKERS if marker != "到手"):
        return False
    return key in {_label_key(label) for label in ORIGINAL_PRICE_LABELS}


def _is_sku_price_label(key: str) -> bool:
    return key in {_label_key(label) for label in SKU_PRICE_LABELS}


def _first_price_after(cells: list[str], label_index: int) -> float | None:
    for cell in cells[label_index + 1:]:
        value = _parse_price_number(cell)
        if value is not None:
            return value
    return None


def _number_after_inline_label(cell: str) -> float | None:
    if not re.search(r"[:：]", cell):
        return None
    return _parse_price_number(re.split(r"[:：]", cell, maxsplit=1)[1])


def _parse_price_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return _round_price(float(value))
    text = _cell_text(value)
    if not text:
        return None
    match = re.search(r"(?:¥|￥)?\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if not match:
        return None
    number = float(match.group(1))
    if number <= 0:
        return None
    return _round_price(number)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and abs(value - int(value)) < 0.0001:
        return str(int(value))
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _label_key(value: str) -> str:
    return re.sub(r"[\s（）()：:，,。；;、/\\_-]+", "", value or "").lower()


def _round_price(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def _different_price(current: Any, incoming: float) -> bool:
    if current is None:
        return True
    try:
        return abs(float(current) - float(incoming)) > 0.0001
    except (TypeError, ValueError):
        return True


def _normalize_pending_fields(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []
