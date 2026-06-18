"""General inspiration chat API."""
import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from config import DEEPSEEK_V4_FLASH_MODEL, DEEPSEEK_V4_PRO_MODEL
from database import get_db
from services.ai_service import ai_service
from services.inspiration_attachments import AttachmentExtractionError, extract_attachment_text
from services.product_rag import find_product_context_for_inspiration
from services.web_research import search_web


router = APIRouter()
logger = logging.getLogger(__name__)
INSPIRATION_AI_TIMEOUT_SECONDS = 45.0
INSPIRATION_THINKING_AI_TIMEOUT_SECONDS = 120.0


class ChatTurn(BaseModel):
    role: str
    content: str = Field(default="", max_length=4000)


class InspirationAttachment(BaseModel):
    filename: str = Field(default="", max_length=200)
    file_type: str = Field(default="", max_length=32)
    text: str = Field(default="", max_length=24000)
    char_count: int = 0


class WebSource(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class InspirationChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    tool_mode: Literal["chat", "thinking", "research", "analysis"] = "chat"
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
    tool_mode: Literal["chat", "thinking", "research", "analysis"] = "chat"
    reasoning: str = ""
    sources: list[WebSource] = Field(default_factory=list)
    attachments_used: list[InspirationAttachment] = Field(default_factory=list)
    product_context_used: bool = False
    products: list["ProductReference"] = Field(default_factory=list)


class ProductReference(BaseModel):
    product_id: int | None = None
    name: str = ""
    category: str = ""
    price: float | None = None


SYSTEM_PROMPT = """你是法采新媒体运营AI工作助手。
你擅长短视频脚本创意、烘焙产品卖点表达、直播与抖音运营、活动文案、拍摄选题和内容复盘。
回答要直接、可执行、适合本地运营团队拿去改写使用。
如果用户问题和法采业务无关，也可以正常协助，但优先把建议落回内容创作和运营执行。
"""

TOOL_MODE_INSTRUCTIONS = {
    "chat": "",
    "thinking": "当前为思考模式。请先做充分推理，再给出结构清晰、可执行的最终答案。",
    "research": "当前为深入研究模式。请优先利用外网搜索结果，给出结论、依据、风险、可执行建议和需要进一步验证的问题。",
    "analysis": "当前为数据分析模式。请优先分析附件数据，再结合外网搜索结果补充行业或运营参照，输出关键发现、异常、原因假设和下一步动作。",
}


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


def _model_for_tool_mode(tool_mode: str) -> str:
    return DEEPSEEK_V4_PRO_MODEL if tool_mode == "thinking" else DEEPSEEK_V4_FLASH_MODEL


def _interface_key_for_tool_mode(tool_mode: str) -> str:
    return {
        "thinking": "inspiration_thinking",
        "research": "inspiration_research",
        "analysis": "inspiration_analysis",
    }.get(tool_mode, "inspiration_chat")


def _ai_timeout_for_tool_mode(tool_mode: str) -> float:
    if tool_mode == "thinking":
        return INSPIRATION_THINKING_AI_TIMEOUT_SECONDS
    return INSPIRATION_AI_TIMEOUT_SECONDS


def _normalize_ai_result(result, model: str) -> tuple[str, str, str]:
    if isinstance(result, dict):
        return (
            str(result.get("content") or ""),
            str(result.get("reasoning") or ""),
            str(result.get("model") or model),
        )
    return str(result or ""), "", model


def _safe_product_context(message: str, db: Session) -> dict:
    try:
        return find_product_context_for_inspiration(message, db, limit=6)
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


def _compose_user_message(
    message: str,
    product_context: dict,
    attachments: list[InspirationAttachment],
    sources: list[dict],
    tool_mode: str,
) -> str:
    sections = [f"用户问题：{message}" if product_context.get("context") or attachments or sources or tool_mode != "chat" else message]
    instruction = TOOL_MODE_INSTRUCTIONS.get(tool_mode, "")
    if instruction:
        sections.append(f"模式要求：{instruction}")
    attachment_context = _attachment_context(attachments)
    if attachment_context:
        sections.append(attachment_context)
    web_context = _web_context(sources)
    if web_context:
        sections.append(web_context)
    product_message = _message_with_product_context(message, product_context)
    if product_message != message:
        sections.append(product_message.replace(f"用户问题：{message}\n\n", ""))
    if attachments or sources:
        sections.append("回答要求：不要编造附件或搜索结果之外的事实；引用外网信息时用自然语言说明依据；优先给出可执行结论。")
    return "\n\n".join(section for section in sections if section)


async def _safe_web_search(message: str, tool_mode: str) -> list[dict]:
    if tool_mode not in {"research", "analysis"}:
        return []
    try:
        return await search_web(message, max_results=5)
    except Exception:
        return []


@router.post("/attachments", response_model=InspirationAttachment)
async def upload_inspiration_attachment(file: UploadFile = File(...)):
    data = await file.read()
    try:
        attachment = extract_attachment_text(file.filename or "attachment", file.content_type or "", data)
    except AttachmentExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return InspirationAttachment(
        filename=attachment.filename,
        file_type=attachment.file_type,
        text=attachment.text,
        char_count=attachment.char_count,
    )


@router.post("/chat", response_model=InspirationChatResponse)
async def chat_with_inspiration(data: InspirationChatRequest, db: Session = Depends(get_db)):
    message = data.message.strip()
    selected_model = _model_for_tool_mode(data.tool_mode)
    interface_key = _interface_key_for_tool_mode(data.tool_mode)
    model = ai_service.get_model_name(selected_model, interface_key=interface_key, db=db)
    product_context = _safe_product_context(message, db)
    products = product_context.get("products") or []
    product_context_used = bool(products)
    sources = await _safe_web_search(message, data.tool_mode)
    attachments_used = [attachment for attachment in data.attachments if (attachment.text or "").strip()]
    if not ai_service.is_available:
        return InspirationChatResponse(
            answer=_fallback_answer_with_products(message, products),
            mode="fallback",
            model=model,
            tool_mode=data.tool_mode,
            sources=sources,
            attachments_used=attachments_used,
            product_context_used=product_context_used,
            products=products,
        )

    system_prompt = SYSTEM_PROMPT
    tool_instruction = TOOL_MODE_INSTRUCTIONS.get(data.tool_mode, "")
    if tool_instruction:
        system_prompt = f"{system_prompt}\n{tool_instruction}"
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_recent_history(data.history))
    messages.append({
        "role": "user",
        "content": _compose_user_message(message, product_context, attachments_used, sources, data.tool_mode),
    })
    timed_out = False
    timeout_seconds = _ai_timeout_for_tool_mode(data.tool_mode)
    try:
        result = await asyncio.wait_for(
            ai_service.chat(
                messages,
                temperature=0.7,
                allow_fallback=False,
                model=selected_model,
                interface_key=interface_key,
                db=db,
                thinking=data.tool_mode == "thinking",
                reasoning_effort="high",
                return_reasoning=True,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        timed_out = True
        logger.warning("Inspiration chat AI call timed out after %.1fs", timeout_seconds)
        result = {"content": "", "reasoning": "", "model": selected_model}
    answer, reasoning, result_model = _normalize_ai_result(result, selected_model)
    answer = answer.strip()
    if not answer:
        return InspirationChatResponse(
            answer=_fallback_answer_with_products(
                message,
                products,
                reason="timeout" if timed_out else "unavailable",
            ),
            mode="fallback",
            model=model,
            tool_mode=data.tool_mode,
            sources=sources,
            attachments_used=attachments_used,
            product_context_used=product_context_used,
            products=products,
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
    )
