"""脚本生成引擎 — 核心业务逻辑"""
from services.ai_service import ai_service
from services.rewrite_prompts import build_rewrite_system_prompt
from services.script_opening import (
    OpeningBrief,
    collect_template_audience_phrases,
    extract_normalized_leading_audience_signature,
    select_opening_brief,
    strip_generic_audience_opening,
    template_allows_audience_call,
    validate_opening,
)
from services.script_price import abstract_script_price, sanitize_script_price_text
from services.script_structure import (
    extract_script_beats,
    format_indexed_script_beats,
    parse_indexed_rewrite,
    strip_visual_notes,
)
from models import ViralScript, ReferenceScript
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Dict, Optional, Any
import json
import logging
import re

logger = logging.getLogger(__name__)


_PRICE_NUMBER = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)"
_PRICE_OR_PROMOTION_COPY_RE = re.compile(
    r"价格|价位|原价|售价|活动价|活动|大促|成本|划算|福利|优惠|促销|折扣|赠品|赠送|"
    r"送你|再送|多花|少花|省钱|券|到手|恢复原价"
    r"|买\s*(?:\d+|[一二两三四五六七八九十几]+)\s*送\s*(?:\d+|[一二两三四五六七八九十几]+)"
    r"|满\s*(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千几]+)\s*(?:元)?\s*减\s*(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千几]+)"
    r"|几毛钱|几块钱|十来块|1开头|一杯奶茶钱|几十块|三位数|千元级"
    r"|[¥￥]\s*\d+(?:\.\d+)?"
    rf"|{_PRICE_NUMBER}\s*(?:元|块|毛|角)(?:\s*{_PRICE_NUMBER})?"
    rf"|{_PRICE_NUMBER}\s*折"
    rf"|立减\s*{_PRICE_NUMBER}"
)
_CTA_COPY_RE = re.compile(
    r"左下角|小黄车|下单|拍下|直接拍|点(?:击)?下方|下方链接|链接(?:里|处)?|"
    r"去看看|可以看看|来看看|直播间|起拍|先备(?:一份|一个|上|着)|赶紧(?:入|买|拍|囤)"
)


