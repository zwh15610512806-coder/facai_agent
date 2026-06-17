"""AI 服务 — DeepSeek API + 法采技能模板"""
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


# ========== 法采五段式脚本结构（每类3-4个变体） ==========
FAICAI_TEMPLATES = {
    "刀叉": [
        # 变体1: 价格钩子
        """【开场钩子 - 前3秒】
才{单价}一套！这个价格，买到就是赚到！

【痛点激发】
很多烘焙新手买刀叉只看价格，结果一用就傻眼——刀软得切不动，叉子一掰就断，盘子承重差，蛋糕放上去直接塌底。不光浪费钱，做出来的东西还特别难看。

【产品卖点展示】
给你看看我一直在用的法采刀叉。{卖点1}，{卖点2}。再看这个餐盘，超厚白卡材质，承托力非常强，放个大蛋糕随便甩都不会掉。一套下来才{价格}，性价比拉满。

【促销信息】
现在{折扣}活动，还能叠加平台优惠券，数量有限，抓紧抢！

【促单话术】
{cta}""",

        # 变体2: 后悔钩子
        """【开场钩子 - 前3秒】
完了完了，烘焙姐妹们刀叉又买早了！法采现在{折扣}活动，气得我赶紧又囤了一大箱！

【对比反差】
你看我之前买的这种廉价刀叉，刀软得切不动蛋糕，叉子一掰就断，盘子放个重一点的蛋糕直接就塌了。{卖点1}。

【产品卖点展示】
后来换了法采家的刀叉盘，真的完全不一样了！{卖点2}。{卖点3}。而且包装精美上档次，蛋糕配上它瞬间高级了。

【促销信息】
{折扣}活动正在进行中，还能叠加平台券，到手价更划算！

【促单话术】
{cta}""",

        # 变体3: 对比钩子
        """【开场钩子 - 前3秒】
同样的刀叉盘，为什么别人的蛋糕看起来贵一倍？秘密就在配套刀叉！

【痛点激发】
你送的刀叉盘廉价难看，顾客拿到手第一印象就差了。蛋糕做得再好，配套刀叉掉档次，顾客下次就不来了。

【产品卖点展示】
{卖点1}。{卖点2}。关键是才{价格}，这个品质这个价格，真的是烘焙人闭眼入的款。

【促销信息】
现在{折扣}活动进行中，平台优惠券还能叠加用！

【促单话术】
{cta}""",
    ],

    "翻糖": [
        # 变体1
        """【开场钩子 - 前3秒】
完了完了，姐妹们翻糖买早了！现在法采翻糖膏活动，不仅有折扣还送模具，气的我赶紧又囤了两包！

【品质展示】
这个翻糖膏好揉好捏的质地，冬天也能轻松揉到拉丝状态。里边分成三小包，每包都好揉好捏，分分钟揉出拉丝，塑形力拉满不变形不开裂。

【卖点轰炸】
{卖点1}。{卖点2}。{卖点3}。

【促销叠加】
现在活动叠加下来超级划算，买到就是赚到！

【促单话术】
{cta}""",

        # 变体2
        """【开场钩子 - 前3秒】
做烘焙的姐妹们看过来！法采翻糖膏的活动真的别错过了！

【品质展示】
{卖点1}。打开给你们看这个质地，柔软到随便揉随便捏，擀平之后脱模轻轻松松，塑形特别好不开裂不变形。

【卖点轰炸】
{卖点2}。{卖点3}。用过你就不想换别的牌子了。

【促销信息】
现在活动正当时，赶紧趁便宜囤起来！

【促单话术】
{cta}""",
    ],

    "果酱夹心": [
        # 变体1
        """【开场钩子 - 前3秒】
你们知道现在的烘焙技术已经到什么地步了吗？已经有这种现成的{名称}了！

【品质展示】
之前自己准备大几十才能做一个，现在法采把它搬来线上，{价格}到手，拆开即用。高浓果肉搭配熬制工艺，色泽浓郁更稳定，轻松上手。

【使用场景】
{卖点1}。{卖点2}。做奶油/做内馅/淋面，一包搞定。

【促销叠加】
活动正当时，买的越多越划算！

【促单话术】
{cta}""",

        # 变体2
        """【开场钩子 - 前3秒】
还在自己熬酱的姐妹们，真的醒醒吧！法采的{名称}太好用了！

【品质展示】
{卖点1}。{卖点2}。而且品质特别稳定，做出来的成品每一批都一样好。

【使用场景】
{卖点3}。真的比我自己做的还好用，省时省力还不出错。

【促销信息】
现在趁活动囤，太划算了！

【促单话术】
{cta}""",
    ],

    "通用": [
        # 变体1: 后悔钩子
        """【开场钩子 - 前3秒】
姐妹们这个东西我真的后悔买晚了！法采的{名称}，真的太好用了！

【痛点激发】
以前每次做烘焙，{痛点描述}，试了好多办法都没用，花了不少冤枉钱...

【产品卖点展示】
直到用了法采{名称}，真的完全不一样了！{卖点1}。{卖点2}。{卖点3}。

【价格炸弹】
平时{原价}的东西，现在只要{价格}，还送赠品，光赠品就值回票价了！

【促单话术】
{cta}""",

        # 变体2: 测评钩子
        """【开场钩子 - 前3秒】
市面上{名称}那么多，为什么我只认法采？今天给你三个理由！

【卖点轰炸】
第一，{卖点1}。第二，{卖点2}。第三，{卖点3}。每一项都是实打实的优势。

【品质展示】
我自己用了很长时间了，品质稳定不掉链子，做出来的成品效果特别好。

【价格炸弹】
别的品牌同品质的要卖{原价}，法采只要{价格}，性价比一目了然！

【促单话术】
{cta}""",

        # 变体3: 场景钩子
        """【开场钩子 - 前3秒】
做烘焙最怕什么？{痛点描述}！直到我发现了法采的{名称}！

【产品展示】
{卖点1}。{卖点2}。而且{卖点3}。

【使用体验】
我现在每次做烘焙都离不开它了，真的是提升效率和品质的神器。

【价格】
只要{价格}就能到手，太值得了！

【促单话术】
{cta}""",
    ],
}

