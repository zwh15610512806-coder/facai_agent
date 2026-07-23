"""脚本生成 API — AI 驱动的核心功能"""
import asyncio

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from database import SessionLocal, get_db
from models import Product, ScriptTemplate, ViralScript, GeneratedScript, ReferenceScript
from schemas import (
    ScriptGenerateRequest, ScriptGenerateResponse,
    ScriptRewriteRequest, ScriptRewriteResponse,
    ScriptShotMatchRequest, ScriptShotMatchResponse,
    ScriptContentBreakdownRequest, ScriptContentBreakdownResponse,
    SeedancePromptGenerateRequest, SeedancePromptGenerateResponse,
    SeedancePromptUploadResponse,
    GeneratedScriptOut, GeneratedScriptPageOut, ApiResponse
)
from services.script_generator import ScriptGenerationError, ScriptGenerator
from services.script_opening import extract_spoken_opening
from services.product_detail import build_product_detail_payload
from services.script_rewriter import ScriptRewriteGenerationError, script_rewriter
from services.inspiration_attachments import AttachmentExtractionError, MAX_ATTACHMENT_BYTES, extract_attachment_text
from services.seedance_prompt_generator import SeedancePromptGenerationError, seedance_prompt_generator
from services.script_content_breakdown import (
    ScriptContentBreakdownError,
    script_content_breakdown_service,
)
from services.script_reference_intent import (
    DEFAULT_VIDEO_TYPES,
    ReferenceSelectionIntent,
    parse_reference_selection_intent,
)
from services.upload_limits import read_upload_bytes
from services.product_markdown_importer import normalize_product_name
from services.background_jobs import (
    create_background_job,
    is_cancel_requested,
    job_to_dict,
    mark_cancelling,
    register_background_handler,
)
from routers.jobs import owner_key_for_request
from typing import List, Optional
import random

router = APIRouter()

# 全局脚本生成器实例
generator = ScriptGenerator()


def _recent_ai_openings(db: Session, product_id: int) -> List[str]:
    records = (
        db.query(GeneratedScript)
        .filter(
            GeneratedScript.product_id == product_id,
            GeneratedScript.ai_model.startswith("AI生成 ·"),
        )
        .order_by(GeneratedScript.id.desc())
        .limit(8)
        .all()
    )
    return [
        opening
        for opening in (extract_spoken_opening(record.script_content) for record in records)
        if opening
    ]


def _script_template_context(template: ScriptTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "video_type": template.video_type,
        "structure": template.structure,
        "hook_templates": template.hook_templates,
        "cta_templates": template.cta_templates,
        "duration_range": template.duration_range,
        "description": template.description,
        "example_script": template.example_script,
    }


def _select_rewrite_template(
    db: Session,
    requested_video_type: str,
    template_id: Optional[int],
    *,
    allow_type_fallback: bool = True,
) -> ScriptTemplate:
    if template_id:
        template = db.query(ScriptTemplate).filter(ScriptTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="脚本模板不存在")
        return template

    candidates = []
    if requested_video_type:
        candidates = db.query(ScriptTemplate).filter(
            ScriptTemplate.video_type == requested_video_type
        ).all()

    if requested_video_type and not candidates and not allow_type_fallback:
        raise HTTPException(
            status_code=422,
            detail=f"未找到{requested_video_type}结构模板，请先在脚本模板库创建对应模板",
        )

    if not candidates:
        candidates = db.query(ScriptTemplate).all()

    if not candidates:
        raise HTTPException(status_code=404, detail="脚本模板库为空，请先在脚本模板库创建模板")

    return random.choice(candidates)


def _random_rewrite_source_from_queries(viral_query, reference_query) -> dict | None:
    viral_count = viral_query.count()
    reference_count = reference_query.count()
    total = viral_count + reference_count
    if total <= 0:
        return None

    selected_index = random.randrange(total)
    if selected_index < viral_count:
        script = viral_query.order_by(ViralScript.id.asc()).offset(selected_index).first()
        source = "facai"
    else:
        script = (
            reference_query.order_by(ReferenceScript.id.asc())
            .offset(selected_index - viral_count)
            .first()
        )
        source = "other"

    if not script:
        return None
    return {
        "id": script.id,
        "source": source,
        "title": (script.title or "无标题脚本").strip() or "无标题脚本",
        "video_type": script.video_type or "",
        "content": script.script_content,
    }


