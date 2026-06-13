"""SQLAlchemy 数据模型"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, JSON,
    DateTime, ForeignKey, func
)
from sqlalchemy.orm import relationship
from database import Base


class Product(Base):
    """产品表"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="产品名称")
    category = Column(String(100), nullable=False, index=True, comment="品类")
    price = Column(Float, nullable=False, comment="售价")
    original_price = Column(Float, comment="原价")
    commission_rate = Column(Float, default=0.0, comment="佣金比例(%)")
    brand = Column(String(100), comment="品牌")
    description = Column(Text, comment="产品描述")
    image_url = Column(String(500), comment="产品图片URL")
    info_file = Column(String(500), comment="产品资料文件路径")
    status = Column(String(20), default="active", comment="状态: active/inactive")
    pending_fields = Column(JSON, default=list, comment="pending product fields")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    selling_points = relationship(
        "SellingPoint", back_populates="product",
        cascade="all, delete-orphan", order_by="SellingPoint.priority"
    )
    generated_scripts = relationship(
        "GeneratedScript", back_populates="product",
        cascade="all, delete-orphan"
    )


class SellingPoint(Base):
    """产品卖点话术表"""
    __tablename__ = "selling_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    point_type = Column(String(50), nullable=False, comment="卖点类型")
    content = Column(Text, nullable=False, comment="话术内容")
    priority = Column(Integer, default=0, comment="优先级")

    product = relationship("Product", back_populates="selling_points")


class ScriptTemplate(Base):
    """脚本模板表"""
    __tablename__ = "script_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="模板名称")
    video_type = Column(String(100), nullable=False, index=True, comment="视频类型")
    structure = Column(JSON, nullable=False, comment="脚本结构定义")
    hook_templates = Column(JSON, comment="黄金开头模板列表")
    cta_templates = Column(JSON, comment="转化话术模板列表")
    duration_range = Column(String(50), comment="建议时长")
    description = Column(Text, comment="模板描述")
    example_script = Column(Text, comment="示例脚本")
    created_at = Column(DateTime, server_default=func.now())


class ViralScript(Base):
    """爆款脚本库"""
    __tablename__ = "viral_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(100), index=True, comment="品类")
    video_type = Column(String(100), index=True, comment="视频类型")
    title = Column(String(300), nullable=False, comment="脚本标题")
    script_content = Column(Text, nullable=False, comment="完整脚本内容")
    performance_data = Column(JSON, comment="跑量数据")
    tags = Column(String(500), comment="标签(逗号分隔)")
    embedding_id = Column(String(200), comment="ChromaDB向量ID")
    is_high_conversion = Column(Integer, default=0, comment="是否高成交：1=是 0=否")
    created_at = Column(DateTime, server_default=func.now())


class GeneratedScript(Base):
    """生成记录表"""
    __tablename__ = "generated_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"))
    template_id = Column(Integer, ForeignKey("script_templates.id", ondelete="SET NULL"))
    script_content = Column(Text, nullable=False, comment="生成的脚本内容")
    video_type = Column(String(100), comment="视频类型")
    ai_model = Column(String(100), comment="使用的AI模型")
    is_high_conversion = Column(Integer, default=0, comment="是否高成交：1=是 0=否")
    created_at = Column(DateTime, server_default=func.now())

    product = relationship("Product", back_populates="generated_scripts")


class ReferenceScript(Base):
    """其他爆款脚本参考库（非本品牌）"""
    __tablename__ = "reference_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), comment="标题")
    video_url = Column(String(500), comment="视频链接")
    script_content = Column(Text, nullable=False, comment="脚本内容")
    video_type = Column(String(100), comment="视频类型")
    tags = Column(String(200), comment="标签")
    notes = Column(Text, comment="备注/亮点")
    is_high_conversion = Column(Integer, default=0, comment="高成交标记")
    embedding_id = Column(String(200), comment="ChromaDB向量ID")
    created_at = Column(DateTime, server_default=func.now())
