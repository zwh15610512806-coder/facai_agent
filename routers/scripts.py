"""脚本生成 API — AI 驱动的核心功能"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import Product, ScriptTemplate, ViralScript, GeneratedScript
from schemas import (
    ScriptGenerateRequest, ScriptGenerateResponse,
    ScriptRewriteRequest, ScriptRewriteResponse,
    ScriptShotMatchRequest, ScriptShotMatchResponse,
    GeneratedScriptOut, GeneratedScriptPageOut, ApiResponse
)
from services.script_generator import ScriptGenerator
from services.script_rewriter import script_rewriter
from typing import List, Optional

router = APIRouter()

# 全局脚本生成器实例
generator = ScriptGenerator()


@router.post("/generate", response_model=ScriptGenerateResponse)
async def generate_script(request: ScriptGenerateRequest, db: Session = Depends(get_db)):
    """生成短视频脚本"""
    # 获取产品信息
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 确定视频类型
    engine = request.engine or "template"
    video_type = request.video_type
    template = None
    auto_high_library = not video_type and not request.template_id

    if request.template_id:
        template = db.query(ScriptTemplate).filter(
            ScriptTemplate.id == request.template_id
        ).first()
        if template:
            video_type = template.video_type
            auto_high_library = False

    if not video_type:
        video_type = "高成交模板库" if auto_high_library else "机制类"
        if auto_high_library:
            engine = "template"

    # 获取相关模板（如果没指定）—— 随机选一个，避免每次生成结果相同
    if not template and not auto_high_library:
        all_templates = db.query(ScriptTemplate).filter(
            ScriptTemplate.video_type == video_type
        ).all()
        if all_templates:
            import random
            template = random.choice(all_templates)

    # 准备产品上下文
    product_context = {
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "original_price": product.original_price,
        "pending_fields": product.pending_fields or [],
        "brand": product.brand,
        "description": product.description,
        "selling_points": [
            {"type": sp.point_type, "content": sp.content, "priority": sp.priority}
            for sp in sorted(product.selling_points, key=lambda x: x.priority)
        ],
    }

    # 准备模板上下文
    template_context = None
    if template:
        template_context = {
            "name": template.name,
            "video_type": template.video_type,
            "structure": template.structure,
            "hook_templates": template.hook_templates,
            "cta_templates": template.cta_templates,
            "example_script": template.example_script,
        }

    # 检索相似爆款脚本（shuffle 避免每次返回同样顺序）
    # 模板库改写模式取更多参考脚本（5条），DeepSeek模式保持3条
    ref_limit = 5 if engine == "template" else 3
    if auto_high_library:
        reference_scripts = generator.find_high_conversion_scripts(
            product_context, db, limit=ref_limit
        )
    else:
        reference_scripts = generator.find_similar_scripts(
            product_context, video_type, db, limit=ref_limit
        )
    import random as _r
    _r.shuffle(reference_scripts)

    if auto_high_library and not reference_scripts:
        raise HTTPException(status_code=404, detail="暂无高成交模板库脚本，请先在模板库标记高成交脚本")

    # 根据引擎类型分支调用
    if engine == "template" and reference_scripts:
        # 模板库改写模式：以参考脚本为主体进行改写
        script_content = await generator.generate_from_library(
            product=product_context,
            video_type=video_type,
            reference_scripts=reference_scripts,
            tone=request.tone,
            extra_requirements=request.extra_requirements,
            include_shot_design=request.include_shot_design,
        )
    else:
        # DeepSeek AI 模式：全新创作，参考脚本仅作灵感
        script_content = await generator.generate(
            product=product_context,
            template=template_context,
            video_type=video_type,
            tone=request.tone,
            extra_requirements=request.extra_requirements,
            reference_scripts=reference_scripts,
            include_shot_design=request.include_shot_design,
        )

    # 保存生成记录
    engine_label = "模板库改写" if engine == "template" and reference_scripts else "DeepSeek AI"
    record = GeneratedScript(
        product_id=product.id,
        template_id=template.id if template else None,
        script_content=script_content,
        video_type=video_type,
        ai_model=f"{engine_label} · {generator.get_model_name()}",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return ScriptGenerateResponse(
        id=record.id,
        product_name=product.name,
        video_type=video_type,
        script_content=script_content,
        created_at=record.created_at,
    )


@router.get("/history", response_model=GeneratedScriptPageOut)
def list_history(
    product_id: Optional[int] = Query(None),
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
):
    """获取生成历史"""
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 20), 100))
    query = db.query(GeneratedScript)

    if product_id:
        query = query.filter(GeneratedScript.product_id == product_id)

    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = query.order_by(GeneratedScript.created_at.desc(), GeneratedScript.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    result = []
    for r in records:
        item = GeneratedScriptOut(
            id=r.id,
            product_id=r.product_id,
            product_name=r.product.name if r.product else None,
            template_id=r.template_id,
            script_content=r.script_content,
            video_type=r.video_type,
            ai_model=r.ai_model,
            is_high_conversion=bool(r.is_high_conversion),
            created_at=r.created_at,
        )
        result.append(item)

    return GeneratedScriptPageOut(
        items=result,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/history/{script_id}", response_model=GeneratedScriptOut)
def get_history(script_id: int, db: Session = Depends(get_db)):
    """获取单条生成记录"""
    record = db.query(GeneratedScript).filter(
        GeneratedScript.id == script_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    return GeneratedScriptOut(
        id=record.id,
        product_id=record.product_id,
        product_name=record.product.name if record.product else None,
        template_id=record.template_id,
        script_content=record.script_content,
        video_type=record.video_type,
        ai_model=record.ai_model,
        is_high_conversion=bool(record.is_high_conversion),
        created_at=record.created_at,
    )


@router.delete("/history/{script_id}")
def delete_history(script_id: int, db: Session = Depends(get_db)):
    """删除生成记录"""
    record = db.query(GeneratedScript).filter(
        GeneratedScript.id == script_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    return ApiResponse(message="记录已删除")


@router.post("/history/{script_id}/save-to-library")
def save_to_library(script_id: int, db: Session = Depends(get_db)):
    """将生成记录保存到爆款脚本库"""
    record = db.query(GeneratedScript).filter(GeneratedScript.id == script_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    product = record.product
    viral = ViralScript(
        category=product.category if product else "通用",
        video_type=record.video_type or "机制类",
        title=f"{product.name if product else 'AI生成'}脚本",
        script_content=record.script_content,
        tags=f"{product.name if product else ''},{product.category if product else ''}",
        performance_data={"source": "AI生成", "product_id": record.product_id},
    )
    db.add(viral)
    db.commit()
    db.refresh(viral)
    try:
        from vector_store.script_store import ScriptVectorStore
        from vector_store import get_chroma_store
        if get_chroma_store().is_available:
            ScriptVectorStore().index_viral_script(viral)
            viral.embedding_id = f"viral_{viral.id}"
            db.commit()
    except Exception:
        pass
    return ApiResponse(message="已保存到爆款脚本库", data={"viral_id": viral.id})


@router.post("/history/{script_id}/toggle-high")
def toggle_high_generated(script_id: int, db: Session = Depends(get_db)):
    """切换生成记录的高成交标记"""
    record = db.query(GeneratedScript).filter(GeneratedScript.id == script_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    record.is_high_conversion = 1 if record.is_high_conversion == 0 else 0
    db.commit()
    return ApiResponse(message=f"已{'标记为' if record.is_high_conversion else '取消'}高成交", data={"is_high": bool(record.is_high_conversion)})


# ========== 文案配镜头 ==========
@router.post("/match-shots", response_model=ScriptShotMatchResponse)
async def match_script_shots(request: ScriptShotMatchRequest, db: Session = Depends(get_db)):
    """保持现有口播文案不变，为每句话匹配拍摄镜头"""
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    record = None
    if request.script_id:
        record = db.query(GeneratedScript).filter(GeneratedScript.id == request.script_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="脚本记录不存在")
        if record.product_id and record.product_id != product.id:
            raise HTTPException(status_code=400, detail="脚本记录与当前产品不匹配")

    selling_points = [
        {"type": sp.point_type, "content": sp.content, "priority": sp.priority}
        for sp in sorted(product.selling_points, key=lambda x: x.priority)
    ]

    matched_script = await generator.match_shots_to_copy(
        script_content=request.script_content,
        product={
            "name": product.name,
            "category": product.category,
            "price": product.price,
            "original_price": product.original_price,
            "pending_fields": product.pending_fields or [],
            "brand": product.brand,
            "description": product.description,
            "selling_points": selling_points,
        },
    )

    if record:
        record.script_content = matched_script
        db.commit()

    return ScriptShotMatchResponse(
        product_name=product.name,
        original_script=request.script_content,
        script_content=matched_script,
    )


# ========== 脚本改写 ==========
@router.post("/rewrite", response_model=ScriptRewriteResponse)
async def rewrite_script(request: ScriptRewriteRequest, db: Session = Depends(get_db)):
    """上传一段脚本，改写为指定产品的版本（保持原结构）"""
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 获取产品卖点
    selling_points = [
        {"type": sp.point_type, "content": sp.content, "priority": sp.priority}
        for sp in sorted(product.selling_points, key=lambda x: x.priority)
    ]

    rewritten = await script_rewriter.rewrite(
        original_script=request.original_script,
        target_product={
            "name": product.name,
            "category": product.category,
            "price": product.price,
            "original_price": product.original_price,
            "pending_fields": product.pending_fields or [],
            "brand": product.brand,
            "description": product.description,
            "selling_points": selling_points,
        },
        video_type=request.video_type,
        extra_requirements=request.extra_requirements,
        include_shot_design=request.include_shot_design,
        db=db,
    )

    return ScriptRewriteResponse(
        original_script=request.original_script,
        rewritten_script=rewritten,
        product_name=product.name,
    )
