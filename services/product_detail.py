"""Build product detail data from local product materials."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import import_materials


PRODUCT_CARD_POINT_LABELS = {
    "一句话卖点",
    "产品名称",
    "规格",
    "售价",
    "一件85折",
    "五件75折",
    "展会一件69折",
    "口味",
    "用户人群",
    "适用人群",
    "保质期",
    "保存方式",
    "储存方式",
    "用途",
    "用途简述",
    "使用场景",
    "用途场景",
    "应用场景",
    "场景用量",
    "推荐用量",
    "使用方法",
    "制作方法",
    "用量",
    "产品亮点",
    "产品卖点",
    "卖点",
    "卖点排序",
    "产品价值",
    "核心优势",
    "痛点切入",
    "差异化卖点",
    "差异化卖点 （重点）",
    "与拉线膏区别",
    "推荐搭配",
    "对比",
}

PRODUCT_CARD_SKIP_SHEETS = {
    "常见问题",
    "解决方案",
    "WpsReserved_CellImgList",
}

PRODUCT_CARD_SHEET_ALIASES = {
    "果泥": "夹心果泥",
    "果馅（多肉）": "多肉果酱",
    "芋泥": "夹心芋泥",
    "白色翻糖": "白色翻糖膏",
    "彩色翻糖": "彩色翻糖膏",
    "翻糖片": "翻糖压片",
    "拉线膏": "彩色拉线膏",
    "红丝绒液": "红丝绒",
    "薄荷糖浆": "调味糖浆",
    "脆皮酱": "巧克力脆皮酱",
    "2元盒装": "盒装刀叉",
    "2.5元盒装": "盒装刀叉",
    "5元盒装刀叉": "盒装刀叉",
    "1.1浆纸盘": "盒装刀叉",
}

PRODUCT_CARD_SOLUTION_PRODUCTS = {
    "夹心类": [
        "夹心珠",
        "夹心脆",
        "奶冻粉",
        "Q弹奶冻粉",
        "Q 弹奶冻粉",
        "晶冻粉",
        "慕斯粉（液）",
        "布蕾粉",
        "夹心芋泥",
        "夹心果泥",
    ],
    "口味蛋糕": ["调味果酱", "茶酱", "开心果酱", "夹心果泥", "多肉果酱", "焦糖酱"],
    "造型蛋糕": ["白色翻糖膏", "彩色翻糖膏", "翻糖压片", "手绘膏", "彩色拉线膏", "拉线膏"],
    "网红颜色还原蛋糕": ["水性色素", "油性色素", "果蔬色素", "浅柔色素", "浅系色素", "色粉盘", "红丝绒"],
    "餐盘仪式感": ["盒装刀叉", "刀叉", "纸盘", "1.1浆纸盘", "5元盒装刀叉", "2元盒装", "2.5元盒装"],
}

RISKY_2026_PHRASES = (
    "待核验",
    "全国销量第一",
    "全网销量领先",
    "全网销量 TOP1",
    "全网TOP1",
    "TOP1",
    "安全健康",
    "安全放心",
    "没有任何影响",
    "无任何影响",
    "0脂肪酸",
    "无反式脂肪酸",
    "没有反式脂肪酸",
    "无添加剂",
    "儿童也可以放心",
    "宝妈也能放心",
    "健康+好吃",
    "更健康",
    "可提高10%",
    "轻松溢价",
    "卖高价",
)


def build_material_product_detail(
    product_name: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    root_path = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    paths = import_materials.get_material_paths(root_path)
    products = _load_material_products(str(root_path.resolve()))
    source = _find_material_product(product_name, products)
    product_names = [product_name]
    if source:
        product_names.append(source.name)

    selling_points = []
    if source:
        selling_points = [
            {
                "point_type": point.get("point_type", "卖点"),
                "content": point.get("content", ""),
                "priority": point.get("priority", index),
            }
            for index, point in enumerate(source.selling_points, start=1)
        ]
    knowledge_points, knowledge_sources = _find_2026_knowledge_points(
        str(root_path.resolve()),
        product_names,
    )
    selling_points = _merge_points(selling_points, knowledge_points)
    manual_source = _manual_source_name(str(paths.product_manual_md))
    sources = [manual_source, *knowledge_sources]

    return {
        "source_name": source.name if source else _base_name(product_name),
        "manual_source": manual_source,
        "knowledge_sources": sources,
        "selling_points": selling_points,
        "sku_prices": build_sku_prices(product_name, root_path),
    }


def build_sku_prices(
    product_name: str,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    root_path = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    paths = import_materials.get_material_paths(root_path)

    rule_name = _resolve_price_rule_name(product_name)
    rule = import_materials.PRICE_RULES.get(rule_name)
    if not rule:
        return []

    override = rule.get("override")
    has_price_filters = any(
        rule.get(key) for key in ("products", "specs", "exclude_specs", "knife_price")
    )
    if isinstance(override, (int, float)) and override > 0 and not has_price_filters:
        return [_override_sku(rule_name, float(override))]

    if rule.get("knife_price"):
        rows = (
            import_materials._parse_knife_price_rows(
                paths.knife_price_xlsx,
                str(rule["knife_price"]),
            )
            if paths.knife_price_xlsx is not None else []
        )
    elif paths.price_system_xlsx is not None:
        rows = import_materials._parse_price_system_rows(paths.price_system_xlsx)
    else:
        rows = []

    matched_rows = [
        row for row in rows
        if import_materials._row_matches_price_rule(row, rule)
    ]

    skus = [_sku_from_price_row(row) for row in matched_rows]
    if skus:
        return skus

    if isinstance(override, (int, float)) and override > 0:
        return [_override_sku(rule_name, float(override))]
    return []


@lru_cache(maxsize=8)
def _manual_source_name(path_text: str) -> str:
    path = Path(path_text)
    try:
        text = import_materials._read_text(path)
    except OSError:
        return path.name
    for line in text.splitlines()[:20]:
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match and "产品手册" in match.group(1):
            return f"{match.group(1)}.md"
    return path.name


def build_product_detail_payload(product: Any, root: Path | str | None = None) -> dict[str, Any]:
    material = build_material_product_detail(product.name, root)
    db_points = [
        {
            "id": point.id,
            "product_id": point.product_id,
            "point_type": point.point_type,
            "content": point.content,
            "priority": point.priority,
        }
        for point in sorted(product.selling_points, key=lambda item: item.priority)
    ]
    selling_points = material["selling_points"] or db_points

    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "original_price": product.original_price,
        "commission_rate": product.commission_rate,
        "brand": product.brand,
        "description": product.description,
        "info_file": product.info_file,
        "pending_fields": product.pending_fields or [],
        "status": product.status,
        "source_name": material["source_name"],
        "manual_source": material["manual_source"],
        "knowledge_sources": material["knowledge_sources"],
        "selling_points": selling_points,
        "sku_prices": material["sku_prices"],
    }


@lru_cache(maxsize=4)
def _load_material_products(root: str) -> tuple[import_materials.ProductInput, ...]:
    root_path = Path(root)
    paths = import_materials.get_material_paths(root_path)
    products = import_materials.merge_product_inputs(
        import_materials.parse_product_knowledge(paths.product_knowledge_md)
        + import_materials.parse_product_manual(paths.product_manual_md)
        + import_materials.parse_2026_product_knowledge(paths.product_2026_dir)
    )
    return tuple(products)


@lru_cache(maxsize=4)
def _load_2026_knowledge(root: str) -> tuple[dict[str, Any], ...]:
    knowledge_dir = Path(root) / "资料" / "2026产品知识库"
    if not knowledge_dir.exists():
        return ()

    entries: list[dict[str, Any]] = []
    index_path = knowledge_dir / "00_产品知识总索引.md"
    if index_path.exists():
        entries.extend(_parse_2026_index(index_path))

    solutions_path = knowledge_dir / "01_五大门店解决方案.md"
    if solutions_path.exists():
        entries.extend(_parse_2026_solutions(solutions_path))

    overview_path = knowledge_dir / "02_核心产品卖点速览.md"
    if overview_path.exists():
        entries.extend(_parse_2026_overview(overview_path))

    faq_path = knowledge_dir / "04_产品常见问题精选.md"
    if faq_path.exists():
        entries.extend(_parse_2026_faq_markdown(faq_path))

    shallow_color_path = knowledge_dir / "06_浅柔色素产品档案.md"
    if shallow_color_path.exists():
        entries.extend(_parse_shallow_color_archive(shallow_color_path))

    product_card_path = knowledge_dir / "【法采】2026年产品手卡.xlsx"
    if product_card_path.exists():
        entries.extend(_parse_product_card_workbook(product_card_path))

    shallow_color_xlsx_path = knowledge_dir / "【法采浅柔色素】产品一页纸.xlsx"
    if shallow_color_xlsx_path.exists():
        entries.extend(_parse_shallow_color_workbook(shallow_color_xlsx_path))

    return tuple(entries)


@lru_cache(maxsize=4)
def _load_2026_aliases(root: str) -> dict[str, set[str]]:
    knowledge_dir = Path(root) / "资料" / "2026产品知识库"
    aliases = _static_2026_aliases()
    naming_path = knowledge_dir / "05_产品命名主数据与旧称对照.md"
    if naming_path.exists():
        _merge_alias_map(aliases, _parse_2026_alias_markdown(naming_path))
    naming_xlsx_path = knowledge_dir / "产品命名规则.xlsx"
    if naming_xlsx_path.exists():
        _merge_alias_map(aliases, _parse_product_naming_workbook(naming_xlsx_path))
    return {name: set(values) for name, values in aliases.items()}


def _find_2026_knowledge_points(
    root: str,
    product_names: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    entries = _load_2026_knowledge(root)
    if not entries:
        return [], []

    aliases = _load_2026_aliases(root)
    candidate_keys = _candidate_keys(product_names, aliases)
    points: list[dict[str, Any]] = []
    sources: list[str] = []
    for entry in entries:
        if not _entry_matches_product(entry["name"], candidate_keys):
            continue
        points.extend(entry["points"])
        if entry["source"] not in sources:
            sources.append(entry["source"])
    if points:
        for alias_source in _alias_sources(root, product_names, aliases):
            if alias_source not in sources:
                sources.append(alias_source)
    return _merge_points([], points), sources


def _parse_2026_index(path: Path) -> list[dict[str, Any]]:
    text = import_materials._read_text(path)
    entries: list[dict[str, Any]] = []
    for title, block in _split_level3_sections(text):
        if not re.match(r"^[A-Z]\.", title):
            continue
        products: list[str] = []
        values: list[str] = []
        collecting_values = False
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("核心客户价值"):
                collecting_values = True
                continue
            if not line.startswith("- "):
                continue
            item = import_materials._clean_markdown(line[2:])
            if collecting_values:
                values.append(item)
            else:
                products.extend(_split_product_list(item))
        if not products or not values:
            continue
        scenario = _clean_solution_title(title)
        content = f"{scenario}：" + "；".join(values)
        for product in products:
            points: list[dict[str, Any]] = []
            _append_2026_point(points, "经营场景", content, path.name)
            if points:
                entries.append({"name": product, "points": points, "source": path.name})
    return entries


def _parse_2026_solutions(path: Path) -> list[dict[str, Any]]:
    text = import_materials._read_text(path)
    entries: list[dict[str, Any]] = []
    for title, block in _split_level2_sections(text):
        if not re.match(r"^\d+\.", title):
            continue
        products: list[str] = []
        for line in _extract_heading_bullets(block, "### 代表产品"):
            products.extend(_split_product_list(line))
        if not products:
            continue

        solution_title = _clean_solution_title(title)
        solution_items = _extract_heading_bullets(block, "### 解决方案")
        value_text = _extract_heading_text(block, "### 门店价值")
        for product in products:
            points: list[dict[str, Any]] = []
            if value_text:
                _append_2026_point(points, "门店方案", f"{solution_title}：{value_text}", path.name)
            if solution_items:
                _append_2026_point(points, "解决方案", f"{solution_title}：" + "；".join(solution_items), path.name)
            if points:
                entries.append({"name": product, "points": points, "source": path.name})
    return entries


def _parse_2026_faq_markdown(path: Path) -> list[dict[str, Any]]:
    text = import_materials._read_text(path)
    entries: list[dict[str, Any]] = []
    for title, block in _split_level2_sections(text):
        if title.startswith("产品常见问题"):
            continue
        points: list[dict[str, Any]] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line.startswith("- "):
                continue
            body = import_materials._clean_markdown(line[2:])
            match = re.match(r"(.+?)[：:]\s*(.+)$", body)
            if match:
                point_type = f"FAQ：{match.group(1).strip()}"
                content = match.group(2).strip()
            else:
                point_type = "FAQ"
                content = body
            _append_2026_point(points, point_type, content, path.name)
        if points:
            entries.append({"name": title, "points": points, "source": path.name})
    return entries


def _parse_2026_overview(path: Path) -> list[dict[str, Any]]:
    text = import_materials._read_text(path)
    entries: list[dict[str, Any]] = []
    for title, block in _split_level2_sections(text):
        if title == "卖点使用规则":
            continue
        points = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            body = import_materials._clean_markdown(line[2:])
            match = re.match(r"(.+?)[：:]\s*(.+)$", body)
            if not match:
                continue
            point_type = match.group(1).strip()
            content = match.group(2).strip()
            if "待核验" in point_type or "待核验" in content:
                continue
            points.append({
                "point_type": point_type,
                "content": content,
                "priority": len(points) + 1,
                "source": path.name,
            })
        if points:
            entries.append({"name": title, "points": points, "source": path.name})
    return entries


def _parse_shallow_color_archive(path: Path) -> list[dict[str, Any]]:
    text = import_materials._read_text(path)
    points: list[dict[str, Any]] = []

    sales_block = _extract_markdown_block(text, "### 可优先使用")
    for line in sales_block.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        _append_2026_point(points, "销售表达", line[2:], path.name)

    value_block = _extract_markdown_block(text, "## 四、产品能力与客户价值")
    for line in value_block.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line or "门店痛点" in line:
            continue
        cells = [import_materials._clean_markdown(cell) for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        content = f"{cells[0]}；{cells[1]}；{cells[2]}"
        _append_2026_point(points, "客户价值", content, path.name)

    if not points:
        return []
    return [{"name": "浅柔色素", "points": points, "source": path.name}]


def _parse_product_card_workbook(path: Path) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    entries: list[dict[str, Any]] = []
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "常见问题" in workbook.sheetnames:
            entries.extend(_parse_product_card_faq_sheet(workbook["常见问题"], path.name))
        if "解决方案" in workbook.sheetnames:
            entries.extend(_parse_product_card_solution_sheet(workbook["解决方案"], path.name))

        for sheet_name in workbook.sheetnames:
            if sheet_name in PRODUCT_CARD_SKIP_SHEETS:
                continue
            worksheet = workbook[sheet_name]
            points = _parse_product_card_sheet(worksheet, path.name)
            if points:
                entries.append({
                    "name": _standardize_product_card_name(sheet_name),
                    "points": points,
                    "source": path.name,
                })
    finally:
        workbook.close()
    return entries


def _parse_product_card_sheet(worksheet: Any, source: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    active_label = ""
    for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        values = [_cell_text(value) for value in row]
        if not any(values):
            continue

        if row_index <= 2:
            title = _join_content(values)
            if "手卡" in title or "一页纸" in title:
                _append_2026_point(points, "资料标题", title, source)

        label_index, label = _find_row_label(values)
        if label:
            active_label = label
            content = _join_content(values[label_index + 1:])
            if not content:
                content = _join_content(value for index, value in enumerate(values) if index != label_index)
            _append_2026_point(points, label, content, source)
            continue

        if active_label and _row_looks_like_continuation(values):
            _append_2026_point(points, active_label, _join_content(values), source)
    return points


def _parse_product_card_faq_sheet(worksheet: Any, source: str) -> list[dict[str, Any]]:
    by_product: dict[str, list[dict[str, Any]]] = {}
    current_product = ""
    for row in worksheet.iter_rows(min_row=2, values_only=True):
        values = [_cell_text(value) for value in row]
        if len(values) < 5:
            continue
        product = values[2]
        question = values[3]
        answer = values[4]
        if product:
            current_product = product
        if not current_product or not question or not answer:
            continue
        points = by_product.setdefault(_standardize_product_card_name(current_product), [])
        _append_2026_point(points, f"FAQ：{question}", answer, source)

    return [
        {"name": product, "points": points, "source": source}
        for product, points in by_product.items()
        if points
    ]


def _parse_product_card_solution_sheet(worksheet: Any, source: str) -> list[dict[str, Any]]:
    rows = [
        [_cell_text(value) for value in row]
        for row in worksheet.iter_rows(min_row=1, max_row=8, values_only=True)
    ]
    scenario_row = _find_sheet_row(rows, "场景")
    solution_row = _find_sheet_row(rows, "法采提供解决方案")
    action_row = _find_sheet_row(rows, "具体行动及结果")
    value_row = _find_sheet_row(rows, "提供价值")
    if not scenario_row:
        return []

    entries_by_product: dict[str, list[dict[str, Any]]] = {}
    for column_index, raw_scenario in enumerate(scenario_row):
        scenario = _strip_leading_number(raw_scenario)
        if not scenario or scenario == "场景":
            continue
        products = _solution_products_for_scenario(scenario)
        if not products:
            continue
        for product in products:
            points = entries_by_product.setdefault(product, [])
            if column_index < len(solution_row):
                _append_2026_point(points, "解决方案", solution_row[column_index], source)
            if column_index < len(action_row):
                _append_2026_point(points, "具体行动及结果", action_row[column_index], source)
            if column_index < len(value_row):
                _append_2026_point(points, "门店价值", f"{scenario}：{value_row[column_index]}", source)

    return [
        {"name": product, "points": points, "source": source}
        for product, points in entries_by_product.items()
        if points
    ]


def _parse_shallow_color_workbook(path: Path) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    points: list[dict[str, Any]] = []
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "产品一页纸" in workbook.sheetnames:
            _append_shallow_color_product_sheet(points, workbook["产品一页纸"], path.name)
        if "浅系色素具体颜色以及名称" in workbook.sheetnames:
            _append_shallow_color_names(points, workbook["浅系色素具体颜色以及名称"], path.name)
    finally:
        workbook.close()

    if not points:
        return []
    return [{"name": "浅柔色素", "points": points, "source": path.name}]


def _append_shallow_color_product_sheet(
    points: list[dict[str, Any]],
    worksheet: Any,
    source: str,
) -> None:
    pending_skus: list[str] = []
    for row in worksheet.iter_rows(min_row=1, max_row=24, values_only=True):
        values = [_cell_text(value) for value in row]
        if not any(values):
            continue
        label_index, label = _find_shallow_color_label(values)
        if not label:
            continue
        content_values = [value for value in values[label_index + 1:] if value]
        if label.lower() == "sku":
            pending_skus = content_values
            _append_2026_point(points, "SKU规格", "、".join(pending_skus), source)
            continue
        if "售价" in label and pending_skus:
            prices = content_values
            pairs = [
                f"{sku}：{price}"
                for sku, price in zip(pending_skus, prices)
                if sku and price
            ]
            _append_2026_point(points, "SKU售价", "；".join(pairs), source)
            pending_skus = []
            continue
        if label in {"用途简述", "储存方式", "保质期"}:
            _append_2026_point(points, label, _join_content(content_values), source)


def _append_shallow_color_names(
    points: list[dict[str, Any]],
    worksheet: Any,
    source: str,
) -> None:
    color_names: list[str] = []
    for row in worksheet.iter_rows(min_row=3, max_row=40, values_only=True):
        values = [_cell_text(value) for value in row]
        if len(values) >= 4 and values[3]:
            color_names.append(values[3])
    if color_names:
        _append_2026_point(points, "颜色体系", "浅柔色素颜色：" + "、".join(color_names[:18]), source)


def _append_2026_point(
    points: list[dict[str, Any]],
    point_type: str,
    content: str,
    source: str,
) -> None:
    cleaned = import_materials._clean_markdown(content)
    if not cleaned or _is_risky_2026_content(cleaned):
        return
    if len(cleaned) > 520:
        cleaned = cleaned[:517].rstrip() + "..."
    points.append({
        "point_type": point_type,
        "content": cleaned,
        "priority": len(points) + 1,
        "source": source,
    })


def _split_level2_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((import_materials._clean_markdown(match.group(1)), text[start:end].strip()))
    return sections


def _extract_markdown_block(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = re.search(r"^#{2,3}\s+", text[start + len(heading):], flags=re.MULTILINE)
    if not next_heading:
        return text[start + len(heading):]
    end = start + len(heading) + next_heading.start()
    return text[start + len(heading):end]


def _split_level3_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^###\s+(.+?)\s*$", text, flags=re.MULTILINE))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((import_materials._clean_markdown(match.group(1)), text[start:end].strip()))
    return sections


def _extract_heading_bullets(block: str, heading: str) -> list[str]:
    heading_block = _extract_markdown_block(block, heading)
    bullets: list[str] = []
    for line in heading_block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            bullets.append(import_materials._clean_markdown(line[2:]))
    return bullets


def _extract_heading_text(block: str, heading: str) -> str:
    heading_block = _extract_markdown_block(block, heading)
    lines = []
    for line in heading_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:]
        lines.append(import_materials._clean_markdown(line))
    return "；".join(lines)


def _split_product_list(value: str) -> list[str]:
    cleaned = import_materials._clean_markdown(value)
    if "：" in cleaned:
        prefix, suffix = cleaned.split("：", 1)
        if "SKU" in prefix or "产品" in prefix:
            cleaned = suffix
    cleaned = (
        cleaned.replace("及其", "、")
        .replace("等", "")
        .replace(" SKU", "")
        .replace("SKU", "")
        .replace("其他包装产品", "包装产品")
    )
    parts = re.split(r"[、,，/]+", cleaned)
    return [part.strip(" 。；;") for part in parts if part.strip(" 。；;")]


def _clean_solution_title(value: str) -> str:
    return re.sub(r"^[A-Z]\.\s*|^\d+\.\s*", "", value).strip()


def _strip_leading_number(value: str) -> str:
    return re.sub(r"^\d+[、.]\s*", "", import_materials._clean_markdown(value)).strip()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and abs(value - int(value)) < 0.0001:
        text = str(int(value))
    else:
        text = str(value)
    text = text.replace("\n", " ").strip()
    if text.startswith("=DISPIMG"):
        return ""
    return import_materials._clean_markdown(text)


def _join_content(values: Any) -> str:
    return "；".join(value for value in values if value)


def _find_row_label(values: list[str]) -> tuple[int, str]:
    for index, value in enumerate(values):
        if not value:
            continue
        normalized = _label_key(value)
        for label in PRODUCT_CARD_POINT_LABELS:
            if normalized == _label_key(label):
                return index, label
    return -1, ""


def _find_sheet_row(rows: list[list[str]], label: str) -> list[str]:
    label_key = _label_key(label)
    for row in rows:
        if any(_label_key(value) == label_key for value in row if value):
            return row
    return []


def _find_shallow_color_label(values: list[str]) -> tuple[int, str]:
    labels = {"sku", "售价（到手价）", "用途简述", "保质期", "储存方式"}
    for index, value in enumerate(values):
        if not value:
            continue
        normalized = _label_key(value)
        for label in labels:
            if normalized == _label_key(label):
                return index, label
    return -1, ""


def _label_key(value: str) -> str:
    return re.sub(r"[\s（）()：:]+", "", value).lower()


def _row_looks_like_continuation(values: list[str]) -> bool:
    content = _join_content(values)
    if not content or len(content) < 4:
        return False
    if _is_risky_2026_content(content):
        return False
    return any(
        marker in content
        for marker in ("【", "：", "1.", "1、", "适合", "用于", "比例", "搭配", "场景", "口感", "规格")
    )


def _standardize_product_card_name(sheet_name: str) -> str:
    return PRODUCT_CARD_SHEET_ALIASES.get(sheet_name, sheet_name)


def _solution_products_for_scenario(scenario: str) -> list[str]:
    for key, products in PRODUCT_CARD_SOLUTION_PRODUCTS.items():
        if key in scenario:
            return products
    return []


def _parse_2026_alias_markdown(path: Path) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for raw_line in import_materials._read_text(path).splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [import_materials._clean_markdown(cell) for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"旧资料名称", "名称", "系列"}:
            continue
        if len(cells) >= 3 and ("统一" in cells[2] or "确认" in cells[2] or "更名" in cells[2]):
            standard = cells[1]
            for old_name in _split_alias_names(cells[0]):
                _add_alias(aliases, standard, old_name)
        if len(cells) >= 4 and cells[1] in {"SKU", "品类统称"}:
            parent = cells[2].split("/")[0].strip()
            if parent and parent != "色素":
                _add_alias(aliases, parent, cells[0])
    return aliases


def _parse_product_naming_workbook(path: Path) -> dict[str, set[str]]:
    from openpyxl import load_workbook

    aliases: dict[str, set[str]] = {}
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for worksheet in workbook.worksheets:
            rows = [[_cell_text(value) for value in row] for row in worksheet.iter_rows(values_only=True)]
            for row_index, values in enumerate(rows):
                if "标准产品名称" in values and "旧资料名称" in values:
                    old_index = values.index("旧资料名称")
                    standard_index = values.index("标准产品名称")
                    for data_values in rows[row_index + 1:]:
                        if len(data_values) <= max(old_index, standard_index):
                            continue
                        standard = data_values[standard_index]
                        for old_name in _split_alias_names(data_values[old_index]):
                            _add_alias(aliases, standard, old_name)
                        continue
                    break
    finally:
        workbook.close()
    return aliases


def _split_alias_names(value: str) -> list[str]:
    cleaned = import_materials._clean_markdown(value)
    cleaned = re.sub(r"（.*?）", "", cleaned)
    return [part.strip() for part in re.split(r"[、,，/]+", cleaned) if part.strip()]


def _static_2026_aliases() -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    pairs = [
        ("慕斯粉（液）", "慕斯粉"),
        ("彩色拉线膏", "拉线膏"),
        ("彩色拉线膏", "手绘拉线膏"),
        ("彩色拉线膏", "防晕染彩色拉线膏"),
        ("白色翻糖膏", "白色翻糖"),
        ("彩色翻糖膏", "彩色翻糖"),
        ("翻糖压片", "翻糖片"),
        ("翻糖压片", "彩色翻糖片"),
        ("巧克力脆皮酱", "脆皮酱"),
        ("红丝绒", "红丝绒液"),
        ("红丝绒", "红丝绒香精"),
        ("调味糖浆", "薄荷糖浆"),
        ("浅柔色素", "浅系色素"),
        ("浅柔色素", "浅色色素"),
        ("夹心果泥", "果泥"),
        ("夹心果泥", "果泥果酱"),
        ("夹心果泥", "免熬果泥果酱"),
        ("多肉果酱", "果馅（多肉）"),
        ("多肉果酱", "果馅（多肉果酱）"),
        ("夹心芋泥", "芋泥"),
        ("夹心芋泥", "免调味芋泥"),
        ("夹心脆", "巧克力夹心脆"),
        ("奶冻粉", "Q 弹奶冻粉"),
        ("奶冻粉", "Q弹奶冻粉"),
        ("奶冻粉", "晶冻粉"),
        ("水性色素", "胶状色素-小"),
        ("水性色素", "胶状色素-大"),
        ("油性色素", "油性色素-小"),
        ("油性色素", "油性色素-大"),
        ("盒装刀叉", "刀叉"),
        ("盒装刀叉", "2元盒装"),
        ("盒装刀叉", "2.5元盒装"),
        ("盒装刀叉", "5元盒装刀叉"),
        ("盒装刀叉", "1.1浆纸盘"),
        ("零卡糖", "0卡糖粉"),
    ]
    for standard, alias in pairs:
        _add_alias(aliases, standard, alias)
    return aliases


def _merge_alias_map(target: dict[str, set[str]], extra: dict[str, set[str]]) -> None:
    for name, aliases in extra.items():
        for alias in aliases:
            _add_alias(target, name, alias)


def _add_alias(aliases: dict[str, set[str]], standard: str, alias: str) -> None:
    standard = import_materials._clean_markdown(standard)
    alias = import_materials._clean_markdown(alias)
    if not standard or not alias:
        return
    aliases.setdefault(standard, set()).add(alias)
    aliases.setdefault(alias, set()).add(standard)


def _alias_sources(root: str, product_names: list[str], aliases: dict[str, set[str]]) -> list[str]:
    knowledge_dir = Path(root) / "资料" / "2026产品知识库"
    naming_path = knowledge_dir / "05_产品命名主数据与旧称对照.md"
    if not naming_path.exists():
        return []
    for name in product_names:
        names = {name, _base_name(name)}
        for candidate in names:
            related = aliases.get(candidate, set())
            if any(_name_key(alias) != _name_key(candidate) for alias in related):
                return [naming_path.name]
    return []


def _is_risky_2026_content(content: str) -> bool:
    compact = re.sub(r"\s+", "", content).lower()
    for phrase in RISKY_2026_PHRASES:
        if re.sub(r"\s+", "", phrase).lower() in compact:
            return True
    return False


def _candidate_keys(product_names: list[str], aliases: dict[str, set[str]] | None = None) -> set[str]:
    keys: set[str] = set()
    for name in product_names:
        for candidate in _candidate_names(name, aliases):
            key = _name_key(candidate)
            if key:
                keys.add(key)
    return keys


def _candidate_names(product_name: str, aliases: dict[str, set[str]] | None = None) -> set[str]:
    base = _base_name(product_name)
    candidates = {product_name, base}
    alias_map = _static_2026_aliases()
    if aliases:
        _merge_alias_map(alias_map, aliases)
    for name in list(candidates):
        candidates.update(alias_map.get(name, set()))
        candidates.update(alias_map.get(_base_name(name), set()))
    return candidates


def _entry_matches_product(entry_name: str, candidate_keys: set[str]) -> bool:
    entry_key = _name_key(_base_name(entry_name))
    raw_entry_key = _name_key(entry_name)
    if entry_key in candidate_keys or raw_entry_key in candidate_keys:
        return True
    for key in candidate_keys:
        if key and key in raw_entry_key:
            return True
    return False


def _merge_points(
    primary: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for point in [*primary, *extra]:
        point_type = point.get("point_type", "卖点")
        content = point.get("content", "")
        key = (import_materials._clean_markdown(point_type), import_materials._clean_markdown(content))
        if not key[1] or key in seen:
            continue
        merged.append({
            **point,
            "point_type": point_type,
            "content": content,
            "priority": len(merged) + 1,
        })
        seen.add(key)
    return merged


def _find_material_product(
    product_name: str,
    products: tuple[import_materials.ProductInput, ...],
) -> import_materials.ProductInput | None:
    requested = _name_key(product_name)

    for product in products:
        if _name_key(product.name) == requested:
            return product

    requested_base = _name_key(_base_name(product_name))
    for product in products:
        if _name_key(product.name) == requested_base:
            return product

    aliases = _aliases_by_product()
    for product in products:
        keys = {_name_key(product.name), *{_name_key(alias) for alias in aliases.get(product.name, [])}}
        if requested in keys or requested_base in keys:
            return product

    for product in products:
        product_key = _name_key(product.name)
        if product_key and (product_key in requested or requested in product_key):
            return product
    return None


def _resolve_price_rule_name(product_name: str) -> str:
    requested = _name_key(product_name)
    requested_base = _name_key(_base_name(product_name))
    candidates = list(import_materials.PRICE_RULES)

    for name in candidates:
        if _name_key(name) in {requested, requested_base}:
            return name

    aliases = _aliases_by_product()
    for name in candidates:
        keys = {_name_key(name), *{_name_key(alias) for alias in aliases.get(name, [])}}
        if requested in keys or requested_base in keys:
            return name

    for name in candidates:
        key = _name_key(name)
        if key and (key in requested or requested_base in key):
            return name
    return _base_name(product_name)


def _aliases_by_product() -> dict[str, list[str]]:
    aliases = dict(import_materials.MANUAL_ALIASES)
    aliases.setdefault("水性色素", []).append("水性色素（胶状）")
    aliases.setdefault("翻糖膏", []).append("防潮翻糖膏")
    return aliases


def _sku_from_price_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": row.get("product", ""),
        "spec": row.get("spec", ""),
        "price": _clean_price(row.get("tag_price")),
        "daily_price": _clean_price(row.get("daily_price")),
        "activity_prices": _clean_activity_prices(row.get("activity_prices", [])),
        "count": _clean_count(row.get("count")),
        "category": row.get("category", ""),
    }


def _override_sku(rule_name: str, override: float) -> dict[str, Any]:
    return {
        "product": rule_name,
        "spec": "默认售价",
        "price": import_materials._round_price(override),
        "daily_price": None,
        "activity_prices": [],
        "count": None,
        "category": "",
    }


def _clean_activity_prices(activity_prices: Any) -> list[dict[str, Any]]:
    if not isinstance(activity_prices, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for activity in activity_prices:
        if not isinstance(activity, dict):
            continue
        item = {
            "mechanism": activity.get("mechanism", ""),
            "tag_price": _clean_price(activity.get("tag_price")),
            "discount": _clean_activity_text(activity.get("discount", "")),
            "coupon": _clean_activity_text(activity.get("coupon", "")),
            "activity_price": _clean_price(activity.get("activity_price")),
            "final_price": _clean_price(activity.get("final_price")),
            "unit_price": _clean_price(activity.get("unit_price")),
            "single_activity": _clean_activity_text(activity.get("single_activity", "")),
            "count": _clean_count(activity.get("count")),
        }
        if item["tag_price"] is None and item["activity_price"] is None and item["final_price"] is None:
            continue
        cleaned.append(item)
    return cleaned


def _clean_activity_text(value: Any) -> str:
    if value is None:
        return ""
    return import_materials._clean_markdown(str(value))


def _clean_price(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return import_materials._round_price(float(value))


def _clean_count(value: Any) -> int | float | None:
    if not isinstance(value, (int, float)):
        return None
    if abs(value - int(value)) < 0.0001:
        return int(value)
    return value


def _base_name(value: str) -> str:
    name = re.sub(r"[（(].*?[）)]", "", value or "")
    return name.strip()


def _name_key(value: str) -> str:
    return re.sub(r"[\s（）()、/\\-]+", "", value or "").lower()
