"""脚本生成引擎 — 核心业务逻辑"""
from services.ai_service import ai_service, AIService, build_faicai_script
from models import ViralScript, ReferenceScript
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
import json
import logging

logger = logging.getLogger(__name__)


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
    }

    def __init__(self):
        self.ai = ai_service

    def get_model_name(self) -> str:
        return self.ai.get_model_name()

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

    async def generate(
        self,
        product: Dict,
        template: Optional[Dict],
        video_type: str,
        tone: str = "活泼",
        extra_requirements: Optional[str] = None,
        reference_scripts: Optional[List[Dict]] = None,
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
        # 如果 AI 不可用，直接用法采模板引擎
        if not self.ai.is_available:
            return build_faicai_script(product, tone)

        # 构建系统提示
        system_prompt = self._build_system_prompt(video_type, tone)

        # 构建用户提示
        user_prompt = self._build_user_prompt(
            product=product,
            template=template,
            video_type=video_type,
            tone=tone,
            extra_requirements=extra_requirements,
            reference_scripts=reference_scripts,
        )

        # 调用 AI
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.ai.chat(messages, temperature=0.85)
        return response.strip()

    def _build_system_prompt(self, video_type: str, tone: str) -> str:
        """构建系统提示词"""
        strategy = self.TYPE_STRATEGIES.get(
            video_type,
            self.TYPE_STRATEGIES["机制类"]
        )
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

        return f"""{ai_service.SYSTEM_PROMPT}

当前任务：
- 视频类型：{video_type}
- 创作策略：{strategy}
- 语言风格：{tone}
- 创意要求：{variation}

请严格按照上述策略创作，确保脚本具备抖音跑量能力。"""

    def _build_user_prompt(
        self,
        product: Dict,
        template: Optional[Dict],
        video_type: str,
        tone: str,
        extra_requirements: Optional[str] = None,
        reference_scripts: Optional[List[Dict]] = None,
    ) -> str:
        """构建用户提示词"""
        parts = []

        # 1. 产品信息
        parts.append("【产品信息】")
        parts.append(f"产品名称：{product.get('name', '')}")
        parts.append(f"品类：{product.get('category', '')}")
        parts.append(f"品牌：{product.get('brand', '')}")
        parts.append(f"售价：{product.get('price', 0)}元")
        if product.get("original_price"):
            parts.append(f"原价：{product.get('original_price')}元")
        if product.get("description"):
            parts.append(f"产品描述：{product.get('description')}")

        # 2. 卖点话术
        selling_points = product.get("selling_points", [])
        if selling_points:
            parts.append("\n【核心卖点话术】（按优先级排序）")
            for i, sp in enumerate(selling_points, 1):
                parts.append(f"{i}. [{sp.get('type', '')}] {sp.get('content', '')}")
        else:
            parts.append("\n【核心卖点】（请根据产品信息提炼）")

        # 3. 模板参考
        if template:
            parts.append("\n【参考模板】")
            parts.append(f"模板名称：{template.get('name', '')}")

            hooks = template.get("hook_templates", [])
            if hooks:
                parts.append(f"推荐开头钩子：{hooks[0]}")
                if len(hooks) > 1:
                    parts.append(f"备选钩子：{' | '.join(hooks[1:3])}")

            ctas = template.get("cta_templates", [])
            if ctas:
                parts.append(f"推荐CTA话术：{ctas[0]}")

            if template.get("example_script"):
                parts.append(f"\n参考示例：\n{template['example_script']}")

        # 4. 爆款参考脚本
        if reference_scripts:
            parts.append("\n【同类爆款脚本参考】")
            for i, rs in enumerate(reference_scripts[:2], 1):
                parts.append(f"\n--- 参考{i}: {rs.get('title', '')} ---")
                parts.append(rs.get("content", "")[:500])
                if rs.get("performance"):
                    perf = rs["performance"]
                    parts.append(f"(播放量:{perf.get('views','N/A')} 转化率:{perf.get('conversion','N/A')})")

        # 5. 创作要求
        parts.append(f"\n【创作要求】")
        parts.append(f"1. 视频类型：{video_type}")
        parts.append(f"2. 语言风格：{tone}")
        parts.append(f"4. 时间标记：每个段落标注时间范围（如 0-3s）")
        parts.append(f"5. 段落标记：用【钩子】【痛点】【卖点】【价格】【CTA】等标记功能")
        parts.append(f"6. 必须包含价格信息和明确的左下角下单引导")
        parts.append(f"7. 融入具体的产品卖点，不要空泛")
        parts.append(f"8. 开头3秒内必须有一个强钩子")

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
    ) -> str:
        """模板库改写模式：将匹配到的高成交脚本改写为目标产品版本

        与 generate() 的核心区别：
        1. 参考脚本是 PRIMARY 改写源，不是次要灵感
        2. 使用完整脚本内容（不截断）
        3. 使用 TEMPLATE_REWRITE_SYSTEM_PROMPT（改写专用）
        4. Prompt 指令是"改写"而非"创作"
        """
        if not self.ai.is_available:
            return build_faicai_script(product, tone)

        # 构建改写专用 Prompt
        product_name = product.get("name", "")
        product_category = product.get("category", "")
        product_price = product.get("price", 0)
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

        user_prompt = f"""你是脚本改写专家。以下是 {len(selected)} 条爆款脚本库中的高成交脚本。

你的任务：选择其中最合适的一条，**改写**为以下目标产品的带货脚本。

====================================
目标产品信息
====================================
产品名称：{product_name}
品类：{product_category}
售价：{product_price}元
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
1. 从以上 {len(selected)} 条中选出最适合改写的一条脚本进行改写
2. **替换**所有产品名、卖点、价格、规格为目标产品内容
3. **保持**原脚本的结构、段落划分、时间标注、情绪节奏
4. **保持**原脚本的语气和口语化风格（感叹号、紧迫感、姐妹称呼等）
5. 镜头指令微调适配新产品，但保留原镜头的功能时机
6. 所有品牌名统一为"法采"
7. CTA 保持原结构，根据新产品价格微调
8. 必须在开头标注你改写了第几条脚本"""

        if extra_requirements:
            user_prompt += f"\n\n【额外要求】{extra_requirements}"

        user_prompt += "\n\n请开始改写脚本："

        messages = [
            {"role": "system", "content": AIService.TEMPLATE_REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.ai.chat(messages, temperature=0.75)
        return response.strip()


# 全局单例
script_generator = ScriptGenerator()