class ScriptGenerationError(RuntimeError):
    """Raised when AI script generation cannot produce a real model result."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class ScriptGenerator:
    """短视频脚本生成引擎"""

    # 视频类型对应的抖音跑量逻辑策略
    TYPE_STRATEGIES = {
        "机制类": "机制钩子 → 规则拆解 → 产品承接 → 利益证明 → CTA。核心是讲清为什么省心、省钱或现在更值得买",
        "痛点类": "痛点场景 → 情绪放大 → 产品解决 → 效果对比 → CTA。核心是让观众觉得问题被精准说中",
        "需求类": "用户需求 → 使用理由 → 卖点匹配 → 购买建议 → CTA。核心是让用户意识到自己确实需要",
        "认知类": "认知反差 → 原理解释 → 产品验证 → 专业建议 → CTA。核心是用知识建立信任",
        "达人分享类": "身份建立 → 真实体验 → 细节展示 → 自然推荐 → CTA。核心是像使用者分享而不是硬广",
        "制作方便": "省事钩子 → 操作演示 → 成品结果 → 下单理由 → CTA。核心是降低上手门槛和制作负担",
        "成本低": "成本钩子 → 成本对账 → 效果证明 → 性价比结论 → CTA。核心是讲清低成本背后的实际收益",
        "对比类": "对比问题 → 同屏对照 → 差异解释 → 结论推荐 → CTA。核心是让差异一眼可见",
        "情绪类": "情绪引入 → 场景共鸣 → 产品释放 → 情绪收尾 → CTA。核心是用成就感、焦虑缓解或惊喜推动行动",
        "场景类": "场景建立 → 动作展示 → 成品呈现 → 场景转化 → CTA。核心是让用户看见自己会在何处使用",
        "AI智能生成": "根据产品资料、价格状态、卖点强弱和抖音跑量逻辑自动选择最适合的生成角度，可以在机制、痛点、需求、认知、场景、对比之间择优组合，但必须输出一个清晰主线",
    }

    def __init__(self):
        self.ai = ai_service

    def get_model_name(self, interface_key: str = "script_generate") -> str:
        try:
            return self.ai.get_model_name(interface_key=interface_key)
        except TypeError as exc:
            if "interface_key" not in str(exc):
                raise
            return self.ai.get_model_name()

    def _ai_available_for_interface(self, interface_key: str) -> bool:
        checker = getattr(self.ai, "is_interface_available", None)
        if checker:
            return bool(checker(interface_key))
        return bool(getattr(self.ai, "is_available", False))

    async def _chat_with_interface(
        self,
        messages: List[Dict],
        temperature: float,
        interface_key: str,
        allow_fallback: bool = True,
    ) -> str:
        try:
            return await self.ai.chat(
                messages,
                temperature=temperature,
                interface_key=interface_key,
                allow_fallback=allow_fallback,
            )
        except TypeError as exc:
            if "allow_fallback" in str(exc):
                try:
                    return await self.ai.chat(messages, temperature=temperature, interface_key=interface_key)
                except TypeError as inner_exc:
                    if "interface_key" not in str(inner_exc):
                        raise
                    return await self.ai.chat(messages, temperature=temperature)
            if "interface_key" not in str(exc):
                raise
            return await self.ai.chat(messages, temperature=temperature)

    def _format_shot_design_requirement(
        self,
        include_shot_design: bool,
        use_template_reference: bool = True,
    ) -> str:
        if include_shot_design:
            reference_line = (
                "- 参考脚本模板库的画面节奏和镜头功能。"
                if use_template_reference
                else "- 参考抖音带货跑量逻辑和真实产品场景的画面节奏。"
            )
            return (
                "\n【画面设计要求】\n"
                f"{reference_line}\n"
                "- 每句话添加镜头说明，让口播文案和画面动作一一对应。\n"
                "- 可使用格式：（镜头/画面说明）口播文案，并保留适度段落结构。"
            )
        reference_line = (
            "- 仍参考脚本模板库的成交结构和表达节奏，但不保留模板里的镜头格式。"
            if use_template_reference
            else "- 仍参考抖音带货跑量逻辑和真实产品场景，但不套用模板脚本格式。"
        )
        connector_line = (
            "- 可以使用“啊、关键、如果、直接”等口语连接词，让文案读起来顺滑自然。"
            if use_template_reference
            else "- 可以使用“关键、如果、直接、你看、说白了”等口语连接词，让文案读起来顺滑自然。"
        )
        return (
            "\n【输出格式要求】\n"
            "- 本节格式要求优先级最高。\n"
            "- 只输出一段连续视频文案，适合直接作为口播稿使用，格式要像自然达人带货口播的一整段话。\n"
            "- 禁止镜头说明、画面说明、分镜标题、字幕提示、口播标签和场景说明。\n"
            "- 禁止时间码、【】段落标签、项目符号、Markdown 标题和“改写自”说明；禁止换行。\n"
            f"{connector_line}\n"
            f"{reference_line}"
        )

    def _format_ai_run_rate_framework(self) -> str:
        return (
            "\n【抖音跑量自检框架】\n"
            "- 黄金前3秒服务 CTR：第一口播小句立即给出具体动作、真实门店冲突、结果反差、认知纠正、产品证明、客户反馈或已核实机制。\n"
            "- 禁止用人群召唤或空洞注意力钩子开场。\n"
            "- 目标人群必须明确为烘焙店老板/烘焙从业者，不要写成泛消费者种草。\n"
            "- 正文用真实使用场景（真实烘焙门店场景）加具体产品证明服务 CVR，让观众能代入备货、出品、配送或打包。\n"
            "- 至少引用2个产品资料里的具体卖点，卖点要落到成本、效率、品质、稳定性、使用步骤或成品效果，禁止空泛夸张。\n"
            "- 价格、活动、赠品必须与输入一致；最终脚本用抽象价格表达，禁止输出几毛几分钱的精确金额；价格待更新时不得编造价格、折扣、赠品或到手价。\n"
            "- 内容重、营销轻，只走一条清晰转化主线；完成产品证明之后自然 CTA，避免全篇硬广。\n"
            "- 先内部自评并修正钩子、场景、产品事实、价格政策和 CTA；最终不要输出评分或解释。"
        )

    def _format_ai_opening_requirement(
        self,
        opening_brief: OpeningBrief,
        recent_openings: Optional[List[str]],
    ) -> str:
        lines = [
            "\n【本次开头策略】",
            f"- 策略家族：{opening_brief.family}",
            f"- 中文指令：{opening_brief.instruction}",
            "- 禁止以“姐妹们”“烘焙姐妹们”“家人们”“老板们看过来”作为开头。\n"
            "- 第一口播小句必须直接提供具体动作、真实门店冲突、结果反差、认知纠正、产品证明、客户反馈或已核实机制。",
        ]
        openings = [opening.strip() for opening in (recent_openings or []) if opening.strip()][:8]
        if openings:
            lines.extend(["\n【近期首句去重】", "- 禁止复制这些首句的角度或句式，也不得只替换商品名后复用。"])
            lines.extend(f"- {opening}" for opening in openings)
        return "\n".join(lines)

    def _price_intent_required(
        self,
        video_type: str,
        opening_family: str,
        extra_requirements: Optional[str],
    ) -> bool:
        requirements = extra_requirements or ""
        intent_pattern = re.compile(r"价格|价位|活动|优惠|促销|赠品|买.{0,12}送|券|折扣|到手")
        intent_matches = list(intent_pattern.finditer(requirements))
        if intent_matches:
            negation = (
                r"(?:不要(?:写|提|说|展示)?|不需要|无需|别|禁止|不提|不写|不展示|不说|"
                r"不包含|不存在|没有|无(?!门槛)|去掉|避免)"
            )
            for match in intent_matches:
                before = requirements[max(0, match.start() - 14) : match.start()]
                after = requirements[match.end() : match.end() + 10]
                no_threshold_promotion = re.search(
                    r"(?:没有|无)\s*门槛(?:的)?$",
                    before,
                )
                negated_before = re.search(
                    rf"{negation}[^，。；;！？!?]{{0,8}}$",
                    before,
                ) if not no_threshold_promotion else None
                negated_after = re.match(
                    rf"[^，。；;！？!?]{{0,4}}{negation}",
                    after,
                )
                if not negated_before and not negated_after:
                    return True
            return False
        if video_type in {"机制类", "成本低"} or opening_family == "cost_mechanism":
            return True
        return False

    def _format_ai_price_policy(self, price_required: bool) -> str:
        if price_required:
            return "价格政策：本条允许使用真实且抽象的价格/活动表达，但只能依据输入事实，不得虚构或输出精确金额。"
        return "价格政策：本条脚本不要求价格，不得为了制造广告压力强行插入价格或促销。"

    def _post_process_script_output(
        self,
        script: str,
        include_shot_design: bool,
        remove_default_audience_opening: bool = False,
    ) -> str:
        text = (script or "").strip()
        if include_shot_design:
            if remove_default_audience_opening:
                text = strip_generic_audience_opening(text)
            return sanitize_script_price_text(text)

        text = self._strip_plain_script_preamble(text)
        text = re.sub(r"(?m)^\s*-{3,}\s*$", " ", text)
        text = re.sub(r"(?m)^\s*\*\*[^*\n]*(?:改写自|爆款脚本|脚本)[^*\n]*\*\*\s*$", " ", text)
        text = re.sub(r"(?m)^\s*(?:改写自|参考|爆款脚本)[^\n]{0,100}\s*$", " ", text)
        text = re.sub(r"\*\*", "", text)
        text = re.sub(r"【[^】]{1,40}】", " ", text)
        text = re.sub(r"(?m)^\s*(?:\d+\s*[-~—到]\s*\d+\s*(?:s|秒)?|第?\d+\s*秒)\s*[:：、-]?\s*", " ", text)
        text = re.sub(r"(?:前|第)\s*\d+\s*秒", " ", text)
        text = re.sub(
            r"[（(][^（）()]{0,120}(?:镜头|画面|分镜|字幕|口播|场景|特写|手部|俯拍|近景|远景|拍摄|对准|切换|展示)[^（）()]{0,120}[）)]",
            " ",
            text,
        )
        text = re.sub(r"(?m)^\s*[-*•·]\s*", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff0-9，。！？、；：])\s+(?=[\u4e00-\u9fff0-9“”])", "", text)
        text = re.sub(r"\s+([，。！？、；：,.!?;:])", r"\1", text)
        if remove_default_audience_opening:
            text = strip_generic_audience_opening(text)
        return sanitize_script_price_text(text.strip())

    def _strip_plain_script_preamble(self, text: str) -> str:
        """Keep only the actual spoken script when the model adds analysis or intro text."""
        if not text:
            return ""

        start_patterns = [
            r"以下是[^\n：:]{0,80}(?:脚本|文案)[^\n：:]*[：:]",
            r"请看[^\n：:]{0,80}(?:脚本|文案)[^\n：:]*[：:]",
            r"最终(?:脚本|文案)[^\n：:]*[：:]",
        ]
        starts = []
        for pattern in start_patterns:
            for match in re.finditer(pattern, text):
                starts.append(match.end())

        if starts:
            return text[max(starts):].strip()

        marker_match = re.search(r"(?m)^\s*(?:\*\*)?改写自[^\n]*\n+", text)
        if marker_match:
            return text[marker_match.end():].strip()

        heading_match = re.search(r"(?m)^\s*【[^】]{1,40}】", text)
        if heading_match and re.search(r"(?:好的|没问题|脚本改写专家|我选择|根据你提供|完全理解)", text[:heading_match.start()]):
            return text[heading_match.start():].strip()

        return text

    async def match_shots_to_copy(self, script_content: str, product: Dict) -> str:
        """Add camera/shot notes to existing copy without changing the spoken text."""
        clean_copy = self._extract_spoken_copy(script_content)
        sentences = self._split_spoken_sentences(clean_copy)
        if not sentences:
            return ""

        lines = []
        for index, sentence in enumerate(sentences):
            shot = self._infer_shot_for_sentence(sentence, product, index)
            lines.append(f"（{shot}）{sentence}")
        return "\n".join(lines)

    def _extract_spoken_copy(self, script_content: str) -> str:
        text = self._strip_plain_script_preamble(script_content or "")
        text = re.sub(r"(?m)^\s*-{3,}\s*$", " ", text)
        text = re.sub(r"(?m)^\s*\*\*[^*\n]*(?:改写自|爆款脚本|脚本)[^*\n]*\*\*\s*$", " ", text)
        text = re.sub(r"(?m)^\s*(?:改写自|参考|爆款脚本)[^\n]{0,100}\s*$", " ", text)
        text = re.sub(r"【[^】]{1,40}】", " ", text)
        text = re.sub(
            r"[（(][^（）()]{0,120}(?:镜头|画面|分镜|字幕|口播|场景|特写|手部|俯拍|近景|远景|拍摄|对准|切换|展示)[^（）()]{0,120}[）)]",
            " ",
            text,
        )
        text = re.sub(r"\*\*", "", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff0-9，。！？、；：])\s+(?=[\u4e00-\u9fff0-9“”])", "", text)
        return text.strip()

    def _split_spoken_sentences(self, script_content: str) -> List[str]:
        text = (script_content or "").strip()
        if not text:
            return []
        sentences = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text)
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def _infer_shot_for_sentence(self, sentence: str, product: Dict, index: int) -> str:
        product_name = product.get("name") or "目标产品"
        category = product.get("category") or "烘焙产品"
        base_product = f"法采{product_name}"

        if index == 0:
            return f"主播半身口播，手拿{base_product}开场，桌面摆放产品和烘焙成品，语气直接有吸引力"
        if re.search(r"左下角|小黄车|下单|拍下|直接拍|库存|抓紧|囤|活动|福利|促销|优惠|省|元|价格|划算|便宜|成本", sentence):
            return f"价格牌和{base_product}同框展示，手指向左下角下单位置，突出活动力度和数量感"
        if re.search(r"蛋糕|生日|顾客|烘焙店|店里|配送|包装|纸袋|精美|卫生|干净", sentence):
            return f"烘焙工作台或蛋糕店实拍，展示{base_product}搭配{category}成品使用的真实场景"
        if re.search(r"切|拿|用|加|倒|搅|凝固|冷藏|制作|操作|搭配|放上|打开|装", sentence):
            return f"手部操作近景，完整展示{base_product}的使用动作和成品状态，画面干净明亮"
        if re.search(r"对比|廉价|传统|以前|之前|麻烦|费时|粗糙|断|不稳|不锈钢|加固", sentence):
            return f"左右对比镜头，左侧展示普通替代品问题，右侧展示{base_product}的细节和优势"
        if product_name in sentence or re.search(r"产品|刀叉|袋装|包装|盘|叉|粉|酱|膏|夹心|奶冻", sentence):
            return f"产品包装和细节特写，镜头缓慢推进，清楚展示{base_product}的规格、质地或卖点"
        return f"主播结合{base_product}进行自然口播，中景切近景，画面围绕产品和{category}使用场景"

    def _extract_keywords(self, product_name: str) -> list:
        """从产品名提取多个候选关键词（从长到短），用于模糊匹配 ViralScript.category"""
        import re
        # 1. 取括号前的主名
        main_name = re.split(r'[（(]', product_name)[0].strip()
        candidates = [main_name] if main_name else []

        # 2. 去掉常见前缀
        prefixes = ['防潮', '彩色', '手绘', '高浓', '油性', '水性', '无糖', '低糖',
                    '零卡', '金丝', '经典', '成品', '天然', '水溶', '水状', '巧克力']
        for prefix in prefixes:
            if main_name.startswith(prefix) and len(main_name) > len(prefix) + 2:
                stripped = main_name[len(prefix):]
                if stripped and stripped not in candidates:
                    candidates.append(stripped)
                break

        # 3. 从尾部逐步提取核心词（支持"彩色翻糖膏" -> "翻糖膏" -> "翻糖"）
        suffix_patterns = ['膏', '粉', '片', '笔', '盘', '脆', '霜', '酱', '松', '汁']
        for suf in suffix_patterns:
            idx = main_name.find(suf)
            if idx > 0:
                base = main_name[:idx]
                if base and base not in candidates:
                    candidates.append(base)
                # 再取倒数第二个词
                words = re.findall(r'[\u4e00-\u9fa5]+', base)
                if len(words) >= 2 and words[-1] not in candidates:
                    candidates.append(words[-1])
                break

        # 去重，保持顺序
        seen = set()
        result = []
        for kw in candidates:
            if kw not in seen and len(kw) >= 2:
                seen.add(kw)
                result.append(kw)
        return result

    def find_similar_scripts(
        self,
        product: Dict,
        video_type: str,
        db: Session,
        limit: int = 3,
    ) -> List[Dict]:
        """Retrieve similar viral scripts — vector search first, keyword fallback."""
        try:
            from vector_store.script_store import ScriptVectorStore
            from vector_store import get_chroma_store

            store = get_chroma_store()
            if store.is_available:
                svs = ScriptVectorStore()
                results = svs.find_similar_scripts(product, video_type, db, limit=limit)
                if results:
                    return self._hydrate_script_results(results, db)

        except Exception as e:
            logger.warning(f"Vector search unavailable, using keyword: {e}")

        return self._find_similar_scripts_keyword(product, video_type, db, limit)

    def _hydrate_script_results(self, results: list, db: Session) -> List[Dict]:
        """Re-hydrate vector search results with full script content from SQLite."""
        viral_ids = [r["db_id"] for r in results if r.get("source") == "viral"]
        ref_ids = [r["db_id"] for r in results if r.get("source") == "reference"]

        viral_map = {}
        ref_map = {}
        if viral_ids:
            virals = db.query(ViralScript).filter(ViralScript.id.in_(viral_ids)).all()
            viral_map = {v.id: v for v in virals}
        if ref_ids:
            refs = db.query(ReferenceScript).filter(ReferenceScript.id.in_(ref_ids)).all()
            ref_map = {r.id: r for r in refs}

        out = []
        for r in results:
            src = r.get("source")
            db_id = r.get("db_id")
            record = viral_map.get(db_id) if src == "viral" else ref_map.get(db_id)
            if record:
                out.append({
                    "title": getattr(record, "title", "") or "",
                    "content": getattr(record, "script_content", "") or "",
                    "video_type": getattr(record, "video_type", "") or "",
                    "category": getattr(record, "category", "") or "",
                    "tags": getattr(record, "tags", "") or "",
                    "performance": getattr(record, "performance_data", None),
                    "is_high_conversion": bool(getattr(record, "is_high_conversion", 0)),
                })
        return out

    def _find_similar_scripts_keyword(
        self, product: Dict, video_type: str, db: Session, limit: int = 3
    ) -> List[Dict]:
        """Fallback: keyword-based similar script search."""
        try:
            product_name = product.get("name", "")
            candidates = self._extract_keywords(product_name)

            def query_by_kw(db_session, conv, excl_ids, limit_n):
                for kw in candidates:
                    q = db_session.query(ViralScript).filter(
                        ViralScript.is_high_conversion == conv,
                        ViralScript.category.contains(kw),
                    )
                    if excl_ids:
                        q = q.filter(~ViralScript.id.in_(excl_ids))
                    res = q.limit(limit_n).all()
                    if res:
                        return res
                return []

            high_by_name = query_by_kw(db, 1, [], limit)
            high_ids = [s.id for s in high_by_name]
            normal_by_name = query_by_kw(db, 0, high_ids, limit - len(high_by_name))
            name_scripts = high_by_name + normal_by_name

            total = len(name_scripts)
            if total < limit:
                remaining = limit - total
                excl_ids = [s.id for s in name_scripts]
                type_high = query_by_kw(db, 1, excl_ids, remaining)
                excl_ids += [s.id for s in type_high]
                type_normal = query_by_kw(db, 0, excl_ids, remaining - len(type_high))
                name_scripts += type_high + type_normal

            scripts = name_scripts[:limit]
            return [
                {
                    "title": s.title,
                    "content": s.script_content,
                    "video_type": s.video_type,
                    "category": s.category,
                    "tags": s.tags,
                    "performance": s.performance_data,
                    "is_high_conversion": bool(s.is_high_conversion),
                }
                for s in scripts
            ]
        except Exception as e:
            logger.warning(f"Keyword similar scripts failed: {e}")
            return []

    def find_high_conversion_scripts(
        self,
        product: Dict,
        db: Session,
        limit: int = 5,
    ) -> List[Dict]:
        """Return only high-conversion viral-library scripts for auto type generation."""
        try:
            product_name = product.get("name", "")
            category = product.get("category", "")
            candidates = self._extract_keywords(product_name)
            scripts = []
            seen_ids = set()

            def append_results(query):
                nonlocal scripts
                for script in query.all():
                    if script.id in seen_ids:
                        continue
                    seen_ids.add(script.id)
                    scripts.append(script)
                    if len(scripts) >= limit:
                        break

            base_query = db.query(ViralScript).filter(ViralScript.is_high_conversion == 1)

            if category:
                append_results(
                    base_query.filter(ViralScript.category.contains(category))
                    .order_by(ViralScript.id.asc())
                    .limit(limit)
                )

            for kw in candidates:
                if len(scripts) >= limit:
                    break
                append_results(
                    base_query.filter(
                        or_(
                            ViralScript.category.contains(kw),
                            ViralScript.title.contains(kw),
                            ViralScript.tags.contains(kw),
                        )
                    )
                    .order_by(ViralScript.id.asc())
                    .limit(limit)
                )

            if len(scripts) < limit:
                append_results(
                    base_query.order_by(ViralScript.id.asc()).limit(limit)
                )

            return [
                {
                    "title": s.title,
                    "content": s.script_content,
                    "video_type": s.video_type,
                    "category": s.category,
                    "tags": s.tags,
                    "performance": s.performance_data,
                    "is_high_conversion": True,
                }
                for s in scripts[:limit]
            ]
        except Exception as e:
            logger.warning(f"High-conversion script search failed: {e}")
            return []

    def find_type_structure_scripts(
        self,
        video_type: str,
        db: Session,
        limit: int = 3,
    ) -> List[Dict]:
        """Return exact-video-type scripts for AI generation structure reference only."""
        if not video_type:
            return []
        try:
            selected = []

            def append_records(records, source: str):
                for record in records:
                    if len(selected) >= limit:
                        break
                    selected.append({
                        "title": getattr(record, "title", "") or "",
                        "content": getattr(record, "script_content", "") or "",
                        "video_type": getattr(record, "video_type", "") or "",
                        "category": getattr(record, "category", "") or "",
                        "tags": getattr(record, "tags", "") or "",
                        "performance": getattr(record, "performance_data", None),
                        "is_high_conversion": bool(getattr(record, "is_high_conversion", 0)),
                        "source": source,
                    })

            query_plan = [
                (
                    "viral",
                    db.query(ViralScript)
                    .filter(ViralScript.video_type == video_type, ViralScript.is_high_conversion == 1)
                    .order_by(ViralScript.id.asc())
                    .limit(limit)
                    .all(),
                ),
                (
                    "reference",
                    db.query(ReferenceScript)
                    .filter(ReferenceScript.video_type == video_type, ReferenceScript.is_high_conversion == 1)
                    .order_by(ReferenceScript.id.asc())
                    .limit(limit)
                    .all(),
                ),
                (
                    "viral",
                    db.query(ViralScript)
                    .filter(ViralScript.video_type == video_type, ViralScript.is_high_conversion != 1)
                    .order_by(ViralScript.id.asc())
                    .limit(limit)
                    .all(),
                ),
                (
                    "reference",
                    db.query(ReferenceScript)
                    .filter(ReferenceScript.video_type == video_type, ReferenceScript.is_high_conversion != 1)
                    .order_by(ReferenceScript.id.asc())
                    .limit(limit)
                    .all(),
                ),
            ]

            for source, records in query_plan:
                append_records(records, source)
                if len(selected) >= limit:
                    break
            return selected[:limit]
        except Exception as e:
            logger.warning(f"Type-structure script search failed: {e}")
            return []

    async def generate(
        self,
        product: Dict,
        template: Optional[Dict],
        video_type: str,
        tone: str = "活泼",
        extra_requirements: Optional[str] = None,
        reference_scripts: Optional[List[Dict]] = None,
        include_shot_design: bool = False,
        recent_openings: Optional[List[str]] = None,
    ) -> str:
        """
        生成短视频脚本

        Args:
            product: 产品信息字典
            template: 脚本模板字典
            video_type: 视频类型
            duration: 时长范围
            tone: 风格基调
            extra_requirements: 额外需求
            reference_scripts: 参考爆款脚本列表
        """
        if not self._ai_available_for_interface("script_generate"):
            raise ScriptGenerationError(
                "AI生成模型未配置，请到 AI配置 中检查脚本生成接口的 API Key、Base URL 和模型服务 ID。",
                status_code=503,
            )

        recent_openings = [opening for opening in (recent_openings or []) if (opening or "").strip()][:8]
        opening_brief = select_opening_brief(video_type, product, recent_openings)
        price_required = self._price_intent_required(video_type, opening_brief.family, extra_requirements)

        # 构建系统提示
        system_prompt = self._build_system_prompt(
            video_type,
            tone,
            include_shot_design=include_shot_design,
            opening_brief=opening_brief,
            recent_openings=recent_openings,
            price_required=price_required,
        )

        # 构建用户提示
        user_prompt = self._build_user_prompt(
            product=product,
            template=None,
            video_type=video_type,
            tone=tone,
            extra_requirements=extra_requirements,
            reference_scripts=reference_scripts or [],
            include_shot_design=include_shot_design,
            price_required=price_required,
        )

        # 调用 AI
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._chat_with_interface(
                messages,
                temperature=0.85,
                interface_key="script_generate",
                allow_fallback=False,
            )
        except ScriptGenerationError:
            raise
        except Exception as exc:
            raise ScriptGenerationError(f"AI生成模型调用失败：{exc}") from exc

        if not (response or "").strip():
            raise ScriptGenerationError("AI生成模型调用失败或未返回内容，请检查 AI 配置后重试。")

        opening_check = validate_opening(response, recent_openings, product.get("name", ""))
        if not opening_check.valid:
            logger.warning(
                "AI opening rejected before repair: reasons=%s opening=%r",
                opening_check.reasons,
                opening_check.opening,
            )
            repair_prompt = (
                "首次脚本未通过开头质量校验，请只修正一次并直接输出完整成稿。\n"
                f"机器校验原因：{json.dumps(list(opening_check.reasons), ensure_ascii=False)}\n"
                f"近期首句：{json.dumps(recent_openings, ensure_ascii=False)}\n"
                f"首次脚本：\n{response}\n\n"
                "必须更换开头角度和第一句句式，重排卖点推进顺序，并更换 CTA 表达；"
                "继续遵守原产品资料、价格政策、输出格式和不编造事实的要求。"
            )
            repair_messages = [
                *messages,
                {"role": "assistant", "content": response},
                {"role": "user", "content": repair_prompt},
            ]
            try:
                repaired_response = await self._chat_with_interface(
                    repair_messages,
                    temperature=0.95,
                    interface_key="script_generate",
                    allow_fallback=False,
                )
            except Exception as exc:
                logger.warning("AI opening repair failed: %s", exc)
                raise ScriptGenerationError(
                    "AI生成开头质量未通过，请重新生成。",
                    status_code=502,
                ) from exc

            repaired_check = validate_opening(
                repaired_response or "",
                recent_openings,
                product.get("name", ""),
            )
            if not (repaired_response or "").strip() or not repaired_check.valid:
                logger.warning(
                    "AI opening rejected after repair: reasons=%s opening=%r",
                    repaired_check.reasons,
                    repaired_check.opening,
                )
                raise ScriptGenerationError(
                    "AI生成开头质量未通过，请重新生成。",
                    status_code=502,
                )
            response = repaired_response

        script = self._post_process_script_output(
            response,
            include_shot_design,
        )
        if not script.strip():
            raise ScriptGenerationError("AI生成模型返回内容为空，请重试或检查 AI 配置。")
        return script

    def _build_system_prompt(
        self,
        video_type: str,
        tone: str,
        include_shot_design: bool = False,
        opening_brief: Optional[OpeningBrief] = None,
        recent_openings: Optional[List[str]] = None,
        price_required: bool = False,
    ) -> str:
        """构建系统提示词"""
        strategy = self.TYPE_STRATEGIES.get(
            video_type,
            self.TYPE_STRATEGIES["机制类"]
        )
        opening_brief = opening_brief or select_opening_brief(video_type, {}, recent_openings)
        opening_requirement = self._format_ai_opening_requirement(opening_brief, recent_openings)
        price_policy = self._format_ai_price_policy(price_required)
        if not include_shot_design:
            return f"""你是法采食品店的短视频带货纯口播文案专家，擅长把烘焙产品卖点写成一段自然达人口播。

