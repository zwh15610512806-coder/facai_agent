"""产品管理 API — CRUD + 搜索 + 筛选 + 文件上传"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import MAX_UPLOAD_SIZE
from database import get_db
from models import Product, SellingPoint
from schemas import (
    ProductCreate, ProductUpdate, ProductOut, ProductWriteOut,
    ProductListItem, SellingPointOut, SellingPointUpdate, ApiResponse
)
from typing import List, Optional
import mimetypes
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlencode
import import_materials
from services.product_detail import (
    HIDDEN_SELLING_POINT_TYPE,
    _is_useless_selling_point,
    _manual_source_name,
    build_product_detail_payload,
)
from services.product_price_extractor import apply_product_price_metadata, extract_product_price_metadata
from services.product_rag import answer_global_product_question, answer_product_question
from services.upload_limits import write_upload_file

router = APIRouter()

# 产品文件存储目录
PRODUCT_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "product_files")
os.makedirs(PRODUCT_FILES_DIR, exist_ok=True)

SOURCE_PREVIEW_CHAR_LIMIT = 120_000
TEXT_SOURCE_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}


def _safe_product_upload_path(product_id: int, filename: Optional[str]) -> str:
    raw_name = os.path.basename((filename or "upload").replace("\\", "/")).strip()
    safe_tail = re.sub(r"[^\w.\-]+", "_", raw_name, flags=re.UNICODE)
    while ".." in safe_tail:
        safe_tail = safe_tail.replace("..", ".")
    safe_tail = safe_tail.strip("._-") or "upload"
    base, ext = os.path.splitext(safe_tail)
    base = (base or "upload")[:120]
    ext = ext[:32]
    safe_name = f"product_{product_id}_{base}{ext}"
    root = os.path.abspath(PRODUCT_FILES_DIR)
    os.makedirs(root, exist_ok=True)
    file_path = os.path.abspath(os.path.join(root, safe_name))
    try:
        if os.path.commonpath([root, file_path]) != root:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    return file_path


async def _write_upload_file(file: UploadFile, file_path: str, *, max_bytes: int) -> None:
    await write_upload_file(file, file_path, max_bytes=max_bytes)


def _path_is_inside(base: Path, path: Path) -> bool:
    try:
        base_resolved = base.resolve()
        path_resolved = path.resolve()
        return os.path.commonpath([str(base_resolved), str(path_resolved)]) == str(base_resolved)
    except (OSError, ValueError):
        return False


def _resolve_owned_product_file(path: str | None) -> Path | None:
    if not path:
        return None
    try:
        resolved = Path(path).resolve()
        base = Path(PRODUCT_FILES_DIR).resolve()
    except (OSError, ValueError):
        return None
    if not _path_is_inside(base, resolved):
        return None
    return resolved


def _safe_source_name(source: str) -> str:
    name = (source or "").strip()
    if (
        not name
        or os.path.isabs(name)
        or "/" in name
        or "\\" in name
        or ":" in name
        or name in {".", ".."}
        or ".." in name
    ):
        raise HTTPException(status_code=400, detail="Invalid source")
    return name


def _material_source_path(source_name: str) -> Path | None:
    root = Path(__file__).resolve().parents[1]
    try:
        paths = import_materials.get_material_paths(root)
    except (OSError, FileNotFoundError):
        paths = None

    material_dirs: list[Path] = []
    aliases: dict[str, Path] = {}
    if paths is not None:
        material_dirs.append(paths.materials_dir)
        if paths.product_2026_dir is not None:
            material_dirs.append(paths.product_2026_dir)
        aliases[paths.product_knowledge_md.name] = paths.product_knowledge_md
        aliases[paths.product_manual_md.name] = paths.product_manual_md
        aliases[_manual_source_name(str(paths.product_manual_md))] = paths.product_manual_md
        if paths.price_system_xlsx is not None:
            aliases[paths.price_system_xlsx.name] = paths.price_system_xlsx
        if paths.knife_price_xlsx is not None:
            aliases[paths.knife_price_xlsx.name] = paths.knife_price_xlsx
        if paths.product_card_xlsx is not None:
            aliases[paths.product_card_xlsx.name] = paths.product_card_xlsx
    else:
        material_dirs.extend([root / "资料", root / "资料" / "2026产品知识库"])

    aliased = aliases.get(source_name)
    if aliased and aliased.exists():
        return aliased.resolve()

    for base in material_dirs:
        if not base or not base.exists():
            continue
        candidate = (base / source_name).resolve()
        if candidate.exists() and candidate.is_file() and _path_is_inside(base, candidate):
            return candidate
    return None


def _uploaded_source_path(source_name: str, product_id: Optional[int], db: Session) -> Path | None:
    if not product_id:
        return None
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.info_file:
        return None
    path = Path(product.info_file)
    if path.name != source_name:
        return None
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        return None
    if not _path_is_inside(Path(PRODUCT_FILES_DIR), resolved):
        return None
    return resolved


def _resolve_source_path(source: str, product_id: Optional[int], db: Session) -> tuple[str, Path]:
    source_name = _safe_source_name(source)
    path = _uploaded_source_path(source_name, product_id, db) or _material_source_path(source_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source_name, path


def _source_download_url(source_name: str, product_id: Optional[int]) -> str:
    params = {"source": source_name}
    if product_id:
        params["product_id"] = str(product_id)
    return "/api/products/source-download?" + urlencode(params)


def _read_source_preview(path: Path) -> tuple[str, bool]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > SOURCE_PREVIEW_CHAR_LIMIT
    if truncated:
        text = text[:SOURCE_PREVIEW_CHAR_LIMIT] + "\n\n...[内容已截断]"
    return text, truncated


class ProductRagRequest(BaseModel):
    query: str = Field(..., min_length=1)
    category: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=30)


class ProductScopedRagRequest(BaseModel):
    query: str = Field(..., min_length=1)


def _visible_selling_points(points):
    return [
        point for point in sorted(points, key=lambda item: item.priority)
        if point.point_type != HIDDEN_SELLING_POINT_TYPE
        and not _is_useless_selling_point(point.point_type, point.content)
    ]


def _clear_hidden_marker(product_id: int, priority: int, db: Session):
    db.query(SellingPoint).filter(
        SellingPoint.product_id == product_id,
        SellingPoint.point_type == HIDDEN_SELLING_POINT_TYPE,
        SellingPoint.priority == priority,
    ).delete(synchronize_session=False)


def _hide_selling_point_priority(product_id: int, priority: int, db: Session):
    priority = int(priority or 0)
    if priority <= 0:
        return
    db.query(SellingPoint).filter(
        SellingPoint.product_id == product_id,
        SellingPoint.priority == priority,
    ).delete(synchronize_session=False)
    db.add(SellingPoint(
        product_id=product_id,
        point_type=HIDDEN_SELLING_POINT_TYPE,
        content="hidden",
        priority=priority,
    ))


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
        sps = _visible_selling_points(p.selling_points)
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
            selling_point_count=len(sps),
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

        pvs = ProductVectorStore()
        results = pvs.search(q, limit=limit, category_filter=category)
        if not results:
            return []

        product_ids = []
        seen_product_ids = set()
        for r in results:
            product_id = r["product_id"]
            if product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            product_ids.append(product_id)
        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        product_map = {p.id: p for p in products}

        out = []
        for product_id in product_ids:
            r = {"product_id": product_id}
            p = product_map.get(r["product_id"])
            if not p:
                continue
            sps = _visible_selling_points(p.selling_points)
            summary = "；".join([f"[{sp.point_type}]{sp.content}" for sp in sps[:3]])
            out.append(ProductListItem(
                id=p.id, name=p.name, category=p.category,
                price=p.price, original_price=p.original_price,
                commission_rate=p.commission_rate, brand=p.brand,
                image_url=p.image_url, info_file=p.info_file,
                pending_fields=_normalize_pending_fields(p.pending_fields),
                status=p.status, selling_point_count=len(sps),
                selling_point_summary=summary if summary else "暂无卖点",
            ))
        return out
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"产品语义检索失败，请检查 ARK_API_KEY、ARK_BASE_URL、EMBEDDING_MODEL_NAME 和火山方舟 endpoint 权限: {e}",
        )


@router.post("/reindex")
def reindex_products(db: Session = Depends(get_db)):
    """批量重建所有产品的向量索引"""
    try:
        from vector_store import VectorStoreError
        from vector_store.product_store import ProductVectorStore
        pvs = ProductVectorStore()
        pvs.store.reset_product_collection()
        count = pvs.index_all_products(db)
        return ApiResponse(message=f"已重建 {count} 个产品知识块向量索引")
    except VectorStoreError as e:
        raise HTTPException(
            status_code=503,
            detail=f"索引未重建：向量集合重置或写入失败，已停止以避免混用旧索引；请检查 ARK_API_KEY、ARK_BASE_URL、EMBEDDING_MODEL_NAME 和火山方舟 endpoint 权限: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"索引重建失败，请检查 ARK_API_KEY、ARK_BASE_URL、EMBEDDING_MODEL_NAME 和火山方舟 endpoint 权限: {e}",
        )


@router.post("/rag-chat")
async def global_product_rag_chat(
    data: ProductRagRequest,
    db: Session = Depends(get_db),
):
    """全局产品 RAG 问答。"""
    query = (data.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入问题")
    return await answer_global_product_question(
        query=query,
        db=db,
        category=(data.category or "").strip() or None,
        limit=data.limit,
    )


@router.get("/rag-chat", include_in_schema=False)
def global_product_rag_chat_get():
    """Avoid routing a browser GET for rag-chat into /{product_id}."""
    return RedirectResponse(url="/app/products", status_code=303)


@router.get("/source-preview")
def preview_product_source(
    source: str = Query(..., min_length=1),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    source_name, path = _resolve_source_path(source, product_id, db)
    download_url = _source_download_url(source_name, product_id)
    preview_kind = "text" if path.suffix.lower() in TEXT_SOURCE_EXTENSIONS else "download_only"
    content = ""
    truncated = False
    if preview_kind == "text":
        content, truncated = _read_source_preview(path)
    return {
        "name": source_name,
        "preview_kind": preview_kind,
        "content": content,
        "truncated": truncated,
        "download_url": download_url,
    }


@router.get("/source-download")
def download_product_source(
    source: str = Query(..., min_length=1),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    source_name, path = _resolve_source_path(source, product_id, db)
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(str(path), media_type=media_type, filename=source_name)


@router.post("/{product_id}/rag-chat")
async def scoped_product_rag_chat(
    product_id: int,
    data: ProductScopedRagRequest,
    db: Session = Depends(get_db),
):
    """只在指定产品资料内进行 RAG 问答。"""
    query = (data.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入问题")
    try:
        return await answer_product_question(product_id=product_id, query=query, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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


@router.post("/", response_model=ProductWriteOut)
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

    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product.id, "upsert")
    db.commit()
    db.refresh(product)
    sync_status = _sync_product_index(product.id, db)
    product.index_sync_status = sync_status if sync_status in {"synced", "pending"} else "synced"
    return product


@router.put("/{product_id}", response_model=ProductWriteOut)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    """更新产品"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product.id, "upsert")
    db.commit()
    db.refresh(product)
    sync_status = _sync_product_index(product.id, db)
    product.index_sync_status = sync_status if sync_status in {"synced", "pending"} else "synced"
    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """删除产品"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "delete")
    db.delete(product)
    db.commit()
    index_sync_status = _delete_product_index(product_id)
    return ApiResponse(message="产品已删除", data={"index_sync_status": index_sync_status})


# ========== 卖点管理 ==========
@router.get("/{product_id}/selling-points", response_model=List[SellingPointOut])
def get_selling_points(product_id: int, db: Session = Depends(get_db)):
    """获取产品卖点列表"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    return _visible_selling_points(product.selling_points)


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
    _clear_hidden_marker(product_id, priority, db)
    db.add(sp)
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
    db.commit()
    db.refresh(sp)
    _sync_product_index(product_id, db)
    return sp


