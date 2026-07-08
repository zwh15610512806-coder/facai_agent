"""脚本改写服务 — 保留参考结构，并统一输出为资料脚本表格式"""
from services.ai_service import ai_service
from services.rewrite_prompts import build_rewrite_system_prompt
from models import ViralScript
from sqlalchemy.orm import Session
import re


class ScriptRewriteGenerationError(RuntimeError):
    """Raised when script rewrite cannot produce a real AI result."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class ScriptRewriter:
    """脚本改写器：保留原参考结构，统一输出为法采资料脚本格式"""

    MATERIAL_SCRIPT_FORMAT = """【资料脚本生成文件格式要求】
输出必须参考《资料/脚本生成.xlsx》的脚本格式：
- 直接输出一条可拍摄的完整短视频脚本，不要解释、不要标题、不要 Markdown、不要编号列表。
- 用中文全角括号写具体画面/拍摄/剪辑指令，必须包含拍摄主体、镜头/景别、动作或道具，例如：（主播半身站在烘焙台前开场，手边摆放产品包装）（产品包装正面近景，手拿转动展示规格）（俯拍操作台，手部倒入原料并搅拌）（切开成品蛋糕近景，展示夹心层次）。
- 括号后面直接接对应口播文案，形成连续成稿，例如：（主播半身站在烘焙台前开场，手边摆放产品包装）老板们别再乱买了，（产品包装正面近景，手拿转动展示规格）看一下法采这款...
- 不要只写（口播画面）（产品空镜）（产品展示）这类泛标签；每一句口播前的括号都要像模板库脚本一样说明“拍什么、怎么拍、展示什么细节”。
- 不要输出【开场钩子】【痛点激发】【产品卖点展示】这类段落标题。
- 不要输出 0-3s、3-10s、00:00-00:03 这类时间戳；如果原文有时间戳，只吸收节奏，不保留时间戳格式。
- 如果原文是一整段话，也要给每个关键句补出具体画面指令，例如主播口播、产品包装近景、手部操作俯拍、成品切面展示、左右对比展示等。
- 必须保留用户参考文案的结构顺序：原文第1句对应改写第1个表达，原文第2句对应改写第2个表达，以此类推。
- 不允许用同类爆款脚本或产品资料重新生成一条全新结构；同类脚本只能参考语气和括号画面写法。
- 口播要保持资料表里的抖音烘焙带货口吻：自然、直接、有画面感，能开拍即用。"""

    SYSTEM_PROMPT = build_rewrite_system_prompt(include_shot_design=True)
    PLAIN_SYSTEM_PROMPT = build_rewrite_system_prompt(include_shot_design=False)

    def __init__(self):
        self.ai = ai_service

    def _ai_available_for_interface(self, interface_key: str) -> bool:
        checker = getattr(self.ai, "is_interface_available", None)
        if checker:
            return bool(checker(interface_key))
        if hasattr(self.ai, "is_available"):
            return bool(getattr(self.ai, "is_available"))
        return True

    def _extract_keywords(self, product_name: str) -> list:
        """从产品名提取多个候选关键词（从长到短）"""
        import re
        main_name = re.split(r'[（(]', product_name)[0].strip()
        candidates = [main_name] if main_name else []
        prefixes = ['防潮', '彩色', '手绘', '高浓', '油性', '水性', '无糖', '低糖',
                    '零卡', '金丝', '经典', '成品', '天然', '水溶', '水状', '巧克力']
        for prefix in prefixes:
            if main_name.startswith(prefix) and len(main_name) > len(prefix) + 2:
                stripped = main_name[len(prefix):]
                if stripped and stripped not in candidates:
                    candidates.append(stripped)
                break
        suffix_patterns = ['膏', '粉', '片', '笔', '盘', '脆', '霜', '酱', '松', '汁']
        for suf in suffix_patterns:
            idx = main_name.find(suf)
            if idx > 0:
                base = main_name[:idx]
                if base and base not in candidates:
                    candidates.append(base)
                words = re.findall(r'[一-龥]+', base)
                if len(words) >= 2 and words[-1] not in candidates:
                    candidates.append(words[-1])
                break
        seen = set()
        result = []
        for kw in candidates:
            if kw not in seen and len(kw) >= 2:
                seen.add(kw)
                result.append(kw)
        return result

    def _keyword_find_scripts(self, db: Session, candidates: list) -> list:
        """Fallback keyword search for rewrite reference scripts."""
        try:
            def qk(db_s, conv, excl, lim):
                for kw in candidates:
                    qq = db_s.query(ViralScript).filter(
                        ViralScript.is_high_conversion == conv,
                        ViralScript.category.contains(kw),
                    )
                    if excl:
                        qq = qq.filter(~ViralScript.id.in_(excl))
                    rr = qq.limit(lim).all()
                    if rr:
                        return rr
                return []
            high = qk(db, 1, [], 2)
            high_ids = [s.id for s in high]
            normal = qk(db, 0, high_ids, 2)
            total = len(high) + len(normal)
            if total < 3:
                excl = [s.id for s in (high + normal)]
                more = qk(db, 1, excl, 1)
                excl += [s.id for s in more]
                more2 = qk(db, 0, excl, 1)
                return list(high) + list(normal) + list(more) + list(more2)
            return list(high) + list(normal)
        except Exception:
            return []

    def _extract_reference_beats(self, original_script: str, limit: int = 45) -> list[dict]:
        """Extract ordered beats from timestamped, line-based, or paragraph scripts."""
        text = (original_script or "").strip()
        if not text:
            return []

        timestamp_re = re.compile(
            r"^\s*(?P<time>\d{1,2}[:：]\d{2}(?::\d{2})?)\s*(?:[-—~至到]\s*\d{1,2}[:：]\d{2}(?::\d{2})?)?\s*(?P<text>.+?)\s*$"
        )
        beats = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = timestamp_re.match(line)
            if match:
                content = match.group("text").strip()
                if content:
                    beats.append({"time": match.group("time").replace("：", ":"), "text": content})

        if not beats:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 1:
                beats = [{"time": "", "text": self._strip_known_prefixes(line)} for line in lines]
            else:
                parts = re.split(r"(?<=[。！？!?；;])\s*", text)
                beats = [{"time": "", "text": self._strip_known_prefixes(part)} for part in parts if part.strip()]

        normalized = []
        for beat in beats:
            content = self._strip_known_prefixes(beat["text"])
            if content:
                normalized.append({"time": beat.get("time", ""), "text": content})
            if len(normalized) >= limit:
                break
        return normalized

    def _strip_known_prefixes(self, text: str) -> str:
        """Remove timing/section wrappers while keeping the user's expression."""
        cleaned = text.strip()
        cleaned = re.sub(r"^\s*【[^】\n]{1,30}】\s*", "", cleaned)
        cleaned = re.sub(r"^\s*[（(][^）)\n]{1,30}[）)]\s*", "", cleaned)
        cleaned = re.sub(
            r"^\s*(?:\d{1,2}[:：]\d{2}(?::\d{2})?|\d{1,2})\s*(?:[-—~至到]\s*(?:\d{1,2}[:：]\d{2}(?::\d{2})?|\d{1,2}))?\s*[s秒]?\s*[:：-]?\s*",
            "",
            cleaned,
        )
        return cleaned.strip()

    def _build_reference_structure(self, original_script: str) -> str:
        """Build a compact ordered outline for the AI to map one-to-one."""
        beats = self._extract_reference_beats(original_script)
        if not beats:
            return "1. 原文为空，请按目标产品生成一条资料脚本格式短视频脚本。"

        lines = []
        for idx, beat in enumerate(beats, 1):
            prefix = f"{idx}. "
            if beat.get("time"):
                prefix += f"[{beat['time']}] "
            lines.append(prefix + beat["text"])
        return "\n".join(lines)

    def find_similar_scripts_for_rewrite(
        self,
        product_name: str,
        video_type: str,
        db: Session,
        limit: int = 3,
    ):
        """检索改写时可参考的同类爆款脚本（向量优先，关键词回退）"""
        try:
            from vector_store.script_store import ScriptVectorStore
            from vector_store import get_chroma_store
            store = get_chroma_store()
            if store.is_available:
                svs = ScriptVectorStore()
                context = {"name": product_name, "category": "", "description": ""}
                results = svs.find_similar_scripts(context, video_type, db, limit=limit)
                viral_ids = [r["db_id"] for r in results if r.get("source") == "viral"]
                if viral_ids:
                    return db.query(ViralScript).filter(ViralScript.id.in_(viral_ids)).all()
        except Exception:
            pass
        return self._keyword_find_scripts(db, self._extract_keywords(product_name))

    async def rewrite(
        self,
        original_script: str,
        target_product: dict,
        video_type: str = None,
        extra_requirements: str = None,
        include_shot_design: bool = True,
        db: Session = None,
    ) -> str:
        """改写脚本"""
        if not self._ai_available_for_interface("script_rewrite"):
            raise ScriptRewriteGenerationError(
                "脚本改写失败：脚本改写模型未配置，请到 AI配置 中检查脚本改写接口后重试。",
                status_code=503,
            )

        name = target_product.get("name", "")
        category = target_product.get("category", "")
        price = target_product.get("price", 0)
        original_price = target_product.get("original_price")
        pending_fields = set(target_product.get("pending_fields") or [])
        price_text = "待更新" if "price" in pending_fields else f"{price}元"
        description = target_product.get("description", "")
        selling_points = target_product.get("selling_points", [])

        candidates = self._extract_keywords(name)

        ref_scripts = []
        if db:
            try:
                from vector_store.script_store import ScriptVectorStore
                from vector_store import get_chroma_store
                store = get_chroma_store()
                if store.is_available:
                    svs = ScriptVectorStore()
                    context = {"name": name, "category": category, "description": description}
                    results = svs.find_similar_scripts(context, video_type or "", db, limit=3)
                    viral_ids = [r["db_id"] for r in results if r.get("source") == "viral"]
                    if viral_ids:
                        ref_scripts = db.query(ViralScript).filter(ViralScript.id.in_(viral_ids)).all()
                if not ref_scripts and candidates:
                    ref_scripts = self._keyword_find_scripts(db, candidates)
            except Exception:
                if candidates:
                    ref_scripts = self._keyword_find_scripts(db, candidates)

        product_info = f"""【目标产品】
名称：{name}
品牌：法采
品类：{category}
售价：{price_text}"""
        if original_price:
            product_info += f"（原价{original_price}元）"
        if description:
            product_info += f"\n描述：{description}"

        if selling_points:
            product_info += "\n\n卖点话术："
            for sp in selling_points:
                product_info += f"\n- [{sp['type']}] {sp['content']}"

        ref_block = ""
        if ref_scripts:
            ref_block = "\n\n【同类爆款脚本参考】（学习其表达风格、画面括号和连续成稿格式）"
            for i, rs in enumerate(ref_scripts[:3], 1):
                ref_block += f"\n\n--- 参考{i}: {rs.title} ---"
                ref_block += f"\n{rs.script_content[:700]}"

        reference_structure = self._build_reference_structure(original_script)

        instructions = f"""请将以下带货脚本改写为"{name}"的版本。

{product_info}{ref_block}

【用户参考文案结构骨架】（必须逐条对应，不可重排，不可换成另一套逻辑）
{reference_structure}

改写要求：
- 必须按上面的结构骨架逐条改写：第1条对应开头，第2条接第2条，第3条接第3条，不要跳段、不要重排
- 可以把特别短的相邻两条自然合并，但不能改变原文信息出现顺序
- 同类爆款脚本只用于学习表达质感，不能替代用户参考文案的结构
- 将所有产品名、卖点、价格、规格替换为新产品信息
- 吸收原脚本的语言风格、情绪节奏和转化逻辑
- 产品卖点自然融入，不生搬硬套
- 参考同类脚本的表达方式，让脚本更接地气
- 最终只输出1条500字以内的文案，不要 Markdown、编号、标题、解释或结构分析"""

        if video_type:
            instructions += f"\n- 保持{video_type}类型脚本的特征"

        if extra_requirements:
            instructions += f"\n\n额外要求：{extra_requirements}"

        if include_shot_design:
            instructions += (
                "\n\n【输出格式要求】用户勾选“需要设计画面”："
                "输出使用“（具体画面/动作/剪辑指令）+口播文案”的连续成稿。"
                "每个关键括号里的画面信息都要写清楚主体、景别/镜头、动作或道具，"
                "例如“主播半身站在烘焙台前开场，手边摆放产品包装”“产品包装正面近景，手拿转动展示规格”。"
                "不要只写“口播画面”“产品空镜”“产品展示”这种泛标签。"
                "不要保留原文的时间戳、【开场钩子】这类段落标题或小标题。"
            )
        else:
            instructions += (
                "\n\n【输出格式覆盖】用户未勾选“需要设计画面”："
                "最终只输出一段连续自然口播文案，禁止输出任何中文括号画面说明、镜头说明、分镜标题、时间戳、换行、列表或解释。"
                "保留参考文案的信息顺序和表达节奏，但把画面括号全部转化为自然口播。"
            )

        instructions += f"\n\n【原始脚本】\n{original_script}\n\n请输出改写后的脚本："

        system_prompt = self.SYSTEM_PROMPT if include_shot_design else self.PLAIN_SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instructions},
        ]
        try:
            result = await self.ai.chat(
                messages,
                temperature=0.45,
                allow_fallback=False,
                max_tokens=2200,
                interface_key="script_rewrite",
            )
        except Exception as exc:
            raise ScriptRewriteGenerationError(
                "脚本改写失败：AI 模型调用失败，请检查 AI 配置后重试。",
                status_code=503,
            ) from exc

        if not (result or "").strip():
            raise ScriptRewriteGenerationError(
                "脚本改写失败：模型未返回有效改写脚本，请检查 AI 配置后重试。"
            )

        if include_shot_design:
            rewritten = self._cleanup_rewrite_output(result)
        else:
            rewritten = self._cleanup_plain_rewrite_output(result)
        if not rewritten.strip():
            raise ScriptRewriteGenerationError(
                "脚本改写失败：模型未返回有效改写脚本，请检查 AI 配置后重试。"
            )
        return rewritten

    def _enrich_scene_label(
        self,
        label: str,
        line: str = "",
        index: int = 0,
        product_name: str = "",
    ) -> str:
        """Expand generic material-script scene labels into shootable shot notes."""
        raw = re.sub(r"\s+", "", (label or "").strip())
        copy = (line or "").strip()
        product = product_name or "产品"
        detailed_markers = (
            "近景", "中景", "特写", "俯拍", "半身", "手部", "转动", "推近",
            "切开", "倒入", "搅拌", "挤出", "包装", "规格", "质地", "成品", "对比",
        )
        generic_labels = {
            "口播画面", "产品空镜", "产品展示", "产品细节展示", "操作演示",
            "对比展示", "价格口播", "促销信息口播", "指向小黄车口播", "场景展示",
            "痛点场景展示",
        }
        if len(raw) >= 12 and any(marker in raw for marker in detailed_markers):
            return raw

        text = raw + copy
        if raw == "口播画面" and index == 0:
            return "主播半身站在烘焙台前开场，手边摆放产品包装"
        if re.search(r"小黄车|链接|下方|详情|下单|拍下|直接拍|先囤|囤起来|活动机制|券|优惠", text):
            return "主播手指下方小黄车，引导查看详情"
        if re.search(r"价格|吊牌价|元|一盒|两盒|规格|500g|100g|克|斤", text):
            return f"{product}包装和价格牌近景，手指点出规格价格"
        if re.search(r"产品|包装|看一下|这款|法采|品牌|粉体|果酱|色素|原料|材料|粉|膏|酱", text):
            return f"{product}包装正面近景，手拿转动展示规格"
        if re.search(r"搅拌|加水|加热|煮|倒|挤|抹|切|打开|使用|操作|调味|比例", text):
            return "俯拍操作台，手部演示使用步骤和状态变化"
        if re.search(r"对比|差距|不如|普通|传统|之前|之后|翻车|稳定|不塌|不出水", text):
            return "左右对比成品状态，镜头推近突出差异"
        if re.search(r"成品|蛋糕|夹心|奶冻|慕斯|口感|切面|质地|状态|出品", text):
            return "切开成品蛋糕近景，展示夹心层次和质地"
        if raw in {"痛点场景展示", "场景展示"} or re.search(r"老板|门店|客户|开店|毕业|日常|备货", text):
            return "烘焙店操作台中景，主播结合门店场景讲解"
        if raw in generic_labels:
            fallback = [
                "主播半身站在烘焙台前开场，手边摆放产品包装",
                f"{product}包装正面近景，手拿转动展示规格",
                "俯拍操作台，手部演示使用步骤和状态变化",
                "切开成品蛋糕近景，展示夹心层次和质地",
                "左右对比成品状态，镜头推近突出差异",
                "主播手指下方小黄车，引导查看详情",
            ]
            return fallback[index % len(fallback)]
        return raw or "主播半身站在烘焙台前开场，手边摆放产品包装"

    def _enrich_scene_labels(self, text: str, product_name: str = "") -> str:
        """Post-process every full-width bracket scene label in a continuous script."""
        matches = list(re.finditer(r"（([^）]{1,60})）", text or ""))
        if not matches:
            return text

        pieces = []
        last = 0
        for idx, match in enumerate(matches):
            pieces.append(text[last:match.start()])
            next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            line = text[match.end():next_start].strip(" ，。；;、\n")
            pieces.append(
                f"（{self._enrich_scene_label(match.group(1), line, idx, product_name)}）"
            )
            last = match.end()
        pieces.append(text[last:])
        return "".join(pieces)

    def _offline_material_rewrite(
        self,
        name: str,
        category: str,
        price,
        selling_points: list[dict],
        original_script: str = "",
    ) -> str:
        """Fallback rewrite when AI is unavailable, still using material-script style."""
        price_display = str(price) if str(price).endswith("元") or str(price) == "待更新" else f"{price}元"
        point_texts = [sp.get("content", "") for sp in selling_points if sp.get("content")]
        if not point_texts:
            point_texts = [
                "品质稳定，适合烘焙门店日常使用",
                "操作方便，能减少出品翻车",
                "性价比高，适合活动期囤货",
            ]
        while len(point_texts) < 4:
            point_texts.append(point_texts[-1])

        beats = self._extract_reference_beats(original_script, limit=18)
        if beats:
            labels = [
                "主播半身站在烘焙台前开场，手边摆放产品包装",
                f"{name}包装正面近景，手拿转动展示规格",
                "俯拍操作台，手部演示使用步骤和状态变化",
                "切开成品蛋糕近景，展示夹心层次和质地",
                "左右对比成品状态，镜头推近突出差异",
                f"{name}包装和价格牌近景，手指点出规格价格",
                "烘焙店操作台中景，主播结合门店场景讲解",
                "主播手指下方小黄车，引导查看详情",
            ]
            clauses = []
            for idx, beat in enumerate(beats):
                label = labels[idx] if idx < len(labels) else self._enrich_scene_label(
                    "口播画面", beat.get("text", ""), idx, name
                )
                point = point_texts[idx % len(point_texts)]
                if idx == 0:
                    copy = f"做烘焙的老板们，如果你也有这种情况，可以看看法采这款{name}"
                elif idx == len(beats) - 1:
                    copy = f"{name}现在吊牌价{price_display}，需要的直接点下方链接看看"
                else:
                    copy = f"它的优势是{point}"
                clauses.append(f"（{label}）{copy}")
            return "，".join(clauses)

        return (
            f"（主播半身站在烘焙台前开场，手边摆放产品包装）烘焙店老板们，做{category or '烘焙'}真的别再随便选材料了，"
            f"尤其是这种天天要用、直接影响出品效果的东西。（{name}包装正面近景，手拿转动展示规格）看一下法采这款{name}，"
            f"{point_texts[0]}。（俯拍操作台，手部演示使用步骤和状态变化）实际用起来也很省心，{point_texts[1]}，"
            f"不管是门店日常出品还是活动备货都很合适。（切开成品蛋糕近景，展示夹心层次和质地）而且它的优势不是只看着好，"
            f"{point_texts[2]}。（{name}包装和价格牌近景，手指点出规格价格）现在吊牌价是{price_display}，想把出品效果和效率都提上来的，"
            f"可以趁现在先囤起来。（主播手指下方小黄车，引导查看详情）需要的烘焙姐妹直接点下方链接看看，别等用到的时候才发现没备货。"
        )

    def _cleanup_rewrite_output(self, text: str) -> str:
        """Light cleanup so AI/fallback output is closer to material-script style."""
        if not text:
            return ""

        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = re.sub(r"^\s*(改写后脚本|改写后的脚本|脚本|输出)\s*[:：]\s*", "", cleaned)
        cleaned = cleaned.replace("**", "")

        section_map = {
            "开场": "口播画面",
            "钩子": "口播画面",
            "痛点": "痛点场景展示",
            "需求": "口播画面",
            "产品": "产品空镜",
            "卖点": "产品展示",
            "展示": "产品展示",
            "对比": "对比展示",
            "场景": "场景展示",
            "促销": "促销信息口播",
            "价格": "促销信息口播",
            "促单": "指向小黄车口播",
            "CTA": "指向小黄车口播",
            "转化": "指向小黄车口播",
        }

        def convert_heading(match: re.Match) -> str:
            heading = match.group(1).strip()
            heading_no_time = re.sub(
                r"\s*\d{1,2}(?:[:：]\d{1,2})?\s*[-—~至到]\s*\d{1,2}(?:[:：]\d{1,2})?\s*[s秒]?\s*",
                "",
                heading,
            ).strip()
            for keyword, label in section_map.items():
                if keyword in heading_no_time:
                    return f"（{label}）"
            return f"（{heading_no_time or '口播画面'}）"

        cleaned = re.sub(r"^\s*【([^】\n]{1,30})】\s*", convert_heading, cleaned, flags=re.M)
        cleaned = re.sub(
            r"^\s*(?:\d{1,2}[:：]\d{2}|\d{1,2})\s*[-—~至到]\s*(?:\d{1,2}[:：]\d{2}|\d{1,2})\s*[s秒]?\s*[:：-]?\s*",
            "",
            cleaned,
            flags=re.M,
        )
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        cleaned = re.sub(r"\n(?=（)", "", cleaned)
        cleaned = re.sub(r"\n+", " ", cleaned)
        cleaned = self._enrich_scene_labels(cleaned)
        return self._limit_rewrite_text(cleaned.strip())

    def _cleanup_plain_rewrite_output(self, text: str) -> str:
        """Remove shot notes and formatting when the user only wants spoken copy."""
        if not text:
            return ""

        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.replace("**", "")
        cleaned = re.sub(r"^\s*(改写后脚本|改写后的脚本|脚本|输出)\s*[:：]\s*", "", cleaned)
        cleaned = re.sub(r"【[^】]{1,80}】", "", cleaned)
        cleaned = re.sub(
            r"^\s*(?:[-*#>]+|\d+[.、])\s*",
            "",
            cleaned,
            flags=re.M,
        )
        cleaned = re.sub(
            r"^\s*(?:\d{1,2}[:：]\d{2}(?::\d{2})?|\d{1,2})\s*[-—–到至]\s*(?:\d{1,2}[:：]\d{2}(?::\d{2})?|\d{1,2})\s*[s秒]?\s*[:：]?\s*",
            "",
            cleaned,
            flags=re.M,
        )
        cleaned = re.sub(r"^\s*\d{1,2}[:：]\d{2}(?::\d{2})?\s*", "", cleaned, flags=re.M)

        shot_keywords = (
            "镜头|画面|分镜|字幕|口播|场景|特写|手部|俯拍|近景|远景|拍摄|对准|切换|展示|"
            "主播|包装|操作台|小黄车|成品|对比|指向|推近|转动|倒入|搅拌|切开|烘焙台|手拿|定格|空镜"
        )
        cleaned = re.sub(
            rf"[（(][^（）()\n]{{0,160}}(?:{shot_keywords})[^（）()\n]{{0,160}}[）)]",
            "",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([，。！？；、])", r"\1", cleaned)
        return self._limit_rewrite_text(cleaned.strip())

    def _limit_rewrite_text(self, text: str, limit: int = 500) -> str:
        """Keep the public rewrite result to one compact copy block."""
        cleaned = (text or "").strip()
        if len(cleaned) <= limit:
            return cleaned

        cut = cleaned[:limit]
        sentence_breaks = [cut.rfind(mark) for mark in "。！？!?；;"]
        last_break = max(sentence_breaks) if sentence_breaks else -1
        if last_break >= int(limit * 0.65):
            cut = cut[:last_break + 1]
        return cut.strip()


script_rewriter = ScriptRewriter()
