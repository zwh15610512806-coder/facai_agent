"""脚本生成引擎 — 核心业务逻辑"""
from services.ai_service import ai_service, AIService, build_faicai_script
from models import ViralScript, ReferenceScript
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Dict, Optional, Any
import json
import logging
import random
import re

logger = logging.getLogger(__name__)


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

    DEEPSEEK_OPENING_STRATEGIES = (
        "价格机制开场：第一句先讲清活动、成本或省心机制，但只能使用输入里真实存在的价格/活动信息",
        "痛点场景开场：第一句直接切进门店备货、打包、配送、出品或接急单时的具体麻烦",
        "结果反差开场：第一句对比普通做法和法采产品带来的效率、品质或成本变化",
        "认知反差开场：第一句先点破烘焙店老板容易忽略的选品细节",
        "动作画面开场：第一句从拿起、切开、装袋、打包、配送、上架等具体动作进入",
        "客户反馈开场：第一句从顾客体验、门店复购或出餐效率切入，不编造具体数据",
    )

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
                "- 参考模板库脚本的画面节奏和镜头功能。"
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
            "- 仍参考模板库的成交逻辑和表达节奏，但不保留模板里的镜头格式。"
            if use_template_reference
            else "- 仍参考抖音带货跑量逻辑和真实产品场景，但不套用模板脚本格式。"
        )
        connector_line = (
            "- 可以使用“啊、姐妹们、关键、如果”等口语连接词，让文案读起来顺滑自然。"
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

    def _format_deepseek_run_rate_framework(self) -> str:
        return (
            "\n【抖音跑量自检框架】\n"
            "- 开头3-5秒必须给出具体钩子，可以是价格机制、痛点反差、场景冲突、效果对比或认知反差，避免泛化开头。\n"
            "- 目标人群必须明确为烘焙店老板/烘焙从业者，不要写成泛消费者种草。\n"
            "- 用一个真实使用场景承接痛点或需求，让观众能立刻代入门店备货、出品、配送、打包或活动促销。\n"
            "- 至少引用2个产品资料里的具体卖点，卖点要落到成本、效率、品质、稳定性、使用步骤或成品效果，禁止空泛夸张。\n"
            "- 价格、活动、赠品必须与输入一致；价格待更新时不得编造价格、折扣、赠品或到手价。\n"
            "- CTA必须自然引导左下角/小黄车，但避免全篇硬广，要先让用户相信产品值得点开。\n"
            "- 先内部自评并修正：钩子是否能留住人，场景是否真实，卖点是否具体，价格是否一致，CTA是否明确；最终不要输出评分或解释。"
        )

    def _choose_deepseek_opening_strategy(self) -> str:
        return random.choice(self.DEEPSEEK_OPENING_STRATEGIES)

    def _format_deepseek_opening_variety_requirement(self, opening_strategy: str) -> str:
        return (
            "\n【开头去重要求】\n"
            f"- 本次开头角度：{opening_strategy}\n"
            "- 禁止以“姐妹们”“烘焙姐妹们”“家人们”“老板们看过来”作为默认开头，除非用户额外要求。\n"
            "- 第一小句必须直接进入价格机制、痛点场景、结果反差、认知反差、客户反馈或具体动作画面，不要先喊人群称呼。\n"
            "- 每次重新生成必须更换开头角度和第一句话句式，不要连续使用同一种开场句。"
        )

    def _post_process_script_output(
        self,
        script: str,
        include_shot_design: bool,
        remove_default_audience_opening: bool = False,
    ) -> str:
        text = (script or "").strip()
        if include_shot_design:
            return self._remove_default_audience_opening(text) if remove_default_audience_opening else text

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
            text = self._remove_default_audience_opening(text)
        return text.strip()

    def _remove_default_audience_opening(self, text: str) -> str:
        """Remove generic audience-call prefixes from DeepSeek-created scripts only."""
        if not text:
            return ""

        prefix_pattern = (
            r"^(\s*(?:[（(][^（）()]{1,120}[）)]\s*)?)"
            r"(?:做烘焙的)?(?:烘焙)?姐妹们(?:看过来|注意了|别划走)?[，,、！!\s]*"
        )

        lines = text.splitlines()
        lines[0] = re.sub(prefix_pattern, r"\1", lines[0]).lstrip()
        return "\n".join(lines).strip()

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

        # 构建系统提示
        system_prompt = self._build_system_prompt(
            video_type,
            tone,
            include_shot_design=include_shot_design,
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

        script = self._post_process_script_output(
            response,
            include_shot_design,
            remove_default_audience_opening=True,
        )
        if not script.strip():
            raise ScriptGenerationError("AI生成模型返回内容为空，请重试或检查 AI 配置。")
        return script

    def _build_system_prompt(self, video_type: str, tone: str, include_shot_design: bool = False) -> str:
        """构建系统提示词"""
        strategy = self.TYPE_STRATEGIES.get(
            video_type,
            self.TYPE_STRATEGIES["机制类"]
        )
        opening_strategy = self._choose_deepseek_opening_strategy()
        opening_requirement = self._format_deepseek_opening_variety_requirement(opening_strategy)
        if not include_shot_design:
            return f"""你是法采食品店的短视频带货纯口播文案专家，擅长把烘焙产品卖点写成一段自然达人口播。

当前输出模式：纯口播一段话。

硬性输出规则：
- 只输出最终视频文案本身，不输出解释、标题、编号或 Markdown。
- 只输出一段连续自然口播文案，不换行，不分段。
- 禁止【】段落标签、时间码、分镜标题、镜头说明、画面说明、字幕提示、口播标签和场景说明。
- 可以借鉴抖音爆款带货视频的成交逻辑、痛点推进、卖点顺序和口语节奏，但不能套用模板脚本格式。
- 语言要像真实带货达人顺口说出来，可以使用“关键、如果、直接、你看、说白了”这类自然连接词。
- 必须包含产品卖点、已有价格/促销信息或价格待更新提示，并有明确左下角下单引导。
{self._format_deepseek_run_rate_framework()}
{opening_requirement}

当前任务：
- 视频类型：{video_type}
- 创作策略：{strategy}
- 语言风格：{tone}

请严格按纯口播一段话输出。"""

        # 随机创意变体，避免每次生成相同的开场套路
        import random
        variations = [
            "这次尝试一个全新的开场角度，避免重复之前的套路。",
            "用不同的情绪基调来开场，可以更夸张或更接地气。",
            "这次换一种叙事节奏，比如先抛问题再揭晓答案。",
            "尝试更有冲击力的镜头语言描述，让画面感更强。",
            "卖点呈现顺序可以打乱，找到最能打透用户心理的排列。",
            "这次的语气可以更真实自然，像朋友推荐一样，减少广告感。",
            "价格部分可以用更有张力的表达方式，制造稀缺感。",
            "CTA 这次换一个完全不同的角度和句式。",
        ]
        variation = random.choice(variations)

        return f"""你是法采食品店的短视频带货口播+画面脚本专家，擅长把烘焙产品卖点写成适合抖音跑量的真实门店场景脚本。

当前输出模式：口播+画面设计。

硬性输出规则：
- 只输出最终脚本本身，不输出解释、创作思路或 Markdown。
- 可以用时间段和功能标签组织脚本，但每一句口播都要配合具体镜头/画面说明。
- 镜头说明必须服务产品证明：真实门店场景、产品细节、使用动作、成品效果、价格机制或左下角下单引导。
- 口语表达要像烘焙店老板/烘焙从业者在真实分享，可以使用“关键、如果、直接、你看、说白了”等自然连接词。
- 必须包含产品卖点、已有价格/促销信息或价格待更新提示，并有明确左下角/小黄车下单引导。
- 避免全篇硬广，先用场景、证明和具体卖点让用户相信产品值得点开。

当前任务：
- 视频类型：{video_type}
- 创作策略：{strategy}
- 语言风格：{tone}
- 创意要求：{variation}
{self._format_deepseek_run_rate_framework()}
{opening_requirement}

请严格按照上述策略创作，确保脚本具备抖音跑量能力。"""

    def _format_prompt_price(self, value: Any) -> str:
        if value is None or value == "":
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value).strip()
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")

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
            return self._trim_prompt_text(sku["line"], limit=220)

        name = sku.get("name") or " / ".join(
            part for part in [sku.get("product"), sku.get("spec")] if part
        ) or "默认规格"
        bits = []
        price = self._format_prompt_price(sku.get("price"))
        daily_price = self._format_prompt_price(sku.get("daily_price"))
        if price:
            bits.append(f"售价¥{price}")
        if daily_price and daily_price != price:
            bits.append(f"日常价¥{daily_price}")

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
            bits.append(f"{mechanism}¥{formatted_price}{suffix}")

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
    ) -> str:
        """构建用户提示词"""
        parts = []

        # 1. 产品信息
        parts.append("【产品信息】")
        parts.append(f"产品名称：{product.get('name', '')}")
        parts.append(f"品类：{product.get('category', '')}")
        parts.append(f"品牌：{product.get('brand', '')}")
        pending_fields = set(product.get("pending_fields") or [])
        price_text = "待更新" if "price" in pending_fields else f"{product.get('price', 0)}元"
        parts.append(f"售价：{price_text}")
        if "price" in pending_fields:
            parts.append("价格约束：价格待更新时不得编造价格、折扣、赠品或到手价，只能提示价格待更新或引导查看详情页。")
        if product.get("original_price"):
            parts.append(f"原价：{product.get('original_price')}元")
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
            parts.append(f"4. 段落标记：用【钩子】【痛点】【卖点】【价格】【CTA】等标记功能")
            parts.append(f"5. 开头3秒内必须有一个强钩子")
        else:
            parts.append(f"3. 开头要有强钩子，但不要用标题、时间码或段落标签标出来")
            parts.append(f"4. 输出风格参考自然达人带货口播，像一口气说完的一段话，不要解释创作过程")
        parts.append(f"6. 必须包含输入中已有的价格/活动信息和明确的左下角下单引导；如果价格待更新，不能编造具体价格")
        parts.append(f"7. 融入具体的产品卖点，不要空泛")

        parts.append(self._format_shot_design_requirement(include_shot_design, use_template_reference=False))

        if extra_requirements:
            parts.append(f"\n【额外要求】{extra_requirements}")

        parts.append(f"\n请开始创作脚本：")

        return "\n".join(parts)

    async def generate_from_library(
        self,
        product: Dict,
        video_type: str,
        reference_scripts: List[Dict],
        tone: str = "活泼",
        extra_requirements: Optional[str] = None,
        include_shot_design: bool = False,
    ) -> str:
        """模板库改写模式：将匹配到的高成交脚本改写为目标产品版本

        与 generate() 的核心区别：
        1. 参考脚本是 PRIMARY 改写源，不是次要灵感
        2. 使用完整脚本内容（不截断）
        3. 使用 TEMPLATE_REWRITE_SYSTEM_PROMPT（改写专用）
        4. Prompt 指令是"改写"而非"创作"
        """
        if not self._ai_available_for_interface("script_library_rewrite"):
            return self._post_process_script_output(
                build_faicai_script(product, tone),
                include_shot_design,
            )

        # 构建改写专用 Prompt
        product_name = product.get("name", "")
        product_category = product.get("category", "")
        product_price = product.get("price", 0)
        product_pending_fields = set(product.get("pending_fields") or [])
        product_price_text = "待更新" if "price" in product_pending_fields else f"{product_price}元"
        selling_points = product.get("selling_points", [])

        # 格式化卖点
        sp_texts = []
        for sp in sorted(selling_points, key=lambda x: x.get("priority", 0) if isinstance(x, dict) else 0):
            sp_texts.append(f"- [{sp.get('type', '')}] {sp.get('content', '')}")
        sp_block = "\n".join(sp_texts) if sp_texts else "（请根据产品信息提炼卖点）"

        # 提取高成交参考脚本（最多3条，完整内容）
        scripts_block = []
        high_conv_scripts = [s for s in reference_scripts if s.get("is_high_conversion")]
        normal_scripts = [s for s in reference_scripts if not s.get("is_high_conversion")]
        selected = (high_conv_scripts + normal_scripts)[:3]

        for i, rs in enumerate(selected, 1):
            scripts_block.append(f"""
=== 爆款脚本 #{i} ===
标题：{rs.get('title', '')}
类型：{rs.get('video_type', '')}
品类：{rs.get('category', '')}
{'⚠ 高成交脚本' if rs.get('is_high_conversion') else ''}

【完整脚本内容】
{rs.get('content', '')}
""")

        scripts_text = "\n".join(scripts_block)

        if include_shot_design:
            rewrite_rules = f"""1. 从以上 {len(selected)} 条中选出最适合改写的一条脚本进行改写
2. **替换**所有产品名、卖点、价格、规格为目标产品内容
3. **保持**原脚本的结构、段落划分、时间标注、情绪节奏
4. **保持**原脚本的语气和口语化风格（感叹号、紧迫感、姐妹称呼等）
5. 镜头指令微调适配新产品，但保留原镜头的功能时机
6. 所有品牌名统一为"法采"
7. CTA 保持原结构，根据新产品价格微调
8. 必须在开头标注你改写了第几条脚本"""
        else:
            rewrite_rules = f"""1. 从以上 {len(selected)} 条中选出最适合改写的一条脚本进行改写
2. **替换**所有产品名、卖点、价格、规格为目标产品内容
3. 只借鉴原脚本的成交逻辑、痛点推进、卖点顺序和口语节奏，不保留原脚本格式
4. 严禁输出“改写自”、爆款脚本编号、时间码、【】段落标题、镜头/画面/字幕/口播/场景说明
5. 最终只输出一段连续口播文案，不换行，不用列表，不用 Markdown
6. 口吻参考达人自然带货口播，多用顺滑连接词，让内容像用户给的例子一样是一整段话
7. 所有品牌名统一为"法采"
8. CTA 按原脚本的成交意图改写，但不要保留原脚本的段落结构"""

        user_prompt = f"""你是脚本改写专家。以下是 {len(selected)} 条爆款脚本库中的高成交脚本。

你的任务：选择其中最合适的一条，**改写**为以下目标产品的带货脚本。

====================================
目标产品信息
====================================
产品名称：{product_name}
品类：{product_category}
售价：{product_price_text}
品牌：法采
视频类型：{video_type}
语言风格：{tone}

核心卖点话术：
{sp_block}
====================================

{scripts_text}

====================================
改写要求
====================================
{rewrite_rules}"""

        user_prompt += self._format_shot_design_requirement(include_shot_design)

        if extra_requirements:
            user_prompt += f"\n\n【额外要求】{extra_requirements}"

        user_prompt += "\n\n请开始改写脚本："

        messages = [
            {"role": "system", "content": self._build_library_system_prompt(include_shot_design)},
            {"role": "user", "content": user_prompt},
        ]

        response = await self._chat_with_interface(messages, temperature=0.75, interface_key="script_library_rewrite")
        return self._post_process_script_output(response, include_shot_design)

    def _build_library_system_prompt(self, include_shot_design: bool) -> str:
        if include_shot_design:
            return AIService.TEMPLATE_REWRITE_SYSTEM_PROMPT

        return """你是法采食品店的高成交模板库口播改写专家，擅长把已验证的爆款结构改写成一段可直接拍摄的自然带货口播。

当前输出模式：纯口播一段话。

改写原则：
1. 参考脚本只作为成交逻辑、痛点推进、卖点顺序和口语节奏的依据。
2. 必须替换为目标产品的名称、卖点、价格、规格和法采品牌表达。
3. 不保留参考脚本的结构化格式，不保留段落标题，不保留时间标注，不保留镜头或画面说明。
4. 只输出一段连续自然口播文案，不换行，不用列表，不用 Markdown，不写“改写自”或脚本编号。
5. 口吻要接近真实达人带货，一口气讲完，逻辑顺序是痛点/需求、产品解决、卖点证明、促销下单。
6. CTA 必须有明确左下角下单引导。"""


# 全局单例
script_generator = ScriptGenerator()