当前输出模式：纯口播一段话。

硬性输出规则：
- 只输出最终视频文案本身，不输出解释、标题、编号或 Markdown。
- 只输出一段连续自然口播文案，不换行，不分段。
- 禁止【】段落标签、时间码、分镜标题、镜头说明、画面说明、字幕提示、口播标签和场景说明。
- 可以借鉴抖音爆款带货视频的成交逻辑、痛点推进、卖点顺序和口语节奏，但不能套用模板脚本格式。
- 语言要像真实带货达人顺口说出来，可以使用“关键、如果、直接、你看、说白了”这类自然连接词。
- 必须包含产品卖点和明确左下角下单引导；价格按本次价格政策执行。
{price_policy}
{self._format_ai_run_rate_framework()}
{opening_requirement}

当前任务：
- 视频类型：{video_type}
- 创作策略：{strategy}
- 语言风格：{tone}

请严格按纯口播一段话输出。"""

        return f"""你是法采食品店的短视频带货口播+画面脚本专家，擅长把烘焙产品卖点写成适合抖音跑量的真实门店场景脚本。

当前输出模式：口播+画面设计。

硬性输出规则：
- 只输出最终脚本本身，不输出解释、创作思路或 Markdown。
- 可以用时间段和功能标签组织脚本，但每一句口播都要配合具体镜头/画面说明。
- 镜头说明必须服务产品证明：真实门店场景、产品细节、使用动作、成品效果、价格机制或左下角下单引导。
- 口语表达要像烘焙店老板/烘焙从业者在真实分享，可以使用“关键、如果、直接、你看、说白了”等自然连接词。
- 必须包含产品卖点和明确左下角/小黄车下单引导；价格按本次价格政策执行。
- {price_policy}
- 避免全篇硬广，先用场景、证明和具体卖点让用户相信产品值得点开。

