"""Parse Qianchuan material-performance Excel exports."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
import zipfile
from xml.etree import ElementTree as ET


@dataclass
class QianchuanParsedRow:
    material_name: str
    material_id: str
    material_evaluation: str
    material_duration: str
    material_created_time: str
    material_source: str
    tags: str
    amount_field: str
    transaction_amount: float
    order_count: int
    user_pay_amount: float
    roi: float
    impressions: int
    ctr: float
    spend: float
    clicks: int
    cvr: float
    play_3s_rate: float
    play_10s_rate: float
    avg_watch_seconds: float
    completion_rate: float
    plan_count: int
    product_count: int
    raw_data: dict[str, str]


@dataclass
class QianchuanParsedWorkbook:
    row_count: int
    amount_field: str
    rows: list[QianchuanParsedRow]


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def parse_qianchuan_workbook(content: bytes, filename: str = "") -> QianchuanParsedWorkbook:
    if not content:
        raise ValueError("文件为空")
    if not zipfile.is_zipfile(BytesIO(content)):
        raise ValueError("暂只支持千川导出的 .xlsx 文件")

    workbook_sheets = _read_xlsx_sheets(content)
    if not workbook_sheets:
        raise ValueError("未读取到表格内容")

    rows: list[QianchuanParsedRow] = []
    workbook_amount_field = ""
    saw_valid_header = False
    for sheet_name, sheet_rows in workbook_sheets:
        if not sheet_rows:
            continue
        header = [str(value or "").strip() for value in sheet_rows[0]]
        amount_field = "净成交金额" if "净成交金额" in header else "用户实际支付金额"
        if "素材名称" not in header or "素材ID" not in header:
            continue
        if amount_field not in header:
            continue
        saw_valid_header = True
        workbook_amount_field = workbook_amount_field or amount_field
        for values in sheet_rows[1:]:
            raw = _row_dict(header, values)
            material_name = raw.get("素材名称", "").strip()
            material_id = raw.get("素材ID", "").strip()
            if material_name == "素材名称" and material_id == "素材ID":
                continue
            if not material_name or material_name == "AIGC动态创意视频素材集合":
                continue
            if not material_id or material_id == "-":
                continue
            raw["_sheet"] = sheet_name
            rows.append(_build_row(raw, amount_field))

    if not saw_valid_header:
        raise ValueError("未找到素材名称、素材ID或成交金额列")

    return QianchuanParsedWorkbook(row_count=len(rows), amount_field=workbook_amount_field, rows=rows)


def _read_xlsx_rows(content: bytes) -> list[list[str]]:
    rows: list[list[str]] = []
    for _sheet_name, sheet_rows in _read_xlsx_sheets(content):
        rows.extend(sheet_rows)
    return rows


def _read_xlsx_sheets(content: bytes) -> list[tuple[str, list[list[str]]]]:
    sheets: list[tuple[str, list[list[str]]]] = []
    rows: list[list[str]] = []
    with zipfile.ZipFile(BytesIO(content)) as workbook:
        shared_strings = _read_shared_strings(workbook)
        sheet_names = sorted(
            name for name in workbook.namelist()
            if name.startswith("xl/worksheets/") and name.endswith(".xml")
        )
        for sheet_name in sheet_names:
            rows = []
            root = ET.fromstring(workbook.read(sheet_name))
            for row in root.findall(f".//{_NS}sheetData/{_NS}row"):
                values: list[str] = []
                for cell in row.findall(f"{_NS}c"):
                    index = _column_index(cell.get("r", "A1"))
                    while len(values) <= index:
                        values.append("")
                    values[index] = _cell_text(cell, shared_strings)
                if any(str(value).strip() for value in values):
                    rows.append(values)
            if rows:
                sheets.append((sheet_name, rows))
    return sheets


def _read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall(f"{_NS}si"):
        strings.append("".join(text.text or "" for text in item.findall(f".//{_NS}t")))
    return strings


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    number = 0
    for ch in letters.upper():
        number = number * 26 + ord(ch) - 64
    return max(0, number - 1)


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(f".//{_NS}t")).strip()
    value = cell.find(f"{_NS}v")
    if value is None or value.text is None:
        return ""
    if cell.get("t") == "s":
        index = _parse_int(value.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    return str(value.text).strip()


def _row_dict(header: list[str], values: list[str]) -> dict[str, str]:
    return {
        name: (values[index].strip() if index < len(values) and values[index] is not None else "")
        for index, name in enumerate(header)
        if name
    }


def _build_row(raw: dict[str, str], amount_field: str) -> QianchuanParsedRow:
    transaction_amount = _parse_float(raw.get(amount_field))
    spend = _parse_float(raw.get("整体消耗"))
    roi = _parse_float(raw.get("整体支付ROI"))
    if not roi and spend > 0:
        roi = transaction_amount / spend
    return QianchuanParsedRow(
        material_name=raw.get("素材名称", ""),
        material_id=raw.get("素材ID", ""),
        material_evaluation=raw.get("素材评估", ""),
        material_duration=raw.get("素材时长", ""),
        material_created_time=raw.get("素材创建时间", ""),
        material_source=raw.get("素材来源", ""),
        tags=raw.get("标签", ""),
        amount_field=amount_field,
        transaction_amount=transaction_amount,
        order_count=_parse_int(raw.get("净成交订单数")),
        user_pay_amount=_parse_float(raw.get("用户实际支付金额")),
        roi=roi,
        impressions=_parse_int(raw.get("整体展示次数")),
        ctr=_parse_percent(raw.get("整体点击率")),
        spend=spend,
        clicks=_parse_int(raw.get("整体点击次数")),
        cvr=_parse_percent(raw.get("整体转化率")),
        play_3s_rate=_parse_percent(raw.get("3秒播放率")),
        play_10s_rate=_parse_percent(raw.get("10秒播放率")),
        avg_watch_seconds=_parse_float(raw.get("平均观看时长")),
        completion_rate=_parse_percent(raw.get("视频完播率")),
        plan_count=_parse_int(raw.get("素材关联的计划数量")),
        product_count=_parse_int(raw.get("素材关联的商品数量")),
        raw_data=raw,
    )


def _parse_float(value) -> float:
    text = str(value or "").strip()
    if not text or text == "-":
        return 0.0
    text = re.sub(r"[,%\s]", "", text)
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_int(value) -> int:
    return int(round(_parse_float(value)))


def _parse_percent(value) -> float:
    text = str(value or "").strip()
    if not text or text == "-":
        return 0.0
    number = _parse_float(text)
    return round(number / 100, 6) if "%" in text else number