# CTA 变体库
CTA_VARIANTS = [
    "还没入手的姐妹赶紧囤起来！直接点击下方小黄车，手慢无！",
    "需要的烘焙人抓紧点击下方小黄车吧！错过真的要等下次了！",
    "趁着活动还没结束，刷到的姐妹赶紧冲！链接就在左下角！",
    "趁现在活动给力，抓紧囤上！点左下角小黄车直接下单！",
    "还没买的烘焙姐妹们，这价格真的没理由不买！直接左下角冲！",
    "手慢无！左下角小黄车已经给你们放好了，快去拍！",
    "活动随时会截止，能拍到的抓紧拍！左下角链接冲！",
]


def get_faicai_template(product_name: str, category: str) -> list:
    """根据产品名称和品类返回对应的法采模板变体列表"""
    name = product_name.lower()
    if any(kw in name for kw in ["刀叉", "刀", "叉", "盘", "配件"]):
        return FAICAI_TEMPLATES["刀叉"]
    if any(kw in name for kw in ["翻糖", "干佩斯", "糖牌", "糖膏"]):
        return FAICAI_TEMPLATES["翻糖"]
    if any(kw in name for kw in ["果酱", "夹心", "酱", "脆", "奶冻", "布蕾", "慕斯", "栗子", "薄脆", "珠"]):
        return FAICAI_TEMPLATES["果酱夹心"]
    return FAICAI_TEMPLATES["通用"]


