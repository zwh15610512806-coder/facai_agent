"""SQLAlchemy 数据模型"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, JSON,
    DateTime, ForeignKey, UniqueConstraint, func
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


class QianchuanImportBatch(Base):
    """千川素材表现导入批次"""
    __tablename__ = "qianchuan_import_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(500), nullable=False)
    file_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    row_count = Column(Integer, default=0)
    imported_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    amount_field = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())


class QianchuanMaterialPerformance(Base):
    """千川素材表现明细"""
    __tablename__ = "qianchuan_material_performance"
    __table_args__ = (
        UniqueConstraint("batch_id", "material_id", name="uq_qianchuan_batch_material"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("qianchuan_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(String(100), nullable=False, index=True)
    material_name = Column(String(500), nullable=False, index=True)
    material_evaluation = Column(String(200))
    material_duration = Column(String(50))
    material_created_time = Column(String(50))
    material_source = Column(String(100))
    tags = Column(String(500))
    amount_field = Column(String(100))
    transaction_amount = Column(Float, default=0.0)
    order_count = Column(Integer, default=0)
    user_pay_amount = Column(Float, default=0.0)
    roi = Column(Float, default=0.0)
    impressions = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    spend = Column(Float, default=0.0)
    clicks = Column(Integer, default=0)
    cvr = Column(Float, default=0.0)
    play_3s_rate = Column(Float, default=0.0)
    play_10s_rate = Column(Float, default=0.0)
    avg_watch_seconds = Column(Float, default=0.0)
    completion_rate = Column(Float, default=0.0)
    plan_count = Column(Integer, default=0)
    product_count = Column(Integer, default=0)
    raw_data = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class QianchuanScriptBinding(Base):
    """脚本与千川素材绑定关系"""
    __tablename__ = "qianchuan_script_bindings"
    __table_args__ = (
        UniqueConstraint("script_id", "material_id", name="uq_qianchuan_script_material"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    script_id = Column(Integer, ForeignKey("viral_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(String(100), nullable=False, index=True)
    material_name = Column(String(500), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class AIInterfaceSetting(Base):
    """Per-interface AI provider/model configuration."""
    __tablename__ = "ai_interface_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    interface_key = Column(String(100), nullable=False, unique=True, index=True)
    provider = Column(String(50), nullable=False, default="deepseek")
    model = Column(String(120), nullable=False)
    max_tokens = Column(Integer, nullable=False, default=2400)
    api_key_secret = Column(Text)
    base_url_override = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AIUsageRecord(Base):
    """Token/call metadata for AI requests. Prompt and response bodies are not stored."""
    __tablename__ = "ai_usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    interface_key = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(120), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    usage_source = Column(String(20), nullable=False, default="estimated")
    latency_ms = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, index=True)
    error_summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class ProductRagQueryLog(Base):
    """Full trace for product knowledge-base RAG requests."""
    __tablename__ = "product_rag_query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False, default="")
    scope = Column(String(30), nullable=False, index=True)
    product_id = Column(Integer, index=True)
    policy = Column(JSON, default=dict)
    retrieval_mode = Column(String(120), nullable=False, default="unknown")
    hit_chunks = Column(JSON, default=list)
    final_product_ids = Column(JSON, default=list)
    excluded_product_ids = Column(JSON, default=list)
    degraded_reason = Column(Text)
    latency_ms = Column(Integer, nullable=False, default=0)
    error_summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class VectorSyncJob(Base):
    """Durable outbox for keeping SQLite business data and Chroma in sync."""

    __tablename__ = "vector_sync_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(40), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    operation = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    last_error = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime)


class JobRun(Base):
    """Persistent progress and outcome for long-running local jobs."""

    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(60), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress_current = Column(Integer, nullable=False, default=0)
    progress_total = Column(Integer, nullable=False, default=0)
    message = Column(Text)
    details = Column(JSON, default=dict)
    error_summary = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