@router.post("/{product_id}/selling-points/hide")
def hide_selling_point(
    product_id: int,
    data: SellingPointUpdate,
    db: Session = Depends(get_db),
):
    """隐藏资料解析出来的卖点块。"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    if data.priority is None:
        raise HTTPException(status_code=400, detail="缺少卖点位置")

    _hide_selling_point_priority(product_id, data.priority, db)
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
    db.commit()
    _sync_product_index(product_id, db)
    return ApiResponse(message="卖点已删除")


@router.put("/{product_id}/selling-points/{sp_id}", response_model=SellingPointOut)
def update_selling_point(
    product_id: int,
    sp_id: int,
    data: SellingPointUpdate,
    db: Session = Depends(get_db),
):
    """更新产品卖点。"""
    sp = db.query(SellingPoint).filter(
        SellingPoint.id == sp_id,
        SellingPoint.product_id == product_id,
    ).first()
    if not sp:
        raise HTTPException(status_code=404, detail="卖点不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "content" in update_data:
        content = (update_data["content"] or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="卖点内容不能为空")
        sp.content = content
    if "point_type" in update_data:
        point_type = (update_data["point_type"] or "").strip()
        if point_type:
            sp.point_type = point_type
    if update_data.get("priority") is not None:
        sp.priority = int(update_data["priority"])

    _clear_hidden_marker(product_id, sp.priority, db)
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
    db.commit()
    db.refresh(sp)
    _sync_product_index(product_id, db)
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

    priority = sp.priority
    should_hide_material = sp.point_type != HIDDEN_SELLING_POINT_TYPE
    db.delete(sp)
    db.flush()
    if should_hide_material:
        _hide_selling_point_priority(product_id, priority, db)
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
    db.commit()
    _sync_product_index(product_id, db)
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
    if (file.filename or "").lower().endswith(".xls"):
        raise HTTPException(status_code=400, detail="Excel 仅支持 .xlsx 文件")

    # 保存文件
    file_path = _safe_product_upload_path(product_id, file.filename)
    temp_path = f"{file_path}.{uuid.uuid4().hex}.uploading"
    try:
        await _write_upload_file(file, temp_path, max_bytes=MAX_UPLOAD_SIZE)
        os.replace(temp_path, file_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise

    # 更新数据库
    product.info_file = file_path
    price_updates = apply_product_price_metadata(product, extract_product_price_metadata(file_path))
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
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
        enqueue_vector_sync(db, "product", product_id, "upsert")
        db.commit()
        _sync_product_index(product_id, db)
        return ApiResponse(
            message=f"文件已上传，并从资料中提取了 {len(points)} 条卖点",
            data={
                "file_path": file_path,
                "file_name": file.filename,
                "points_extracted": len(points),
                "price_updated": "price" in price_updates,
                "updated_fields": price_updates,
            },
        )

    _sync_product_index(product_id, db)
    return ApiResponse(
        message=f"文件已上传",
        data={
            "file_path": file_path,
            "file_name": file.filename,
            "price_updated": "price" in price_updates,
            "updated_fields": price_updates,
        }
    )


@router.get("/{product_id}/download")
def download_product_file(product_id: int, db: Session = Depends(get_db)):
    """下载产品资料文件"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.info_file:
        raise HTTPException(status_code=404, detail="文件不存在")

    safe_path = _resolve_owned_product_file(product.info_file)
    if safe_path is None or not safe_path.exists():
        raise HTTPException(status_code=404, detail="文件已被删除")

    return FileResponse(str(safe_path), filename=safe_path.name)


