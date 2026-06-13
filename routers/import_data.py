"""数据导入 API — CSV/Excel 批量导入产品"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Product, SellingPoint
from schemas import ImportResult, ApiResponse
import csv
import io
import os
from config import UPLOAD_DIR

router = APIRouter()


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

    content = await file.read()
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

    content = await file.read()
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