当前任务：
- 视频类型：{video_type}
- 创作策略：{strategy}
- 语言风格：{tone}
{self._format_ai_run_rate_framework()}
{opening_requirement}

请严格按照上述策略创作，确保脚本具备抖音跑量能力。"""

    def _format_prompt_price(self, value: Any) -> str:
        return abstract_script_price(value)

    def _trim_prompt_text(self, value: Any, limit: int = 180) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    def _dedupe_prompt_texts(self, values: List[Any], limit: int = 6) -> List[str]:
        seen = set()
        result = []
        for value in values:
            text = self._trim_prompt_text(value, limit=120)
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    def _format_sku_prompt_line(self, sku: Dict) -> str:
        if sku.get("line"):
            return self._trim_prompt_text(sanitize_script_price_text(sku["line"]), limit=220)

        name = sku.get("name") or " / ".join(
            part for part in [sku.get("product"), sku.get("spec")] if part
        ) or "默认规格"
        bits = []
        price = self._format_prompt_price(sku.get("price"))
        daily_price = self._format_prompt_price(sku.get("daily_price"))
        if price:
            bits.append(f"售价{price}")
        if daily_price and daily_price != price:
            bits.append(f"日常价{daily_price}")

        for activity in (sku.get("activity_prices") or [])[:3]:
            activity_price = (
                activity.get("price")
                or activity.get("final_price")
                or activity.get("activity_price")
                or activity.get("tag_price")
            )
            formatted_price = self._format_prompt_price(activity_price)
            if not formatted_price:
                continue
            mechanism = activity.get("mechanism") or "活动价"
            meta = []
            if activity.get("meta"):
                meta.append(str(activity["meta"]))
            if activity.get("discount"):
                meta.append(str(activity["discount"]))
            if activity.get("coupon") and activity.get("coupon") != "0":
                meta.append(f"券{activity['coupon']}")
            suffix = f"（{' / '.join(meta)}）" if meta else ""
            bits.append(f"{mechanism}{formatted_price}{suffix}")

        if not bits:
            return self._trim_prompt_text(name, limit=220)
        return self._trim_prompt_text(f"{name}：" + "；".join(bits), limit=220)

    def _format_product_knowledge_context(self, product: Dict) -> List[str]:
        sections = product.get("profile_sections") or []
        sku_prices = product.get("sku_prices") or []
        if not sections and not sku_prices and not product.get("knowledge_sources"):
            return []

        pending_price = "price" in set(product.get("pending_fields") or [])
        lines = ["\n【产品知识库资料】"]
        sources = self._dedupe_prompt_texts([
            product.get("source_name"),
            product.get("manual_source"),
            *(product.get("knowledge_sources") or []),
        ])
        if sources:
            lines.append(f"资料来源：{'、'.join(sources)}")

        rendered_sku_lines = 0
        for section in sections[:5]:
            section_id = section.get("id") or ""
            if pending_price and section_id == "product_price":
                continue
            items = section.get("items") or []
            section_skus = [] if pending_price else (section.get("sku_prices") or [])
            useful_lines = []
            for item in items[:5]:
                content = self._trim_prompt_text(item.get("content"))
                if not content:
                    continue
                label = self._trim_prompt_text(item.get("label") or "资料", limit=40)
                useful_lines.append(f"- {label}：{content}")
            for sku in section_skus[:3]:
                sku_line = self._format_sku_prompt_line(sku)
                if sku_line:
                    useful_lines.append(f"- {sku_line}")
                    rendered_sku_lines += 1
            if not useful_lines:
                continue
            lines.append(f"【{section.get('title') or '产品资料'}】")
            lines.extend(useful_lines)

        if sku_prices and not pending_price and rendered_sku_lines == 0:
            lines.append("【SKU/价格】")
            for sku in sku_prices[:4]:
                sku_line = self._format_sku_prompt_line(sku)
                if sku_line:
                    lines.append(f"- {sku_line}")

        if len(lines) <= 1:
            return []
        return lines

    def _has_any(self, text: str, patterns: List[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)

    def _infer_reference_structure(self, content: str) -> Dict[str, str]:
        text = re.sub(r"\s+", " ", content or "").strip()
        if not text:
            return {
                "opening": "3-5秒内直接抛出具体场景或明确利益点",
                "pain": "用门店真实问题承接，不泛泛铺垫",
                "selling": "按用户最关心的1-2个卖点推进到产品证明",
                "price": "价格/机制放在中后段，承接信任后再释放购买理由",
                "cta": "结尾自然引导左下角/小黄车，不用硬广口号",
                "visual": "按开场、证明、使用、成品或下单动作组织画面功能",
            }

        opening = "3-5秒内直接进入具体产品判断或门店使用场景"
        if self._has_any(text, [r"价格|活动|优惠|券|到手|恢复原价|买.*送|囤"]):
            opening = "用价格机制、活动利益或囤货理由开场，先给用户继续看的动机"
        elif self._has_any(text, [r"痛|麻烦|不好|粘手|开裂|踩坑|费时|翻车"]):
            opening = "用高频痛点开场，先让烘焙从业者觉得问题被说中"
        elif self._has_any(text, [r"客户|门店|出单|打包|生日蛋糕|甜品"]):
            opening = "用真实门店/客户场景开场，快速建立使用语境"

        pain = "先承接一个真实使用阻碍，再让产品卖点进入解决方案"
        if self._has_any(text, [r"以前|之前|原来|但是|结果|别等|后悔"]):
            pain = "用前后状态或损失感推进，让用户意识到现在处理更划算"
        elif self._has_any(text, [r"客户|老板|门店|出单"]):
            pain = "围绕门店接单、出品、备货或客户体验推进需求"

        selling = "先讲最强证明型卖点，再补使用便利或成本效率"
        if self._has_any(text, [r"包装|规格|克|g|保质|封口|独立"]):
            selling = "先讲包装/规格/保存等可信信息，再讲使用效果"
        elif self._has_any(text, [r"质地|口感|稳定|不裂|不粘|成品"]):
            selling = "先展示质地或成品效果，再补稳定性和操作省心"

        price = "价格/机制放在卖点证明之后，用作最后购买理由"
        if self._has_any(text, [r"开头|前3秒|一上来|先说.*价|价格.*离谱"]):
            price = "机制利益前置，开头就用价格/活动吸引点击"
        elif self._has_any(text, [r"最后|结尾|左下角|小黄车|拍下|下单"]):
            price = "机制利益后置，在CTA前强化下单理由"

        cta = "结尾自然引导左下角/小黄车，避免照搬原脚本促单句"
        if self._has_any(text, [r"左下角|小黄车|拍下|下单|链接"]):
            cta = "CTA在结尾出现，用动作指令承接前面的产品证明"
        elif self._has_any(text, [r"别等|赶紧|现在|错过"]):
            cta = "CTA带轻微紧迫感，但要换成当前产品的自然说法"

        visual = "按开场口播、产品细节、使用动作、成品结果、下单引导安排画面功能"
        if self._has_any(text, [r"镜头|画面|展示|特写|近景|俯拍|切换|定格"]):
            visual = "画面节奏包含产品细节、手部操作、对比或成品展示，可借鉴功能时机"
        elif self._has_any(text, [r"包装|规格|封口|瓶|袋|盒"]):
            visual = "优先安排包装规格和拿取保存细节，让产品证明可视化"

        return {
            "opening": opening,
            "pain": pain,
            "selling": selling,
            "price": price,
            "cta": cta,
            "visual": visual,
        }

    def _format_type_structure_reference(
        self,
        video_type: str,
        reference_scripts: Optional[List[Dict]],
    ) -> List[str]:
        if video_type == "AI智能生成" or not reference_scripts:
            return []

        lines = [
            "\n【同类型脚本结构参考】",
            "以下只学习同类型脚本的成交结构、推进节奏和画面功能，不作为改写源。",
            "硬性约束：禁止复制参考脚本原文、商品名、价格、CTA原句、称呼和固定开头；禁止输出“改写自”或说明参考了第几条。",
        ]
        for index, script in enumerate(reference_scripts[:3], 1):
            structure = self._infer_reference_structure(script.get("content", ""))
            quality = "高成交" if script.get("is_high_conversion") else "普通"
            lines.append(f"结构参考 #{index}（{script.get('video_type') or video_type}，{quality}）：")
            lines.append(f"- 开头方式：{structure['opening']}")
            lines.append(f"- 痛点推进：{structure['pain']}")
            lines.append(f"- 卖点顺序：{structure['selling']}")
            lines.append(f"- 价格/机制位置：{structure['price']}")
            lines.append(f"- CTA节奏：{structure['cta']}")
            lines.append(f"- 画面段落功能：{structure['visual']}")
        return lines

    def _build_user_prompt(
        self,
        product: Dict,
        template: Optional[Dict],
        video_type: str,
        tone: str,
        extra_requirements: Optional[str] = None,
        reference_scripts: Optional[List[Dict]] = None,
        include_shot_design: bool = False,
        price_required: bool = False,
    ) -> str:
        """构建用户提示词"""
        parts = []

        # 1. 产品信息
        parts.append("【产品信息】")
        parts.append(f"产品名称：{product.get('name', '')}")
        parts.append(f"品类：{product.get('category', '')}")
        parts.append(f"品牌：{product.get('brand', '')}")
        pending_fields = set(product.get("pending_fields") or [])
        price_text = "待更新" if "price" in pending_fields else abstract_script_price(product.get("price", 0))
        parts.append(f"售价：{price_text}")
        if "price" in pending_fields:
            parts.append("价格约束：价格待更新时不得编造价格、折扣、赠品或到手价，只能提示价格待更新或引导查看详情页。")
        if product.get("original_price"):
            parts.append(f"原价：{abstract_script_price(product.get('original_price'))}")
        parts.append("价格表达规则：价格信息只用于判断价格带，最终脚本禁止输出精确金额、小数金额、¥xx.xx、xx.xx元；请用几毛钱、十块以内、十来块、1开头、一杯奶茶钱、几十块、三位数等抽象说法。")
        if product.get("description"):
            parts.append(f"产品描述：{product.get('description')}")

        # 2. 卖点话术
        selling_points = product.get("selling_points", [])
        if selling_points:
            parts.append("\n【核心卖点话术】（按优先级排序）")
            for i, sp in enumerate(selling_points, 1):
                point_type = sp.get("type") or sp.get("point_type") or "卖点"
                parts.append(f"{i}. [{point_type}] {sp.get('content', '')}")
        else:
            parts.append("\n【核心卖点】（请根据产品信息提炼）")

        parts.extend(self._format_product_knowledge_context(product))
        parts.extend(self._format_type_structure_reference(video_type, reference_scripts))

        # 3. 创作要求
        parts.append(f"\n【创作要求】")
        parts.append(f"1. 视频类型：{video_type}")
        parts.append(f"2. 语言风格：{tone}")
        if include_shot_design:
            parts.append(f"3. 时间标记：每个段落标注时间范围（如 0-3s）")
            functional_markers = "【钩子】【痛点】【卖点】"
            if price_required:
                functional_markers += "【价格】"
            functional_markers += "【CTA】"
            parts.append(f"4. 段落标记：用{functional_markers}等标记功能")
            parts.append(f"5. 开头3秒内必须有一个强钩子")
        else:
            parts.append(f"3. 开头要有强钩子，但不要用标题、时间码或段落标签标出来")
            parts.append(f"4. 输出风格参考自然达人带货口播，像一口气说完的一段话，不要解释创作过程")
        parts.append(f"6. {self._format_ai_price_policy(price_required)}并保留明确的左下角下单引导；价格待更新时不能编造具体价格")
        parts.append(f"7. 融入具体的产品卖点，不要空泛")

        parts.append(self._format_shot_design_requirement(include_shot_design, use_template_reference=False))

        if extra_requirements:
            parts.append(f"\n【额外要求】{extra_requirements}")

        parts.append(f"\n请开始创作脚本：")

        return "\n".join(parts)

    def _format_template_prompt_value(self, value: Any, limit: int = 1200) -> str:
        if value is None or value == "" or value == [] or value == {}:
            return "（未填写）"
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            text = str(value)
        text = text.strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    def _format_template_prompt_list(self, value: Any, limit: int = 5) -> str:
        if not value:
            return "（未填写）"
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        else:
            items = [value]

        lines = []
        for item in items[:limit]:
            text = self._trim_prompt_text(item, limit=220)
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines) if lines else "（未填写）"

    def _format_rewrite_template_block(self, template: Dict) -> str:
        return f"""引用模板：{template.get('name') or '未命名模板'}
