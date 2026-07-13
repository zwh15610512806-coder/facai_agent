"""Pydantic contracts for the creator-business domain."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas import StrictRequestModel


class CreatorStage(str, Enum):
    lead = "lead"
    contacted = "contacted"
    negotiating = "negotiating"
    sampled = "sampled"
    scheduled = "scheduled"
    cooperating = "cooperating"
    completed = "completed"
    paused = "paused"


class CollaborationType(str, Enum):
    short_video = "short_video"
    live = "live"
    graphic = "graphic"
    other = "other"


class CollaborationStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class AmountStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"


class SampleOrderStatus(str, Enum):
    pending_shipment = "pending_shipment"
    shipped = "shipped"
    received = "received"
    cancelled = "cancelled"


class FollowupMethod(str, Enum):
    douyin = "douyin"
    wechat = "wechat"
    phone = "phone"
    offline = "offline"
    other = "other"


class OrmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NonNullableUpdateModel(StrictRequestModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        invalid = sorted(
            field
            for field in self.non_nullable_fields
            if field in self.model_fields_set and getattr(self, field) is None
        )
        if invalid:
            raise ValueError("以下字段不能显式设为空：" + "、".join(invalid))
        return self


class BdMemberCreate(StrictRequestModel):
    name: str = Field(..., min_length=1, max_length=100)


class BdMemberUpdate(NonNullableUpdateModel):
    non_nullable_fields = frozenset({"name", "active"})
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    active: Optional[bool] = Field(None, strict=True)


class BdMemberOut(OrmOut):
    id: int
    name: str
    active: bool
    created_at: datetime
    updated_at: datetime


class CreatorCreate(StrictRequestModel):
    platform: str = Field(default="douyin", min_length=1, max_length=30)
    platform_uid: Optional[str] = Field(None, max_length=200)
    douyin_handle: Optional[str] = Field(None, max_length=200)
    nickname: str = Field(..., min_length=1, max_length=200)
    homepage_url: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = Field(None, max_length=1000)
    mcn_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    wechat_id: Optional[str] = Field(None, max_length=100)
    owner_id: Optional[int] = Field(None, gt=0, strict=True)
    stage: CreatorStage = CreatorStage.lead
    tags: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_identity(self):
        if not (self.platform_uid or self.douyin_handle):
            raise ValueError("官方达人 ID 和抖音号至少填写一项")
        return self


class CreatorUpdate(NonNullableUpdateModel):
    non_nullable_fields = frozenset({"platform", "nickname", "stage", "tags"})
    platform: Optional[str] = Field(None, min_length=1, max_length=30)
    platform_uid: Optional[str] = Field(None, max_length=200)
    douyin_handle: Optional[str] = Field(None, max_length=200)
    nickname: Optional[str] = Field(None, min_length=1, max_length=200)
    homepage_url: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = Field(None, max_length=1000)
    mcn_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    wechat_id: Optional[str] = Field(None, max_length=100)
    owner_id: Optional[int] = Field(None, gt=0, strict=True)
    stage: Optional[CreatorStage] = None
    tags: Optional[list[str]] = Field(None, max_length=100)


class CreatorPortraitUpdate(NonNullableUpdateModel):
    non_nullable_fields = frozenset(
        {
            "primary_categories",
            "content_formats",
            "audience_profile",
            "regions",
            "style_tags",
            "cooperation_preferences",
        }
    )
    primary_categories: Optional[list[str]] = Field(None, max_length=50)
    content_formats: Optional[list[str]] = Field(None, max_length=50)
    follower_count: Optional[int] = Field(None, ge=0, strict=True)
    audience_profile: Optional[dict[str, Any]] = None
    regions: Optional[list[str]] = Field(None, max_length=50)
    style_tags: Optional[list[str]] = Field(None, max_length=50)
    cooperation_preferences: Optional[list[str]] = Field(None, max_length=50)
    price_range: Optional[str] = Field(None, max_length=200)
    fit_score: Optional[int] = Field(None, ge=1, le=5, strict=True)
    risk_notes: Optional[str] = Field(None, max_length=10000)
    assessed_at: Optional[datetime] = None


class CreatorPortraitCreate(CreatorPortraitUpdate):
    primary_categories: list[str] = Field(default_factory=list, max_length=50)
    content_formats: list[str] = Field(default_factory=list, max_length=50)
    audience_profile: dict[str, Any] = Field(default_factory=dict)
    regions: list[str] = Field(default_factory=list, max_length=50)
    style_tags: list[str] = Field(default_factory=list, max_length=50)
    cooperation_preferences: list[str] = Field(default_factory=list, max_length=50)


class CreatorPortraitOut(OrmOut):
    id: int
    creator_id: int
    primary_categories: list[str] = Field(default_factory=list)
    content_formats: list[str] = Field(default_factory=list)
    follower_count: Optional[int] = None
    audience_profile: dict[str, Any] = Field(default_factory=dict)
    regions: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    cooperation_preferences: list[str] = Field(default_factory=list)
    price_range: Optional[str] = None
    fit_score: Optional[int] = None
    risk_notes: Optional[str] = None
    assessed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CreatorAddressCreate(StrictRequestModel):
    recipient_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=1, max_length=50)
    province: str = Field(..., min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    detail: str = Field(..., min_length=1, max_length=1000)
    is_default: bool = Field(default=False, strict=True)


class CreatorAddressUpdate(NonNullableUpdateModel):
    non_nullable_fields = frozenset(
        {"recipient_name", "phone", "province", "city", "detail", "is_default"}
    )
    recipient_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, min_length=1, max_length=50)
    province: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    detail: Optional[str] = Field(None, min_length=1, max_length=1000)
    is_default: Optional[bool] = Field(None, strict=True)


class CreatorAddressOut(OrmOut):
    id: int
    creator_id: int
    recipient_name: str
    phone: str
    province: str
    city: str
    district: Optional[str] = None
    detail: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CreatorAddressMaskedOut(StrictRequestModel):
    id: int
    creator_id: int
    recipient_name: str
    phone: str
    province: str
    city: str
    district: Optional[str] = None
    detail: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CreatorFollowupCreate(StrictRequestModel):
    owner_id: Optional[int] = Field(None, gt=0, strict=True)
    followed_up_at: Optional[datetime] = None
    method: FollowupMethod
    content: str = Field(..., min_length=1, max_length=20000)
    result: Optional[str] = Field(None, max_length=10000)
    next_followup_at: Optional[datetime] = None
    stage_after: Optional[CreatorStage] = None


class CreatorFollowupUpdate(NonNullableUpdateModel):
    non_nullable_fields = frozenset({"followed_up_at", "method", "content"})
    owner_id: Optional[int] = Field(None, gt=0, strict=True)
    followed_up_at: Optional[datetime] = None
    method: Optional[FollowupMethod] = None
    content: Optional[str] = Field(None, min_length=1, max_length=20000)
    result: Optional[str] = Field(None, max_length=10000)
    next_followup_at: Optional[datetime] = None
    stage_after: Optional[CreatorStage] = None


class CreatorFollowupOut(OrmOut):
    id: int
    creator_id: int
    owner_id: Optional[int] = None
    followed_up_at: datetime
    method: FollowupMethod
    content: str
    result: Optional[str] = None
    next_followup_at: Optional[datetime] = None
    stage_after: Optional[CreatorStage] = None
    created_at: datetime
    updated_at: datetime


class CollaborationProductCreate(StrictRequestModel):
    product_id: int = Field(..., gt=0, strict=True)
    note: Optional[str] = Field(None, max_length=5000)


class CollaborationProductIn(CollaborationProductCreate):
    pass


class CollaborationProductUpdate(StrictRequestModel):
    product_id: Optional[int] = Field(None, gt=0, strict=True)
    note: Optional[str] = Field(None, max_length=5000)


class CollaborationProductOut(OrmOut):
    id: int
    product_id: Optional[int] = None
    product_name_snapshot: str
    note: Optional[str] = None


class CreatorCollaborationCreate(StrictRequestModel):
    owner_id: Optional[int] = Field(None, gt=0, strict=True)
    source_type: str = Field(default="manual", min_length=1, max_length=50)
    external_record_id: Optional[str] = Field(None, max_length=200)
    internal_code: str = Field(..., min_length=1, max_length=100)
    collaboration_type: CollaborationType
    collaboration_date: date
    status: CollaborationStatus = CollaborationStatus.planned
    actual_paid_cents: int = Field(default=0, ge=0, strict=True)
    amount_status: AmountStatus = AmountStatus.pending
    notes: Optional[str] = Field(None, max_length=20000)
    products: list[CollaborationProductIn] = Field(default_factory=list, max_length=100)


class CreatorCollaborationUpdate(NonNullableUpdateModel):
    non_nullable_fields = frozenset(
        {"collaboration_type", "collaboration_date", "status", "actual_paid_cents", "amount_status"}
    )
    owner_id: Optional[int] = Field(None, gt=0, strict=True)
    collaboration_type: Optional[CollaborationType] = None
    collaboration_date: Optional[date] = None
    status: Optional[CollaborationStatus] = None
    actual_paid_cents: Optional[int] = Field(None, ge=0, strict=True)
    amount_status: Optional[AmountStatus] = None
    notes: Optional[str] = Field(None, max_length=20000)
    products: Optional[list[CollaborationProductIn]] = Field(None, max_length=100)


class CreatorCollaborationOut(OrmOut):
    id: int
    creator_id: int
    owner_id: Optional[int] = None
    source_type: str
    external_record_id: Optional[str] = None
    internal_code: str
    collaboration_type: CollaborationType
    collaboration_date: date
    status: CollaborationStatus
    actual_paid_cents: int
    amount_status: AmountStatus
    notes: Optional[str] = None
    products: list[CollaborationProductOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SampleOrderItemCreate(StrictRequestModel):
    product_id: int = Field(..., gt=0, strict=True)
    specification: Optional[str] = Field(None, max_length=300)
    quantity: int = Field(default=1, gt=0, le=10000, strict=True)
    note: Optional[str] = Field(None, max_length=5000)


class SampleOrderItemIn(SampleOrderItemCreate):
    pass


class SampleOrderItemUpdate(StrictRequestModel):
    product_id: Optional[int] = Field(None, gt=0, strict=True)
    specification: Optional[str] = Field(None, max_length=300)
    quantity: Optional[int] = Field(None, gt=0, le=10000, strict=True)
    note: Optional[str] = Field(None, max_length=5000)


class SampleOrderItemOut(OrmOut):
    id: int
    product_id: Optional[int] = None
    product_name_snapshot: str
    specification: Optional[str] = None
    quantity: int
    note: Optional[str] = None


class CreatorSampleOrderCreate(StrictRequestModel):
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    address_id: int = Field(..., gt=0, strict=True)
    collaboration_id: Optional[int] = Field(None, gt=0, strict=True)
    notes: Optional[str] = Field(None, max_length=10000)
    items: list[SampleOrderItemIn] = Field(..., min_length=1, max_length=100)


class CreatorSampleOrderUpdate(StrictRequestModel):
    status: SampleOrderStatus
    shipping_company: Optional[str] = Field(None, max_length=100)
    tracking_number: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=10000)


class CreatorSampleOrderOut(OrmOut):
    id: int
    creator_id: int
    address_id: Optional[int] = None
    collaboration_id: Optional[int] = None
    idempotency_key: str
    status: SampleOrderStatus
    recipient_name_snapshot: str
    phone_snapshot: str
    province_snapshot: str
    city_snapshot: str
    district_snapshot: Optional[str] = None
    address_detail_snapshot: str
    shipping_company: Optional[str] = None
    tracking_number: Optional[str] = None
    shipped_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    notes: Optional[str] = None
    items: list[SampleOrderItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CreatorMetrics(StrictRequestModel):
    confirmed_paid_cents: int = Field(default=0, ge=0)
    confirmed_collaboration_count: int = Field(default=0, ge=0)
    average_paid_cents: int = Field(default=0, ge=0)
    latest_collaboration_date: Optional[date] = None


class CreatorListItem(StrictRequestModel):
    id: int
    platform: str
    platform_uid: Optional[str] = None
    douyin_handle: Optional[str] = None
    nickname: str
    avatar_url: Optional[str] = None
    mcn_name: Optional[str] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    stage: CreatorStage
    tags: list[str] = Field(default_factory=list)
    follower_count: Optional[int] = None
    primary_categories: list[str] = Field(default_factory=list)
    masked_contact_phone: Optional[str] = None
    metrics: CreatorMetrics = Field(default_factory=CreatorMetrics)
    last_followup_at: Optional[datetime] = None
    next_followup_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


class CreatorDetailOut(CreatorListItem):
    homepage_url: Optional[str] = None
    contact_name: Optional[str] = None
    masked_wechat_id: Optional[str] = None
    portrait: Optional[CreatorPortraitOut] = None
    addresses: list[CreatorAddressMaskedOut] = Field(default_factory=list)
    portrait_summary: str = ""
    collaboration_count: int = 0
    followup_count: int = 0
    sample_order_count: int = 0
    created_at: datetime
    updated_at: datetime


class CreatorPageOut(StrictRequestModel):
    items: list[CreatorListItem]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    per_page: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)


class PrivateContactOut(StrictRequestModel):
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    wechat_id: Optional[str] = None
    addresses: list[CreatorAddressOut] = Field(default_factory=list)


class ImportMappingRequest(StrictRequestModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class ImportValidateRequest(ImportMappingRequest):
    token: str = Field(..., min_length=8, max_length=100)


class ImportCommitRequest(StrictRequestModel):
    token: str = Field(..., min_length=8, max_length=100)


class ImportResultOut(StrictRequestModel):
    token: str
    status: str
    row_count: int = 0
    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
