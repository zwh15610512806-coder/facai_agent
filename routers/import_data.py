"""数据导入 API — CSV/Excel 批量导入产品"""
import asyncio
import csv
import io
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import MAX_UPLOAD_SIZE, UPLOAD_DIR
from database import SessionLocal, get_db
from models import Product, SellingPoint
from schemas import ApiResponse, ImportResult
from services import task_queue
from services.bounded_executor import WorkQueueFull, run_blocking
from services.product_markdown_importer import (
    PENDING_LABEL,
    decode_markdown_bytes,
    normalize_product_name,
    parse_product_markdown,
)
from services.product_price_extractor import apply_product_price_metadata
from services.upload_limits import read_upload_bytes
from services.upload_validation import UploadPolicy, UploadValidationError, validate_upload

router = APIRouter()

PRODUCT_TABLE_POLICY = UploadPolicy(
    extensions=frozenset({".csv", ".xlsx"}),
    max_bytes=MAX_UPLOAD_SIZE,
    max_uncompressed_bytes=50 * 1024 * 1024,
    max_rows=20_000,
    max_columns=200,
)

PRODUCT_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "product_files")
os.makedirs(PRODUCT_FILES_DIR, exist_ok=True)

LOCAL_PRODUCT_SOURCE_DIR = os.getenv(
    "LOCAL_PRODUCT_SOURCE_DIR",
    r"\\192.168.0.118\法采共享盘2026\产品资料库",
)
LOCAL_PRODUCT_SCAN_SESSION_FACTORY = SessionLocal
LOCAL_PRODUCT_SCAN_ERROR_LIMIT = 50
MAX_MARKDOWN_UPLOAD_FILES = int(os.getenv("MAX_MARKDOWN_UPLOAD_FILES", "20"))
LOCAL_PRODUCT_STRUCTURED_EXTENSIONS = {".md", ".markdown", ".csv", ".xlsx"}
LOCAL_PRODUCT_ATTACHMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg"}

_local_product_scan_lock = threading.RLock()
_local_product_scan_state = {
    "is_running": False,
    "source_dir": LOCAL_PRODUCT_SOURCE_DIR,
    "recursive": True,
    "total": 0,
    "processed": 0,
    "created": 0,
    "updated": 0,
    "attached": 0,
    "skipped": 0,
    "unsupported": 0,
    "error_count": 0,
    "errors": [],
    "ids": [],
    "started_at": None,
    "finished_at": None,
    "message": "待扫描",
    "job_id": None,
}


# 导入模板字段说明
IMPORT_FIELDS = [
    "name(产品名称*)",
    "category(品类*)",
    "price(售价*)",
    "original_price(原价)",
    "commission_rate(佣金比例)",
    "brand(品牌)",
    "description(产品描述)",
    "selling_point_type(卖点类型)",
    "selling_point_content(卖点话术)",
    "selling_point_priority(卖点优先级)",
]


@router.get("/template")
def download_template():
    """下载CSV导入模板"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    template_path = os.path.join(UPLOAD_DIR, "import_template.csv")

    with open(template_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(IMPORT_FIELDS)
        writer.writerow([
            "示例精华液", "美妆护肤", "89", "299", "30", "姿研堂",
            "含玻尿酸+胶原蛋白双肽，深层补水抗皱",
            "功效", "3重玻尿酸，28天淡化细纹", "1"
        ])
        writer.writerow([
            "示例精华液", "美妆护肤", "89", "299", "30", "姿研堂",
            "", "性价比", "专柜同品质，价格只要大牌的1/3", "2"
        ])

    return FileResponse(
        template_path,
        media_type="text/csv",
        filename="product_import_template.csv",
    )


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """导入CSV文件"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持CSV文件")

    content = await read_upload_bytes(file, max_bytes=MAX_UPLOAD_SIZE)
    try:
        await run_blocking(validate_upload, file.filename or "products.csv", content, PRODUCT_TABLE_POLICY)
        result, _ids = await run_blocking(_import_csv_content, content, db)
    except WorkQueueFull as exc:
        raise HTTPException(status_code=503, detail="文件解析任务繁忙，请稍后重试") from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return result


