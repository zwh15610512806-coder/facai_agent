"""脚本模板 & 爆款脚本 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, Form, UploadFile, File
from sqlalchemy import or_
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models import ScriptTemplate, ViralScript
from schemas import (
    ScriptTemplateCreate, ScriptTemplateOut,
    ViralScriptCreate, ViralScriptOut, ViralScriptPageOut, ApiResponse
)
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import asyncio
import hashlib
import os
import re
import json
import threading

from config import MAX_UPLOAD_SIZE
from services.ai_service import ai_service
from services.upload_limits import read_upload_bytes

router = APIRouter()

LOCAL_TXT_SCRIPT_SOURCE_DIR = os.getenv(
    "LOCAL_TXT_SCRIPT_SOURCE_DIR",
    r"\\192.168.0.118\法采共享盘2026\视频素材\源素材",
)
LOCAL_TXT_SCAN_SESSION_FACTORY = SessionLocal
LOCAL_TXT_SCAN_ERROR_LIMIT = 50

_local_txt_scan_lock = threading.RLock()
_local_txt_scan_state = {
    "is_running": False,
    "source_dir": LOCAL_TXT_SCRIPT_SOURCE_DIR,
    "recursive": True,
    "total": 0,
    "processed": 0,
    "success": 0,
    "skipped": 0,
    "error_count": 0,
    "errors": [],
    "ids": [],
    "started_at": None,
    "finished_at": None,
    "message": "待扫描",
}


def format_script(text: str) -> str:
    """将带时间戳/标记的脚本格式化为纯段落形式"""
    # 去掉时间戳如 (00:00-00:03)、(0-3s) 等
    text = re.sub(r'[（(]\d{1,2}:\d{2}[-~]\d{1,2}:\d{2}[）)]', '', text)
    text = re.sub(r'[（(]\d{1,2}[-~]\d{1,2}[sS秒][）)]', '', text)
    # 去掉所有形如【xxx-s】或【xxx秒】的段落标记（如【开场钩子-0-3s】、【痛点-3-10s】）
    text = re.sub(r'【[^】]*?\d+[-~]\d+[sS秒][^】]*?】', '', text)
    # 去掉纯时间标记如 00:00-00:03 或 00:00
    text = re.sub(r'\d{1,2}:\d{2}\s*[-~]\s*\d{1,2}:\d{2}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去掉行首时间戳如 "00:00  文本" 或 "00:00"
    text = re.sub(r'^\d{1,2}:\d{2}\s*', '', text, flags=re.MULTILINE)
    # 去掉行内空格后，合并所有行为一整段话
    text = re.sub(r'\n\s*', '', text)
    return text.strip()


async def analyze_script_ai(text: str, user_type: str = "") -> dict:
    """AI分析脚本：识别视频类型、结构、跑量点"""
    if not ai_service.is_available:
        return {}

    prompt = f"""分析以下带货短视频脚本，输出JSON：

{text[:3000]}

提取：
1. video_type：视频类型（从以下选一个最匹配的：机制类/痛点类/需求类/认知类/达人分享类/制作方便/成本低/对比类/情绪类/场景类）
2. structure：脚本结构（如"价格钩子→痛点→卖点展示→促销叠加→强CTA"）
3. viral_points：跑量点分析（30字以内，如"低价冲击+年货节紧迫感+体感对比"）
4. tags：标签（逗号分隔，如"刀叉盘,年货节,价格锚点"）