模板类型：{template.get('video_type') or '未填写'}
建议时长：{template.get('duration_range') or '未填写'}
模板描述：{self._format_template_prompt_value(template.get('description'), limit=400)}

模板结构：
{self._format_template_prompt_value(template.get('structure'), limit=1600)}

开头模板：
{self._format_template_prompt_list(template.get('hook_templates'))}

CTA 模板：
{self._format_template_prompt_list(template.get('cta_templates'))}

示例脚本：
{self._format_template_prompt_value(template.get('example_script'), limit=1600)}"""

    def _template_has_price_structure(self, template: Dict) -> bool:
        fields = (
            template.get("structure"),
            template.get("hook_templates"),
            template.get("cta_templates"),
            template.get("description"),
            template.get("example_script"),
        )
        text = "\n".join(
            self._format_template_prompt_value(value, limit=4000)
            for value in fields
        )
        return bool(re.search(
            r"价格|价位|售价|到手价|活动|成本|优惠|折扣|赠品|券|促销|满减|立减|买.{0,12}送"
            r"|(?:价格|活动|优惠|促销|折扣|赠送|满减|到手|成本)\s*机制"
            r"|机制\s*(?:价格|活动|优惠|促销|折扣|赠送|满减|到手|成本)",
            text,
        ))

    def _contains_price_or_promotion_copy(self, text: str) -> bool:
        return bool(_PRICE_OR_PROMOTION_COPY_RE.search(text or ""))

    def _format_library_template_policy(
        self,
        allows_audience_call: bool,
        has_price_structure: bool,
    ) -> str:
        if allows_audience_call:
            audience_policy = (
                "- 模板明确包含人群召唤，可保留相同结构的人群召唤；"
                "不得新增其他人群称呼，也不得强化或扩写该召唤。"
            )
        else:
            audience_policy = (
                "- 模板不包含人群召唤，禁止新增“姐妹们”“宝子们”“家人们”"
                "“老板们看过来”或泛化的“做/开...的...们”开头。"
            )

        if has_price_structure:
            price_policy = (
                "- 模板包含价格或机制功能，可在模板对应结构位置使用目标产品的抽象价格；"
                "价格待更新时不得编造价格、活动、优惠、折扣、赠品或促销机制。"
            )
        else:
            price_policy = (
                "- 模板没有价格或机制段落，最终脚本不得新增价格、优惠、折扣、赠品或促销内容，"
                "也不得额外增加价格或机制段落。"
            )
        return f"\n【本次模板专属最高优先级政策】\n{audience_policy}\n{price_policy}"

    def _format_rewrite_template_guardrails(self, template: Dict) -> str:
        return f"""结构模板：{template.get('name') or '未命名模板'}
