"""General inspiration chat API."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from services.ai_service import ai_service


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


@router.post("/chat", response_model=InspirationChatResponse)
async def chat_with_inspiration(data: InspirationChatRequest):
    message = data.message.strip()
    model = ai_service.get_model_name()
    if not ai_service.is_available:
        return InspirationChatResponse(answer=_fallback_answer(message), mode="fallback", model=model)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_recent_history(data.history))
    messages.append({"role": "user", "content": message})
    answer = (await ai_service.chat(messages, temperature=0.7, allow_fallback=False)).strip()
    if not answer:
        return InspirationChatResponse(answer=_fallback_answer(message), mode="fallback", model=model)
    return InspirationChatResponse(answer=answer, mode="ai", model=model)
