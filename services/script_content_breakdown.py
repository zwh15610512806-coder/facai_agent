"""AI-backed analysis for generated short-video scripts."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from schemas import ScriptContentBreakdownResponse
from services.ai_service import ai_service


BREAKDOWN_PROVIDER_TIMEOUT_SECONDS = 35.0
BREAKDOWN_TOTAL_TIMEOUT_SECONDS = 50.0


class ScriptContentBreakdownError(Exception):
    """Raised when a content breakdown cannot be produced."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ScriptContentBreakdownService:
    def __init__(self, ai=None):
        self.ai = ai or ai_service

    async def generate(
        self,
        *,
        script_content: str,
        product: dict[str, Any],
        video_type: str,
        engine: str,
        template: dict[str, Any] | None = None,
        source_script: dict[str, Any] | None = None,
        db=None,
    ) -> dict[str, Any]:
        script = (script_content or "").strip()
        if not script:
            raise ScriptContentBreakdownError(422, "脚本内容不能为空")

        interface_key = "script_library_rewrite" if engine == "template" else "script_generate"
        messages = self._build_messages(
            script=script,
            product=product or {},
            video_type=video_type,
            engine=engine,
            template=template,
            source_script=source_script,
        )
        try:
            content = await asyncio.wait_for(
                self.ai.chat(
                    messages,
                    temperature=0.35,
                    interface_key=interface_key,
                    allow_fallback=False,
                    raise_on_error=True,
                    request_timeout=BREAKDOWN_PROVIDER_TIMEOUT_SECONDS,
                    db=db,
                ),
                timeout=BREAKDOWN_TOTAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise ScriptContentBreakdownError(
                503,
                "内容拆解模型响应超时，请稍后点击重新拆解。",
            ) from exc
        except Exception as exc:
            raise ScriptContentBreakdownError(
                503,
                "内容拆解模型不可用或调用失败，请稍后重试。",
            ) from exc

        payload = self._parse_json(content)
        try:
            payload["source"] = "ai"
            parsed = ScriptContentBreakdownResponse.model_validate(payload)
        except Exception as exc:
            raise ScriptContentBreakdownError(
                502,
                "内容拆解模型未返回完整的结构化结果，请重新拆解。",
            ) from exc

        result = parsed.model_dump()
        required_lists = (
            "structure",
            "core_selling_points",
            "conversion_triggers",
            "optimization_suggestions",
            "shooting_notes",
            "shot_requirements",
        )
        if not result["generation_rationale"].strip() or not result["target_audience"].strip():
            raise ScriptContentBreakdownError(502, "内容拆解模型返回的信息不完整，请重新拆解。")
        if any(not result[field] for field in required_lists):
            raise ScriptContentBreakdownError(502, "内容拆解模型返回的信息不完整，请重新拆解。")
        return result

    def _build_messages(
        self,
        *,
        script: str,
        product: dict[str, Any],
        video_type: str,
        engine: str,
        template: dict[str, Any] | None,
        source_script: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        context = {
            "生成方式": "模板库改写" if engine == "template" else "AI生成",
            "视频类型": video_type or "未标注",
            "产品资料": product,
            "结构模板": template,
            "引用脚本": source_script,
        }
        user_prompt = (
            "请分析下面这条抖音带货脚本，解释为什么采用这样的创作方式，并给出可执行的拍摄建议。\n"
            "分析必须以脚本文字和提供的产品资料为事实边界；模型推断要使用‘判断/建议/可能’等措辞。\n"
            "不得虚构投放数据、CTR、CVR、销量或用户反馈，不得承诺一定爆量。\n"
            "目标人群要具体到使用者或采购决策者；下单触发点必须引用脚本中的对应片段。\n"
            "镜头与画面要求要能直接指导竖屏短视频拍摄，写清景别、主体动作和可见证明。\n"
            "只输出一个 JSON 对象，不要 Markdown、代码围栏或解释。字段严格如下：\n"
            "{\n"
            '  "generation_rationale": "生成思路",\n'
            '  "target_audience": "目标人群",\n'
            '  "structure": [{"stage":"结构阶段","copy_excerpt":"脚本片段","purpose":"该段作用"}],\n'
            '  "core_selling_points": ["主要卖点"],\n'
            '  "conversion_triggers": [{"copy_excerpt":"脚本片段","reason":"可能吸引下单的原因"}],\n'
            '  "optimization_suggestions": [{"issue":"可优化点","recommendation":"具体优化方式"}],\n'
            '  "shooting_notes": ["拍摄注意事项"],\n'
            '  "shot_requirements": [{"script_segment":"对应脚本段落","shot_type":"景别/机位","subject_action":"主体动作","visual_requirement":"画面要求"}]\n'
            "}\n\n"
            f"生成上下文：\n{self._safe_json(context, 16000)}\n\n"
            f"当前脚本：\n{script[:24000]}"
        )
        return [
            {
                "role": "system",
                "content": (
                    "你是抖音电商短视频内容策略与拍摄分析师。"
                    "你负责拆解现有脚本，不重写脚本，也不夸大效果。"
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _safe_json(value: Any, limit: int) -> str:
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= limit else text[:limit] + "…"

    @staticmethod
    def _parse_json(content: Any) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ScriptContentBreakdownError(502, "内容拆解模型未返回内容，请重新拆解。")
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ScriptContentBreakdownError(502, "内容拆解模型未返回有效 JSON，请重新拆解。")
        try:
            payload = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ScriptContentBreakdownError(502, "内容拆解模型未返回有效 JSON，请重新拆解。") from exc
        if not isinstance(payload, dict):
            raise ScriptContentBreakdownError(502, "内容拆解模型返回格式不正确，请重新拆解。")
        return payload


script_content_breakdown_service = ScriptContentBreakdownService()
