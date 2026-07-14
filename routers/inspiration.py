"""General inspiration chat API."""
import asyncio
import json
import logging
import re
import time
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from config import (
    INSPIRATION_AI_TIMEOUT_SECONDS as CONFIG_INSPIRATION_AI_TIMEOUT_SECONDS,
    INSPIRATION_THINKING_AI_TIMEOUT_SECONDS as CONFIG_INSPIRATION_THINKING_AI_TIMEOUT_SECONDS,
)
from database import get_db
from services.ai_service import ai_service
from services.ai_config import get_or_create_interface_setting, get_provider_definition
from services.inspiration_attachments import (
    AttachmentExtractionError,
    MAX_ATTACHMENT_BYTES,
    extract_inspiration_attachment,
    load_image_attachment_data_url,
    resolve_image_attachment,
)
from services.inspiration_agent import InspirationAgentResult, run_inspiration_agent
from services import inspiration_documents
from services.product_rag import find_product_context_for_inspiration
from services.seedance_prompt_generator import (
    SEEDANCE_INTERFACE_KEY,
    SeedancePromptGenerationError,
    seedance_prompt_generator,
)
from services.upload_limits import read_upload_bytes
from services.web_research import search_web
from schemas import StrictRequestModel
from vector_store import get_embedding_degraded_reason


router = APIRouter()
logger = logging.getLogger(__name__)
INSPIRATION_AI_TIMEOUT_SECONDS = CONFIG_INSPIRATION_AI_TIMEOUT_SECONDS
INSPIRATION_THINKING_AI_TIMEOUT_SECONDS = CONFIG_INSPIRATION_THINKING_AI_TIMEOUT_SECONDS
InspirationToolMode = Literal["chat", "thinking", "research", "analysis", "seedance"]
ProductContextMode = Literal["off", "auto", "always"]
WebSearchMode = Literal["auto", "always"]


class ChatTurn(StrictRequestModel):
    role: str
    content: str = Field(default="", max_length=4000)


class DocumentChatTurn(StrictRequestModel):
    role: str
    content: str = Field(default="", max_length=60000)


class InspirationAttachment(StrictRequestModel):
    filename: str = Field(default="", max_length=200)
    file_type: str = Field(default="", max_length=32)
    text: str = Field(default="", max_length=24000)
    char_count: int = 0
    kind: Literal["text", "image"] = "text"
    attachment_id: str = Field(default="", max_length=80)
    mime_type: str = Field(default="", max_length=80)
    preview_url: str = Field(default="", max_length=240)