只输出JSON：{{"video_type":"...","structure":"...","viral_points":"...","tags":"..."}}"""

    try:
        result = await ai_service.chat([
            {"role": "system", "content": "你是短视频脚本分析专家，只输出JSON"},
            {"role": "user", "content": prompt},
        ], temperature=0.2, interface_key="viral_script_analyze")
        start = result.find('{')
        end = result.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(result[start:end])
    except:
        pass
    return {}


def _decode_txt(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码，请使用 UTF-8、GBK 或 UTF-16 文本")


def _title_from_filename(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        return "导入脚本"
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name.strip() or "导入脚本"


def _reset_local_txt_scan_state() -> None:
    with _local_txt_scan_lock:
        _local_txt_scan_state.update({
            "is_running": False,
            "source_dir": LOCAL_TXT_SCRIPT_SOURCE_DIR,
            "recursive": True,
            "total": 0,
            "processed": 0,
            "success": 0,
            "skipped": 0,
            "error_count": 0,
            "errors": [],
            "ids": [],
            "started_at": None,
            "finished_at": None,
            "message": "待扫描",
        })


def _local_txt_scan_snapshot() -> dict:
    with _local_txt_scan_lock:
        snapshot = dict(_local_txt_scan_state)
        snapshot["errors"] = list(_local_txt_scan_state["errors"])
        snapshot["ids"] = list(_local_txt_scan_state["ids"])
        return snapshot


def _update_local_txt_scan_state(**changes) -> None:
    with _local_txt_scan_lock:
        _local_txt_scan_state.update(changes)


def _append_local_txt_scan_error(message: str) -> None:
    with _local_txt_scan_lock:
        _local_txt_scan_state["error_count"] += 1
        if len(_local_txt_scan_state["errors"]) < LOCAL_TXT_SCAN_ERROR_LIMIT:
            _local_txt_scan_state["errors"].append(message)


def _normalized_file_path(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))


def _script_content_hash(script_text: str) -> str:
    return hashlib.sha256((script_text or "").encode("utf-8")).hexdigest()


def _relative_path_for_display(path: Path, source_dir: Path) -> str:
    try:
        relative_path = os.path.relpath(str(path), str(source_dir))
    except ValueError:
        relative_path = path.name
    return relative_path.replace("\\", "/")


def _title_from_relative_path(relative_path: str) -> str:
    stem = os.path.splitext(relative_path.replace("\\", "/"))[0]
    title = " / ".join(part for part in stem.split("/") if part).strip()
    if not title:
        title = "导入脚本"
    if len(title) > 300:
        title = "..." + title[-297:]
    return title


def _combine_tags(base_tags: str, ai_tags: str) -> str:
    parts = [part.strip() for part in (base_tags or "").split(",") if part.strip()]
    parts.extend(part.strip() for part in (ai_tags or "").split(",") if part.strip())
    return ",".join(dict.fromkeys(parts))


def _resolve_viral_script_category(db: Session, category: str = "", product_name: str = "") -> str:
    auto_category = category or ""
    if product_name and not auto_category:
        from models import Product
        matched = db.query(Product).filter(Product.name == product_name).first()
        if matched:
            auto_category = matched.category
    return auto_category or "烘焙配件"


def _find_existing_local_txt_script(db: Session, local_path: str, content_sha256: str):
    normalized_path = _normalized_file_path(local_path)
    for script in db.query(ViralScript).all():
        data = script.performance_data if isinstance(script.performance_data, dict) else {}
        existing_path = data.get("local_path")
        if existing_path and _normalized_file_path(existing_path) == normalized_path:
            return script
        if data.get("content_sha256") == content_sha256:
            return script
        if _script_content_hash(script.script_content or "") == content_sha256:
            return script
    return None


async def _analyze_local_txt_script(script_text: str, video_type: str) -> dict:
    try:
        return await analyze_script_ai(script_text, video_type)
    except Exception:
        return {}


def _discover_local_txt_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, _dir_names, file_names in os.walk(source_dir):
        file_names.sort()
        for name in file_names:
            if name.lower().endswith(".txt"):
                files.append(Path(current_root) / name)
    files.sort(key=lambda item: _relative_path_for_display(item, source_dir).lower())
    return files


async def _scan_local_txt_scripts(
    *,
    source_dir: Path,
    category: str,
    video_type: str,
    tags: str,
    product_name: str,
    db: Session,
) -> None:
    files = _discover_local_txt_files(source_dir)
    _update_local_txt_scan_state(total=len(files), message=f"发现 {len(files)} 个 txt 文件")

    auto_category = _resolve_viral_script_category(db, category=category, product_name=product_name)
    for path in files:
        safe_name = path.name
        relative_path = _relative_path_for_display(path, source_dir)
        try:
            stat = path.stat()
            if stat.st_size > MAX_UPLOAD_SIZE:
                raise ValueError(f"文件过大，请控制在 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB 以内。")

            script_text = format_script(_decode_txt(path.read_bytes()))
            if len(script_text) < 20:
                raise ValueError("脚本内容太短")

            content_sha256 = _script_content_hash(script_text)
            if _find_existing_local_txt_script(db, str(path), content_sha256):
                with _local_txt_scan_lock:
                    _local_txt_scan_state["skipped"] += 1
                    _local_txt_scan_state["processed"] += 1
                    _local_txt_scan_state["message"] = f"已跳过重复脚本：{relative_path}"
                continue

            ai_analysis = await _analyze_local_txt_script(script_text, video_type)
            viral = ViralScript(
                category=auto_category,
                video_type=ai_analysis.get("video_type") or video_type or "机制类",
                title=_title_from_relative_path(relative_path),
                script_content=script_text,
                tags=_combine_tags(tags or "本地txt", ai_analysis.get("tags", "")),
                performance_data={
                    "source": "本地TXT扫描",
                    "local_path": str(path),
                    "relative_path": relative_path,
                    "filename": safe_name,
                    "content_sha256": content_sha256,
                    "file_size": stat.st_size,
                    "file_modified": datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat(),
                    "ai_structure": ai_analysis.get("structure", ""),
                    "ai_viral_points": ai_analysis.get("viral_points", ""),
                },
            )
            db.add(viral)
            db.commit()
            db.refresh(viral)
            _sync_viral_index(viral, db)
            with _local_txt_scan_lock:
                _local_txt_scan_state["success"] += 1
                _local_txt_scan_state["processed"] += 1
                _local_txt_scan_state["ids"].append(viral.id)
                _local_txt_scan_state["message"] = f"已导入：{relative_path}"
        except Exception as exc:
            db.rollback()
            with _local_txt_scan_lock:
                _local_txt_scan_state["skipped"] += 1
                _local_txt_scan_state["processed"] += 1
                _local_txt_scan_state["message"] = f"跳过：{relative_path}"
            _append_local_txt_scan_error(f"{relative_path}: {exc}")


def _run_local_txt_scan(source_dir: str, category: str, video_type: str, tags: str, product_name: str) -> None:
    db = LOCAL_TXT_SCAN_SESSION_FACTORY()
    try:
        asyncio.run(_scan_local_txt_scripts(
            source_dir=Path(source_dir),
            category=category,
            video_type=video_type,
            tags=tags,
            product_name=product_name,
            db=db,
        ))
        snapshot = _local_txt_scan_snapshot()
        _update_local_txt_scan_state(
            message=(
                f"扫描完成：新增 {snapshot['success']}，跳过 {snapshot['skipped']}，"
                f"错误 {snapshot['error_count']}"
            )
        )
    except Exception as exc:
        _append_local_txt_scan_error(str(exc))
        _update_local_txt_scan_state(message=f"扫描失败：{exc}")
    finally:
        db.close()
        _update_local_txt_scan_state(is_running=False, finished_at=datetime.now().replace(microsecond=0).isoformat())


# ========== 脚本模板管理 ==========
@router.get("/", response_model=List[ScriptTemplateOut])
def list_templates(
    video_type: Optional[str] = Query(None, description="视频类型筛选"),
    db: Session = Depends(get_db),
):
    """获取模板列表"""
    query = db.query(ScriptTemplate)
    if video_type:
        query = query.filter(ScriptTemplate.video_type == video_type)
    return query.order_by(ScriptTemplate.id).all()


@router.get("/types", response_model=List[str])
def list_video_types(db: Session = Depends(get_db)):
    """获取所有视频类型"""
    types = db.query(ScriptTemplate.video_type).distinct().order_by(
        ScriptTemplate.video_type
    ).all()
    return [t[0] for t in types]


@router.get("/{template_id}", response_model=ScriptTemplateOut)
def get_template(template_id: int, db: Session = Depends(get_db)):
    """获取模板详情"""
    template = db.query(ScriptTemplate).filter(
        ScriptTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template


@router.post("/", response_model=ScriptTemplateOut)
def create_template(data: ScriptTemplateCreate, db: Session = Depends(get_db)):
    """创建脚本模板"""
    template = ScriptTemplate(**data.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    """删除脚本模板"""
    template = db.query(ScriptTemplate).filter(
        ScriptTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(template)
    db.commit()
    return ApiResponse(message="模板已删除")


# ========== 爆款脚本库 ==========
@router.get("/viral/list", response_model=ViralScriptPageOut)
def list_viral_scripts(
    category: Optional[str] = Query(None, description="品类筛选"),
    video_type: Optional[str] = Query(None, description="视频类型筛选"),
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 24,
    sort: str = "desc",
    high_only: bool = Query(False, description="仅返回高成交脚本"),
    db: Session = Depends(get_db),
):
    """获取爆款脚本列表"""
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 24), 200))
    query = db.query(ViralScript)
    if category:
        query = query.filter(ViralScript.category == category)
    if video_type:
        query = query.filter(ViralScript.video_type == video_type)
    if q:
        needle = f"%{q.strip()}%"
        if needle != "%%":
            query = query.filter(or_(
                ViralScript.title.ilike(needle),
                ViralScript.script_content.ilike(needle),
                ViralScript.tags.ilike(needle),
                ViralScript.category.ilike(needle),
                ViralScript.video_type.ilike(needle),
            ))
    if high_only:
        query = query.filter(ViralScript.is_high_conversion == 1)
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    order_by = (ViralScript.created_at.asc(), ViralScript.id.asc()) if sort == "oldest" else (ViralScript.created_at.desc(), ViralScript.id.desc())
    scripts = query.order_by(*order_by).offset((page - 1) * per_page).limit(per_page).all()
    return ViralScriptPageOut(
        items=[ViralScriptOut.model_validate(script) for script in scripts],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


# ========== RAG: 语义搜索 + 索引管理 ==========

@router.get("/viral/search")
def semantic_search_scripts(
    q: str = Query(..., description="自然语言搜索查询"),
    limit: int = Query(10, ge=1, le=50),
    video_type: Optional[str] = Query(None),
    high_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """语义搜索爆款脚本/参考脚本"""
    try:
        from vector_store.script_store import ScriptVectorStore
        from vector_store import get_chroma_store
        store = get_chroma_store()
        if not store.is_available:
            return []
        svs = ScriptVectorStore()
        results = svs.search(q, limit=limit, video_type=video_type)
        if not results:
            return []
        viral_ids = [r["db_id"] for r in results if r.get("source") == "viral"]
        ref_ids = [r["db_id"] for r in results if r.get("source") == "reference"]
        out = []
        if viral_ids:
            virals = db.query(ViralScript).filter(ViralScript.id.in_(viral_ids)).all()
            vmap = {v.id: v for v in virals}
            for r in results:
                if r.get("source") == "viral" and r["db_id"] in vmap:
                    s = vmap[r["db_id"]]
                    out.append({
                        "id": s.id, "title": s.title, "category": s.category,
                        "video_type": s.video_type, "tags": s.tags,
                        "script_content": (s.script_content or "")[:300],
                        "is_high_conversion": bool(s.is_high_conversion),
                        "source": "viral", "distance": r.get("distance", 0),
                        "created_at": str(s.created_at) if s.created_at else None,
                    })
        if ref_ids:
            refs = db.query(ReferenceScript).filter(ReferenceScript.id.in_(ref_ids)).all()
            rmap = {r.id: r for r in refs}
            for r in results:
                if r.get("source") == "reference" and r["db_id"] in rmap:
                    s = rmap[r["db_id"]]
                    out.append({
                        "id": s.id, "title": s.title,
                        "video_type": s.video_type, "tags": s.tags,
                        "script_content": (s.script_content or "")[:300],
                        "is_high_conversion": bool(s.is_high_conversion),
                        "source": "reference", "distance": r.get("distance", 0),
                        "created_at": str(s.created_at) if s.created_at else None,
                    })
        if high_only:
            out = [s for s in out if s.get("is_high_conversion")]
        out.sort(key=lambda x: x.get("distance", 1))
        return out[:limit]
    except Exception:
        return []


@router.post("/reindex")
def reindex_scripts(db: Session = Depends(get_db)):
    """批量重建所有脚本的向量索引"""
    try:
        from vector_store.script_store import ScriptVectorStore
        svs = ScriptVectorStore()
        count = svs.index_all_scripts(db)
        return ApiResponse(message=f"已重建 {count} 个脚本的向量索引")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引重建失败: {e}")


@router.post("/viral/scan-local-txt")
def start_local_txt_scan(
    category: str = Form(""),
    video_type: str = Form(""),
    tags: str = Form(""),
    product_name: str = Form(""),
):
    """Start a background scan of the configured local TXT script directory."""
    source_dir = LOCAL_TXT_SCRIPT_SOURCE_DIR
    if not os.path.exists(source_dir):
        raise HTTPException(status_code=404, detail=f"路径不可访问：{source_dir}")

    with _local_txt_scan_lock:
        if _local_txt_scan_state["is_running"]:
            return ApiResponse(message="本地脚本扫描正在运行", data=_local_txt_scan_snapshot())
        _local_txt_scan_state.update({
            "is_running": True,
            "source_dir": source_dir,
            "recursive": True,
            "total": 0,
            "processed": 0,
            "success": 0,
            "skipped": 0,
            "error_count": 0,
            "errors": [],
            "ids": [],
            "started_at": datetime.now().replace(microsecond=0).isoformat(),
            "finished_at": None,
            "message": "扫描启动中",
        })

    thread = threading.Thread(
        target=_run_local_txt_scan,
        args=(source_dir, category, video_type, tags or "本地txt", product_name),
        name="facai-local-txt-scan",
        daemon=True,
    )
    thread.start()
    return ApiResponse(message="本地脚本扫描已启动", data=_local_txt_scan_snapshot())


@router.get("/viral/scan-local-txt/status")
def local_txt_scan_status():
    """Return the latest local TXT script scan status."""
    return ApiResponse(message="ok", data=_local_txt_scan_snapshot())


@router.get("/viral/{script_id}", response_model=ViralScriptOut)
def get_viral_script(script_id: int, db: Session = Depends(get_db)):
    """获取爆款脚本详情"""
    script = db.query(ViralScript).filter(ViralScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="爆款脚本不存在")
    return script


@router.post("/viral/{script_id}/toggle-high")
def toggle_high_viral(script_id: int, db: Session = Depends(get_db)):
    """切换爆款脚本的高成交标记"""
    script = db.query(ViralScript).filter(ViralScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="爆款脚本不存在")
    script.is_high_conversion = 1 if script.is_high_conversion == 0 else 0
    db.commit()
    return ApiResponse(message=f"已{'标记为' if script.is_high_conversion else '取消'}高成交", data={"is_high": bool(script.is_high_conversion)})


@router.delete("/viral/{script_id}")
def delete_viral_script(script_id: int, db: Session = Depends(get_db)):
    """删除爆款脚本"""
    script = db.query(ViralScript).filter(ViralScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="爆款脚本不存在")
    _delete_script_index(f"viral_{script.id}")
    db.delete(script)
    db.commit()
    return ApiResponse(message="已删除")


@router.post("/viral/upload")
async def upload_viral_script(
    title: str = Form(""),
    category: str = Form(""),
    video_type: str = Form(""),
    tags: str = Form(""),
    product_name: str = Form(""),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    """上传法采脚本，产品名匹配品类+AI分析"""
    script_text = format_script(content)
    if len(script_text) < 20:
        raise HTTPException(status_code=400, detail="脚本内容太短")

    # 通过产品名直接匹配数据库中产品获取品类
    auto_category = category or ""
    if product_name and not auto_category:
        from models import Product
        matched = db.query(Product).filter(Product.name == product_name).first()
        if matched:
            auto_category = matched.category
    if not auto_category:
        auto_category = "烘焙配件"

    ai_analysis = await analyze_script_ai(script_text, video_type)

    viral = ViralScript(
        category=auto_category,
        video_type=ai_analysis.get("video_type") or video_type or "机制类",
        title=title or (product_name + "脚本" if product_name else "未命名脚本"),
        script_content=script_text,
        tags=(tags or "") + ("," + ai_analysis.get("tags","") if ai_analysis.get("tags") else ""),
        performance_data={"source": "手动上传", "ai_structure": ai_analysis.get("structure",""), "ai_viral_points": ai_analysis.get("viral_points","")},
    )
    db.add(viral)
    db.commit()
    db.refresh(viral)
    _sync_viral_index(viral, db)
    return ApiResponse(message=f"已上传并AI分析，归类为「{auto_category}」", data={"id": viral.id, "category": auto_category, "analysis": ai_analysis})


@router.post("/viral/upload-txt-batch")
async def upload_viral_txt_batch(
    files: List[UploadFile] = File(...),
    category: str = Form(""),
    video_type: str = Form(""),
    tags: str = Form(""),
    product_name: str = Form(""),
    db: Session = Depends(get_db),
):
    """Batch upload local .txt scripts into the viral script library."""
    result = {"total": len(files), "success": 0, "skipped": 0, "errors": [], "ids": []}
    if not files:
        raise HTTPException(status_code=400, detail="请选择 txt 文件")

    auto_category = category or ""
    if product_name and not auto_category:
        from models import Product
        matched = db.query(Product).filter(Product.name == product_name).first()
        if matched:
            auto_category = matched.category
    if not auto_category:
        auto_category = "烘焙配件"

    for upload in files:
        filename = upload.filename or ""
        safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1] or "未命名.txt"
        if not safe_name.lower().endswith(".txt"):
            result["skipped"] += 1
            result["errors"].append(f"{safe_name}: 仅支持 .txt 文件")
            continue

        try:
            content = await read_upload_bytes(upload, max_bytes=MAX_UPLOAD_SIZE)
            script_text = format_script(_decode_txt(content))
            if len(script_text) < 20:
                raise ValueError("脚本内容太短")

            ai_analysis = await analyze_script_ai(script_text, video_type)
            viral = ViralScript(
                category=auto_category,
                video_type=ai_analysis.get("video_type") or video_type or "机制类",
                title=_title_from_filename(safe_name),
                script_content=script_text,
                tags=(tags or "") + ("," + ai_analysis.get("tags", "") if ai_analysis.get("tags") else ""),
                performance_data={
                    "source": "批量TXT上传",
                    "filename": safe_name,
                    "ai_structure": ai_analysis.get("structure", ""),
                    "ai_viral_points": ai_analysis.get("viral_points", ""),
                },
            )
            db.add(viral)
            db.commit()
            db.refresh(viral)
            _sync_viral_index(viral, db)
            result["success"] += 1
            result["ids"].append(viral.id)
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            result["skipped"] += 1
            result["errors"].append(f"{safe_name}: {exc}")

    return ApiResponse(message=f"已导入 {result['success']} 个 txt 脚本", data=result)


async def categorize_product_ai(name: str) -> str:
    if not ai_service.is_available: return ""
    try:
        r = await ai_service.chat([{"role":"system","content":"归类到：烘焙调色/烘焙装饰/烘焙调味/烘焙夹心/烘焙配件。只输出品类名。"},{"role":"user","content":name}], temperature=0.1, interface_key="viral_script_analyze")
        for c in ["烘焙调色","烘焙装饰","烘焙调味","烘焙夹心","烘焙配件"]:
            if c in r: return c
    except: pass
    return ""


# ========== 索引同步辅助 ==========

from models import ReferenceScript


def _sync_viral_index(viral, db: Session):
    try:
        from vector_store.script_store import ScriptVectorStore
        from vector_store import get_chroma_store
        if not get_chroma_store().is_available:
            return
        ScriptVectorStore().index_viral_script(viral)
        viral.embedding_id = f"viral_{viral.id}"
        db.commit()
    except Exception:
        pass


def _sync_reference_index(ref, db: Session):
    try:
        from vector_store.script_store import ScriptVectorStore
        from vector_store import get_chroma_store
        if not get_chroma_store().is_available:
            return
        ScriptVectorStore().index_reference_script(ref)
        ref.embedding_id = f"ref_{ref.id}"
        db.commit()
    except Exception:
        pass


def _delete_script_index(doc_id: str):
    try:
        from vector_store.script_store import ScriptVectorStore
        ScriptVectorStore().delete_embedding(doc_id)
    except Exception:
        pass