模板类型：{template.get('video_type') or '未填写'}
建议时长：{template.get('duration_range') or '未填写'}
模板描述：{self._format_template_prompt_value(template.get('description'), limit=400)}

注意：该通用模板只用于确认视频类型、建议时长和合规边界。其段落结构、开头模板、CTA 模板和示例脚本都不是本次改写骨架，不得覆盖或重排具体引用脚本。"""

    def _library_structure_positions(self, beats: List[Dict]) -> tuple[set[int], set[int]]:
        price_positions = {
            index
            for index, beat in enumerate(beats, 1)
            if self._contains_price_or_promotion_copy(beat.get("text", ""))
        }
        cta_positions = {
            index
            for index, beat in enumerate(beats, 1)
            if _CTA_COPY_RE.search(beat.get("text", ""))
        }
        return price_positions, cta_positions

    def _format_library_source_policy(
        self,
        beats: List[Dict],
        *,
        price_pending: bool,
    ) -> str:
        price_positions, cta_positions = self._library_structure_positions(beats)
        source_copy = "".join(beat.get("text", "") for beat in beats)
        audience_call = extract_normalized_leading_audience_signature(source_copy)

        if price_positions and price_pending:
            price_policy = (
                f"- 原脚本的第 {', '.join(map(str, sorted(price_positions)))} 个表达点包含价格或促销，"
                "但目标产品价格待更新；必须在原价格表达点的位置改写为真实价值证明，禁止编造价格、活动或赠品。"
            )
        elif price_positions:
            price_policy = (
                f"- 原脚本仅允许在第 {', '.join(map(str, sorted(price_positions)))} 个表达点保留价格或促销功能，"
                "必须使用目标产品真实且抽象的价格表达，其他位置禁止出现价格或促销。"
            )
        else:
            price_policy = "- 原脚本没有价格或促销表达，禁止通用结构模板新增价格、活动、优惠、赠品或促销段落。"

        if cta_positions:
            cta_policy = (
                f"- 原脚本仅在第 {', '.join(map(str, sorted(cta_positions)))} 个表达点包含 CTA；"
                "改写后 CTA 仍只能出现在这些位置，不得提前或新增。"
            )
        else:
            cta_policy = "- 原脚本没有 CTA，禁止通用结构模板新增左下角、小黄车、下单或链接引导。"

        if audience_call:
            audience_policy = "- 原脚本包含开头人群召唤，可保留相同的开头功能，但必须适配目标产品受众且不得强化为空钩子。"
        else:
            audience_policy = "- 原脚本没有泛人群召唤，禁止新增“姐妹们”“宝子们”“家人们”“老板们看过来”等称呼开头。"

        return (
            "\n【具体引用脚本专属最高优先级政策】\n"
            f"{price_policy}\n{cta_policy}\n{audience_policy}"
        )

    def _library_spoken_length(self, text: str) -> int:
        spoken = strip_visual_notes(text)
        return len(re.sub(r"\s+", "", spoken))

    def _validate_library_structure(
        self,
        response: str,
        source_beats: List[Dict],
        *,
        price_pending: bool,
    ) -> tuple[List[str], List[str]]:
        segments, reasons = parse_indexed_rewrite(response, len(source_beats))
        if reasons or len(segments) != len(source_beats):
            return segments, reasons or ["表达点序号缺失、重复或顺序错误"]

        source_length = sum(self._library_spoken_length(beat.get("text", "")) for beat in source_beats)
        output_length = sum(self._library_spoken_length(segment) for segment in segments)
        if source_length and not (source_length * 0.65 <= output_length <= source_length * 1.4):
            reasons.append("总口播长度不在原脚本的 65%-140% 范围内")

        source_price, source_cta = self._library_structure_positions(source_beats)
        output_beats = [{"text": strip_visual_notes(segment)} for segment in segments]
        output_price, output_cta = self._library_structure_positions(output_beats)
        if price_pending:
            if output_price:
                reasons.append("价格待更新但改写结果仍包含价格或促销")
        elif not source_price and output_price:
            reasons.append("价格或促销出现在原脚本没有的位置")
        elif output_price - source_price:
            reasons.append("价格或促销位置与原脚本不一致")
        elif source_price and not output_price:
            reasons.append("原脚本的价格或促销机制在改写结果中完全缺失")

        if not source_cta and output_cta:
            reasons.append("CTA 出现在原脚本没有的位置")
        elif source_cta != output_cta:
            reasons.append("CTA 位置与原脚本不一致")

        source_copy = "".join(beat.get("text", "") for beat in source_beats)
        output_copy = "".join(strip_visual_notes(segment) for segment in segments)
        source_audience = extract_normalized_leading_audience_signature(source_copy)
        output_audience = extract_normalized_leading_audience_signature(output_copy)
        if not source_audience and output_audience:
            reasons.append("新增了原脚本没有的泛人群召唤")
        elif source_audience and not output_audience:
            reasons.append("缺少原脚本的人群召唤结构")
        return segments, list(dict.fromkeys(reasons))

    def _format_library_structure_repair_prompt(
        self,
        *,
        reasons: List[str],
        source_skeleton: str,
        first_response: str,
        include_shot_design: bool,
        expected_count: int,
    ) -> str:
        output_rule = (
            "每个序号后继续使用（具体画面说明）+口播文案，并让每个表达点独占一行。"
            if include_shot_design
            else "每个序号后只写口播文案，序号之间可以连续输出，不要添加画面说明。"
        )
        reason_block = "\n".join(f"- {reason}" for reason in reasons)
        return f"""首次模板库改写未通过结构校验，请只修正一次并直接输出完整改写稿。

