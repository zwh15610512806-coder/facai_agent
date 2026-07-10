"""其他爆款脚本参考库 API"""
from fastapi import APIRouter, Depends, HTTPException, Form, Query
from sqlalchemy.orm import Session
from database import get_db
from models import ReferenceScript
from schemas import ApiResponse
from typing import List
import re
import json
from services.ai_service import ai_service

router = APIRouter()


def clean_script(text: str) -> str:
    """格式化脚本：去时间戳"""
    text = re.sub(r'[（(]\d{1,2}:\d{2}[-~]\d{1,2}:\d{2}[）)]', '', text)
    text = re.sub(r'[（(]\d{1,2}[-~]\d{1,2}[sS秒][）)]', '', text)
    text = re.sub(r'【[^】]*?\d+[-~]\d+[sS秒][^】]*?】', '', text)
    text = re.sub(r'\d{1,2}:\d{2}\s*[-~]\s*\d{1,2}:\d{2}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^\d{1,2}:\d{2}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n\s*', '', text)
    return text.strip()


@router.get("/list")
def list_reference_scripts(
    video_type: str = None,
    search: str = None,
    high_only: bool = Query(False, description="仅返回高成交脚本"),
    db: Session = Depends(get_db),
):
    """获取其他爆款脚本列表"""
    query = db.query(ReferenceScript)
    if video_type:
        query = query.filter(ReferenceScript.video_type == video_type)
    if search:
        query = query.filter(ReferenceScript.title.contains(search) | ReferenceScript.script_content.contains(search))
    if high_only:
        query = query.filter(ReferenceScript.is_high_conversion == 1)
    scripts = query.order_by(ReferenceScript.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "video_url": s.video_url,
            "video_type": s.video_type,
            "tags": s.tags,
            "notes": s.notes,
            "is_high_conversion": bool(s.is_high_conversion),
            "script_content": s.script_content,
            "created_at": str(s.created_at),
        }
        for s in scripts
    ]


@router.post("/upload")
async def upload_reference_script(
    title: str = Form(...),
    video_url: str = Form(""),
    video_type: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    """上传其他爆款脚本，自动格式化 + AI分析"""
    script_text = clean_script(content)
    if len(script_text) < 20:
        raise HTTPException(status_code=400, detail="脚本内容太短")

    # AI 分析
    analysis = {}
    if ai_service.is_available and len(script_text) > 100:
        try:
            prompt = f"""分析以下带货短视频脚本，输出JSON：
{script_text[:3000]}
提取：video_type（从：机制类/痛点类/需求类/认知类/达人分享类/制作方便/成本低/对比类/情绪类/场景类 选最匹配的一个）、structure（脚本结构描述）、viral_points（跑量点分析）、tags（逗号分隔的标签）
只输出JSON：{{"video_type":"...","structure":"...","viral_points":"...","tags":"..."}}"""
            result = await ai_service.chat([
                {"role": "system", "content": "你是短视频脚本分析专家，只输出JSON"},
                {"role": "user", "content": prompt},
            ], temperature=0.2, interface_key="reference_script_analyze")
            s = result.find('{'); e = result.rfind('}') + 1
            if s >= 0 and e > s: analysis = json.loads(result[s:e])
        except: pass

    ref = ReferenceScript(
        title=title,
        video_url=video_url,
        script_content=script_text,
        video_type=analysis.get("video_type") or video_type or "",
        tags=(tags or "") + ("," + analysis.get("tags","") if analysis.get("tags") else ""),
        notes=(notes or "") + (" | AI分析: " + analysis.get("structure","") + " | 跑量点: " + analysis.get("viral_points","") if analysis else ""),
    )
    db.add(ref)
    db.flush()
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "reference_script", ref.id, "upsert")
    db.commit()
    db.refresh(ref)
    index_sync_status = _sync_ref_index(ref, db)
    return ApiResponse(
        message="已上传并AI分析",
        data={"id": ref.id, "analysis": analysis, "index_sync_status": index_sync_status},
    )


@router.get("/{script_id}")
def get_reference(script_id: int, db: Session = Depends(get_db)):
    """获取单个脚本详情"""
    s = db.query(ReferenceScript).filter(ReferenceScript.id == script_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="不存在")
    return {
        "id": s.id, "title": s.title, "video_url": s.video_url,
        "video_type": s.video_type, "tags": s.tags, "notes": s.notes,
        "is_high_conversion": bool(s.is_high_conversion),
        "script_content": s.script_content,
    }


@router.post("/{script_id}/toggle-high")
def toggle_high(script_id: int, db: Session = Depends(get_db)):
    s = db.query(ReferenceScript).filter(ReferenceScript.id == script_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="不存在")
    s.is_high_conversion = 1 if s.is_high_conversion == 0 else 0
    db.commit()
    return ApiResponse(message=f"已{'标记' if s.is_high_conversion else '取消'}")


@router.delete("/{script_id}")
def delete_reference(script_id: int, db: Session = Depends(get_db)):
    s = db.query(ReferenceScript).filter(ReferenceScript.id == script_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="不存在")
    from services.vector_sync import enqueue_vector_sync
    enqueue_vector_sync(db, "reference_script", script_id, "delete")
    db.delete(s)
    db.commit()
    index_sync_status = _delete_ref_index(f"ref_{script_id}")
    return ApiResponse(message="已删除", data={"index_sync_status": index_sync_status})


def _sync_ref_index(ref, db: Session):
    from services.vector_sync import ensure_and_process_vector_sync

    status = ensure_and_process_vector_sync(db, "reference_script", ref.id, "upsert")
    return "synced" if status == "succeeded" else "pending"


def _delete_ref_index(doc_id: str):
    from database import SessionLocal
    from services.vector_sync import ensure_and_process_vector_sync

    entity_id = int(doc_id.removeprefix("ref_"))
    db = SessionLocal()
    try:
        status = ensure_and_process_vector_sync(db, "reference_script", entity_id, "delete")
        return "synced" if status == "succeeded" else "pending"
    finally:
        db.close()