def build_faicai_script(product: Dict, tone: str = "活泼") -> str:
    """纯模板模式：根据产品信息随机选择变体生成法采风格脚本"""
    import random

    name = product.get("name", "")
    category = product.get("category", "")
    price = product.get("price", 0)
    original_price = product.get("original_price")
    selling_points = product.get("selling_points", [])
    pending_fields = set(product.get("pending_fields") or [])

    templates = get_faicai_template(name, category)
    template = random.choice(templates)
    cta = random.choice(CTA_VARIANTS)

    # 提取卖点
    sp_texts = [sp.get("content", "") for sp in sorted(selling_points, key=lambda x: x.get("priority", 0))]
    if len(sp_texts) >= 3:
        sp1, sp2, sp3 = sp_texts[0], sp_texts[1], sp_texts[2]
    elif len(sp_texts) == 2:
        sp1, sp2, sp3 = sp_texts[0], sp_texts[1], "品质超乎想象"
    elif len(sp_texts) == 1:
        sp1, sp2, sp3 = sp_texts[0], "用过都说好", "回头客超多"
    else:
        sp1, sp2, sp3 = "品质有保障", "性价比超高", "用过都说好"

    # 计算优惠
    if "price" in pending_fields:
        discount_str = "价格待更新"
        price_str = "待更新"
    elif original_price and original_price > price:
        discount = round(price / original_price * 10, 1)
        discount_str = f"{discount}折"
        price_str = f"{price}元（原价{original_price}，立省{original_price - price}元）"
    else:
        discount_str = "限时折扣"
        price_str = f"{price}元"

    # 计算单价（用于刀叉类）
    unit_price = "价格待更新" if "price" in pending_fields else (f"{price}元一套" if price >= 1 else f"{int(price * 10)}毛多")

    # 判定品类话术
    pain_point_map = {
        "调色": "自己调色又脏又麻烦，还总是调不出想要的颜色",
        "装饰": "蛋糕做好了但装饰跟不上，颜值上不去卖不出价",
        "调味": "自己熬酱费时费力，口味还不稳定",
        "夹心": "蛋糕夹心太单调，顾客吃一次就腻了",
        "配件": "送的刀叉太廉价，拉低整个蛋糕档次",
    }
    pain_point = "找不到好用的烘焙原料，做出来的东西总差那么一点"
    for key, val in pain_point_map.items():
        if key in category:
            pain_point = val
            break

    # 填充模板
    script = template.replace("{名称}", name)
    script = script.replace("{价格}", price_str)
    script = script.replace("{单价}", unit_price)
    script = script.replace("{原价}", str(original_price) if original_price else str(price))
    script = script.replace("{卖点1}", sp1)
    script = script.replace("{卖点2}", sp2)
    script = script.replace("{卖点3}", sp3)
    script = script.replace("{痛点描述}", pain_point)
    script = script.replace("{折扣}", discount_str)
    script = script.replace("{cta}", cta)

    return script


