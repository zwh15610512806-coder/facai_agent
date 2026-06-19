"""数据导入 API — CSV/Excel 批量导入产品"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Product, SellingPoint
from schemas import ImportResult, ApiResponse
from services.product_markdown_importer import (
    PENDING_LABEL,
    decode_markdown_bytes,
    normalize_product_name,
    parse_product_markdown,
)
import csv
import io
import os
import re
from typing import Any, List
from config import MAX_UPLOAD_SIZE, UPLOAD_DIR
from services.upload_limits import read_upload_bytes

router = APIRouter()

PRODUCT_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "product_files")
os.makedirs(PRODUCT_FILES_DIR, exist_ok=True)


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
    result = ImportResult()

    try:
        # 尝试多种编码
        text = None
        for encoding in ["utf-8-sig", "utf-8", "gbk", "gb2312"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            result.errors.append("无法识别文件编码，请使用UTF-8编码")
            return result

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

        # 按产品名称分组（同一产品的多行是不同卖点）
        product_groups = {}
        for i, row in enumerate(rows):
            name = row.get("name(产品名称*)") or row.get("name", "").strip()
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
                    "selling_points": [],
                }
            product_groups[name]["rows"].append(row)

        for name, group in product_groups.items():
            # 检查是否已存在
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

                # 导入卖点
                for row in group["rows"]:
                    sp_type = row.get("selling_point_type(卖点类型)") or row.get("selling_point_type", "")
                    sp_content = row.get("selling_point_content(卖点话术)") or row.get("selling_point_content", "")

                    if sp_type and sp_content:
                        sp_priority = _parse_int(
                            row.get("selling_point_priority(卖点优先级)") or row.get("selling_point_priority"), 0
                        )
                        sp = SellingPoint(
                            product_id=product.id,
                            point_type=sp_type,
                            content=sp_content,
                            priority=sp_priority,
                        )
                        db.add(sp)

                result.success += 1
            except Exception as e:
                result.errors.append(f"产品 '{name}'：导入失败 - {str(e)}")

        db.commit()
        result.total = result.success + result.skipped

    except Exception as e:
        result.errors.append(f"文件解析失败: {str(e)}")

    return result


@router.post("/excel", response_model=ImportResult)
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """导入Excel文件(.xlsx)"""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持Excel文件(.xlsx/.xls)")

    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="需要安装 openpyxl 和 pandas")

    content = await read_upload_bytes(file, max_bytes=MAX_UPLOAD_SIZE)
    result = ImportResult()

    try:
        df = pd.read_excel(io.BytesIO(content))

        # 标准化列名
        col_map = {}
        for col in df.columns:
            col_clean = col.strip()
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

        # 按产品分组
        if "name" not in df.columns:
            result.errors.append("未找到产品名称列")
            return result

        for name, group in df.groupby("name"):
            name = str(name).strip()
            if not name:
                continue

            existing = db.query(Product).filter(Product.name == name).first()
            if existing:
                result.skipped += 1
                continue

            first_row = group.iloc[0]
            try:
                product = Product(
                    name=name,
                    category=str(first_row.get("category", "")).strip(),
                    price=_safe_float(first_row.get("price", 0)),
                    original_price=_safe_float(first_row.get("original_price")),
                    commission_rate=_safe_float(first_row.get("commission_rate"), 0),
                    brand=str(first_row.get("brand", "")).strip() if pd.notna(first_row.get("brand")) else None,
                    description=str(first_row.get("description", "")).strip() if pd.notna(first_row.get("description")) else None,
                )

                if not product.category or not product.price:
                    result.errors.append(f"产品 '{name}'：品类或价格缺失，已跳过")
                    continue

                db.add(product)
                db.flush()

                for _, row in group.iterrows():
                    sp_type = str(row.get("selling_point_type", "")).strip() if pd.notna(row.get("selling_point_type")) else ""
                    sp_content = str(row.get("selling_point_content", "")).strip() if pd.notna(row.get("selling_point_content")) else ""

                    if sp_type and sp_content:
                        sp = SellingPoint(
                            product_id=product.id,
                            point_type=sp_type,
                            content=sp_content,
                            priority=_safe_int(row.get("selling_point_priority"), 0),
                        )
                        db.add(sp)

                result.success += 1
            except Exception as e:
                result.errors.append(f"产品 '{name}'：导入失败 - {str(e)}")

        db.commit()
        result.total = result.success + result.skipped

    except Exception as e:
        result.errors.append(f"文件解析失败: {str(e)}")

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

    for upload in files:
        filename = upload.filename or "product.md"
        if not filename.lower().endswith((".md", ".markdown")):
            result["skipped"] += 1
            result["errors"].append(f"{filename}: 仅支持 .md/.markdown 文件")
            continue

        try:
            content = await read_upload_bytes(upload, max_bytes=MAX_UPLOAD_SIZE)
            text = decode_markdown_bytes(content)
            if text is None:
                result["skipped"] += 1
                result["errors"].append(f"{filename}: 无法识别文件编码，请使用 UTF-8")
                continue

            parsed = parse_product_markdown(text, filename=filename)
            product = _find_existing_product(db, parsed.name)
            action = "updated" if product else "created"
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
                result["created"] += 1
            else:
                updated_fields = _apply_markdown_update(product, parsed)
                result["updated"] += 1

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
            if pending_fields:
                result["warnings"].append(f"{filename}: {', '.join(pending_fields)} 待更新")

            db.commit()
            db.refresh(product)
            _sync_product_index(product.id, db)
            result["products"].append({
                "id": product.id,
                "name": product.name,
                "action": action,
                "updated_fields": updated_fields,
                "pending_fields": _normalize_pending_fields(product.pending_fields),
            })
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            result["skipped"] += 1
            result["errors"].append(f"{filename}: 导入失败 - {exc}")

    return result


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
    try:
        from vector_store.product_store import ProductVectorStore

        product = db.query(Product).filter(Product.id == product_id).first()
        if product and product.status == "active":
            ProductVectorStore().index_product(product, db)
    except Exception:
        pass


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