def _normalize_reference_query(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _reference_query_filter(column, reference_query: str):
    escaped = reference_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _available_reference_video_types(db: Session) -> list[str]:
    stored = [
        value
        for (value,) in db.query(ScriptTemplate.video_type).distinct().all()
        if value
    ]
    return list(dict.fromkeys([*DEFAULT_VIDEO_TYPES, *stored]))


def _parse_reference_selection_intent(
    requirements: str | None,
    video_types: Optional[List[str]] = None,
) -> ReferenceSelectionIntent:
    if video_types is None:
        return parse_reference_selection_intent(requirements)
    return parse_reference_selection_intent(requirements, video_types)


def _extract_reference_query_from_requirements(requirements: str | None) -> tuple[str | None, str | None]:
    intent = _parse_reference_selection_intent(requirements)
    return intent.product_query, intent.remaining_requirements


def _resolve_reference_product_terms(db: Session, reference_query: str) -> list[str]:
    normalized_query = _normalize_reference_query(reference_query)
    query_key = normalize_product_name(normalized_query)
    if not query_key:
        return []

    products = db.query(Product).all()
    exact_names = [
        product.name
        for product in products
        if normalize_product_name(product.name) == query_key
    ]
    if exact_names:
        return list(dict.fromkeys(exact_names))

    family_names = [
        product.name
        for product in products
        if query_key in normalize_product_name(product.name)
        or normalize_product_name(product.name) in query_key
    ]
    return list(dict.fromkeys([normalized_query, *family_names]))


def _reference_terms_filter(columns, terms: List[str]):
    clauses = [
        and_(column.is_not(None), _reference_query_filter(column, term))
        for term in terms
        for column in columns
        if term
    ]
    return or_(*clauses)


def _matching_reference_queries(
    db: Session,
    terms: List[str],
    video_type: str = "",
    *,
    exclude_terms: Optional[List[str]] = None,
):
    viral_filters = [_reference_terms_filter(
        (ViralScript.title, ViralScript.category, ViralScript.tags, ViralScript.script_content),
        terms,
    )]
    reference_filters = [_reference_terms_filter(
        (ReferenceScript.title, ReferenceScript.tags, ReferenceScript.notes, ReferenceScript.script_content),
        terms,
    )]
    if video_type:
        viral_filters.append(ViralScript.video_type == video_type)
        reference_filters.append(ReferenceScript.video_type == video_type)
    else:
        viral_filters.append(and_(ViralScript.video_type.is_not(None), ViralScript.video_type != ""))
        reference_filters.append(and_(ReferenceScript.video_type.is_not(None), ReferenceScript.video_type != ""))
    if exclude_terms:
        viral_filters.append(~_reference_terms_filter(
            (ViralScript.title, ViralScript.category, ViralScript.tags, ViralScript.script_content),
            exclude_terms,
        ))
        reference_filters.append(~_reference_terms_filter(
            (ReferenceScript.title, ReferenceScript.tags, ReferenceScript.notes, ReferenceScript.script_content),
            exclude_terms,
        ))
    return (
        db.query(ViralScript).filter(*viral_filters),
        db.query(ReferenceScript).filter(*reference_filters),
    )


def _all_reference_queries(
    db: Session,
    video_type: str = "",
    *,
    exclude_terms: Optional[List[str]] = None,
):
    viral_filters = []
    reference_filters = []
    if video_type:
        viral_filters.append(ViralScript.video_type == video_type)
        reference_filters.append(ReferenceScript.video_type == video_type)
    if exclude_terms:
        viral_filters.append(~_reference_terms_filter(
            (ViralScript.title, ViralScript.category, ViralScript.tags, ViralScript.script_content),
            exclude_terms,
        ))
        reference_filters.append(~_reference_terms_filter(
            (ReferenceScript.title, ReferenceScript.tags, ReferenceScript.notes, ReferenceScript.script_content),
            exclude_terms,
        ))
    return (
        db.query(ViralScript).filter(*viral_filters),
        db.query(ReferenceScript).filter(*reference_filters),
    )


def _select_rewrite_source_script(
    db: Session,
    video_type: str,
    *,
    reference_query: str | None = None,
    allow_product_type_fallback: bool = False,
    exclude_product_query: str | None = None,
) -> dict:
    normalized_query = _normalize_reference_query(reference_query)
    normalized_exclusion = _normalize_reference_query(exclude_product_query)
    exclusion_terms = (
        _resolve_reference_product_terms(db, normalized_exclusion)
        if normalized_exclusion
        else []
    )
    if normalized_exclusion and not exclusion_terms:
        exclusion_terms = [normalized_exclusion]

    if (
        normalized_query
        and normalized_exclusion
        and normalize_product_name(normalized_query) == normalize_product_name(normalized_exclusion)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"指定参考产品“{normalized_query}”与当前生成产品相同，"
                "请改用其他产品脚本"
            ),
        )

    if normalized_query:
        terms = _resolve_reference_product_terms(db, normalized_query)
        if not terms:
            terms = [normalized_query]
        viral_query, reference_query_set = _matching_reference_queries(
            db,
            terms,
            video_type,
            exclude_terms=exclusion_terms,
        )
        same_type_source = _random_rewrite_source_from_queries(
            viral_query,
            reference_query_set,
        )
        if same_type_source:
            return same_type_source
        if allow_product_type_fallback:
            viral_query, reference_query_set = _matching_reference_queries(
                db,
                terms,
                exclude_terms=exclusion_terms,
            )
            fallback_source = _random_rewrite_source_from_queries(
                viral_query,
                reference_query_set,
            )
            if fallback_source:
                return fallback_source
        raise HTTPException(
            status_code=422,
            detail=(
                f"未找到“{normalized_query}”的{video_type}参考脚本，请先在脚本模板库导入对应脚本"
                if video_type
                else f"未找到“{normalized_query}”的参考脚本，请先在脚本模板库导入对应脚本"
            ),
        )

    viral_query, reference_query_set = _all_reference_queries(
        db,
        video_type,
        exclude_terms=exclusion_terms,
    )
    same_type_source = _random_rewrite_source_from_queries(viral_query, reference_query_set)
    if same_type_source:
        return same_type_source

    viral_query, reference_query_set = _all_reference_queries(
        db,
        exclude_terms=exclusion_terms,
    )
    fallback_source = _random_rewrite_source_from_queries(viral_query, reference_query_set)
    if fallback_source:
        return fallback_source

    if normalized_exclusion:
        if db.query(ViralScript).count() == 0 and db.query(ReferenceScript).count() == 0:
            raise HTTPException(
                status_code=404,
                detail="具体脚本库为空，请先在脚本模板库添加法采脚本或其他脚本",
            )
        raise HTTPException(
            status_code=422,
            detail=(
                f"剔除当前产品“{normalized_exclusion}”的脚本后，没有可用参考脚本，"
                "请先导入其他产品脚本"
            ),
        )
    raise HTTPException(
        status_code=404,
        detail="具体脚本库为空，请先在脚本模板库添加法采脚本或其他脚本",
    )


