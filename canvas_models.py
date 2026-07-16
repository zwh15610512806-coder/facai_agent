"""Persistence models for Product Canvas projects and asset metadata."""
from __future__ import annotations

from typing import Literal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

from database import Base


OperationType = Literal["cutout", "compose", "export"]
OperationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "interrupted",
]
GenerationStatus = Literal[
    "queued",
    "running",
    "partially_failed",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "interrupted",
    "unknown",
]
AttemptStatus = Literal[
    "queued",
    "submitting",
    "polling",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "unknown",
]
ItemStatus = Literal[
    "queued",
    "running",
    "composing",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "unknown",
]


def _new_uuid() -> str:
    return str(uuid4())


class CanvasProject(Base):
    __tablename__ = "canvas_projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','archived','deleting')",
            name="ck_canvas_projects_status",
        ),
        CheckConstraint("schema_version >= 1", name="ck_canvas_projects_schema_version"),
        CheckConstraint("revision >= 1", name="ck_canvas_projects_revision"),
        Index("ix_canvas_projects_status_updated_at", "status", "updated_at"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(200), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    semantic_state = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    layout_state = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    schema_version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    revision = Column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at = Column(DateTime)


class CanvasAsset(Base):
    __tablename__ = "canvas_assets"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_canvas_assets_project_id",
        ),
        UniqueConstraint(
            "project_id",
            "relative_path",
            name="uq_canvas_assets_project_relative_path",
        ),
        ForeignKeyConstraint(
            ["project_id", "source_asset_id"],
            ["canvas_assets.project_id", "canvas_assets.id"],
            name="fk_canvas_assets_project_source_asset",
        ),
        CheckConstraint("byte_count >= 0", name="ck_canvas_assets_byte_count"),
        CheckConstraint("width >= 0", name="ck_canvas_assets_width"),
        CheckConstraint("height >= 0", name="ck_canvas_assets_height"),
        CheckConstraint(
            "asset_type IN ('composed','cutout','export','generated_background',"
            "'preview','source','working')",
            name="ck_canvas_assets_asset_type",
        ),
        Index("ix_canvas_assets_project_type", "project_id", "asset_type"),
        Index("ix_canvas_assets_source_asset_id", "source_asset_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    project_id = Column(
        String(36),
        ForeignKey("canvas_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type = Column(String(40), nullable=False)
    relative_path = Column(String(1000), nullable=False)
    original_filename = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=False)
    byte_count = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    source_asset_id = Column(String(36))
    transparency_status = Column(
        String(30),
        nullable=False,
        default="unknown",
        server_default=text("'unknown'"),
    )
    processor_version = Column(String(100))
    metadata_json = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    deleted_at = Column(DateTime)


class CanvasAssetOperation(Base):
    __tablename__ = "canvas_asset_operations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "operation_type",
            "idempotency_key",
            name="uq_canvas_asset_operations_project_type_idempotency",
        ),
        ForeignKeyConstraint(
            ["project_id", "input_asset_id"],
            ["canvas_assets.project_id", "canvas_assets.id"],
            name="fk_canvas_asset_operations_project_input_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "output_asset_id"],
            ["canvas_assets.project_id", "canvas_assets.id"],
            name="fk_canvas_asset_operations_project_output_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "operation_type IN ('compose','cutout','export')",
            name="ck_canvas_asset_operations_type",
        ),
        CheckConstraint(
            "status IN ('cancel_requested','cancelled','failed','interrupted',"
            "'queued','running','succeeded')",
            name="ck_canvas_asset_operations_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_canvas_asset_operations_attempt_count",
        ),
        Index(
            "ix_canvas_asset_operations_queue",
            "status",
            "operation_type",
            "next_attempt_at",
            "created_at",
        ),
        Index("ix_canvas_asset_operations_lease", "lease_expires_at"),
        Index(
            "ix_canvas_asset_operations_project_status",
            "project_id",
            "status",
        ),
        Index("ix_canvas_asset_operations_input_asset_id", "input_asset_id"),
        Index("ix_canvas_asset_operations_output_asset_id", "output_asset_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    project_id = Column(
        String(36),
        ForeignKey("canvas_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_type = Column(String(30), nullable=False)
    status = Column(
        String(30),
        nullable=False,
        default="queued",
        server_default=text("'queued'"),
    )
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    worker_id = Column(String(100))
    lease_expires_at = Column(DateTime)
    heartbeat_at = Column(DateTime)
    next_attempt_at = Column(DateTime, nullable=False, server_default=func.now())
    cancel_requested_at = Column(DateTime)
    input_asset_id = Column(String(36), nullable=False)
    output_asset_id = Column(String(36))
    request_snapshot_json = Column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )
    processor_version = Column(String(100))
    idempotency_key = Column(String(200), nullable=False)
    safe_error_json = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class CanvasProjectSku(Base):
    __tablename__ = "canvas_project_skus"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "sort_order",
            name="uq_canvas_project_skus_project_sort_order",
        ),
        ForeignKeyConstraint(
            ["project_id", "reference_asset_id"],
            ["canvas_assets.project_id", "canvas_assets.id"],
            name="fk_canvas_project_skus_project_reference_asset",
        ),
        CheckConstraint("sort_order >= 0", name="ck_canvas_project_skus_sort_order"),
        Index(
            "ix_canvas_project_skus_project_sort_order",
            "project_id",
            "sort_order",
        ),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    project_id = Column(
        String(36),
        ForeignKey("canvas_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reference_asset_id = Column(String(36))
    prompt = Column(Text, nullable=False, default="", server_default=text("''"))
    config_json = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    deleted_at = Column(DateTime)


class ImageProviderConnection(Base):
    __tablename__ = "image_provider_connections"
    __table_args__ = (
        CheckConstraint("config_version >= 1", name="ck_image_provider_connections_version"),
        Index("ix_image_provider_connections_enabled_name", "enabled", "name"),
        Index("ix_image_provider_connections_adapter_type", "adapter_type"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    adapter_type = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    base_url = Column(String(2048), nullable=False)
    auth_type = Column(String(50), nullable=False)
    encrypted_credential = Column(Text)
    environment_credential_ref = Column(String(200))
    credential_hint = Column(String(200))
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    config_version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageModelProfile(Base):
    __tablename__ = "image_model_profiles"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "model_id",
            name="uq_image_model_profiles_provider_model",
        ),
        CheckConstraint("config_version >= 1", name="ck_image_model_profiles_version"),
        Index("ix_image_model_profiles_provider_enabled", "provider_id", "enabled"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    provider_id = Column(
        String(36),
        ForeignKey("image_provider_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_id = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=False)
    capabilities_json = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    config_json = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    config_version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CanvasGeneration(Base):
    __tablename__ = "canvas_generations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_canvas_generations_project_idempotency",
        ),
        CheckConstraint(
            "mode IN ('advanced','complete_set')",
            name="ck_canvas_generations_mode",
        ),
        CheckConstraint(
            "status IN ('cancel_requested','cancelled','failed','interrupted','partially_failed',"
            "'queued','running','succeeded','unknown')",
            name="ck_canvas_generations_status",
        ),
        CheckConstraint("project_revision >= 1", name="ck_canvas_generations_revision"),
        CheckConstraint(
            "total_items >= 0 AND total_items <= 50 AND succeeded_items >= 0 "
            "AND failed_items >= 0 AND cancelled_items >= 0 AND unknown_items >= 0 "
            "AND succeeded_items + failed_items + cancelled_items + unknown_items <= total_items",
            name="ck_canvas_generations_totals",
        ),
        CheckConstraint(
            "storage_reservation_bytes >= 0 AND storage_reservation_remaining_bytes >= 0 "
            "AND storage_reservation_remaining_bytes <= storage_reservation_bytes",
            name="ck_canvas_generations_storage_reservation",
        ),
        Index("ix_canvas_generations_queue", "status", "created_at"),
        Index("ix_canvas_generations_lease", "lease_expires_at"),
        Index("ix_canvas_generations_project_status", "project_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    project_id = Column(
        String(36),
        ForeignKey("canvas_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode = Column(String(30), nullable=False)
    project_revision = Column(Integer, nullable=False)
    request_snapshot_json = Column(Text, nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(30), nullable=False, default="queued", server_default=text("'queued'"))
    total_items = Column(Integer, nullable=False, default=0, server_default=text("0"))
    succeeded_items = Column(Integer, nullable=False, default=0, server_default=text("0"))
    failed_items = Column(Integer, nullable=False, default=0, server_default=text("0"))
    cancelled_items = Column(Integer, nullable=False, default=0, server_default=text("0"))
    unknown_items = Column(Integer, nullable=False, default=0, server_default=text("0"))
    storage_reservation_bytes = Column(Integer, nullable=False, default=0, server_default=text("0"))
    storage_reservation_remaining_bytes = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    safe_storage_block_reason = Column(String(500))
    storage_blocked_at = Column(DateTime)
    cancel_requested_at = Column(DateTime)
    worker_id = Column(String(100))
    lease_expires_at = Column(DateTime)
    heartbeat_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class CanvasGenerationItem(Base):
    __tablename__ = "canvas_generation_items"
    __table_args__ = (
        UniqueConstraint(
            "generation_id",
            "ordinal",
            name="uq_canvas_generation_items_generation_ordinal",
        ),
        UniqueConstraint(
            "generation_id",
            "board_id",
            name="uq_canvas_generation_items_generation_board",
        ),
        CheckConstraint("ordinal >= 0", name="ck_canvas_generation_items_ordinal"),
        CheckConstraint("board_order_snapshot >= 0", name="ck_canvas_generation_items_board_order"),
        CheckConstraint("width > 0 AND height > 0", name="ck_canvas_generation_items_dimensions"),
        CheckConstraint("attempt_count >= 0", name="ck_canvas_generation_items_attempt_count"),
        CheckConstraint(
            "output_type IN ('detail','main','sku')",
            name="ck_canvas_generation_items_output_type",
        ),
        CheckConstraint(
            "status IN ('cancel_requested','cancelled','composing','failed','queued','running',"
            "'succeeded','unknown')",
            name="ck_canvas_generation_items_status",
        ),
        Index("ix_canvas_generation_items_generation_status", "generation_id", "status"),
        Index("ix_canvas_generation_items_model_profile_id", "model_profile_id"),
        Index("ix_canvas_generation_items_latest_background", "latest_background_asset_id"),
        Index("ix_canvas_generation_items_latest_composed", "latest_composed_asset_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    generation_id = Column(
        String(36),
        ForeignKey("canvas_generations.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal = Column(Integer, nullable=False)
    output_type = Column(String(40), nullable=False)
    sku_id_snapshot = Column(String(36))
    sku_name_snapshot = Column(String(200))
    board_id = Column(String(100), nullable=False)
    node_id = Column(String(100), nullable=False)
    board_order_snapshot = Column(Integer, nullable=False)
    provider_id = Column(
        String(36),
        ForeignKey("image_provider_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_config_version = Column(Integer, nullable=False)
    model_profile_id = Column(
        String(36),
        ForeignKey("image_model_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_config_version = Column(Integer, nullable=False)
    provider_config_snapshot_json = Column(Text, nullable=False)
    model_config_snapshot_json = Column(Text, nullable=False)
    prompt = Column(Text, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    ratio = Column(String(30), nullable=False)
    composition_group_id = Column(String(100))
    # ``composition_layout_hash`` is the authoritative ``sha256:`` prefix plus
    # the 64 hexadecimal digest characters (71 characters in total).
    layout_hash = Column(String(71), nullable=False)
    layout_snapshot_json = Column(Text, nullable=False)
    latest_background_asset_id = Column(
        String(36),
        ForeignKey("canvas_assets.id", ondelete="RESTRICT"),
    )
    latest_composed_asset_id = Column(
        String(36),
        ForeignKey("canvas_assets.id", ondelete="RESTRICT"),
    )
    safe_current_error_code = Column(String(100))
    safe_current_error_summary = Column(String(1000))
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    status = Column(String(30), nullable=False, default="queued", server_default=text("'queued'"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class CanvasGenerationItemInput(Base):
    __tablename__ = "canvas_generation_item_inputs"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "input_role",
            "ordinal",
            name="uq_canvas_generation_item_inputs_role_ordinal",
        ),
        CheckConstraint("ordinal >= 0", name="ck_canvas_generation_item_inputs_ordinal"),
        Index("ix_canvas_generation_item_inputs_asset_id", "asset_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    item_id = Column(
        String(36),
        ForeignKey("canvas_generation_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id = Column(
        String(36),
        ForeignKey("canvas_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    input_role = Column(String(50), nullable=False)
    ordinal = Column(Integer, nullable=False)
    asset_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CanvasGenerationAttempt(Base):
    __tablename__ = "canvas_generation_attempts"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "attempt_no",
            name="uq_canvas_generation_attempts_item_attempt",
        ),
        UniqueConstraint(
            "compose_operation_id",
            name="uq_canvas_generation_attempts_compose_operation",
        ),
        CheckConstraint("attempt_no >= 1", name="ck_canvas_generation_attempts_attempt_no"),
        CheckConstraint(
            "status IN ('cancel_requested','cancelled','failed','polling','queued','submitting',"
            "'succeeded','unknown')",
            name="ck_canvas_generation_attempts_status",
        ),
        CheckConstraint(
            "provider_result_stage IN ('awaiting_provider','receiving','background_persisted',"
            "'composing','complete')",
            name="ck_canvas_generation_attempts_result_stage",
        ),
        Index("ix_canvas_generation_attempts_queue", "status", "next_poll_at", "created_at"),
        Index("ix_canvas_generation_attempts_lease", "lease_expires_at"),
        Index(
            "ix_canvas_generation_attempts_provider_model_status",
            "provider_id",
            "model_profile_id",
            "status",
        ),
        Index("ix_canvas_generation_attempts_background_asset", "background_asset_id"),
        Index(
            "ix_canvas_generation_attempts_background_preview_asset",
            "background_preview_asset_id",
        ),
        Index("ix_canvas_generation_attempts_composed_asset", "composed_asset_id"),
        Index(
            "ix_canvas_generation_attempts_composed_preview_asset",
            "composed_preview_asset_id",
        ),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    item_id = Column(
        String(36),
        ForeignKey("canvas_generation_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_no = Column(Integer, nullable=False)
    provider_id = Column(
        String(36),
        ForeignKey("image_provider_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_config_version = Column(Integer, nullable=False)
    model_profile_id = Column(
        String(36),
        ForeignKey("image_model_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_config_version = Column(Integer, nullable=False)
    provider_config_snapshot_json = Column(Text, nullable=False)
    model_config_snapshot_json = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="queued", server_default=text("'queued'"))
    provider_result_stage = Column(
        String(40),
        nullable=False,
        default="awaiting_provider",
        server_default=text("'awaiting_provider'"),
    )
    provider_accepted_at = Column(DateTime)
    provider_request_id = Column(String(500))
    external_task_id = Column(String(500))
    upstream_idempotency_key = Column(String(200), nullable=False)
    worker_id = Column(String(100))
    lease_expires_at = Column(DateTime)
    heartbeat_at = Column(DateTime)
    next_poll_at = Column(DateTime)
    last_polled_at = Column(DateTime)
    submission_started_at = Column(DateTime)
    submitted_at = Column(DateTime)
    cancel_requested_at = Column(DateTime)
    usage_json = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    background_asset_id = Column(String(36), ForeignKey("canvas_assets.id", ondelete="RESTRICT"))
    background_preview_asset_id = Column(
        String(36),
        ForeignKey("canvas_assets.id", ondelete="RESTRICT"),
    )
    composed_asset_id = Column(String(36), ForeignKey("canvas_assets.id", ondelete="RESTRICT"))
    composed_preview_asset_id = Column(
        String(36),
        ForeignKey("canvas_assets.id", ondelete="RESTRICT"),
    )
    compose_operation_id = Column(
        String(36),
        ForeignKey("canvas_asset_operations.id", ondelete="RESTRICT"),
    )
    normalized_error_code = Column(String(100))
    safe_error_summary = Column(String(1000))
    safe_upstream_error_code = Column(String(200))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class CanvasEvent(Base):
    __tablename__ = "canvas_events"
    __table_args__ = (
        Index("ix_canvas_events_project_id", "project_id", "id"),
        Index("ix_canvas_events_operation_id", "operation_id"),
        Index("ix_canvas_events_generation_id", "generation_id"),
        Index("ix_canvas_events_item_id", "item_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        String(36),
        ForeignKey("canvas_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(100), nullable=False)
    operation_id = Column(
        String(36),
        ForeignKey("canvas_asset_operations.id", ondelete="SET NULL"),
    )
    generation_id = Column(
        String(36),
        ForeignKey("canvas_generations.id", ondelete="SET NULL"),
    )
    item_id = Column(
        String(36),
        ForeignKey("canvas_generation_items.id", ondelete="SET NULL"),
    )
    payload_json = Column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
