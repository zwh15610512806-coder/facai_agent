"""AI-backed analysis for generated short-video scripts."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from schemas import ScriptContentBreakdownResponse
from services.ai_service import ai_service


BREAKDOWN_PROVIDER_TIMEOUT_SECONDS = 12.0
BREAKDOWN_TOTAL_TIMEOUT_SECONDS = 15.0

logger = logging.getLogger(__name__)


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
                    max_tokens=2200,
                    interface_key=interface_key,
                    allow_fallback=False,
                    raise_on_error=True,
                    request_timeout=BREAKDOWN_PROVIDER_TIMEOUT_SECONDS,
                    db=db,
                ),
                timeout=BREAKDOWN_TOTAL_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("内容拆解模型调用失败，使用本地拆解: %s", exc)
            return self._build_local_breakdown(
                script=script,
                product=product or {},
                video_type=video_type,
            )

        fallback = self._build_local_breakdown(
            script=script,
            product=product or {},
            video_type=video_type,
        )
        try:
            payload = self._parse_json(content)
            payload = self._merge_with_fallback(payload, fallback)
            payload["source"] = "ai"
            parsed = ScriptContentBreakdownResponse.model_validate(payload)
        except Exception as exc:
            logger.warning("内容拆解模型返回格式不可用，使用本地拆解: %s", exc)
            return fallback
        return parsed.model_dump()

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
            "产品资料": self._compact_product(product),
            "结构模板": self._compact_template(template),
            "引用脚本": self._compact_source_script(source_script),
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
            f"生成上下文：\n{self._safe_json(context, 7000)}\n\n"
            f"当前脚本：\n{script[:12000]}"
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
            raise ValueError("empty response")
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("json object not found")
        try:
            payload = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("invalid json") from exc
        if not isinstance(payload, dict):
            raise ValueError("json response is not an object")
        return payload

    @staticmethod
    def _compact_product(product: dict[str, Any]) -> dict[str, Any]:
        compact = {
            key: product.get(key)
            for key in ("name", "category", "brand", "description", "pending_fields")
            if product.get(key) not in (None, "", [])
        }
        compact["selling_points"] = [
            {
                "type": item.get("type") or item.get("point_type") or "",
                "content": str(item.get("content") or "")[:500],
            }
            for item in (product.get("selling_points") or [])[:6]
            if isinstance(item, dict) and item.get("content")
        ]
        compact["profile_sections"] = [
            {
                "title": str(section.get("title") or "")[:80],
                "items": [
                    {
                        "label": str(item.get("label") or "")[:80],
                        "content": str(item.get("content") or "")[:500],
                    }
                    for item in (section.get("items") or [])[:5]
                    if isinstance(item, dict) and item.get("content")
                ],
            }
            for section in (product.get("profile_sections") or [])[:5]
            if isinstance(section, dict)
        ]
        compact["knowledge_sources"] = [
            str(item)[:180] for item in (product.get("knowledge_sources") or [])[:8]
        ]
        return compact

    @staticmethod
    def _compact_template(template: dict[str, Any] | None) -> dict[str, Any] | None:
        if not template:
            return None
        return {
            key: template.get(key)
            for key in ("name", "video_type", "description", "structure")
            if template.get(key) not in (None, "", [])
        }

    @staticmethod
    def _compact_source_script(source_script: dict[str, Any] | None) -> dict[str, Any] | None:
        if not source_script:
            return None
        return {
            "title": source_script.get("title"),
            "source": source_script.get("source"),
            "content": str(source_script.get("content") or "")[:1600],
        }

    @staticmethod
    def _merge_with_fallback(
        payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(fallback)
        for field in ("generation_rationale", "target_audience"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                merged[field] = value.strip()
        for field in (
            "structure",
            "core_selling_points",
            "conversion_triggers",
            "optimization_suggestions",
            "shooting_notes",
            "shot_requirements",
        ):
            value = payload.get(field)
            if isinstance(value, list) and value:
                merged[field] = value
        return merged

    def _build_local_breakdown(
        self,
        *,
        script: str,
        product: dict[str, Any],
        video_type: str,
    ) -> dict[str, Any]:
        sentences = self._script_sentences(script)
        first = sentences[0]
        middle = sentences[len(sentences) // 2] if len(sentences) > 2 else sentences[-1]
        last = sentences[-1]
        product_name = str(product.get("name") or "当前产品").strip()
        category = str(product.get("category") or "").strip()
        audience = self._infer_audience(category, script)
        selling_points = self._selling_points(product, sentences)

        structure = [
            {
                "stage": "开头切入",
                "copy_excerpt": first[:90],
                "purpose": "用具体场景、问题或结果建立观看理由。",
            }
        ]
        if middle != first and middle != last:
            structure.append(
                {
                    "stage": "卖点与证明",
                    "copy_excerpt": middle[:90],
                    "purpose": "承接需求并说明产品能带来的实际价值。",
                }
            )
        if last != first:
            structure.append(
                {
                    "stage": "转化收束",
                    "copy_excerpt": last[:90],
                    "purpose": "总结价值，并根据原文自然承接行动。",
                }
            )

        trigger_sentences = [
            item for item in sentences
            if re.search(r"稳定|省|方便|简单|效果|成本|价格|活动|下单|链接|小黄车|适合|不易|不用", item)
        ][:3]
        if not trigger_sentences:
            trigger_sentences = [middle]
        conversion_triggers = [
            {
                "copy_excerpt": item[:90],
                "reason": "这段把产品价值落到可理解的结果或使用收益上，可能降低用户的决策顾虑。",
            }
            for item in trigger_sentences
        ]

        optimizations = []
        if len(first) > 42:
            optimizations.append(
                {
                    "issue": "开头信息偏密",
                    "recommendation": "拍摄时先保留一个最具体的冲突或结果，其他信息放到后续画面展开。",
                }
            )
        if not re.search(r"展示|看|切开|搅拌|对比|实拍|试用|静置|成品", script):
            optimizations.append(
                {
                    "issue": "可见证明不足",
                    "recommendation": "补一组真实操作或成品特写，让口播卖点能被画面直接验证。",
                }
            )
        if not optimizations:
            optimizations.append(
                {
                    "issue": "卖点节奏还可更紧",
                    "recommendation": "每个口播句只对应一个动作或一个证明，删掉重复形容词，保留真实结果。",
                }
            )

        result = {
            "generation_rationale": (
                f"这条脚本采用“{video_type or '短视频带货'}”角度，围绕{product_name}的使用价值展开。"
                "判断上先建立观看理由，再用产品卖点或结果承接，最后完成自然收束。"
            ),
            "target_audience": audience,
            "structure": structure,
            "core_selling_points": selling_points,
            "conversion_triggers": conversion_triggers,
            "optimization_suggestions": optimizations,
            "shooting_notes": [
                "在真实使用环境中拍摄，台面、工具和成品状态要与口播内容一致。",
                "口播提到效果时同步给出近景证明，避免只拍包装或只做空泛讲解。",
                "竖屏构图预留字幕区，产品标签、操作动作和成品结果不要被字幕遮挡。",
            ],
            "shot_requirements": [
                {
                    "script_segment": first[:70],
                    "shot_type": "近景或中近景",
                    "subject_action": "直接呈现开头所说的问题、动作或结果。",
                    "visual_requirement": "前三秒主体清楚，避免空镜和无关铺垫。",
                },
                {
                    "script_segment": middle[:70],
                    "shot_type": "操作特写",
                    "subject_action": "按口播完成一次真实操作，并展示过程变化。",
                    "visual_requirement": "对焦产品质地、使用步骤或成品状态，保证卖点可见。",
                },
                {
                    "script_segment": last[:70],
                    "shot_type": "成品近景或人物中景",
                    "subject_action": "展示最终结果，并完成原脚本已有的收束表达。",
                    "visual_requirement": "结尾画面保持简洁；原稿没有促销信息时不要额外增加价格贴片。",
                },
            ],
            "source": "local",
        }
        return ScriptContentBreakdownResponse.model_validate(result).model_dump()

    @staticmethod
    def _script_sentences(script: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", script or "").strip()
        parts = [
            item.strip(" ，,。！？!?；;：:")
            for item in re.split(r"[。！？!?；;\n]+", cleaned)
            if item.strip(" ，,。！？!?；;：:")
        ]
        if not parts:
            return [cleaned[:180] or "当前脚本"]
        return parts[:10]

    @staticmethod
    def _infer_audience(category: str, script: str) -> str:
        text = f"{category} {script}"
        if re.search(r"烘焙|蛋糕|奶油|慕斯|面包|甜品", text):
            return "需要稳定出品、控制操作效率和成品效果的烘焙店老板、私房烘焙主理人及一线制作人员。"
        if re.search(r"门店|采购|批量|成本", text):
            return "关注采购成本、使用效率和稳定交付的门店经营者及采购决策者。"
        return "对当前产品用途、使用结果和购买价值有明确需求的实际使用者与采购决策者。"

    @staticmethod
    def _selling_points(product: dict[str, Any], sentences: list[str]) -> list[str]:
        points = [
            str(item.get("content") or "").strip()
            for item in (product.get("selling_points") or [])
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        ][:5]
        if points:
            return points
        candidates = [item[:100] for item in sentences[1:4] if item]
        return candidates or ["脚本强调了当前产品的实际使用价值与成品结果。"]


script_content_breakdown_service = ScriptContentBreakdownService()
