"""Pydantic 数据校验模型"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime


# ============ 产品相关 ============
def _normalize_pending_fields(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


class StrictRequestModel(BaseModel):
    """统一拒绝未知字段、空白文本和非有限数。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class SellingPointCreate(StrictRequestModel):
    point_type: str = Field(..., min_length=1, max_length=50, description="卖点类型")
    content: str = Field(..., min_length=1, max_length=8000, description="话术内容")
    priority: int = Field(default=0, ge=0, le=9999, description="优先级")


class SellingPointUpdate(StrictRequestModel):
    point_type: Optional[str] = Field(None, min_length=1, max_length=50, description="卖点类型")
    content: Optional[str] = Field(None, max_length=8000, description="话术内容")
    priority: Optional[int] = Field(None, ge=0, le=9999, description="优先级")


class SellingPointOut(SellingPointCreate):
    id: int
    product_id: int

    class Config:
        from_attributes = True


class ProductCreate(StrictRequestModel):
    name: str = Field(..., min_length=1, max_length=200, description="产品名称")
    category: str = Field(..., min_length=1, max_length=100, description="品类")
    price: float = Field(..., ge=0, description="售价")
    original_price: Optional[float] = Field(None, ge=0, description="原价")
    commission_rate: float = Field(default=0.0, ge=0, le=100, description="佣金比例")
    brand: Optional[str] = Field(None, max_length=100, description="品牌")
    description: Optional[str] = Field(None, max_length=20000, description="产品描述")
    image_url: Optional[str] = Field(None, max_length=500, description="图片URL")
    pending_fields: List[str] = Field(default_factory=list, max_length=32)
    selling_points: List[SellingPointCreate] = Field(default_factory=list, max_length=100)

    @field_validator("pending_fields", mode="before")
    @classmethod
    def normalize_pending_fields(cls, value):
        return _normalize_pending_fields(value)


class ProductUpdate(StrictRequestModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    price: Optional[float] = Field(None, ge=0)
    original_price: Optional[float] = Field(None, ge=0)
    commission_rate: Optional[float] = Field(None, ge=0, le=100)
    brand: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=20000)
    image_url: Optional[str] = Field(None, max_length=500)
    pending_fields: Optional[List[str]] = Field(None, max_length=32)
    status: Optional[str] = Field(None, max_length=20)

    @field_validator("pending_fields", mode="before")
    @classmethod
    def normalize_pending_fields(cls, value):
        return _normalize_pending_fields(value)


class ProductOut(BaseModel):
    id: int
    name: str
    category: str
    price: float
    original_price: Optional[float] = None
    commission_rate: float
    brand: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    info_file: Optional[str] = None
    pending_fields: List[str] = Field(default_factory=list)
    status: str
    selling_points: List[SellingPointOut] = []
    selling_point_summary: str = ""
    created_at: datetime

    @field_validator("pending_fields", mode="before")
    @classmethod
    def normalize_pending_fields(cls, value):
        return _normalize_pending_fields(value)

    class Config:
        from_attributes = True


class ProductListItem(BaseModel):
    id: int
    name: str
    category: str
    price: float
    original_price: Optional[float] = None
    commission_rate: float
    brand: Optional[str] = None
    image_url: Optional[str] = None
    info_file: Optional[str] = None
    pending_fields: List[str] = Field(default_factory=list)
    status: str
    selling_point_count: int = 0
    selling_point_summary: str = ""

    @field_validator("pending_fields", mode="before")
    @classmethod
    def normalize_pending_fields(cls, value):
        return _normalize_pending_fields(value)


class ProductPageOut(BaseModel):
    items: List[ProductListItem]
    total: int
    page: int
    per_page: int
    total_pages: int

    class Config:
        from_attributes = True


# ============ 模板相关 ============
class ScriptTemplateCreate(StrictRequestModel):
    name: str = Field(..., min_length=1, max_length=200)
    video_type: str = Field(..., min_length=1, max_length=100)
    structure: dict = Field(..., description="脚本结构定义")
    hook_templates: Optional[List[str]] = Field(default_factory=list, max_length=100)
    cta_templates: Optional[List[str]] = Field(default_factory=list, max_length=100)
    duration_range: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=20000)
    example_script: Optional[str] = Field(None, max_length=120000)


class ScriptTemplateOut(ScriptTemplateCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 爆款脚本相关 ============
class ViralScriptCreate(StrictRequestModel):
    category: str = Field(..., min_length=1, max_length=100)
    video_type: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=300)
    script_content: str = Field(..., min_length=1, max_length=120000)
    performance_data: Optional[dict] = None
    tags: Optional[str] = Field(None, max_length=500)


class ViralScriptOut(ViralScriptCreate):
    id: int
    is_high_conversion: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 脚本生成相关 ============
class ScriptGenerateRequest(StrictRequestModel):
    product_id: int = Field(..., gt=0, description="产品ID")
    template_id: Optional[int] = Field(None, gt=0, description="模板ID")
    video_type: Optional[str] = Field(None, max_length=100, description="视频类型")
    tone: str = Field(default="活泼", min_length=1, max_length=100, description="风格基调")
    extra_requirements: Optional[str] = Field(None, max_length=4000, description="额外需求")
    engine: Optional[Literal["template", "deepseek"]] = Field(default="template", description="引擎类型")


    include_shot_design: bool = Field(default=False, description="是否需要设计画面和镜头说明")