@router.delete("/{product_id}/file")
def delete_product_file(product_id: int, db: Session = Depends(get_db)):
    """删除产品资料文件"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    safe_path = _resolve_owned_product_file(product.info_file)
    if product.info_file and safe_path is None:
        raise HTTPException(status_code=400, detail="文件路径不安全")
    if safe_path and safe_path.exists():
        safe_path.unlink()

    product.info_file = None
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
    db.commit()
    _sync_product_index(product_id, db)
    return ApiResponse(message="文件已删除")


# ========== 卖点重整理 ==========
@router.post("/{product_id}/extract-points")
async def extract_points_from_file(product_id: int, db: Session = Depends(get_db)):
    """从产品资料文件中提取卖点，替换现有卖点"""
    from services.selling_point_extractor import extract_selling_points

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    safe_path = _resolve_owned_product_file(product.info_file)
    if not product.info_file or safe_path is None or not safe_path.exists():
        raise HTTPException(status_code=400, detail="请先上传产品资料文件")

    # 提取卖点
    points = await extract_selling_points(
        str(safe_path),
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

    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "product", product_id, "upsert")
    db.commit()
    _sync_product_index(product_id, db)
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
        safe_path = _resolve_owned_product_file(product.info_file)
        if safe_path is None:
            results.append({"id": product.id, "name": product.name, "status": "文件路径不安全"})
            continue
        if not safe_path.exists():
            results.append({"id": product.id, "name": product.name, "status": "文件不存在"})
            continue

        try:
            points = await extract_selling_points(
                str(safe_path), product.name, product.category
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
                from services.vector_sync import enqueue_vector_sync
                enqueue_vector_sync(db, "product", product.id, "upsert")
                db.commit()
                _sync_product_index(product.id, db)
                results.append({"id": product.id, "name": product.name, "status": f"已提取{len(points)}条"})
            else:
                results.append({"id": product.id, "name": product.name, "status": "未能提取"})
        except Exception as e:
            db.rollback()
            results.append({"id": product.id, "name": product.name, "status": f"失败: {e}"})

    return ApiResponse(message=f"处理完成", data={"total": len(products), "results": results})


# ========== 索引同步辅助 ==========

from vector_store import get_chroma_store


def _sync_product_index(product_id: int, db: Session):
    """处理持久化同步任务；失败时保留 pending，不再静默丢失。"""
    from services.vector_sync import ensure_and_process_vector_sync

    status = ensure_and_process_vector_sync(db, "product", product_id, "upsert")
    return "synced" if status == "succeeded" else "pending"


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
    """处理产品删除索引任务；失败时由队列继续重试。"""
    from database import SessionLocal
    from services.vector_sync import ensure_and_process_vector_sync

    db = SessionLocal()
    try:
        status = ensure_and_process_vector_sync(db, "product", product_id, "delete")
        return "synced" if status == "succeeded" else "pending"
    finally:
        db.close()
