"""脚本改写服务 — 保留参考结构，并统一输出为资料脚本表格式"""
from services.ai_service import ai_service
from models import ViralScript
from sqlalchemy.orm import Session
import re


class ScriptRewriter:
    """脚本改写器：保留原参考结构，统一输出为法采资料脚本格式"""

    MATERIAL_SCRIPT_FORMAT = """【资料脚本生成文件格式要求】
输出必须参考《资料/脚本生成.xlsx》的脚本格式：
- 直接输出一条可拍摄的完整短视频脚本，不要解释、不要标题、不要 Markdown、不要编号列表。
- 用中文全角括号写画面/拍摄/剪辑指令，例如：（口播画面）（产品空镜）（展示对比）（主播拿着产品口播）。
- 括号后面直接接对应口播文案，形成连续成稿，例如：（口播画面）老板们别再乱买了，（产品空镜）看一下法采这款...
- 不要输出【开场钩子】【痛点激发】【产品卖点展示】这类段落标题。
- 不要输出 0-3s、3-10s、00:00-00:03 这类时间戳；如果原文有时间戳，只吸收节奏，不保留时间戳格式。
- 如果原文是一整段话，也要补出必要的（口播画面）（产品展示）（空镜/对比/操作演示）等括号画面指令。
- 必须保留用户参考文案的结构顺序：原文第1句对应改写第1个表达，原文第2句对应改写第2个表达，以此类推。
- 不允许用同类爆款脚本或产品资料重新生成一条全新结构；同类脚本只能参考语气和括号画面写法。
- 口播要保持资料表里的抖音烘焙带货口吻：自然、直接、有画面感，能开拍即用。"""

    SYSTEM_PROMPT = """你是法采食品店的脚本改写专家。你的任务是将一段现有带货脚本改写为法采目标产品版本。

核心要求：
1. **统一输出格式**：无论原脚本是带时间戳、分段标题，还是一整段话，输出都必须按资料脚本生成文件的格式。
2. **保留参考结构**：必须沿着用户原脚本的顺序逐句/逐段改写，不能重排、不能另起一套新结构。
3. **替换所有产品相关信息**：产品名、品类名、卖点、价格、规格全部替换为目标产品信息。
4. **补足拍摄指令**：每个关键表达前用（口播画面）（产品空镜）（展示对比）（操作演示）等中文全角括号标注画面。
5. **卖点自然融入**：新产品卖点要自然嵌入脚本，不生搬硬套。
6. **学习资料表表达方式**：只学习资料表的画面括号、口播质感和连续成稿形式，不改变用户参考文案的结构。

优先级：
用户参考文案结构 > 目标产品信息替换 > 资料脚本格式 > 同类爆款表达。任何时候都不能让同类参考脚本覆盖用户参考文案结构。

输出：直接输出改写后的完整脚本，不要任何解释说明。

""" + MATERIAL_SCRIPT_FORMAT

    def __init__(self):
        self.ai = ai_service

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
        db: Session = None,
    ) -> str:
        """改写脚本"""
        name = target_product.get("name", "")
        category = target_product.get("category", "")
        price = target_product.get("price", 0)
        original_price = target_product.get("original_price")
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
售价：{price}元"""
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
- 不管原脚本是带时间戳、分段标题，还是一整段话，输出都必须统一为资料脚本生成文件里的连续脚本格式
- 输出使用“（画面/动作/剪辑指令）+口播文案”的连续成稿，不要 Markdown、不要编号、不要解释
- 不要保留原文的时间戳、【开场钩子】这类段落标题或小标题
- 原文如果没有画面指令，要根据内容补出（口播画面）（产品空镜）（操作演示）（对比展示）等拍摄提示
- 必须按上面的结构骨架逐条改写：第1条对应开头，第2条接第2条，第3条接第3条，不要跳段、不要重排
- 可以把特别短的相邻两条自然合并进同一个画面括号，但不能改变原文信息出现顺序
- 同类爆款脚本只用于学习资料表的表达质感，不能替代用户参考文案的结构
- 将所有产品名、卖点、价格、规格替换为新产品信息
- 吸收原脚本的语言风格、情绪节奏和转化逻辑
- 产品卖点自然融入，不生搬硬套
- 参考同类脚本的表达方式，让脚本更接地气"""

        if video_type:
            instructions += f"\n- 保持{video_type}类型脚本的特征"

        if extra_requirements:
            instructions += f"\n\n额外要求：{extra_requirements}"

        instructions += f"\n\n【原始脚本】\n{original_script}\n\n请输出改写后的脚本："

        if self.ai.is_available:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": instructions},
            ]
            try:
                response = self.ai.client.chat.completions.create(
                    model=self.ai.model,
                    messages=messages,
                    temperature=0.45,
                    max_tokens=2200,
                    top_p=0.85,
                )
                result = response.choices[0].message.content
                return self._cleanup_rewrite_output(result)
            except Exception:
                return self._offline_material_rewrite(
                    name, category, price, selling_points, original_script=original_script
                )

        return self._offline_material_rewrite(
            name, category, price, selling_points, original_script=original_script
        )

    def _offline_material_rewrite(
        self,
        name: str,
        category: str,
        price: float,
        selling_points: list[dict],
        original_script: str = "",
    ) -> str:
        """Fallback rewrite when AI is unavailable, still using material-script style."""
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
                "口播画面",
                "口播画面",
                "产品空镜",
                "操作演示",
                "产品展示",
                "对比展示",
                "产品细节展示",
                "价格口播",
                "指向小黄车口播",
            ]
            clauses = []
            for idx, beat in enumerate(beats):
                label = labels[idx] if idx < len(labels) else "口播画面"
                point = point_texts[idx % len(point_texts)]
                if idx == 0:
                    copy = f"做烘焙的老板们，如果你也有这种情况，可以看看法采这款{name}"
                elif idx == len(beats) - 1:
                    copy = f"{name}现在吊牌价{price}元，需要的直接点下方链接看看"
                else:
                    copy = f"它的优势是{point}"
                clauses.append(f"（{label}）{copy}")
            return "，".join(clauses)

        return (
            f"（口播画面）烘焙店老板们，做{category or '烘焙'}真的别再随便选材料了，"
            f"尤其是这种天天要用、直接影响出品效果的东西。（产品空镜）看一下法采这款{name}，"
            f"{point_texts[0]}。（操作演示）实际用起来也很省心，{point_texts[1]}，"
            f"不管是门店日常出品还是活动备货都很合适。（产品细节展示）而且它的优势不是只看着好，"
            f"{point_texts[2]}。（价格口播）现在吊牌价是{price}元，想把出品效果和效率都提上来的，"
            f"可以趁现在先囤起来。（指向小黄车口播）需要的烘焙姐妹直接点下方链接看看，别等用到的时候才发现没备货。"
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
        return cleaned.strip()


script_rewriter = ScriptRewriter()