机器校验原因：
{reason_block}

必须严格对应的原脚本结构骨架：
{source_skeleton}

首次结果：
{first_response}

修正规则：
- 必须完整输出从 [[BEAT_1]] 到 [[BEAT_{expected_count}]] 的全部内部序号，每个序号恰好一次且顺序不变。
- 每个表达点只改写对应原表达，不新增、删除或重排；资料不对应时换成同功能的真实卖点或证明。
- 价格、CTA 和人群召唤只能保留在原脚本对应位置。
- 总口播长度保持在原脚本的 65%-140%。
- {output_rule}
- 不要输出解释、分析、Markdown 或序号之外的前言。"""

    async def generate_from_library(
        self,
        product: Dict,
        video_type: str,
        template: Dict,
        source_script: Optional[Dict] = None,
        tone: str = "活泼",
        extra_requirements: Optional[str] = None,
        include_shot_design: bool = False,
    ) -> str:
        """模板库改写模式：使用结构模板和一条具体脚本改写目标产品版本。"""
        if not self._ai_available_for_interface("script_library_rewrite"):
            raise ScriptGenerationError(
                "模板库改写模型未配置，请到 AI配置 中检查模板库改写接口后重试。",
                status_code=503,
            )
        if not template:
            raise ScriptGenerationError("模板库改写缺少引用模板，请先在脚本模板库创建模板。", status_code=404)
        strict_source_structure = source_script is not None
        if source_script is not None and not (source_script.get("content") or "").strip():
            raise ScriptGenerationError("模板库改写引用脚本正文为空，请先补充脚本内容。", status_code=422)
        if source_script is None:
            source_script = {
                "source": "facai",
                "title": template.get("name") or "结构模板示例",
                "video_type": template.get("video_type") or video_type,
                "content": template.get("example_script") or "",
            }

        # 构建改写专用 Prompt
        product_name = product.get("name", "")
        product_category = product.get("category", "")
        product_price = product.get("price", 0)
        product_pending_fields = set(product.get("pending_fields") or [])
        product_price_text = "待更新" if "price" in product_pending_fields else abstract_script_price(product_price)
        selling_points = product.get("selling_points", [])

        # 格式化卖点
        sp_texts = []
        for sp in sorted(selling_points, key=lambda x: x.get("priority", 0) if isinstance(x, dict) else 0):
            sp_texts.append(f"- [{sp.get('type', '')}] {sp.get('content', '')}")
        sp_block = "\n".join(sp_texts) if sp_texts else "（请根据产品信息提炼卖点）"

        template_block = (
            self._format_rewrite_template_guardrails(template)
            if strict_source_structure
            else self._format_rewrite_template_block(template)
        )
        source_name = "法采脚本" if source_script.get("source") == "facai" else "其他脚本"
        source_title = self._trim_prompt_text(source_script.get("title") or "无标题脚本", limit=300)
        source_video_type = self._trim_prompt_text(source_script.get("video_type") or "未标注", limit=100)
        source_content_with_lines = sanitize_script_price_text(source_script.get("content") or "")[:6000]
        source_content = self._trim_prompt_text(source_content_with_lines, limit=6000)
        source_beats = extract_script_beats(source_content_with_lines) if strict_source_structure else []
        if strict_source_structure and not source_beats:
            raise ScriptGenerationError("模板库改写无法从引用脚本提取有效表达点，请先检查脚本内容。", status_code=422)
        source_skeleton = format_indexed_script_beats(source_beats) if source_beats else ""
        source_block = (
            f"来源：{source_name}\n"
            f"标题：{source_title}\n"
            f"视频类型：{source_video_type}\n"
            f"脚本正文：\n{source_content}"
        )
        if source_skeleton:
            source_block += f"\n\n逐表达点主骨架（内部序号必须原样返回）：\n{source_skeleton}"

        allowed_audience_phrases = collect_template_audience_phrases(template)
        allows_audience_call = template_allows_audience_call(template)
        if strict_source_structure:
            source_price_positions, _source_cta_positions = self._library_structure_positions(source_beats)
            has_price_structure = bool(source_price_positions)
            template_policy = self._format_library_source_policy(
                source_beats,
                price_pending="price" in product_pending_fields,
            )
        else:
            has_price_structure = self._template_has_price_structure(template)
            template_policy = self._format_library_template_policy(
                allows_audience_call,
                has_price_structure,
            )

        if strict_source_structure and include_shot_design:
            rewrite_rules = f"""1. 具体引用脚本是唯一主结构，必须逐表达点对应：第 1 个表达改写第 1 个，第 2 个改写第 2 个，直到第 {len(source_beats)} 个；除特别短的相邻表达可在同一表达点内自然衔接外，不得增删、合并序号或重排。
2. 通用结构模板不得新增、删除或重排表达点；只用于确认视频类型、建议时长和合规边界。
3. 每个表达点必须保留对应原文的功能、开头方式、证明位置、价格位置、CTA 位置和推进节奏，只替换商品名、品牌、卖点、规格和事实。
4. 目标产品资料不能直接对应时，在原位置换成同功能的真实卖点或证明，不得编造数据，也不得删除这个表达点。
5. 每个表达点必须以对应的 [[BEAT_数字]] 内部序号开头，序号必须从 1 到 {len(source_beats)} 完整、唯一且有序；每个序号后写（具体画面说明）+口播文案，并让每个表达点独占一行。
6. 画面说明必须服务该表达点的原有功能，写清主体、景别、动作或道具，不得用通用模板另起画面段落。
7. 禁止复制原脚本具体措辞、旧商品名、品牌、精确价格和 CTA 原句；禁止输出“改写自”、选择过程、分析解释或 Markdown。"""
        elif strict_source_structure:
            rewrite_rules = f"""1. 具体引用脚本是唯一主结构，必须逐表达点对应：第 1 个表达改写第 1 个，第 2 个改写第 2 个，直到第 {len(source_beats)} 个；除特别短的相邻表达可在同一表达点内自然衔接外，不得增删、合并序号或重排。
