"""产品管理 API — CRUD + 搜索 + 筛选 + 文件上传"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Product, SellingPoint
from schemas import (
    ProductCreate, ProductUpdate, ProductOut,
    ProductListItem, SellingPointOut, ApiResponse
)
from typing import List, Optional
import os
import shutil
from services.product_detail import build_product_detail_payload

router = APIRouter()

# 产品文件存储目录
PRODUCT_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "product_files")
os.makedirs(PRODUCT_FILES_DIR, exist_ok=True)


@router.get("/", response_model=List[ProductListItem])
def list_products(
    category: Optional[str] = Query(None, description="品类筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    status: str = Query("active", description="状态"),
    db: Session = Depends(get_db),
):
    """获取产品列表，支持品类筛选和关键词搜索"""
    query = db.query(Product).filter(Product.status == status)

    if category:
        query = query.filter(Product.category == category)
    if search:
        search = search.strip()
    if search:
        query = query.filter(Product.name.contains(search))

    products = query.order_by(Product.created_at.desc()).all()

    result = []
    for p in products:
        sps = sorted(p.selling_points, key=lambda x: x.priority)
        summary = "；".join([f"[{sp.point_type}]{sp.content}" for sp in sps[:3]])
        item = ProductListItem(
            id=p.id,
            name=p.name,
            category=p.category,
            price=p.price,
            original_price=p.original_price,
            commission_rate=p.commission_rate,
            brand=p.brand,
            image_url=p.image_url,
            info_file=p.info_file,
            pending_fields=_normalize_pending_fields(p.pending_fields),
            status=p.status,
            selling_point_count=len(p.selling_points),
            selling_point_summary=summary if summary else "暂无卖点",
        )
        result.append(item)

    return result


@router.get("/categories", response_model=List[str])
def list_categories(db: Session = Depends(get_db)):
    """获取所有产品品类"""
    categories = db.query(Product.category).filter(
        Product.status == "active"
    ).distinct().order_by(Product.category).all()
    return [c[0] for c in categories]


# ========== RAG: 语义搜索 + 索引管理 ==========

@router.get("/search/semantic", response_model=List[ProductListItem])
def semantic_search_products(
    q: str = Query(..., description="自然语言搜索查询"),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None, description="品类筛选"),
    db: Session = Depends(get_db),
):
    """语义搜索产品——理解意图而非精确匹配关键词"""
    try:
        from vector_store.product_store import ProductVectorStore
        store = get_chroma_store()
        if not store.is_available:
            return list_products(search=q, category=category, status="active", db=db)

        pvs = ProductVectorStore()
        results = pvs.search(q, limit=limit, category_filter=category)
        if not results:
            return list_products(search=q, category=category, status="active", db=db)

        product_ids = [r["product_id"] for r in results]
        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        product_map = {p.id: p for p in products}

        out = []
        for r in results:
            p = product_map.get(r["product_id"])
            if not p:
                continue
            sps = sorted(p.selling_points, key=lambda sp: sp.priority)
            summary = "；".join([f"[{sp.point_type}]{sp.content}" for sp in sps[:3]])
            out.append(ProductListItem(
                id=p.id, name=p.name, category=p.category,
                price=p.price, original_price=p.original_price,
                commission_rate=p.commission_rate, brand=p.brand,
                image_url=p.image_url, info_file=p.info_file,
                pending_fields=_normalize_pending_fields(p.pending_fields),
                status=p.status, selling_point_count=len(p.selling_points),
                selling_point_summary=summary if summary else "暂无卖点",
            ))
        return out
    except Exception:
        return list_products(search=q, category=category, status="active", db=db)


@router.post("/reindex")
def reindex_products(db: Session = Depends(get_db)):
    """批量重建所有产品的向量索引"""
    try:
        from vector_store.product_store import ProductVectorStore
        pvs = ProductVectorStore()
        count = pvs.index_all_products(db)
        return ApiResponse(message=f"已重建 {count} 个产品的向量索引")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引重建失败: {e}")


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """获取产品详情（含卖点）"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    return product


@router.get("/{product_id}/detail")
def get_product_detail(product_id: int, db: Session = Depends(get_db)):
    """获取产品卡片弹窗详情（含资料卖点与 SKU 售价）。"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    return build_product_detail_payload(product)


@router.post("/", response_model=ProductOut)
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    """创建产品"""
    sps_data = data.selling_points
    product_data = data.model_dump(exclude={"selling_points"})

    product = Product(**product_data)
    db.add(product)
    db.flush()

    for sp in sps_data:
        selling_point = SellingPoint(product_id=product.id, **sp.model_dump())
        db.add(selling_point)

    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    """更新产品"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    _sync_product_index(product.id, db)
    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """删除产品"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    _delete_product_index(product_id)
    db.delete(product)
    db.commit()
    return ApiResponse(message="产品已删除")


# ========== 卖点管理 ==========
@router.get("/{product_id}/selling-points", response_model=List[SellingPointOut])
def get_selling_points(product_id: int, db: Session = Depends(get_db)):
    """获取产品卖点列表"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    return product.selling_points