class WebSource(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class ProductReference(BaseModel):
    product_id: int | None = None
    name: str = ""
    category: str = ""
    price: float | None = None


class AgentTraceStep(BaseModel):
    tool: str = Field(default="", max_length=40)
    label: str = Field(default="", max_length=40)
    status: str = Field(default="success", max_length=20)
    summary: str = Field(default="", max_length=240)


class InspirationChatRequest(StrictRequestModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    tool_mode: InspirationToolMode = "chat"
    product_context_mode: ProductContextMode = "off"
    web_search_mode: WebSearchMode = "auto"
    attachments: list[InspirationAttachment] = Field(default_factory=list, max_length=6)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请输入聊天内容")
        return value


class InspirationChatResponse(BaseModel):
    answer: str
    mode: Literal["ai", "fallback"]
    model: str
    tool_mode: InspirationToolMode = "chat"
    reasoning: str = ""
    sources: list[WebSource] = Field(default_factory=list)
    attachments_used: list[InspirationAttachment] = Field(default_factory=list)
    product_context_used: bool = False
    products: list["ProductReference"] = Field(default_factory=list)
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


class InspirationDocumentRequest(StrictRequestModel):
    message: str = Field(default="", max_length=4000)
    answer: str = Field(..., min_length=1, max_length=120000)
    history: list[DocumentChatTurn] = Field(default_factory=list, max_length=40)
    attachments: list[InspirationAttachment] = Field(default_factory=list, max_length=6)
    products: list[ProductReference] = Field(default_factory=list, max_length=6)
    title: str = Field(default="", max_length=120)


class InspirationDocumentResponse(BaseModel):
    title: str
    filename: str
    download_url: str


SYSTEM_PROMPT = """你是法采新媒体运营AI工作助手。
你擅长短视频脚本创意、烘焙产品卖点表达、直播与抖音运营、活动文案、拍摄选题和内容复盘。
回答要直接、可执行、适合本地运营团队拿去改写使用。
如果用户问题和法采业务无关，也可以正常协助，但优先把建议落回内容创作和运营执行。
"""

NO_PRODUCT_CONTEXT_INSTRUCTION = (
    "当前未启用“基于产品资料”。遇到“法采的产品怎么样”这类泛问题时，"
    "只做高层判断、分析维度或追问用户想看哪类产品/场景；"
    "不要编造 SKU、价格、具体产品资料，不要输出产品资料式清单或脚本模板。"
)

TOOL_MODE_INSTRUCTIONS = {
    "chat": "",
    "thinking": "当前为思考模式。请先做充分推理，再给出结构清晰、可执行的最终答案。",
    "research": "当前为深入研究模式。请优先利用外网搜索结果，给出结论、依据、风险、可执行建议和需要进一步验证的问题。",
    "analysis": "当前为数据分析模式。请优先分析附件数据，再结合外网搜索结果补充行业或运营参照，输出关键发现、异常、原因假设和下一步动作。",
}

WEB_SEARCH_INTENT_TERMS = (
    "网上",
    "公开信息",
    "公开资料",
    "全网",
    "联网",
    "搜索",
    "检索",
    "外网",
    "官网",
    "官方网站",
    "小红书",
    "抖音",
    "大众点评",
    "电商平台",
)

WEB_SEARCH_QUERY_STOP_PHRASES = (
    "根据网上公开信息",
    "根据网上的公开信息",
    "根据公开信息",
    "网上公开信息",
    "网上的公开信息",
    "公开信息",
    "公开资料",
    "联网搜索",
    "搜索一下",
    "搜索",
    "检索",
    "帮我",
    "请",
    "告诉我",
    "给我",
    "一个",
    "两个",
    "三个",
    "四个",
    "五个",
    "几个",
    "一些",
    "汇总一下",
    "汇总",
    "整理一下",
    "整理",
    "就是",
    "所有的",
    "所有",
    "一下",
    "看看",
    "基于",
    "按照",
)


def _recent_history(history: list[ChatTurn]) -> list[dict[str, str]]:
    cleaned = []
    for item in history:
        content = (item.content or "").strip()
        if content and item.role in {"user", "assistant"}:
            cleaned.append({"role": item.role, "content": content})
    return cleaned[-12:]


def _fallback_answer(message: str, reason: Literal["unavailable", "timeout"] = "unavailable") -> str:
    intro = (
        "AI 响应超时，已先返回兜底建议：\n\n"
        if reason == "timeout"
        else "AI 服务暂时不可用，但可以先这样拆解你的问题：\n\n"
    )
    closing = (
        "等 AI 响应恢复后，我可以继续把它整理成完整方案。"
        if reason == "timeout"
        else "等 AI 服务恢复后，我可以继续把它整理成完整方案。"
    )
    return (
        f"{intro}你刚才问的是：{message}\n\n"
        "1. 先明确目标：要做选题、脚本、标题、活动文案，还是拍摄方向。\n"
        "2. 再补充对象：产品名、使用场景、价格活动、希望强调的卖点。\n"
        "3. 最后给出约束：平台、时长、语气、是否需要镜头说明。\n\n"
        f"{closing}"
    )


def _fallback_answer_with_products(
    message: str,
    products: list[dict],
    reason: Literal["unavailable", "timeout"] = "unavailable",
) -> str:
    answer = _fallback_answer(message, reason=reason)
    if not products:
        return answer
    names = "、".join(product.get("name", "") for product in products[:6] if product.get("name"))
    if not names:
        return answer
    return answer + f"\n\n已先匹配到可参考产品：{names}。AI 响应恢复后可以继续把这些资料整理成完整创意方案。"


def _image_fallback_answer(message: str) -> str:
    return (
        "图片已上传，但当前 AI 接口没有返回图片理解结果。"
        "这通常是当前模型或火山方舟 Endpoint 暂不支持图片输入，"
        "请在 AI配置里切换到支持视觉/多模态的模型后再试。\n\n"
        f"你刚才的问题是：{message}"
    )


def _model_for_tool_mode(tool_mode: str) -> str | None:
    return None


def _interface_key_for_tool_mode(tool_mode: str) -> str:
    if tool_mode == "seedance":
        return SEEDANCE_INTERFACE_KEY
    return {
        "thinking": "inspiration_thinking",
        "research": "inspiration_research",
        "analysis": "inspiration_analysis",
    }.get(tool_mode, "inspiration_chat")


def _ai_timeout_for_tool_mode(tool_mode: str) -> float:
    if tool_mode == "thinking":
        return INSPIRATION_THINKING_AI_TIMEOUT_SECONDS
    return INSPIRATION_AI_TIMEOUT_SECONDS


def _tool_mode_label(tool_mode: str) -> str:
    return {
        "chat": "AI 对话",
        "thinking": "思考模式",
        "research": "深入研究",
        "analysis": "数据分析",
        "seedance": "分镜提示词生成",
    }.get(tool_mode, "AI 对话")


def _is_model_status_question(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    model_terms = (
        "模型",
        "model",
        "deepseek",
        "豆包",
        "doubao",
        "火山",
        "方舟",
        "qwen",
        "通义",
        "glm",
        "智谱",
        "minimax",
    )
    status_terms = (
        "你用",
        "用的是",
        "当前",
        "现在",
        "这里",
        "这个",
        "调用",
        "是什么",
        "什么模型",
        "哪个模型",
        "是不是",
        "还是",
        "哪一个",
        "哪款",
    )
    return any(term in text for term in model_terms) and any(term in text for term in status_terms)


def _model_status_answer(tool_mode: str, interface_key: str, db: Session) -> tuple[str, str]:
    setting = get_or_create_interface_setting(db, interface_key)
    provider = get_provider_definition(setting.provider)
    model = (setting.model or "").strip() or provider.default_model()
    mode_label = _tool_mode_label(tool_mode)
    comparison = (
        "按当前 AI配置，这一轮会走 DeepSeek。"
        if setting.provider == "deepseek"
        else f"按当前 AI配置，这一轮会走 {provider.label}，不是 DeepSeek。"
    )
    answer = (
        f"当前功能：{mode_label}\n"
        f"服务商：{provider.label}\n"
        f"模型：{model}\n\n"
        f"{comparison}\n"
        "这类模型状态问题我会直接读取本地 AI配置回答，不进入思考模式生成。"
    )
    return answer, model


def _normalize_ai_result(result, model: str) -> tuple[str, str, str]:
    if isinstance(result, dict):
        return (
            str(result.get("content") or ""),
            str(result.get("reasoning") or ""),
            str(result.get("model") or model),
        )
    return str(result or ""), "", model


def _safe_product_context(message: str, db: Session, *, force: bool = False) -> dict:
    try:
        return find_product_context_for_inspiration(message, db, limit=6, force=force)
    except Exception:
        return {"used": False, "context": "", "products": []}


def _message_with_product_context(message: str, product_context: dict) -> str:
    context = (product_context.get("context") or "").strip()
    if not context:
        return message
    return (
        f"用户问题：{message}\n\n"
        f"可引用的产品资料：\n{context}\n\n"
        "回答要求：以创意、脚本、选题、文案或运营表达为主；"
        "自然结合上面的产品资料；不要编造资料外的产品信息；"
        "不要单独列“来源”段落。"
    )


def _attachment_context(attachments: list[InspirationAttachment]) -> str:
    if not attachments:
        return ""
    parts = ["附件资料："]
    for index, attachment in enumerate(attachments[:6], start=1):
        text = (attachment.text or "").strip()
        if not text:
            continue
        parts.append(
            f"[{index}] 文件：{attachment.filename}\n"
            f"类型：{attachment.file_type}\n"
            f"内容摘录：\n{text[:8000]}"
        )
    return "\n\n".join(parts)


def _text_attachments(attachments: list[InspirationAttachment]) -> list[InspirationAttachment]:
    return [attachment for attachment in attachments if (attachment.text or "").strip()]


def _image_attachments(attachments: list[InspirationAttachment], tool_mode: str) -> list[InspirationAttachment]:
    if tool_mode == "seedance":
        return []
    return [
        attachment
        for attachment in attachments
        if attachment.kind == "image" and (attachment.attachment_id or "").strip()
    ]


def _multimodal_user_content(
    text: str,
    attachments: list[InspirationAttachment],
) -> str | list[dict]:
    if not attachments:
        return text
    image_parts: list[dict] = []
    image_names: list[str] = []
    for attachment in attachments[:6]:
        try:
            image_url = load_image_attachment_data_url(attachment.attachment_id)
        except AttachmentExtractionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        image_names.append(attachment.filename or "图片附件")
        image_parts.append({"type": "image_url", "image_url": {"url": image_url}})
    prompt = text
    if image_names:
        prompt = f"{text}\n\n图片附件：{', '.join(image_names)}\n请结合图片内容回答。"
    return [{"type": "text", "text": prompt}, *image_parts]


def _web_context(sources: list[dict]) -> str:
    if not sources:
        return ""
    parts = ["外网搜索结果："]
    for index, source in enumerate(sources[:6], start=1):
        parts.append(
            f"[{index}] {source.get('title', '')}\n"
            f"URL：{source.get('url', '')}\n"
            f"摘要：{source.get('snippet', '')}"
        )
    return "\n\n".join(parts)


def _agent_trace_context(agent_trace: list[dict] | None) -> str:
    if not agent_trace:
        return ""
    lines = []
    for step in agent_trace[:6]:
        if not isinstance(step, dict):
            continue
        label = str(step.get("label") or step.get("tool") or "工具").strip()
        summary = str(step.get("summary") or "").strip()
        status = str(step.get("status") or "").strip()
        if not label and not summary:
            continue
        suffix = summary or status or "已执行"
        lines.append(f"- {label}：{suffix}")
    if not lines:
        return ""
    return "Agent 工具摘要：\n" + "\n".join(lines)


def _embedding_degraded_reason(product_context: dict, *, since_monotonic: float | None = None) -> str:
    reason = ""
    if isinstance(product_context, dict):
        reason = str(
            product_context.get("degraded_reason")
            or product_context.get("embedding_degraded_reason")
            or ""
        ).strip()
    if not reason:
        reason = get_embedding_degraded_reason(max_age_seconds=30.0, since_monotonic=since_monotonic).strip()
    return reason[:200]


def _trace_embedding_degradation(
    agent_trace: list[dict],
    product_context: dict,
    *,
    since_monotonic: float | None = None,
) -> list[dict]:
    reason = _embedding_degraded_reason(product_context, since_monotonic=since_monotonic)
    if not reason:
        return agent_trace
    if any(reason in str(step.get("summary") or "") for step in agent_trace):
        return agent_trace
    return [
        *agent_trace,
        {
            "tool": "product_rag",
            "label": "向量检索",
            "status": "warning",
            "summary": f"向量检索降级：{reason}"[:240],
        },
    ]


def _should_search_web(message: str, tool_mode: str, web_search_mode: str = "auto") -> bool:
    if web_search_mode == "always" and tool_mode != "seedance":
        return True
    if tool_mode in {"research", "analysis"}:
        return True
    if tool_mode != "chat":
        return False
    text = (message or "").strip()
    return any(term in text for term in WEB_SEARCH_INTENT_TERMS)


def _web_search_query(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""
    query = text
    for phrase in WEB_SEARCH_QUERY_STOP_PHRASES:
        query = query.replace(phrase, " ")
    query = re.sub(r"[，。！？；、,.!?;:：()（）\[\]【】\"'“”]+", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    if len(query) < 2:
        query = text
    return query[:120].strip()


def _empty_web_search_notice(message: str, sources: list[dict], tool_mode: str, web_search_mode: str = "auto") -> str:
    if sources or not _should_search_web(message, tool_mode, web_search_mode):
        return ""
    return (
        "联网搜索提示：后端已尝试检索外网公开信息，但本次没有获取到可用网页结果。"
        "不要声称自己没有联网搜索权限；可以说明未检索到可用结果，"
        "再基于用户已提供信息给出下一步建议或更具体的检索关键词。"
    )


def _compose_user_message(
    message: str,
    product_context: dict,
    attachments: list[InspirationAttachment],
    sources: list[dict],
    tool_mode: str,
    web_search_mode: str = "auto",
    agent_trace: list[dict] | None = None,
) -> str:
    sections = [f"用户问题：{message}" if product_context.get("context") or attachments or sources or tool_mode != "chat" else message]
    instruction = TOOL_MODE_INSTRUCTIONS.get(tool_mode, "")
    if instruction:
        sections.append(f"模式要求：{instruction}")
    agent_context = _agent_trace_context(agent_trace)
    if agent_context:
        sections.append(agent_context)
    attachment_context = _attachment_context(attachments)
    if attachment_context:
        sections.append(attachment_context)
    web_context = _web_context(sources)
    if web_context:
        sections.append(web_context)
    empty_web_notice = _empty_web_search_notice(message, sources, tool_mode, web_search_mode)
    if empty_web_notice:
        sections.append(empty_web_notice)
    product_message = _message_with_product_context(message, product_context)
    if product_message != message:
        sections.append(product_message.replace(f"用户问题：{message}\n\n", ""))
    if attachments or sources:
        sections.append("回答要求：不要编造附件或搜索结果之外的事实；引用外网信息时用自然语言说明依据；优先给出可执行结论。")
    return "\n\n".join(section for section in sections if section)


async def _safe_web_search(message: str, tool_mode: str, web_search_mode: str = "auto") -> list[dict]:
    if not _should_search_web(message, tool_mode, web_search_mode):
        return []
    try:
        return await search_web(_web_search_query(message), max_results=5)
    except Exception:
        return []


def _document_user_payload(data: InspirationDocumentRequest) -> str:
    sections = [
        f"用户需求：{data.message.strip() or '未提供'}",
        f"AI 原始回答：\n{data.answer.strip()}",
    ]
    recent_history = _recent_history(data.history)
    if recent_history:
        history_text = "\n".join(f"{item['role']}：{item['content']}" for item in recent_history[-8:])
        sections.append(f"对话上下文：\n{history_text}")
    if data.products:
        products = []
        for product in data.products[:6]:
            meta = " / ".join(
                part for part in [
                    product.name,
                    product.category,
                    f"¥{product.price}" if product.price is not None else "",
                ] if part
            )
            if meta:
                products.append(meta)
        if products:
            sections.append("参考产品：\n" + "\n".join(f"- {item}" for item in products))
    if data.attachments:
        attachments = [
            f"- {attachment.filename}：{(attachment.text or '').strip()[:800]}"
            for attachment in data.attachments[:6]
            if (attachment.filename or "").strip() and (attachment.text or "").strip()
        ]
        if attachments:
            sections.append("附件摘录：\n" + "\n".join(attachments))
    sections.append(
        "输出要求：请整理成一份可直接交付的 Word 文档正文。"
        "保留可执行结构，可以使用一级/二级标题、编号清单和短段落；"
        "不要输出寒暄语，不要编造未提供的产品信息。"
    )
    return "\n\n".join(sections)


async def _build_document_content(data: InspirationDocumentRequest, db: Session) -> str:
    fallback = data.answer.strip()
    if not ai_service.is_interface_available("inspiration_chat", db=db):
        return fallback
    document_model = ai_service.get_model_name(interface_key="inspiration_chat", db=db)
    try:
        result = await asyncio.wait_for(
            ai_service.chat(
                [
                    {
                        "role": "system",
                        "content": "你是法采新媒体运营文档整理助手，负责把 AI 对话结果整理成清晰的业务文档正文。",
                    },
                    {"role": "user", "content": _document_user_payload(data)},
                ],
                temperature=0.4,
                allow_fallback=False,
                model=None,
                interface_key="inspiration_chat",
                db=db,
            ),
            timeout=INSPIRATION_AI_TIMEOUT_SECONDS,
        )
        content, _, _ = _normalize_ai_result(result, document_model)
        return content.strip() or fallback
    except Exception as exc:
        logger.warning("Inspiration document AI formatting failed: %s", exc)
        return fallback


def _seedance_payload_from_chat(data: InspirationChatRequest) -> tuple[str, str | None, list[InspirationAttachment]]:
    attachments_used = _text_attachments(data.attachments)
    if attachments_used:
        script_content = "\n\n".join((attachment.text or "").strip() for attachment in attachments_used)
        requirements = data.message.strip() or None
        return script_content, requirements, attachments_used
    return data.message.strip(), None, []


async def _chat_with_seedance(data: InspirationChatRequest, db: Session) -> InspirationChatResponse:
    script_content, requirements, attachments_used = _seedance_payload_from_chat(data)
    model = ai_service.get_model_name(interface_key=SEEDANCE_INTERFACE_KEY, db=db)
    try:
        result = await seedance_prompt_generator.generate(
            script_content=script_content,
            requirements=requirements,
            db=db,
        )
    except SeedancePromptGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    answer = str(result.get("prompt_text") or "").strip()
    if not answer:
        raise HTTPException(status_code=502, detail="DeepSeek V4 Pro 未返回可用的 Seedance 分镜提示词，请重试。")
    return InspirationChatResponse(
        answer=answer,
        mode="ai",
        model=model,
        tool_mode="seedance",
        attachments_used=attachments_used,
        product_context_used=False,
        products=[],
        sources=[],
    )


@router.post("/attachments", response_model=InspirationAttachment)
async def upload_inspiration_attachment(file: UploadFile = File(...)):
    data = await read_upload_bytes(file, max_bytes=MAX_ATTACHMENT_BYTES)
    try:
        from services.bounded_executor import WorkQueueFull, run_blocking
        attachment = await run_blocking(
            extract_inspiration_attachment,
            file.filename or "attachment",
            file.content_type or "",
            data,
        )
    except WorkQueueFull as exc:
        raise HTTPException(status_code=503, detail="文件解析任务繁忙，请稍后重试") from exc
    except AttachmentExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return InspirationAttachment(
        filename=attachment.filename,
        file_type=attachment.file_type,
        text=attachment.text,
        char_count=attachment.char_count,
        kind=attachment.kind,
        attachment_id=attachment.attachment_id,
        mime_type=attachment.mime_type,
        preview_url=attachment.preview_url,
    )


@router.get("/attachments/{attachment_id}/preview")
async def preview_inspiration_attachment(attachment_id: str):
    try:
        path, mime_type = resolve_image_attachment(attachment_id)
    except AttachmentExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FileResponse(path, media_type=mime_type)


@router.post("/documents", response_model=InspirationDocumentResponse)
async def create_inspiration_document(data: InspirationDocumentRequest, db: Session = Depends(get_db)):
    content = await _build_document_content(data, db)
    try:
        generated = inspiration_documents.create_inspiration_document(
            message=data.message,
            content=content,
            products=[product.model_dump() for product in data.products],
            attachments=[attachment.model_dump() for attachment in data.attachments],
            title=data.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    encoded = quote(generated.filename)
    return InspirationDocumentResponse(
        title=generated.title,
        filename=generated.filename,
        download_url=f"/api/inspiration/documents/{encoded}/download",
    )


@router.get("/documents/{filename}/download")
def download_inspiration_document(filename: str):
    try:
        path = inspiration_documents.resolve_document_path(filename)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="文档不存在") from exc
    return FileResponse(
        str(path),
        media_type=inspiration_documents.DOCX_MEDIA_TYPE,
        filename=filename,
    )


@router.post("/chat", response_model=InspirationChatResponse)
async def chat_with_inspiration(data: InspirationChatRequest, db: Session = Depends(get_db)):
    message = data.message.strip()
    interface_key = _interface_key_for_tool_mode(data.tool_mode)
    if _is_model_status_question(message):
        answer, model = _model_status_answer(data.tool_mode, interface_key, db)
        return InspirationChatResponse(
            answer=answer,
            mode="ai",
            model=model,
            tool_mode=data.tool_mode,
            product_context_used=False,
            products=[],
        )
    if data.tool_mode == "seedance":
        return await _chat_with_seedance(data, db)
    model_override = _model_for_tool_mode(data.tool_mode)
    model = ai_service.get_model_name(model_override, interface_key=interface_key, db=db)
    force_product_context = data.product_context_mode == "always"
    text_attachments_used = _text_attachments(data.attachments)
    image_attachments_used = _image_attachments(data.attachments, data.tool_mode)
    attachments_used = text_attachments_used + image_attachments_used
    agent_trace: list[dict] = []
    vector_trace_started_at = time.monotonic()
    if force_product_context:
        try:
            agent_result = await run_inspiration_agent(
                message=message,
                db=db,
                product_context_enabled=True,
                web_search_enabled=_should_search_web(message, data.tool_mode, data.web_search_mode),
                attachments=text_attachments_used,
                tool_mode=data.tool_mode,
                product_context_func=find_product_context_for_inspiration,
                web_search_func=search_web,
                product_limit=6,
                web_query=_web_search_query(message),
                web_max_results=5,
            )
        except Exception as exc:
            logger.warning("AI-work agentic RAG failed: %s", exc)
            agent_result = InspirationAgentResult(
                product_context={"used": False, "context": "", "products": []},
                sources=[],
                agent_trace=[
                    {
                        "tool": "agent",
                        "label": "Agent",
                        "status": "error",
                        "summary": "工具编排失败，已降级为普通回答。",
                    }
                ],
            )
        product_context = agent_result.product_context
        sources = agent_result.sources
        agent_trace = agent_result.agent_trace
    else:
        product_context = {"used": False, "context": "", "products": []}
        sources = await _safe_web_search(message, data.tool_mode, data.web_search_mode)
    if force_product_context:
        agent_trace = _trace_embedding_degradation(
            agent_trace,
            product_context,
            since_monotonic=vector_trace_started_at,
        )
    products = product_context.get("products") or []
    product_context_used = bool(products)
    if not ai_service.is_interface_available(interface_key, db=db):
        return InspirationChatResponse(
            answer=_fallback_answer_with_products(message, products),
            mode="fallback",
            model=model,
            tool_mode=data.tool_mode,
            sources=sources,
            attachments_used=attachments_used,
            product_context_used=product_context_used,
            products=products,
            agent_trace=agent_trace,
        )

    system_prompt = SYSTEM_PROMPT
    tool_instruction = TOOL_MODE_INSTRUCTIONS.get(data.tool_mode, "")
    if tool_instruction:
        system_prompt = f"{system_prompt}\n{tool_instruction}"
    if not force_product_context and data.tool_mode == "chat":
        system_prompt = f"{system_prompt}\n{NO_PRODUCT_CONTEXT_INSTRUCTION}"
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_recent_history(data.history))
    user_message_text = _compose_user_message(
        message,
        product_context,
        text_attachments_used,
        sources,
        data.tool_mode,
        data.web_search_mode,
        agent_trace,
    )
    messages.append({
        "role": "user",
        "content": _multimodal_user_content(user_message_text, image_attachments_used),
    })
    timed_out = False
    timeout_seconds = _ai_timeout_for_tool_mode(data.tool_mode)
    try:
        result = await asyncio.wait_for(
            ai_service.chat(
                messages,
                temperature=0.7,
                allow_fallback=False,
                model=model_override,
                interface_key=interface_key,
                db=db,
                thinking=data.tool_mode == "thinking",
                reasoning_effort="high",
                return_reasoning=True,
                request_timeout=timeout_seconds,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        timed_out = True
        logger.warning("Inspiration chat AI call timed out after %.1fs", timeout_seconds)
        result = {"content": "", "reasoning": "", "model": model}
    answer, reasoning, result_model = _normalize_ai_result(result, model)
    answer = answer.strip()
    if not answer:
        fallback_answer = (
            _image_fallback_answer(message)
            if image_attachments_used and not timed_out
            else _fallback_answer_with_products(
                message,
                products,
                reason="timeout" if timed_out else "unavailable",
            )
        )
        return InspirationChatResponse(
            answer=fallback_answer,
            mode="fallback",
            model=model,
            tool_mode=data.tool_mode,
            sources=sources,
            attachments_used=attachments_used,
            product_context_used=product_context_used,
            products=products,
            agent_trace=agent_trace,
        )
    return InspirationChatResponse(
        answer=answer,
        mode="ai",
        model=result_model or model,
        tool_mode=data.tool_mode,
        reasoning=reasoning,
        sources=sources,
        attachments_used=attachments_used,
        product_context_used=product_context_used,
        products=products,
        agent_trace=agent_trace,
    )


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _stream_context_payload(
    *,
    sources: list[dict],
    attachments: list[InspirationAttachment],
    products: list[dict],
    product_context_used: bool,
    agent_trace: list[dict],
) -> dict:
    return {
        "sources": sources,
        "attachments": [attachment.model_dump() for attachment in attachments],
        "products": products,
        "product_context_used": product_context_used,
        "agent_trace": agent_trace,
    }


async def _inspiration_stream_events(data: InspirationChatRequest, request: Request, db: Session):
    message = data.message.strip()
    interface_key = _interface_key_for_tool_mode(data.tool_mode)
    model = ai_service.get_model_name(
        _model_for_tool_mode(data.tool_mode),
        interface_key=interface_key,
        db=db,
    )
    yield _sse_event(
        "meta",
        {"model": model, "tool_mode": data.tool_mode, "interface_key": interface_key},
    )

    if _is_model_status_question(message) or data.tool_mode == "seedance":
        response = (
            await _chat_with_seedance(data, db)
            if data.tool_mode == "seedance"
            else InspirationChatResponse(
                answer=_model_status_answer(data.tool_mode, interface_key, db)[0],
                mode="ai",
                model=_model_status_answer(data.tool_mode, interface_key, db)[1],
                tool_mode=data.tool_mode,
            )
        )
        context = _stream_context_payload(
            sources=[source.model_dump() for source in response.sources],
            attachments=response.attachments_used,
            products=[product.model_dump() for product in response.products],
            product_context_used=response.product_context_used,
            agent_trace=[step.model_dump() for step in response.agent_trace],
        )
        yield _sse_event("context", context)
        if response.reasoning:
            yield _sse_event("reasoning_delta", {"text": response.reasoning})
        yield _sse_event("delta", {"text": response.answer})
        yield _sse_event("done", {"mode": response.mode, "model": response.model, **context})
        return

    model_override = _model_for_tool_mode(data.tool_mode)
    text_attachments_used = _text_attachments(data.attachments)
    image_attachments_used = _image_attachments(data.attachments, data.tool_mode)
    attachments_used = text_attachments_used + image_attachments_used
    vector_trace_started_at = time.monotonic()
    agent_trace: list[dict] = []

    if data.product_context_mode == "always":
        try:
            agent_result = await run_inspiration_agent(
                message=message,
                db=db,
                product_context_enabled=True,
                web_search_enabled=_should_search_web(message, data.tool_mode, data.web_search_mode),
                attachments=text_attachments_used,
                tool_mode=data.tool_mode,
                product_context_func=find_product_context_for_inspiration,
                web_search_func=search_web,
                product_limit=6,
                web_query=_web_search_query(message),
                web_max_results=5,
            )
            product_context = agent_result.product_context
            sources = agent_result.sources
            agent_trace = agent_result.agent_trace
        except Exception as exc:
            logger.warning("AI-work streaming agentic RAG failed: %s", exc)
            product_context = {"used": False, "context": "", "products": []}
            sources = await _safe_web_search(message, data.tool_mode, data.web_search_mode)
            agent_trace = [{
                "tool": "agent",
                "label": "Agent",
                "status": "error",
                "summary": "工具编排失败，已降级为普通回答。",
            }]
    elif data.product_context_mode == "auto":
        product_context = _safe_product_context(message, db, force=False)
        sources = await _safe_web_search(message, data.tool_mode, data.web_search_mode)
    else:
        product_context = {"used": False, "context": "", "products": []}
        sources = await _safe_web_search(message, data.tool_mode, data.web_search_mode)

    if data.product_context_mode != "off":
        agent_trace = _trace_embedding_degradation(
            agent_trace,
            product_context,
            since_monotonic=vector_trace_started_at,
        )
    products = product_context.get("products") or []
    product_context_used = bool(products)
    context = _stream_context_payload(
        sources=sources,
        attachments=attachments_used,
        products=products,
        product_context_used=product_context_used,
        agent_trace=agent_trace,
    )
    yield _sse_event("context", context)

    if not ai_service.is_interface_available(interface_key, db=db):
        fallback = _fallback_answer_with_products(message, products)
        yield _sse_event("delta", {"text": fallback})
        yield _sse_event("done", {"mode": "fallback", "model": model, **context})
        return

    system_prompt = SYSTEM_PROMPT
    tool_instruction = TOOL_MODE_INSTRUCTIONS.get(data.tool_mode, "")
    if tool_instruction:
        system_prompt = f"{system_prompt}\n{tool_instruction}"
    if data.product_context_mode == "off" and data.tool_mode == "chat":
        system_prompt = f"{system_prompt}\n{NO_PRODUCT_CONTEXT_INSTRUCTION}"
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_recent_history(data.history))
    user_message_text = _compose_user_message(
        message,
        product_context,
        text_attachments_used,
        sources,
        data.tool_mode,
        data.web_search_mode,
        agent_trace,
    )
    messages.append({
        "role": "user",
        "content": _multimodal_user_content(user_message_text, image_attachments_used),
    })

    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    result_model = model
    try:
        async for event in ai_service.stream_chat(
            messages,
            temperature=0.7,
            model=model_override,
            interface_key=interface_key,
            db=db,
            thinking=data.tool_mode == "thinking",
            reasoning_effort="high",
            request_timeout=_ai_timeout_for_tool_mode(data.tool_mode),
        ):
            if await request.is_disconnected():
                return
            event_type = str(event.get("type") or "")
            if event_type == "reasoning_delta":
                text_value = str(event.get("text") or "")
                reasoning_parts.append(text_value)
                yield _sse_event("reasoning_delta", {"text": text_value})
            elif event_type == "delta":
                text_value = str(event.get("text") or "")
                answer_parts.append(text_value)
                yield _sse_event("delta", {"text": text_value})
            elif event_type == "done":
                result_model = str(event.get("model") or result_model)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Inspiration streaming request failed: %s", exc)
        yield _sse_event("error", {"message": str(exc)[:1000], "partial": "".join(answer_parts)})
        return

    if not answer_parts:
        fallback = _fallback_answer_with_products(message, products)
        yield _sse_event("delta", {"text": fallback})
        answer_parts.append(fallback)
        mode = "fallback"
    else:
        mode = "ai"
    yield _sse_event(
        "done",
        {
            "mode": mode,
            "model": result_model,
            "reasoning": "".join(reasoning_parts),
            **context,
        },
    )


@router.post("/chat/stream")
async def stream_chat_with_inspiration(
    data: InspirationChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return StreamingResponse(
        _inspiration_stream_events(data, request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
