"""SQLAlchemy models for the Douyin creator-business domain."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


def normalize_platform_uid(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


def normalize_douyin_handle(value: str | None) -> str | None:
    normalized = (value or "").strip()
    while normalized.startswith("@"):
        normalized = normalized[1:].strip()
    return normalized or None


class BdMember(Base):
    __tablename__ = "bd_members"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_bd_members_name_nonblank"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class Creator(Base):
    __tablename__ = "creators"
    __table_args__ = (
        CheckConstraint(
            "(platform_uid_normalized IS NOT NULL AND length(trim(platform_uid_normalized)) > 0) "
            "OR (douyin_handle_normalized IS NOT NULL AND length(trim(douyin_handle_normalized)) > 0)",
            name="ck_creators_identity_present",
        ),
        CheckConstraint(
            "stage IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')",
            name="ck_creators_stage",
        ),
        Index(
            "uq_creators_platform_uid",
            "platform",
            "platform_uid_normalized",
            unique=True,
            sqlite_where=text("platform_uid_normalized IS NOT NULL"),
            postgresql_where=text("platform_uid_normalized IS NOT NULL"),
        ),
        Index(
            "uq_creators_douyin_handle",
            "platform",
            "douyin_handle_normalized",
            unique=True,
            sqlite_where=text("douyin_handle_normalized IS NOT NULL"),
            postgresql_where=text("douyin_handle_normalized IS NOT NULL"),
        ),
        Index("ix_creators_stage_owner_archived", "stage", "owner_id", "archived_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(30), nullable=False, default="douyin")
    platform_uid = Column(String(200))
    platform_uid_normalized = Column(String(200))
    douyin_handle = Column(String(200))
    douyin_handle_normalized = Column(String(200))
    nickname = Column(String(200), nullable=False, index=True)
    homepage_url = Column(String(1000))
    avatar_url = Column(String(1000))
    mcn_name = Column(String(200))
    contact_name = Column(String(100))
    contact_phone = Column(String(50))
    wechat_id = Column(String(100))
    owner_id = Column(Integer, ForeignKey("bd_members.id", ondelete="SET NULL"), index=True)
    stage = Column(String(30), nullable=False, default="lead", index=True)
    tags = Column(JSON, nullable=False, default=list)
    archived_at = Column(DateTime, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    owner = relationship("BdMember", foreign_keys=[owner_id])
    portrait = relationship(
        "CreatorPortrait", back_populates="creator", uselist=False, cascade="all, delete-orphan"
    )
    addresses = relationship("CreatorAddress", back_populates="creator", cascade="all, delete-orphan")
    followups = relationship("CreatorFollowup", back_populates="creator", cascade="all, delete-orphan")
    collaborations = relationship(
        "CreatorCollaboration", back_populates="creator", cascade="all, delete-orphan"
    )
    sample_orders = relationship(
        "CreatorSampleOrder", back_populates="creator", cascade="all, delete-orphan"
    )


class CreatorPortrait(Base):
    __tablename__ = "creator_portraits"
    __table_args__ = (
        CheckConstraint("follower_count IS NULL OR follower_count >= 0", name="ck_creator_portraits_followers"),
        CheckConstraint("fit_score IS NULL OR (fit_score >= 1 AND fit_score <= 5)", name="ck_creator_portraits_fit"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, unique=True)
    primary_categories = Column(JSON, nullable=False, default=list)
    content_formats = Column(JSON, nullable=False, default=list)
    follower_count = Column(Integer)
    audience_profile = Column(JSON, nullable=False, default=dict)
    regions = Column(JSON, nullable=False, default=list)
    style_tags = Column(JSON, nullable=False, default=list)
    cooperation_preferences = Column(JSON, nullable=False, default=list)
    price_range = Column(String(200))
    fit_score = Column(Integer)
    risk_notes = Column(Text)
    assessed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("Creator", back_populates="portrait")


class CreatorAddress(Base):
    __tablename__ = "creator_addresses"
    __table_args__ = (
        Index("ix_creator_addresses_creator_default", "creator_id", "is_default"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    recipient_name = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=False)
    province = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    district = Column(String(100))
    detail = Column(String(1000), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("Creator", back_populates="addresses")


class CreatorFollowup(Base):
    __tablename__ = "creator_followups"
    __table_args__ = (
        CheckConstraint(
            "method IN ('douyin','wechat','phone','offline','other')",
            name="ck_creator_followups_method",
        ),
        CheckConstraint(
            "stage_after IS NULL OR stage_after IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')",
            name="ck_creator_followups_stage_after",
        ),
        Index("ix_creator_followups_creator_time", "creator_id", "followed_up_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("bd_members.id", ondelete="SET NULL"))
    followed_up_at = Column(DateTime, nullable=False, server_default=func.now())
    method = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    result = Column(Text)
    next_followup_at = Column(DateTime)
    stage_after = Column(String(30))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("Creator", back_populates="followups")
    owner = relationship("BdMember", foreign_keys=[owner_id])


class CreatorCollaboration(Base):
    __tablename__ = "creator_collaborations"
    __table_args__ = (
        CheckConstraint("actual_paid_cents >= 0", name="ck_creator_collaborations_paid_nonnegative"),
        CheckConstraint(
            "length(trim(internal_code)) > 0",
            name="ck_creator_collaborations_internal_code_nonblank",
        ),
        CheckConstraint(
            "collaboration_type IN ('short_video','live','graphic','other')",
            name="ck_creator_collaborations_type",
        ),
        CheckConstraint(
            "status IN ('planned','in_progress','completed','cancelled')",
            name="ck_creator_collaborations_status",
        ),
        CheckConstraint(
            "amount_status IN ('pending','confirmed')",
            name="ck_creator_collaborations_amount_status",
        ),
        Index(
            "uq_creator_collaboration_external",
            "source_type",
            "external_record_id",
            unique=True,
            sqlite_where=text("external_record_id IS NOT NULL"),
            postgresql_where=text("external_record_id IS NOT NULL"),
        ),
        Index(
            "ix_creator_collaborations_creator_date_status",
            "creator_id",
            "collaboration_date",
            "status",
            "amount_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("bd_members.id", ondelete="SET NULL"))
    source_type = Column(String(50), nullable=False, default="manual")
    external_record_id = Column(String(200))
    internal_code = Column(String(100), nullable=False, unique=True)
    collaboration_type = Column(String(30), nullable=False)
    collaboration_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="planned")
    actual_paid_cents = Column(Integer, nullable=False, default=0)
    amount_status = Column(String(30), nullable=False, default="pending")
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("Creator", back_populates="collaborations")
    owner = relationship("BdMember", foreign_keys=[owner_id])
    products = relationship(
        "CreatorCollaborationProduct", back_populates="collaboration", cascade="all, delete-orphan"
    )
    sample_orders = relationship("CreatorSampleOrder", back_populates="collaboration")


class CreatorCollaborationProduct(Base):
    __tablename__ = "creator_collaboration_products"
    __table_args__ = (
        UniqueConstraint("collaboration_id", "product_id", name="uq_creator_collaboration_product"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    collaboration_id = Column(
        Integer, ForeignKey("creator_collaborations.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"))
    product_name_snapshot = Column(String(200), nullable=False)
    note = Column(Text)

    collaboration = relationship("CreatorCollaboration", back_populates="products")


class CreatorSampleOrder(Base):
    __tablename__ = "creator_sample_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_shipment','shipped','received','cancelled')",
            name="ck_creator_sample_orders_status",
        ),
        Index("ix_creator_sample_orders_creator_status", "creator_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    address_id = Column(Integer, ForeignKey("creator_addresses.id", ondelete="SET NULL"))
    collaboration_id = Column(Integer, ForeignKey("creator_collaborations.id", ondelete="SET NULL"))
    idempotency_key = Column(String(100), nullable=False, unique=True)
    request_fingerprint = Column(String(64))
    status = Column(String(30), nullable=False, default="pending_shipment")
    recipient_name_snapshot = Column(String(100), nullable=False)
    phone_snapshot = Column(String(50), nullable=False)
    province_snapshot = Column(String(100), nullable=False)
    city_snapshot = Column(String(100), nullable=False)
    district_snapshot = Column(String(100))
    address_detail_snapshot = Column(String(1000), nullable=False)
    shipping_company = Column(String(100))
    tracking_number = Column(String(200))
    shipped_at = Column(DateTime)
    received_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("Creator", back_populates="sample_orders")
    address = relationship("CreatorAddress")
    collaboration = relationship("CreatorCollaboration", back_populates="sample_orders")
    items = relationship("CreatorSampleOrderItem", back_populates="sample_order", cascade="all, delete-orphan")


class CreatorSampleOrderItem(Base):
    __tablename__ = "creator_sample_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_creator_sample_items_quantity_positive"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_order_id = Column(
        Integer, ForeignKey("creator_sample_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"))
    product_name_snapshot = Column(String(200), nullable=False)
    specification = Column(String(300))
    quantity = Column(Integer, nullable=False, default=1)
    note = Column(Text)

    sample_order = relationship("CreatorSampleOrder", back_populates="items")


class CreatorImportBatch(Base):
    __tablename__ = "creator_import_batches"
    __table_args__ = (
        Index("ix_creator_import_batch_file_lookup", "kind", "file_sha256", "status"),
        Index(
            "uq_creator_import_committed_file",
            "kind",
            "file_sha256",
            unique=True,
            sqlite_where=text("status = 'committed'"),
            postgresql_where=text("status = 'committed'"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(100), nullable=False, unique=True)
    kind = Column(String(30), nullable=False)
    source_type = Column(String(50), nullable=False)
    filename = Column(String(500), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    status = Column(String(30), nullable=False, default="previewed")
    mapping = Column(JSON, nullable=False, default=dict)
    errors = Column(JSON, nullable=False, default=list)
    row_count = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    committed_at = Column(DateTime)