@router.post("/seedance-prompts/upload", response_model=SeedancePromptUploadResponse)
async def upload_seedance_prompt_script(file: UploadFile = File(...)):
    """Extract script text for Seedance prompt generation without persisting it."""
    data = await read_upload_bytes(file, max_bytes=MAX_ATTACHMENT_BYTES)
    try:
        from services.bounded_executor import WorkQueueFull, run_blocking
        attachment = await run_blocking(
            extract_attachment_text,
            file.filename or "attachment",
            file.content_type or "",
            data,
        )
    except WorkQueueFull as exc:
        raise HTTPException(status_code=503, detail="文件解析任务繁忙，请稍后重试") from exc
    except AttachmentExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SeedancePromptUploadResponse(
        filename=attachment.filename,
        file_type=attachment.file_type,
        text=attachment.text,
        char_count=attachment.char_count,
    )


@router.post("/seedance-prompts", response_model=SeedancePromptGenerateResponse)
async def generate_seedance_prompts(request: SeedancePromptGenerateRequest, db: Session = Depends(get_db)):
    """Generate Seedance 2.0 storyboard prompts from an uploaded or pasted script."""
    try:
        result = await seedance_prompt_generator.generate(
            script_content=request.script_content,
            requirements=request.requirements,
            db=db,
        )
    except SeedancePromptGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return SeedancePromptGenerateResponse(**result)


