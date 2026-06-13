"""模板匹配服务 — 基于产品和视频类型智能推荐最佳模板"""
from sqlalchemy.orm import Session
from models import ScriptTemplate, ViralScript
from typing import Optional, Dict, List


class TemplateMatcher:
    """智能模板匹配器"""

    # 品类 → 推荐视频类型映射
    CATEGORY_TYPE_MAP = {
        "美妆护肤": ["需求类", "痛点类", "对比类", "达人分享类"],
        "3C数码": ["对比类", "认知类", "达人分享类", "成本低"],
        "食品饮料": ["场景类", "情绪类", "成本低"],
        "家居日用": ["机制类", "成本低", "需求类"],
        "服饰配饰": ["达人分享类", "场景类", "情绪类"],
        "运动户外": ["对比类", "场景类", "认知类"],
        # 法采烘焙品类
        "烘焙调色": ["对比类", "场景类", "机制类", "认知类"],
        "烘焙装饰": ["场景类", "达人分享类", "需求类"],
        "烘焙调味": ["需求类", "对比类", "认知类"],
        "烘焙夹心": ["制作方便", "成本低", "痛点类"],
        "烘焙配件": ["机制类", "成本低", "对比类"],
    }

    @classmethod
    def recommend_types(cls, category: str) -> List[str]:
        """根据品类推荐视频类型"""
        return cls.CATEGORY_TYPE_MAP.get(category, [
            "机制类", "痛点类", "需求类"
        ])

    @classmethod
    def find_best_template(
        cls,
        category: str,
        video_type: str,
        db: Session,
    ) -> Optional[Dict]:
        """找到最匹配的脚本模板"""
        # 精确匹配
        template = db.query(ScriptTemplate).filter(
            ScriptTemplate.video_type == video_type
        ).first()

        if template:
            return {
                "id": template.id,
                "name": template.name,
                "video_type": template.video_type,
                "structure": template.structure,
                "hook_templates": template.hook_templates,
                "cta_templates": template.cta_templates,
                "example_script": template.example_script,
            }

        # 兜底：返回第一个模板
        template = db.query(ScriptTemplate).first()
        if template:
            return {
                "id": template.id,
                "name": template.name,
                "video_type": template.video_type,
                "structure": template.structure,
                "hook_templates": template.hook_templates,
                "cta_templates": template.cta_templates,
                "example_script": template.example_script,
            }

        return None