@router.post("/excel", response_model=ImportResult)
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """导入Excel文件(.xlsx)"""
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持Excel文件(.xlsx)")

    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="需要安装 openpyxl 和 pandas")

    content = await read_upload_bytes(file, max_bytes=MAX_UPLOAD_SIZE)
    try:
        await run_blocking(validate_upload, file.filename or "products.xlsx", content, PRODUCT_TABLE_POLICY)
        result, _ids = await run_blocking(_import_excel_content, content, db)
    except WorkQueueFull as exc:
        raise HTTPException(status_code=503, detail="文件解析任务繁忙，请稍后重试") from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return result


# ========== 辅助函数 ==========
@router.post("/markdown")
async def import_markdown_products(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Import one or more Markdown product files as new or updated products."""
    result: dict[str, Any] = {
        "total": len(files or []),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "warnings": [],
        "errors": [],
        "products": [],
    }

    if not files:
        result["errors"].append("未选择 Markdown 文件")
        return result
    if len(files) > MAX_MARKDOWN_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"单次最多上传 {MAX_MARKDOWN_UPLOAD_FILES} 个 Markdown 文件",
        )

    for upload in files:
        filename = upload.filename or "product.md"
        if not filename.lower().endswith((".md", ".markdown")):
            result["skipped"] += 1
            result["errors"].append(f"{filename}: 仅支持 .md/.markdown 文件")
            continue

        try:
            content = await read_upload_bytes(upload, max_bytes=MAX_UPLOAD_SIZE)
            item = _import_markdown_product_content(filename, content, db)
            result[item["action_count"]] += 1
            if item.get("warning"):
                result["warnings"].append(item["warning"])
            result["products"].append(item["product"])
        except HTTPException:
            raise
        except ValueError as exc:
            db.rollback()
            result["skipped"] += 1
            result["errors"].append(f"{filename}: {exc}")
        except Exception as exc:
            db.rollback()
            result["skipped"] += 1
            result["errors"].append(f"{filename}: 导入失败 - {exc}")

    return result


def _decode_csv_bytes(content: bytes) -> str | None:
    for encoding in ["utf-8-sig", "utf-8", "gbk", "gb2312"]:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _sync_product_ids(product_ids: list[int], db: Session) -> None:
    for product_id in product_ids:
        _sync_product_index(product_id, db)


def _import_csv_content(content: bytes, db: Session) -> tuple[ImportResult, list[int]]:
    result = ImportResult()
    product_ids: list[int] = []

    try:
        text = _decode_csv_bytes(content)
        if text is None:
            result.errors.append("无法识别文件编码，请使用UTF-8编码")
            return result, product_ids

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

        product_groups = {}
        for i, row in enumerate(rows):
            name = (row.get("name(产品名称*)") or row.get("name") or "").strip()
            if not name:
                result.errors.append(f"第{i+2}行：产品名称为空，已跳过")
                continue

            if name not in product_groups:
                product_groups[name] = {
                    "rows": [],
                    "data": {
                        "name": name,
                        "category": row.get("category(品类*)") or row.get("category", ""),
                        "price": float(row.get("price(售价*)") or row.get("price", 0)),
                        "original_price": _parse_float(row.get("original_price(原价)") or row.get("original_price")),
                        "commission_rate": _parse_float(row.get("commission_rate(佣金比例)") or row.get("commission_rate"), 0),
                        "brand": row.get("brand(品牌)") or row.get("brand", ""),
                        "description": row.get("description(产品描述)") or row.get("description", ""),
                    },
                }
            product_groups[name]["rows"].append(row)

        for name, group in product_groups.items():
            existing = db.query(Product).filter(Product.name == name).first()
            if existing:
                result.skipped += 1
                continue

            try:
                pdata = group["data"]
                if not pdata["category"] or not pdata["price"]:
                    result.errors.append(f"产品 '{name}'：品类或价格缺失，已跳过")
                    continue

                product = Product(**pdata)
                db.add(product)
                db.flush()

                for row in group["rows"]:
                    sp_type = row.get("selling_point_type(卖点类型)") or row.get("selling_point_type", "")
                    sp_content = row.get("selling_point_content(卖点话术)") or row.get("selling_point_content", "")

                    if sp_type and sp_content:
                        sp_priority = _parse_int(
                            row.get("selling_point_priority(卖点优先级)") or row.get("selling_point_priority"), 0
                        )
                        db.add(SellingPoint(
                            product_id=product.id,
                            point_type=sp_type,
                            content=sp_content,
                            priority=sp_priority,
                        ))

                product_ids.append(product.id)
                result.success += 1
            except Exception as e:
                result.errors.append(f"产品 '{name}'：导入失败 - {str(e)}")

        db.commit()
        result.total = result.success + result.skipped
        _sync_product_ids(product_ids, db)
    except Exception as e:
        db.rollback()
        result.errors.append(f"文件解析失败: {str(e)}")

    return result, product_ids


def _import_excel_content(content: bytes, db: Session) -> tuple[ImportResult, list[int]]:
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="需要安装 openpyxl 和 pandas")

    result = ImportResult()
    product_ids: list[int] = []

    try:
        df = pd.read_excel(io.BytesIO(content))

        col_map = {}
        for col in df.columns:
            col_clean = str(col).strip()
            if "产品名称" in col_clean or col_clean.lower() == "name":
                col_map[col] = "name"
            elif "品类" in col_clean or col_clean.lower() == "category":
                col_map[col] = "category"
            elif "售价" in col_clean or "价格" in col_clean or col_clean.lower() == "price":
                col_map[col] = "price"
            elif "原价" in col_clean or col_clean.lower() == "original_price":
                col_map[col] = "original_price"
            elif "佣金" in col_clean or col_clean.lower() == "commission_rate":
                col_map[col] = "commission_rate"
            elif "品牌" in col_clean or col_clean.lower() == "brand":
                col_map[col] = "brand"
            elif "描述" in col_clean or col_clean.lower() == "description":
                col_map[col] = "description"
            elif "卖点类型" in col_clean:
                col_map[col] = "selling_point_type"
            elif "卖点话术" in col_clean or "卖点内容" in col_clean:
                col_map[col] = "selling_point_content"
            elif "优先级" in col_clean:
                col_map[col] = "selling_point_priority"

        df = df.rename(columns=col_map)

        if "name" not in df.columns:
            result.errors.append("未找到产品名称列")
            return result, product_ids

        for name, group in df.groupby("name"):
            name = str(name).strip()
            if not name:
                continue

            first_row = group.iloc[0]
            try:
                category = _safe_text(first_row.get("category"))
                price = _safe_float(first_row.get("price"))
                original_price = _safe_float(first_row.get("original_price"))
                commission_rate = _safe_float(first_row.get("commission_rate")) if "commission_rate" in group.columns else None
                brand = _safe_text(first_row.get("brand")) or None
                description = _safe_text(first_row.get("description")) or None
                product = db.query(Product).filter(Product.name == name).first()

                if product is None and (not category or not price):
                    result.errors.append(f"产品 '{name}'：品类或价格缺失，已跳过")
                    continue

                if product is None:
                    product = Product(
                        name=name,
                        category=category,
                        price=price or 0,
                        original_price=original_price,
                        commission_rate=commission_rate or 0,
                        brand=brand,
                        description=description,
                    )
                    db.add(product)
                    db.flush()
                else:
                    _update_existing_product_from_excel_row(
                        product,
                        category=category,
                        price=price,
                        original_price=original_price,
                        commission_rate=commission_rate,
                        brand=brand,
                        description=description,
                    )

                for _, row in group.iterrows():
                    sp_type = str(row.get("selling_point_type", "")).strip() if pd.notna(row.get("selling_point_type")) else ""
                    sp_content = str(row.get("selling_point_content", "")).strip() if pd.notna(row.get("selling_point_content")) else ""

                    if sp_type and sp_content:
                        db.add(SellingPoint(
                            product_id=product.id,
                            point_type=sp_type,
                            content=sp_content,
                            priority=_safe_int(row.get("selling_point_priority"), 0),
                        ))

                product_ids.append(product.id)
                result.success += 1
            except Exception as e:
                result.errors.append(f"产品 '{name}'：导入失败 - {str(e)}")

        db.commit()
        result.total = result.success + result.skipped
        _sync_product_ids(product_ids, db)
    except Exception as e:
        db.rollback()
        result.errors.append(f"文件解析失败: {str(e)}")

    return result, product_ids


def _import_markdown_product_content(filename: str, content: bytes, db: Session) -> dict[str, Any]:
    text = decode_markdown_bytes(content)
    if text is None:
        raise ValueError("无法识别文件编码，请使用 UTF-8")

    parsed = parse_product_markdown(text, filename=filename)
    product = _find_existing_product(db, parsed.name)
    action = "updated" if product else "created"
    action_count = "updated" if product else "created"
    if product is None:
        product = Product(
            name=parsed.name,
            category=parsed.category,
            price=parsed.price,
            original_price=parsed.original_price,
            commission_rate=parsed.commission_rate or 0.0,
            brand=parsed.brand,
            description=parsed.description,
            image_url=parsed.image_url,
            status="active",
            pending_fields=list(parsed.pending_fields),
        )
        db.add(product)
        db.flush()
        updated_fields = ["name", "category", "price"]
        if parsed.brand:
            updated_fields.append("brand")
        if parsed.description:
            updated_fields.append("description")
        if parsed.image_url:
            updated_fields.append("image_url")
        if parsed.original_price is not None:
            updated_fields.append("original_price")
        if parsed.commission_rate is not None:
            updated_fields.append("commission_rate")
    else:
        updated_fields = _apply_markdown_update(product, parsed)

    product.info_file = _save_markdown_product_file(product.id, filename, content)
    if "info_file" not in updated_fields:
        updated_fields.append("info_file")

    if parsed.selling_points:
        db.query(SellingPoint).filter(SellingPoint.product_id == product.id).delete()
        for point in parsed.selling_points:
            db.add(SellingPoint(
                product_id=product.id,
                point_type=point.point_type,
                content=point.content,
                priority=point.priority,
            ))
        if "selling_points" not in updated_fields:
            updated_fields.append("selling_points")

    pending_fields = _normalize_pending_fields(product.pending_fields)
    warning = f"{filename}: {', '.join(pending_fields)} 待更新" if pending_fields else ""

    db.commit()
    db.refresh(product)
    _sync_product_index(product.id, db)
    return {
        "id": product.id,
        "action": action,
        "action_count": action_count,
        "warning": warning,
        "product": {
            "id": product.id,
            "name": product.name,
            "action": action,
            "updated_fields": updated_fields,
            "pending_fields": _normalize_pending_fields(product.pending_fields),
        },
    }


def _find_existing_product(db: Session, product_name: str) -> Product | None:
    target = normalize_product_name(product_name)
    if not target:
        return None
    for product in db.query(Product).all():
        if normalize_product_name(product.name) == target:
            return product
    return None


def _apply_markdown_update(product: Product, parsed) -> list[str]:
    updated_fields: list[str] = []
    pending_fields = set(_normalize_pending_fields(product.pending_fields))

    if parsed.name and product.name != parsed.name:
        product.name = parsed.name
        updated_fields.append("name")

    field_map = {
        "category": parsed.category,
        "price": parsed.price,
        "original_price": parsed.original_price,
        "commission_rate": parsed.commission_rate,
        "brand": parsed.brand,
        "description": parsed.description,
        "image_url": parsed.image_url,
    }
    for field, value in field_map.items():
        if field not in parsed.provided_fields:
            continue
        if value is None or value == "":
            continue
        if getattr(product, field) != value:
            setattr(product, field, value)
            updated_fields.append(field)
        pending_fields.discard(field)

    for field in parsed.pending_fields:
        if field in pending_fields:
            continue
        if field == "category" and not product.category:
            product.category = PENDING_LABEL
            pending_fields.add(field)
        elif field == "price" and product.price is None:
            product.price = 0.0
            pending_fields.add(field)

    product.pending_fields = sorted(pending_fields)
    return updated_fields


def _update_existing_product_from_excel_row(
    product: Product,
    *,
    category: str,
    price: float | None,
    original_price: float | None,
    commission_rate: float | None,
    brand: str | None,
    description: str | None,
) -> list[str]:
    updated_fields: list[str] = []
    pending_fields = set(_normalize_pending_fields(product.pending_fields))

    if category and product.category != category:
        product.category = category
        updated_fields.append("category")
        pending_fields.discard("category")
    if price is not None and price > 0:
        updated_fields.extend(apply_product_price_metadata(product, {"price": price}))
        pending_fields = set(_normalize_pending_fields(product.pending_fields))
    if original_price is not None and original_price > 0:
        updated_fields.extend(apply_product_price_metadata(product, {"original_price": original_price}))
        pending_fields = set(_normalize_pending_fields(product.pending_fields))
    if commission_rate is not None and product.commission_rate != commission_rate:
        product.commission_rate = commission_rate
        updated_fields.append("commission_rate")
    if brand and product.brand != brand:
        product.brand = brand
        updated_fields.append("brand")
    if description and product.description != description:
        product.description = description
        updated_fields.append("description")

    product.pending_fields = sorted(pending_fields)
    return list(dict.fromkeys(updated_fields))


def _normalize_pending_fields(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _save_markdown_product_file(product_id: int, filename: str, content: bytes) -> str:
    safe_name = os.path.basename(filename or "product.md")
    safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", safe_name).strip("._")
    if not safe_name:
        safe_name = "product.md"
    path = os.path.join(PRODUCT_FILES_DIR, f"product_{product_id}_{safe_name}")
    with open(path, "wb") as handle:
        handle.write(content)
    return path


def _sync_product_index(product_id: int, db: Session):
    from services.vector_sync import ensure_and_process_vector_sync

    status = ensure_and_process_vector_sync(db, "product", product_id, "upsert")
    return "synced" if status == "succeeded" else "pending"


def _reset_local_product_scan_state() -> None:
    with _local_product_scan_lock:
        _local_product_scan_state.update({
            "is_running": False,
            "source_dir": LOCAL_PRODUCT_SOURCE_DIR,
            "recursive": True,
            "total": 0,
            "processed": 0,
            "created": 0,
            "updated": 0,
            "attached": 0,
            "skipped": 0,
            "unsupported": 0,
            "error_count": 0,
            "errors": [],
            "ids": [],
            "started_at": None,
            "finished_at": None,
            "message": "待扫描",
            "job_id": None,
        })


def _local_product_scan_snapshot() -> dict:
    with _local_product_scan_lock:
        snapshot = dict(_local_product_scan_state)
        snapshot["errors"] = list(_local_product_scan_state["errors"])
        snapshot["ids"] = list(_local_product_scan_state["ids"])
    from services.job_runs import latest_job
    snapshot["job_run"] = latest_job("local_product_scan")
    return snapshot


def _update_local_product_scan_state(**changes) -> None:
    with _local_product_scan_lock:
        _local_product_scan_state.update(changes)
        snapshot = dict(_local_product_scan_state)
    if snapshot.get("job_id"):
        from services.job_runs import update_job
        update_job(
            snapshot["job_id"],
            current=snapshot.get("processed", 0),
            total=snapshot.get("total", 0),
            message=snapshot.get("message", ""),
        )


def _append_local_product_scan_error(message: str) -> None:
    with _local_product_scan_lock:
        _local_product_scan_state["error_count"] += 1
        if len(_local_product_scan_state["errors"]) < LOCAL_PRODUCT_SCAN_ERROR_LIMIT:
            _local_product_scan_state["errors"].append(message)


def _mark_local_product_file_processed(message: str = "", **increments) -> None:
    with _local_product_scan_lock:
        _local_product_scan_state["processed"] += 1
        for key, value in increments.items():
            if key == "ids":
                existing = set(_local_product_scan_state["ids"])
                for product_id in value:
                    if product_id not in existing:
                        _local_product_scan_state["ids"].append(product_id)
                        existing.add(product_id)
            else:
                _local_product_scan_state[key] += int(value or 0)
        if message:
            _local_product_scan_state["message"] = message
        snapshot = dict(_local_product_scan_state)
    if snapshot.get("job_id"):
        from services.job_runs import update_job
        update_job(
            snapshot["job_id"],
            current=snapshot.get("processed", 0),
            total=snapshot.get("total", 0),
            message=snapshot.get("message", ""),
        )


def _relative_local_product_path(path: Path, source_dir: Path) -> str:
    try:
        relative_path = os.path.relpath(str(path), str(source_dir))
    except ValueError:
        relative_path = path.name
    return relative_path.replace("\\", "/")


def _discover_local_product_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(source_dir):
        dir_names.sort()
        for name in sorted(file_names):
            if name.startswith("~$"):
                continue
            files.append(Path(current_root) / name)
    files.sort(key=lambda item: _relative_local_product_path(item, source_dir).lower())
    return files


def _safe_local_product_file_path(product_id: int, filename: str) -> str:
    safe_name = os.path.basename((filename or "product_file").replace("\\", "/")).strip()
    safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", safe_name).strip("._-")
    if not safe_name:
        safe_name = "product_file"
    base, ext = os.path.splitext(safe_name)
    base = (base or "product_file")[:120]
    ext = ext[:32]
    root = os.path.abspath(PRODUCT_FILES_DIR)
    os.makedirs(root, exist_ok=True)
    candidate = os.path.abspath(os.path.join(root, f"product_{product_id}_{base}{ext}"))
    index = 2
    while os.path.exists(candidate):
        candidate = os.path.abspath(os.path.join(root, f"product_{product_id}_{base}_{index}{ext}"))
        index += 1
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid local product filename")
    return candidate


def _normalized_product_key(value: str) -> str:
    return normalize_product_name(value or "")


def _match_product_for_local_file(path: Path, source_dir: Path, db: Session) -> tuple[Product | None, str]:
    products = db.query(Product).filter(Product.status == "active").all()
    if not products:
        return None, "没有可匹配的产品"

    relative_path = _relative_local_product_path(path, source_dir)
    rel_parts = [part for part in Path(relative_path).parts if part]
    exact_tokens = [path.stem]
    if path.parent != source_dir:
        exact_tokens.append(path.parent.name)

    for token in exact_tokens:
        token_key = _normalized_product_key(token)
        if not token_key:
            continue
        matches = [product for product in products if _normalized_product_key(product.name) == token_key]
        if len(matches) == 1:
            return matches[0], ""
        if len(matches) > 1:
            return None, f"匹配到多个产品：{token}"

    candidates: list[tuple[int, Product]] = []
    token_keys = [_normalized_product_key(path.stem)]
    token_keys.extend(_normalized_product_key(part) for part in rel_parts[:-1])
    token_keys = [key for key in token_keys if len(key) >= 2]
    for product in products:
        product_key = _normalized_product_key(product.name)
        if len(product_key) < 2:
            continue
        if any(product_key in token_key or token_key in product_key for token_key in token_keys):
            candidates.append((len(product_key), product))

    if not candidates:
        return None, "未匹配到产品"
    candidates.sort(key=lambda item: item[0], reverse=True)
    top_score = candidates[0][0]
    top_products = [product for score, product in candidates if score == top_score]
    unique = {product.id: product for product in top_products}
    if len(unique) == 1:
        return next(iter(unique.values())), ""
    return None, "匹配结果有歧义"


def _existing_selling_point_keys(product_id: int, db: Session) -> set[tuple[str, str]]:
    points = db.query(SellingPoint).filter(SellingPoint.product_id == product_id).all()
    return {
        (str(point.point_type or "").strip(), str(point.content or "").strip())
        for point in points
    }


async def _append_extracted_points(file_path: str, product: Product, db: Session) -> int:
    try:
        from services.selling_point_extractor import extract_selling_points

        points = await extract_selling_points(file_path, product.name, product.category)
    except Exception as exc:
        _append_local_product_scan_error(f"{os.path.basename(file_path)}: 卖点提取失败 - {exc}")
        return 0

    if not points:
        return 0

    existing = _existing_selling_point_keys(product.id, db)
    max_priority = db.query(SellingPoint).filter(SellingPoint.product_id == product.id).count()
    added = 0
    for point in points:
        point_type = str(point.get("point_type") or "卖点").strip() or "卖点"
        content = str(point.get("content") or "").strip()
        if not content:
            continue
        key = (point_type, content)
        if key in existing:
            continue
        max_priority += 1
        db.add(SellingPoint(
            product_id=product.id,
            point_type=point_type,
            content=content,
            priority=_parse_int(point.get("priority"), max_priority),
        ))
        existing.add(key)
        added += 1
    return added


async def _attach_local_product_file(path: Path, source_dir: Path, db: Session) -> tuple[str, int | None, str]:
    product, reason = _match_product_for_local_file(path, source_dir, db)
    relative_path = _relative_local_product_path(path, source_dir)
    if product is None:
        return "skipped", None, f"{relative_path}: {reason}"
    if product.info_file:
        return "skipped", product.id, f"{relative_path}: 产品已有资料文件，未覆盖"

    file_path = _safe_local_product_file_path(product.id, path.name)
    shutil.copyfile(path, file_path)
    product.info_file = file_path
    await _append_extracted_points(file_path, product, db)
    db.commit()
    _sync_product_index(product.id, db)
    return "attached", product.id, f"已挂载资料：{relative_path}"


def _apply_tabular_scan_result(relative_path: str, result: ImportResult, product_ids: list[int]) -> None:
    for error in result.errors:
        _append_local_product_scan_error(f"{relative_path}: {error}")
    message = f"已处理：{relative_path}"
    _mark_local_product_file_processed(
        message,
        created=result.success,
        skipped=result.skipped,
        ids=product_ids,
    )


def _import_product_input(product_input, db: Session) -> dict[str, Any]:
    product = _find_existing_product(db, product_input.name)
    action = "updated" if product else "created"
    if product is None:
        product = Product(
            name=product_input.name,
            category=product_input.category,
            price=product_input.price or 0.0,
            original_price=product_input.original_price,
            commission_rate=0.0,
            brand=product_input.brand,
            description=product_input.description,
            status="active",
        )
        db.add(product)
    else:
        product.name = product_input.name
        product.category = product_input.category
        product.price = product_input.price or 0.0
        product.original_price = product_input.original_price
        product.commission_rate = 0.0
        product.brand = product_input.brand
        product.description = product_input.description
        product.status = "active"

    db.flush()

    content = (product_input.section_text or product_input.description or product_input.name).encode("utf-8")
    product.info_file = _save_markdown_product_file(product.id, f"{product_input.name}.md", content)

    db.query(SellingPoint).filter(SellingPoint.product_id == product.id).delete()
    for point in product_input.selling_points:
        db.add(SellingPoint(product_id=product.id, **point))

    db.commit()
    db.refresh(product)
    _sync_product_index(product.id, db)
    return {"id": product.id, "action": action}


def _find_2026_knowledge_dirs(source_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for current_root, dir_names, file_names in os.walk(source_dir):
        dir_names.sort()
        names = set(file_names)
        if "00_产品知识总索引.md" in names and "05_产品命名主数据与旧称对照.md" in names:
            dirs.append(Path(current_root))
    return dirs


def _knowledge_dir_for_path(path: Path, knowledge_dirs: list[Path]) -> Path | None:
    for knowledge_dir in knowledge_dirs:
        try:
            path.resolve().relative_to(knowledge_dir.resolve())
            return knowledge_dir
        except ValueError:
            continue
    return None


def _import_2026_knowledge_package(knowledge_dir: Path, db: Session) -> dict[str, Any]:
    import import_materials

    products = import_materials.parse_2026_product_knowledge(knowledge_dir)
    created = 0
    updated = 0
    ids: list[int] = []
    for product_input in products:
        item = _import_product_input(product_input, db)
        ids.append(item["id"])
        if item["action"] == "created":
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated, "ids": ids}


async def _scan_local_products(*, source_dir: Path, db: Session) -> None:
    files = _discover_local_product_files(source_dir)
    _update_local_product_scan_state(total=len(files), message=f"发现 {len(files)} 个文件")
    if not files:
        _update_local_product_scan_state(message="未发现可识别文件")
        return

    knowledge_dirs = _find_2026_knowledge_dirs(source_dir)
    processed_knowledge_dirs: set[Path] = set()

    for path in files:
        relative_path = _relative_local_product_path(path, source_dir)
        ext = path.suffix.lower()
        try:
            stat = path.stat()
            if stat.st_size > MAX_UPLOAD_SIZE:
                raise ValueError(f"文件过大，请控制在 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB 以内。")

            knowledge_dir = _knowledge_dir_for_path(path, knowledge_dirs)
            if knowledge_dir is not None:
                if knowledge_dir not in processed_knowledge_dirs:
                    result = _import_2026_knowledge_package(knowledge_dir, db)
                    processed_knowledge_dirs.add(knowledge_dir)
                    _mark_local_product_file_processed(
                        f"已同步 2026 产品知识包：{knowledge_dir.name}",
                        created=result["created"],
                        updated=result["updated"],
                        ids=result["ids"],
                    )
                else:
                    _mark_local_product_file_processed(f"已由 2026 产品知识包处理：{relative_path}", skipped=1)
                continue

            if ext in {".md", ".markdown"}:
                item = _import_markdown_product_content(path.name, path.read_bytes(), db)
                _mark_local_product_file_processed(
                    f"已导入：{relative_path}",
                    **{item["action_count"]: 1},
                    ids=[item["id"]],
                )
            elif ext == ".csv":
                result, product_ids = _import_csv_content(path.read_bytes(), db)
                _apply_tabular_scan_result(relative_path, result, product_ids)
            elif ext == ".xlsx":
                result, product_ids = _import_excel_content(path.read_bytes(), db)
                _apply_tabular_scan_result(relative_path, result, product_ids)
            elif ext in LOCAL_PRODUCT_ATTACHMENT_EXTENSIONS:
                status, product_id, message = await _attach_local_product_file(path, source_dir, db)
                if status == "attached":
                    _mark_local_product_file_processed(message, attached=1, ids=[product_id] if product_id else [])
                else:
                    _mark_local_product_file_processed(message, skipped=1)
            else:
                _mark_local_product_file_processed(f"不支持的文件类型：{relative_path}", unsupported=1)
        except Exception as exc:
            db.rollback()
            _append_local_product_scan_error(f"{relative_path}: {exc}")
            _mark_local_product_file_processed(f"跳过：{relative_path}", skipped=1)


def _run_local_product_scan(source_dir: str, job_id: int | None = None) -> None:
    db = LOCAL_PRODUCT_SCAN_SESSION_FACTORY()
    terminal_status = "succeeded"
    terminal_error = ""
    try:
        asyncio.run(_scan_local_products(source_dir=Path(source_dir), db=db))
        snapshot = _local_product_scan_snapshot()
        if snapshot["total"] == 0:
            message = "未发现可识别文件"
        else:
            message = (
                f"扫描完成：新增 {snapshot['created']}，更新 {snapshot['updated']}，"
                f"附件 {snapshot['attached']}，跳过 {snapshot['skipped']}，"
                f"不支持 {snapshot['unsupported']}，错误 {snapshot['error_count']}"
            )
        _update_local_product_scan_state(message=message)
    except Exception as exc:
        terminal_status = "failed"
        terminal_error = str(exc)
        _append_local_product_scan_error(str(exc))
        _update_local_product_scan_state(message=f"扫描失败：{exc}")
    finally:
        db.close()
        _update_local_product_scan_state(
            is_running=False,
            finished_at=datetime.now().replace(microsecond=0).isoformat(),
        )
        if job_id:
            from services.job_runs import finish_job
            snapshot = _local_product_scan_snapshot()
            finish_job(
                job_id,
                status=terminal_status,
                message=snapshot.get("message", ""),
                details={key: snapshot.get(key) for key in ("total", "processed", "created", "updated", "attached", "skipped", "unsupported", "error_count")},
                error_summary=terminal_error,
            )


def _run_local_product_scan_task(payload: dict) -> None:
    _run_local_product_scan(str(payload["source_dir"]), payload.get("job_id"))


task_queue.register_task_handler("local_product_scan", _run_local_product_scan_task)


@router.post("/scan-local-products")
def start_local_product_scan():
    """Start a background scan of the configured local product materials directory."""
    source_dir = LOCAL_PRODUCT_SOURCE_DIR
    if not os.path.exists(source_dir):
        raise HTTPException(status_code=404, detail=f"路径不可访问：{source_dir}")

    with _local_product_scan_lock:
        if _local_product_scan_state["is_running"]:
            return ApiResponse(message="本地产品资料扫描正在运行", data=_local_product_scan_snapshot())
        from services.job_runs import start_job
        job_id = start_job("local_product_scan", message="本地产品资料扫描启动中", details={"source_dir": source_dir})
        _local_product_scan_state.update({
            "is_running": True,
            "source_dir": source_dir,
            "recursive": True,
            "total": 0,
            "processed": 0,
            "created": 0,
            "updated": 0,
            "attached": 0,
            "skipped": 0,
            "unsupported": 0,
            "error_count": 0,
            "errors": [],
            "ids": [],
            "started_at": datetime.now().replace(microsecond=0).isoformat(),
            "finished_at": None,
            "message": "扫描启动中",
            "job_id": job_id,
        })

    task_payload = {"source_dir": source_dir, "job_id": job_id}
    if task_queue.task_worker_status()["alive"]:
        task_queue.enqueue_task("local_product_scan", task_payload, max_attempts=3)
    else:
        # Router-only test/dev apps do not run the main lifespan worker.
        threading.Thread(
            target=_run_local_product_scan_task,
            args=(task_payload,),
            name="facai-local-product-scan-fallback",
            daemon=True,
        ).start()
    return ApiResponse(message="本地产品资料扫描已启动", data=_local_product_scan_snapshot())


@router.get("/scan-local-products/status")
def local_product_scan_status():
    """Return the latest local product materials scan status."""
    return ApiResponse(message="ok", data=_local_product_scan_snapshot())


def _parse_float(value, default=None):
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_int(value, default=0):
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=None):
    import pandas as pd
    if pd.isna(value) or value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default=0):
    import pandas as pd
    if pd.isna(value) or value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _safe_text(value) -> str:
    import pandas as pd
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text