2. 通用结构模板不得新增、删除或重排表达点；只用于确认视频类型、建议时长和合规边界。
3. 每个表达点必须保留对应原文的功能、开头方式、证明位置、价格位置、CTA 位置和推进节奏，只替换商品名、品牌、卖点、规格和事实。
4. 目标产品资料不能直接对应时，在原位置换成同功能的真实卖点或证明，不得编造数据，也不得删除这个表达点。
5. 每个表达点必须以对应的 [[BEAT_数字]] 内部序号开头，序号必须从 1 到 {len(source_beats)} 完整、唯一且有序；序号后只写对应口播，不写画面说明。特别短的相邻表达可在最终口播中连成一句，但两个内部序号仍必须保留。
6. 额外要求只能融入最合适的已有表达点，不得在结尾追加新段落。
7. 禁止复制原脚本具体措辞、旧商品名、品牌、精确价格和 CTA 原句；禁止输出“改写自”、模板名称、时间码、段落标题、镜头说明、分析解释或 Markdown。"""
        elif include_shot_design:
            rewrite_rules = """1. 结构模板决定段落功能和顺序；具体参考脚本只用于借鉴开头方式、痛点推进、卖点顺序、口语节奏和画面功能。
2. 替换参考内容中的产品名、品牌、卖点和规格为目标产品内容，所有品牌名统一为“法采”。
3. 严格保留结构模板实际包含的段落功能和顺序，不新增模板没有的功能段落。
4. 禁止复制模板示例脚本原文，也禁止复制具体参考脚本的原文、开头原句、CTA 原句、商品名、品牌、精确价格或固定称呼。
5. 每一句口播都要匹配具体镜头/画面说明，画面要服务产品证明和下单转化。
6. 禁止输出“改写自”、模板编号、选择过程、分析解释或 Markdown。"""
        else:
            rewrite_rules = """1. 结构模板决定段落功能和顺序，只借鉴模板的成交结构；具体参考脚本只用于借鉴开头方式、痛点推进、卖点顺序和口语节奏。
2. 替换参考内容中的产品名、品牌、卖点和规格为目标产品内容，所有品牌名统一为“法采”。
3. 禁止复制模板示例脚本原文，也禁止复制具体参考脚本的原文、开头原句、CTA 原句、商品名、品牌、精确价格或固定称呼。
4. 严禁输出“改写自”、模板名称、模板编号、时间码、【】段落标题、镜头/画面/字幕/口播/场景说明。
5. 最终只输出一段连续口播文案，不换行，不用列表，不用 Markdown。
6. 口吻参考达人自然带货口播，多用顺滑连接词，让内容像一整段真实口播。"""

        task_description = (
            "本次必须以具体引用脚本作为唯一主骨架，按表达点逐条替换为目标产品内容；通用结构模板不得改变原脚本结构。"
            if strict_source_structure
            else "本次使用 1 条结构模板和 1 条具体参考脚本进行重新创作。"
        )
        task_instruction = (
            "你的任务：在不改变具体引用脚本表达点数量、顺序和功能位置的基础上，逐条替换为目标产品的真实内容。"
            if strict_source_structure
            else "你的任务：服从结构模板的段落功能，根据具体参考脚本的成交推进节奏，重新创作以下目标产品的带货脚本。"
        )
        template_heading = "脚本类型与合规参考（非结构来源）" if strict_source_structure else "脚本模板库结构模板"

        user_prompt = f"""你是脚本模板库改写专家。{task_description}

{task_instruction}

====================================
目标产品信息
====================================
产品名称：{product_name}
品类：{product_category}
售价：{product_price_text}
品牌：法采
视频类型：{video_type}
语言风格：{tone}
价格表达规则：价格信息只用于判断价格带，最终脚本禁止输出精确金额、小数金额、¥xx.xx、xx.xx元；请用几毛钱、十块以内、十来块、1开头、一杯奶茶钱、几十块、三位数等抽象说法。

核心卖点话术：
{sp_block}
====================================

====================================
{template_heading}
====================================
结构模板：{template.get('name') or '未命名模板'}
{template_block}

====================================
具体参考脚本
====================================
{source_block}

====================================
改写要求
====================================
{rewrite_rules}"""

        user_prompt += self._format_shot_design_requirement(include_shot_design)

        if extra_requirements:
            extra_policy = (
                "（必须融入最合适的已有表达点，不得追加新段落）"
                if strict_source_structure
                else ""
            )
            user_prompt += f"\n\n【额外要求】{extra_requirements}{extra_policy}"

        user_prompt += template_policy
        user_prompt += "\n\n请开始改写脚本："

        system_prompt = self._build_library_system_prompt(include_shot_design) + template_policy
        if strict_source_structure:
            system_prompt += (
                "\n- 本次长度以具体引用脚本为准，最终口播保持原稿的 65%-140%；"
                "原稿超过500字时允许改写稿超过500字，结构完整性优先于默认500字限制。"
            )
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._chat_with_interface(
                messages,
                temperature=0.45,
                interface_key="script_library_rewrite",
                allow_fallback=False,
            )
        except ScriptGenerationError:
            raise
        except Exception as exc:
            raise ScriptGenerationError(
                f"模板库改写模型调用失败：{exc}",
                status_code=503,
            ) from exc

        if not strict_source_structure and not (response or "").strip():
            raise ScriptGenerationError("模板库改写模型未返回有效脚本，请检查 AI 配置后重试。")

        structured_segments: List[str] = []
        if strict_source_structure:
            structured_segments, structure_reasons = self._validate_library_structure(
                response,
                source_beats,
                price_pending="price" in product_pending_fields,
            )
            if structure_reasons:
                repair_prompt = self._format_library_structure_repair_prompt(
                    reasons=structure_reasons,
                    source_skeleton=source_skeleton,
                    first_response=response,
                    include_shot_design=include_shot_design,
                    expected_count=len(source_beats),
                )
                repair_messages = [
                    messages[0],
                    messages[1],
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": repair_prompt},
                ]
                try:
                    response = await self._chat_with_interface(
                        repair_messages,
                        temperature=0.25,
                        interface_key="script_library_rewrite",
                        allow_fallback=False,
                    )
                except Exception as exc:
                    raise ScriptGenerationError(
                        "模板库改写结构未通过，请重新生成。",
                        status_code=502,
                    ) from exc
                structured_segments, structure_reasons = self._validate_library_structure(
                    response,
                    source_beats,
                    price_pending="price" in product_pending_fields,
                )
                if structure_reasons:
                    raise ScriptGenerationError(
                        "模板库改写结构未通过，请重新生成。",
                        status_code=502,
                    )
        elif not has_price_structure and self._contains_price_or_promotion_copy(response):
            raise ScriptGenerationError(
                "模板库改写结果擅自加入价格或促销信息，请重试。",
                status_code=502,
            )

        response_for_output = response
        if strict_source_structure:
            response_for_output = (
                "\n".join(structured_segments)
                if include_shot_design
                else "".join(structured_segments)
            )
        script = self._post_process_script_output(
            response_for_output,
            include_shot_design,
            remove_default_audience_opening=False,
        )
        if not strict_source_structure:
            output_audience_phrase = extract_normalized_leading_audience_signature(script)
            if (
                output_audience_phrase
                and output_audience_phrase not in allowed_audience_phrases
            ):
                script = strip_generic_audience_opening(script)
        if not script.strip():
            raise ScriptGenerationError("模板库改写模型返回内容为空，请重试或检查 AI 配置。")
        if not strict_source_structure and not has_price_structure and self._contains_price_or_promotion_copy(script):
            raise ScriptGenerationError(
                "模板库改写结果擅自加入价格或促销信息，请重试。",
                status_code=502,
            )
        return script

    def _build_library_system_prompt(self, include_shot_design: bool) -> str:
        return build_rewrite_system_prompt(include_shot_design)


# 全局单例
script_generator = ScriptGenerator()