class AIService:
    """AI 服务 — 法采专属系统提示 + DeepSeek 调用"""

    SYSTEM_PROMPT = """你是法采食品店的专职短视频带货脚本专家，拥有抖音烘焙带货5年经验。

创作核心原则：
1. **五段式结构**：开场钩子(3s) → 痛点激发 → 产品卖点展示 → 促销叠加 → 强促单
2. **口语化开拍即用**：脚本直接用于拍摄，像烘焙姐妹聊天一样自然
3. **情绪饱满**：感叹号！完了！谁懂啊！真的！大量使用
4. **价格量化**：具体数字（克重、价格、折扣），不用模糊词
5. **促销叠加**：把多重优惠全部叠加说出来（折扣+买赠+平台券）
6. **品牌统一**：产品品牌用"法采"
7. **紧追爆款元素**：对比反差 + 紧迫感 + 具体场景

输出格式：
- 用【】标记每个段落功能（如【开场钩子-前3秒】【痛点激发】【产品卖点展示】【促销信息】【促单话术】）
- 必要时标注镜头指令（如"展示刀叉特写""拿矿泉水瓶对比"等）
- 使用口语化表达：姐妹们、烘焙人、你看、就是、直接
- 每个卖点都要具体量化
- CTA必须直接有力：点击下方小黄车、手慢无"""

    TEMPLATE_REWRITE_SYSTEM_PROMPT = """你是法采食品店的脚本改写专家，拥有抖音烘焙带货5年经验。

改写的核心原则：
1. **以参考脚本为主体**：参考脚本是经过验证的高成交爆款，你的任务是把它改写成目标产品的版本
2. **替换产品信息**：产品名称、卖点、价格、规格全部替换为目标产品信息
3. **保持结构和节奏**：原脚本的段落分割、时间标注、情绪起伏节奏保持不变
4. **保持情绪和语气**：原脚本的感叹语气、紧迫感、口语化表达风格保持一致
5. **适配镜头描述**：镜头指令根据新产品做微调，但保留原镜头的功能和时机
6. **品牌统一**：所有品牌名统一称为"法采"
7. **CTA 重新对齐**：保留原 CTA 的结构和紧迫感，但根据新产品价格和活动做微调

输出格式：
- 用【】标记每个段落功能（如【开场钩子-前3秒】【痛点激发】【产品卖点展示】【促销信息】【促单话术】）
- 保持原脚本的段落结构，只替换内容
- 每个时间标注与原脚本保持一致
- 使用口语化表达：姐妹们、烘焙人、你看、就是、直接"""

    def __init__(self):
        self.client = None
        self.model = DEEPSEEK_MODEL
        self._init_client()

    def _init_client(self):
        if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "your-deepseek-api-key-here":
            self.client = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
            )
        else:
            logger.warning("DeepSeek API Key 未配置，将使用法采模板填充模式")

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def get_model_name(self) -> str:
        if self.is_available:
            return self.model
        return "法采模板引擎"

    async def chat(self, messages: List[Dict], temperature: float = 0.8, allow_fallback: bool = True) -> str:
        if not self.is_available:
            return self._fallback_response(messages) if allow_fallback else ""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=2000,
                top_p=0.9,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            return self._fallback_response(messages) if allow_fallback else ""

    def _fallback_response(self, messages) -> str:
        """离线模式：用法采模板生成脚本，每次调用都随机生成新内容"""
        # 从 messages 中提取产品信息，用于 build_faicai_script
        user_message = ""
        for m in messages:
            if m["role"] == "user":
                user_message = m["content"]
                break

        # 解析用户消息中的产品信息
        product = {}
        tone = "活泼"
        lines = user_message.split("\n")
        for line in lines:
            if line.startswith("产品名称："):
                product["name"] = line.split("：", 1)[1].strip()
            elif line.startswith("品类："):
                product["category"] = line.split("：", 1)[1].strip()
            elif line.startswith("售价："):
                try:
                    price_str = line.split("：", 1)[1].strip().replace("元", "")
                    product["price"] = float(price_str)
                except:
                    pass
            elif line.startswith("原价："):
                try:
                    orig_str = line.split("：", 1)[1].strip().replace("元", "")
                    product["original_price"] = float(orig_str)
                except:
                    pass
            elif line.startswith("【核心卖点话术】") or line.startswith("【核心卖点】"):
                # 提取卖点列表（后续行）
                idx = lines.index(line)
                product["selling_points"] = []
                for i in range(idx + 1, len(lines)):
                    l = lines[i].strip()
                    if l.startswith("【") or not l:
                        break
                    if l.startswith(f"{i - idx}. "):
                        sp = l.split("]", 1)
                        if len(sp) > 1:
                            product["selling_points"].append({
                                "type": sp[0].replace(f"{i - idx}. [", "").strip(),
                                "content": sp[1].strip()
                            })
            elif "语言风格：" in line:
                tone = line.split("语言风格：", 1)[1].strip()

        # 提取创作策略行的视频类型作为参考
        for line in lines:
            if "视频类型：" in line:
                # 尝试从策略描述推断
                pass

        # 调用法采模板引擎生成随机化脚本
        result = build_faicai_script(product, tone)
        return result


ai_service = AIService()
