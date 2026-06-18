"""General inspiration chat API."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from database import get_db
from services.ai_service import ai_service
from services.product_rag import find_product_context_for_inspiration


router = APIRouter()


class ChatTurn(BaseModel):
    role: str
    content: str = Field(default="", max_length=4000)


class InspirationChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)

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
    product_context_used: bool = False
    products: list["ProductReference"] = Field(default_factory=list)


class ProductReference(BaseModel):
    product_id: int | None = None
    name: str = ""
    category: str = ""
    price: float | None = None


SYSTEM_PROMPT = """你是法采新媒体运营灵感助手。
你擅长短视频脚本创意、烘焙产品卖点表达、直播与抖音运营、活动文案、拍摄选题和内容复盘。
回答要直接、可执行、适合本地运营团队拿去改写使用。
如果用户问题和法采业务无关，也可以正常协助，但优先把建议落回内容创作和运营执行。
"""


def _recent_history(history: list[ChatTurn]) -> list[dict[str, str]]:
    cleaned = []
    for item in history:
        content = (item.content or "").strip()
        if content and item.role in {"user", "assistant"}:
            cleaned.append({"role": item.role, "content": content})
    return cleaned[-12:]


def _fallback_answer(message: str) -> str:
    return (
        "AI 服务暂时不可用，但可以先这样拆解你的问题：\n\n"
        f"你刚才问的是：{message}\n\n"
        "1. 先明确目标：要做选题、脚本、标题、活动文案，还是拍摄方向。\n"
        "2. 再补充对象：产品名、使用场景、价格活动、希望强调的卖点。\n"
        "3. 最后给出约束：平台、时长、语气、是否需要镜头说明。\n\n"
        "等 AI 服务恢复后，我可以继续把它整理成完整方案。"
    )


def _fallback_answer_with_products(message: str, products: list[dict]) -> str:
    answer = _fallback_answer(message)
    if not products:
        return answer
    names = "、".join(product.get("name", "") for product in products[:6] if product.get("name"))
    if not names:
        return answer
    return answer + f"\n\n已先匹配到可参考产品：{names}。AI 恢复后可以继续把这些资料整理成完整创意方案。"


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


@router.post("/chat", response_model=InspirationChatResponse)
async def chat_with_inspiration(data: InspirationChatRequest, db: Session = Depends(get_db)):
    message = data.message.strip()
    model = ai_service.get_model_name()
    product_context = _safe_product_context(message, db)
    products = product_context.get("products") or []
    product_context_used = bool(products)
    if not ai_service.is_available:
        return InspirationChatResponse(
            answer=_fallback_answer_with_products(message, products),
            mode="fallback",
            model=model,
            product_context_used=product_context_used,
            products=products,
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_recent_history(data.history))
    messages.append({"role": "user", "content": _message_with_product_context(message, product_context)})
    answer = (await ai_service.chat(messages, temperature=0.7, allow_fallback=False)).strip()
    if not answer:
        return InspirationChatResponse(
            answer=_fallback_answer_with_products(message, products),
            mode="fallback",
            model=model,
            product_context_used=product_context_used,
            products=products,
        )
    return InspirationChatResponse(
        answer=answer,
        mode="ai",
        model=model,
        product_context_used=product_context_used,
        products=products,
    )