@router.post("/content-breakdown", response_model=ScriptContentBreakdownResponse)
async def generate_content_breakdown(
    request: ScriptContentBreakdownRequest,
    db: Session = Depends(get_db),
):
    """Analyze the user's current version without blocking or replacing the generated script."""
    record = db.query(GeneratedScript).filter(GeneratedScript.id == request.script_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="生成记录不存在")

    product = record.product
    if not product:
        raise HTTPException(status_code=404, detail="生成记录关联的产品不存在")

    product_context = {
        "name": product.name,
        "category": product.category,
        "brand": product.brand,
        "price": product.price,
        "original_price": product.original_price,
        "description": product.description,
        "pending_fields": product.pending_fields or [],
        "selling_points": [
            {"type": sp.point_type, "content": sp.content, "priority": sp.priority}
            for sp in sorted(product.selling_points, key=lambda item: item.priority)
        ],
    }
    product_context.update(build_product_detail_payload(product))

    template_context = None
    if record.template_id:
        template = db.query(ScriptTemplate).filter(ScriptTemplate.id == record.template_id).first()
        if template:
            template_context = _script_template_context(template)

    source_script = None
    if record.source_script_title or record.source_script_content:
        source_script = {
            "id": record.source_script_id,
            "source": record.source_script_source,
            "title": record.source_script_title,
            "content": record.source_script_content,
        }

    engine = "template" if (record.ai_model or "").startswith("模板库改写") else "deepseek"
    try:
        result = await script_content_breakdown_service.generate(
            script_content=request.script_content,
            product=product_context,
            video_type=record.video_type or "AI智能生成",
            engine=engine,
            template=template_context,
            source_script=source_script,
            db=db,
        )
    except ScriptContentBreakdownError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return ScriptContentBreakdownResponse(**result)