class ScriptRewriteRequest(StrictRequestModel):
    """脚本改写请求"""
    original_script: str = Field(..., min_length=1, max_length=24000, description="原始脚本")
    product_id: int = Field(..., gt=0, description="目标产品ID")
    video_type: Optional[str] = Field(None, max_length=100, description="保持的视频类型")
    extra_requirements: Optional[str] = Field(None, max_length=4000, description="额外改写要求")
    include_shot_design: bool = Field(default=False, description="是否需要设计画面和镜头说明")


class ScriptRewriteResponse(BaseModel):
    original_script: str = Field(..., description="原始脚本")
    rewritten_script: str = Field(..., description="改写后的脚本")
    product_name: str = Field(..., description="目标产品名称")


class ScriptShotMatchRequest(StrictRequestModel):
    """为现有口播文案匹配拍摄镜头"""
    product_id: int = Field(..., gt=0, description="产品ID")
    script_content: str = Field(..., min_length=1, max_length=24000, description="需要匹配画面的文案")
    script_id: Optional[int] = Field(None, gt=0, description="当前生成记录ID")

    @field_validator("script_content")
    @classmethod
    def script_content_must_not_be_blank(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("文案不能为空")
        return text


class ScriptShotMatchResponse(BaseModel):
    product_name: str = Field(..., description="产品名称")
    original_script: str = Field(..., description="原始文案")
    script_content: str = Field(..., description="匹配镜头后的脚本")


class ScriptContentBreakdownRequest(StrictRequestModel):
    """对当前生成脚本做内容、转化和拍摄拆解。"""
    script_id: int = Field(..., gt=0, description="生成记录ID")
    script_content: str = Field(..., min_length=1, max_length=24000, description="用户当前编辑后的脚本")

    @field_validator("script_content")
    @classmethod
    def script_content_must_not_be_blank(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("脚本不能为空")
        return text


class ScriptBreakdownStructureItem(BaseModel):
    stage: str
    copy_excerpt: str
    purpose: str


class ScriptBreakdownConversionTrigger(BaseModel):
    copy_excerpt: str
    reason: str


class ScriptBreakdownOptimization(BaseModel):
    issue: str
    recommendation: str


class ScriptBreakdownShotRequirement(BaseModel):
    script_segment: str
    shot_type: str
    subject_action: str
    visual_requirement: str


class ScriptContentBreakdownResponse(BaseModel):
    generation_rationale: str
    target_audience: str
    structure: List[ScriptBreakdownStructureItem]
    core_selling_points: List[str]
    conversion_triggers: List[ScriptBreakdownConversionTrigger]
    optimization_suggestions: List[ScriptBreakdownOptimization]
    shooting_notes: List[str]
    shot_requirements: List[ScriptBreakdownShotRequirement]
    source: Literal["ai", "local"]


class SeedancePromptUploadResponse(BaseModel):
    """Seedance 分镜脚本上传解析结果"""
    filename: str = Field(..., description="上传文件名")
    file_type: str = Field(..., description="文件类型")
    text: str = Field(..., description="提取出的脚本文本")
    char_count: int = Field(..., description="提取文本字数")


class SeedancePromptItem(BaseModel):
    """单条 Seedance 分镜提示词"""
    scene_number: int = Field(..., description="画面序号")
    label: str = Field(..., description="画面标签")
    prompt: str = Field(..., description="Seedance 2.0 提示词")


class SeedancePromptGenerateRequest(StrictRequestModel):
    """Seedance 分镜提示词生成请求"""
    script_content: str = Field(..., min_length=1, max_length=24000, description="脚本内容")
    requirements: Optional[str] = Field(None, max_length=2000, description="用户需求")

    @field_validator("script_content")
    @classmethod
    def script_content_must_not_be_blank(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("脚本不能为空")
        return text

    @field_validator("requirements")
    @classmethod
    def normalize_requirements(cls, value: Optional[str]) -> Optional[str]:
        text = (value or "").strip()
        return text or None


class SeedancePromptGenerateResponse(BaseModel):
    """Seedance 分镜提示词生成结果"""
    prompt_text: str = Field(..., description="完整可复制提示词")
    items: List[SeedancePromptItem] = Field(default_factory=list, description="分镜提示词列表")
    source: Literal["ai"] = Field(..., description="生成来源")


class ScriptGenerateResponse(BaseModel):
    id: int
    product_name: str
    video_type: str
    script_content: str
    created_at: datetime
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    template_reference_script: Optional[str] = None
    source_script_id: Optional[int] = None
    source_script_source: Optional[Literal["facai", "other"]] = None
    source_script_title: Optional[str] = None
    source_script_content: Optional[str] = None
    source_match_query: Optional[str] = None

    class Config:
        from_attributes = True


class ProductWriteOut(ProductOut):
    index_sync_status: Literal["synced", "pending"]


# ============ 生成历史 ============
class GeneratedScriptOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    template_reference_script: Optional[str] = None
    source_script_id: Optional[int] = None
    source_script_source: Optional[Literal["facai", "other"]] = None
    source_script_title: Optional[str] = None
    source_script_content: Optional[str] = None
    script_content: str
    video_type: Optional[str] = None
    ai_model: Optional[str] = None
    is_high_conversion: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 数据导入 ============
class ViralScriptPageOut(BaseModel):
    items: List[ViralScriptOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 24
    total_pages: int = 1

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


class GeneratedScriptPageOut(BaseModel):
    items: List[GeneratedScriptOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    total_pages: int = 1

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


class ImportResult(BaseModel):
    total: int = 0
    success: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)


# ============ 通用 ============
class ApiResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Optional[dict] = None