@router.post("/{product_id}/selling-points", response_model=SellingPointOut)
def add_selling_point(
    product_id: int,
    point_type: str = Query(...),
    content: str = Query(...),
    priority: int = Query(0),
    db: Session = Depends(get_db),
):
    """添加产品卖点"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    sp = SellingPoint(
        product_id=product_id,
        point_type=point_type,
        content=content,
        priority=priority,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


@router.delete("/{product_id}/selling-points/{sp_id}")
def delete_selling_point(product_id: int, sp_id: int, db: Session = Depends(get_db)):
    """删除产品卖点"""
    sp = db.query(SellingPoint).filter(
        SellingPoint.id == sp_id,
        SellingPoint.product_id == product_id,
    ).first()
    if not sp:
        raise HTTPException(status_code=404, detail="卖点不存在")

    db.delete(sp)
    db.commit()
    return ApiResponse(message="卖点已删除")


# ========== 文件上传 ==========
@router.post("/{product_id}/upload")
async def upload_product_file(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """为产品上传资料文件（PDF/Word/图片等）"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 保存文件
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    safe_name = f"product_{product_id}_{file.filename}"
    file_path = os.path.join(PRODUCT_FILES_DIR, safe_name)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 更新数据库
    product.info_file = file_path
    db.commit()

    # 自动从资料中提取卖点
    from services.selling_point_extractor import extract_selling_points
    points = await extract_selling_points(file_path, product.name, product.category)

    if points:
        # 删除旧卖点
        db.query(SellingPoint).filter(SellingPoint.product_id == product_id).delete()
        # 写入新卖点
        for i, pt in enumerate(points):
            sp = SellingPoint(
                product_id=product_id,
                point_type=pt.get("point_type", "功效"),
                content=pt.get("content", ""),
                priority=pt.get("priority", i + 1),
            )
            db.add(sp)
        db.commit()
        return ApiResponse(
            message=f"文件已上传，并从资料中提取了 {len(points)} 条卖点",
            data={"file_path": file_path, "file_name": file.filename, "points_extracted": len(points)},
        )

    return ApiResponse(
        message=f"文件已上传",
        data={"file_path": file_path, "file_name": file.filename}
    )


@router.get("/{product_id}/download")
def download_product_file(product_id: int, db: Session = Depends(get_db)):
    """下载产品资料文件"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.info_file:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not os.path.exists(product.info_file):
        raise HTTPException(status_code=404, detail="文件已被删除")

    return FileResponse(product.info_file, filename=os.path.basename(product.info_file))


@router.delete("/{product_id}/file")
def delete_product_file(product_id: int, db: Session = Depends(get_db)):
    """删除产品资料文件"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    if product.info_file and os.path.exists(product.info_file):
        os.remove(product.info_file)

    product.info_file = None
    db.commit()
    return ApiResponse(message="文件已删除")


# ========== 卖点重整理 ==========
@router.post("/{product_id}/extract-points")
async def extract_points_from_file(product_id: int, db: Session = Depends(get_db)):
    """从产品资料文件中提取卖点，替换现有卖点"""
    from services.selling_point_extractor import extract_selling_points

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    if not product.info_file or not os.path.exists(product.info_file):
        raise HTTPException(status_code=400, detail="请先上传产品资料文件")

    # 提取卖点
    points = await extract_selling_points(
        product.info_file,
        product.name,
        product.category,
    )

    if not points:
        raise HTTPException(status_code=400, detail="未能从文件中提取到卖点，请检查文件内容")

    # 删除旧卖点
    db.query(SellingPoint).filter(SellingPoint.product_id == product_id).delete()

    # 写入新卖点
    for i, pt in enumerate(points):
        sp = SellingPoint(
            product_id=product_id,
            point_type=pt.get("point_type", "功效"),
            content=pt.get("content", ""),
            priority=pt.get("priority", i + 1),
        )
        db.add(sp)

    db.commit()
    return ApiResponse(
        message=f"已从资料中提取 {len(points)} 条卖点",
        data={"points": points},
    )


@router.post("/extract-all-points")
async def extract_all_points(db: Session = Depends(get_db)):
    """批量处理：所有有资料文件的产品重新整理卖点"""
    from services.selling_point_extractor import extract_selling_points

    products = db.query(Product).filter(
        Product.info_file.isnot(None)
    ).all()

    results = []
    for product in products:
        if not os.path.exists(product.info_file):
            results.append({"id": product.id, "name": product.name, "status": "文件不存在"})
            continue

        try:
            points = await extract_selling_points(
                product.info_file, product.name, product.category
            )
            if points:
                db.query(SellingPoint).filter(SellingPoint.product_id == product.id).delete()
                for i, pt in enumerate(points):
                    sp = SellingPoint(
                        product_id=product.id,
                        point_type=pt.get("point_type", "功效"),
                        content=pt.get("content", ""),
                        priority=pt.get("priority", i + 1),
                    )
                    db.add(sp)
                results.append({"id": product.id, "name": product.name, "status": f"已提取{len(points)}条"})
            else:
                results.append({"id": product.id, "name": product.name, "status": "未能提取"})
        except Exception as e:
            results.append({"id": product.id, "name": product.name, "status": f"失败: {e}"})

    db.commit()
    return ApiResponse(message=f"处理完成", data={"total": len(products), "results": results})


# ========== 索引同步辅助 ==========

from vector_store import get_chroma_store


def _sync_product_index(product_id: int, db: Session):
    """同步产品到 ChromaDB"""
    try:
        from vector_store.product_store import ProductVectorStore
        store = get_chroma_store()
        if not store.is_available:
            return
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and product.status == "active":
            ProductVectorStore().index_product(product, db)
    except Exception:
        pass


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


def _delete_product_index(product_id: int):
    """从 ChromaDB 删除产品索引"""
    try:
        from vector_store.product_store import ProductVectorStore
        ProductVectorStore().delete_embedding(product_id)
    except Exception:
        pass