@router.post("/generate", response_model=ScriptGenerateResponse)
async def generate_script(request: ScriptGenerateRequest, db: Session = Depends(get_db)):
    """生成短视频脚本"""
    # 获取产品信息
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 确定视频类型
    engine = request.engine or "template"
    requested_video_type = (request.video_type or "").strip()
    video_type = requested_video_type
    template = None
    source_script = None
    source_match_query = None
    generation_requirements = request.extra_requirements

    if engine == "template":
        reference_intent = _parse_reference_selection_intent(
            request.extra_requirements,
            _available_reference_video_types(db),
        )
        generation_requirements = reference_intent.remaining_requirements
        source_match_query = reference_intent.product_query

        if request.template_id:
            template = _select_rewrite_template(
                db=db,
                requested_video_type=requested_video_type,
                template_id=request.template_id,
            )
            if (
                reference_intent.explicit_video_type
                and template.video_type != reference_intent.explicit_video_type
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"需求指定{reference_intent.explicit_video_type}，"
                        f"但结构模板是{template.video_type}，请统一后重试"
                    ),
                )
            video_type = template.video_type

        if source_match_query:
            preferred_video_type = reference_intent.explicit_video_type or video_type
            source_script = _select_rewrite_source_script(
                db,
                preferred_video_type,
                reference_query=source_match_query,
                allow_product_type_fallback=(
                    reference_intent.explicit_video_type is None
                    and not requested_video_type
                    and request.template_id is None
                ),
                exclude_product_query=product.name,
            )
            if not request.template_id:
                if reference_intent.explicit_video_type:
                    video_type = reference_intent.explicit_video_type
                elif requested_video_type:
                    video_type = requested_video_type
                else:
                    video_type = source_script.get("video_type") or preferred_video_type
                template = _select_rewrite_template(
                    db=db,
                    requested_video_type=video_type,
                    template_id=None,
                    allow_type_fallback=False,
                )
        else:
            template = _select_rewrite_template(
                db=db,
                requested_video_type=requested_video_type,
                template_id=request.template_id,
            )
            if not requested_video_type or request.template_id:
                video_type = template.video_type
            source_script = _select_rewrite_source_script(
                db,
                video_type,
                exclude_product_query=product.name,
            )

    if not video_type:
        if engine != "template":
            video_type = "AI智能生成"

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
    if engine != "template":
        product_context.update(build_product_detail_payload(product))

    # 准备模板上下文；模板库改写才使用结构化模板
    template_context = None
    if template and engine == "template":
        template_context = _script_template_context(template)

    # 模板库改写使用脚本模板库；AI生成只在用户明确选择类型时参考同类型结构
    reference_scripts = []
    if engine != "template" and requested_video_type:
        reference_scripts = generator.find_type_structure_scripts(
            video_type,
            db,
            limit=3,
        )

    # 根据引擎类型分支调用
    if engine == "template":
        # 模板库改写模式：以脚本模板库中选中的模板为主体进行改写
        try:
            script_content = await generator.generate_from_library(
                product=product_context,
                video_type=video_type,
                template=template_context,
                source_script=source_script,
                tone=request.tone,
                extra_requirements=generation_requirements,
                include_shot_design=request.include_shot_design,
            )
        except ScriptGenerationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=f"模板库改写失败：{exc}") from exc
        if not (script_content or "").strip():
            raise HTTPException(status_code=502, detail="模板库改写失败：模型未返回有效脚本，请检查 AI 配置后重试")
    else:
        # AI生成模式：基于产品资料创作；明确选择类型时只参考同类型脚本结构
        recent_openings = _recent_ai_openings(db, product.id)
        try:
            script_content = await generator.generate(
                product=product_context,
                template=template_context,
                video_type=video_type,
                tone=request.tone,
                extra_requirements=generation_requirements,
                reference_scripts=reference_scripts,
                include_shot_design=request.include_shot_design,
                recent_openings=recent_openings,
            )
        except ScriptGenerationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=f"AI生成失败：{exc}") from exc
        if not (script_content or "").strip():
            raise HTTPException(status_code=502, detail="AI生成失败：模型未返回有效脚本，请检查 AI 配置后重试")

    # 保存生成记录
    using_template_library = engine == "template" and template is not None
    engine_label = "模板库改写" if using_template_library else "AI生成"
    model_interface_key = "script_library_rewrite" if using_template_library else "script_generate"
    record = GeneratedScript(
        product_id=product.id,
        template_id=template.id if template else None,
        source_script_id=source_script["id"] if source_script else None,
        source_script_source=source_script["source"] if source_script else None,
        source_script_title=source_script["title"] if source_script else None,
        source_script_content=source_script["content"] if source_script else None,
        script_content=script_content,
        video_type=video_type,
        ai_model=f"{engine_label} · {generator.get_model_name(model_interface_key)}",
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
        template_id=template.id if template else None,
        template_name=template.name if template else None,
        template_reference_script=template.example_script if template else None,
        source_script_id=source_script["id"] if source_script else None,
        source_script_source=source_script["source"] if source_script else None,
        source_script_title=source_script["title"] if source_script else None,
        source_script_content=source_script["content"] if source_script else None,
        source_match_query=source_match_query,
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
    template_ids = {r.template_id for r in records if r.template_id}
    templates_by_id = {}
    if template_ids:
        templates_by_id = {
            t.id: t
            for t in db.query(ScriptTemplate).filter(ScriptTemplate.id.in_(template_ids)).all()
        }
    result = []
    for r in records:
        template = templates_by_id.get(r.template_id)
        item = GeneratedScriptOut(
            id=r.id,
            product_id=r.product_id,
            product_name=r.product.name if r.product else None,
            template_id=r.template_id,
            template_name=template.name if template else None,
            template_reference_script=template.example_script if template else None,
            source_script_id=r.source_script_id,
            source_script_source=r.source_script_source,
            source_script_title=r.source_script_title,
            source_script_content=r.source_script_content,
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

    template = (
        db.query(ScriptTemplate).filter(ScriptTemplate.id == record.template_id).first()
        if record.template_id
        else None
    )

    return GeneratedScriptOut(
        id=record.id,
        product_id=record.product_id,
        product_name=record.product.name if record.product else None,
        template_id=record.template_id,
        template_name=template.name if template else None,
        template_reference_script=template.example_script if template else None,
        source_script_id=record.source_script_id,
        source_script_source=record.source_script_source,
        source_script_title=record.source_script_title,
        source_script_content=record.source_script_content,
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

    try:
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
    except ScriptRewriteGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if not (rewritten or "").strip():
        raise HTTPException(status_code=502, detail="脚本改写失败：模型未返回有效改写脚本，请检查 AI 配置后重试")

    return ScriptRewriteResponse(
        original_script=request.original_script,
        rewritten_script=rewritten,
        product_name=product.name,
    )


@router.post("/generate/jobs", status_code=202)
def enqueue_script_generation(
    data: ScriptGenerateRequest,
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    x_facai_source_ref: str | None = Header(None, alias="X-Facai-Source-Ref"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    job, created = create_background_job(
        db,
        owner_key=owner_key_for_request(request, x_facai_client_id),
        job_type="ai.scripts.generate",
        request_payload=data.model_dump(mode="json"),
        origin_path="/app/generate",
        source_ref=x_facai_source_ref or "",
        queue_group="ai",
        idempotency_key=idempotency_key or "",
        max_attempts=2,
        message="脚本生成任务等待执行",
    )
    return {"job": job_to_dict(job), "created": created}


@router.post("/rewrite/jobs", status_code=202)
def enqueue_script_rewrite(
    data: ScriptRewriteRequest,
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    x_facai_source_ref: str | None = Header(None, alias="X-Facai-Source-Ref"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    job, created = create_background_job(
        db,
        owner_key=owner_key_for_request(request, x_facai_client_id),
        job_type="ai.scripts.rewrite",
        request_payload=data.model_dump(mode="json"),
        origin_path="/app/rewrite",
        source_ref=x_facai_source_ref or "",
        queue_group="ai",
        idempotency_key=idempotency_key or "",
        max_attempts=2,
        message="脚本改写任务等待执行",
    )
    return {"job": job_to_dict(job), "created": created}


def _run_script_generate_job(payload: dict, job_id: int) -> dict | None:
    if is_cancel_requested(job_id):
        mark_cancelling(job_id)
        return None

    async def run() -> dict:
        with SessionLocal() as worker_db:
            result = await generate_script(ScriptGenerateRequest.model_validate(payload), worker_db)
            return result.model_dump(mode="json")

    return asyncio.run(run())


def _run_script_rewrite_job(payload: dict, job_id: int) -> dict | None:
    if is_cancel_requested(job_id):
        mark_cancelling(job_id)
        return None

    async def run() -> dict:
        with SessionLocal() as worker_db:
            result = await rewrite_script(ScriptRewriteRequest.model_validate(payload), worker_db)
            return result.model_dump(mode="json")

    return asyncio.run(run())


register_background_handler("ai.scripts.generate", _run_script_generate_job, queue_group="ai")
register_background_handler("ai.scripts.rewrite", _run_script_rewrite_job, queue_group="ai")
