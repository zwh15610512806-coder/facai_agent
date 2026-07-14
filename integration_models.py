"""Persistent control-plane models for ecommerce provider integrations."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from uuid import uuid4

from database import Base
from integrations.types import (
    AuthorizationStatus,
    ConnectionStatus,
    ConnectionType,
    CheckpointStatus,
    ExportStatus,
    JobStatus,
    JobType,
    Provider,
    ResourceType,
    SyncSource,
    SyncStatus,
    persisted_enum,
    utc_now,
)


class IntegrationAppConfig(Base):
    __tablename__ = "integration_app_configs"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            name="uq_integration_app_configs_provider",
        ),
        Index("ix_integration_app_configs_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(
        persisted_enum(Provider, name="ck_integration_app_configs_provider"),
        nullable=False,
    )
    app_id = Column(String(255), nullable=False)
    app_secret_ciphertext = Column(Text)
    app_secret_tail = Column(String(4))
    status = Column(String(32), nullable=False, default="configured")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class IntegrationAuthorization(Base):
    __tablename__ = "integration_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_subject_id",
            name="uq_integration_authorizations_provider_external_subject_id",
        ),
        UniqueConstraint(
            "id",
            "provider",
            name="uq_integration_authorizations_id_provider",
        ),
        Index("ix_integration_authorizations_status", "status"),
        Index(
            "ix_integration_authorizations_refresh_lease_expires_at",
            "refresh_lease_expires_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(
        persisted_enum(Provider, name="ck_integration_authorizations_provider"),
        nullable=False,
    )
    external_subject_id = Column(String(255), nullable=False)
    scopes = Column(JSON, nullable=False, default=list)
    access_token_ciphertext = Column(Text, nullable=False)
    access_token_tail = Column(String(4), nullable=False)
    refresh_token_ciphertext = Column(Text)
    refresh_token_tail = Column(String(4))
    access_expires_at = Column(DateTime(timezone=True))
    refresh_expires_at = Column(DateTime(timezone=True))
    refresh_lease_owner = Column(String(255))
    refresh_lease_expires_at = Column(DateTime(timezone=True))
    status = Column(
        persisted_enum(
            AuthorizationStatus,
            name="ck_integration_authorizations_status",
        ),
        nullable=False,
        default=AuthorizationStatus.ACTIVE,
    )
    last_authorized_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_refreshed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    connections = relationship(
        "IntegrationConnection",
        back_populates="authorization",
        passive_deletes=True,
    )


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "connection_type",
            "external_account_id",
            name="uq_integration_connections_provider_type_external_account",
        ),
        UniqueConstraint(
            "id",
            "provider",
            name="uq_integration_connections_id_provider",
        ),
        ForeignKeyConstraint(
            ("authorization_id", "provider"),
            (
                "integration_authorizations.id",
                "integration_authorizations.provider",
            ),
            name="fk_integration_connections_authorization_provider",
            ondelete="RESTRICT",
        ),
        Index("ix_integration_connections_authorization_id", "authorization_id"),
        Index("ix_integration_connections_provider_status", "provider", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    authorization_id = Column(Integer, nullable=False)
    provider = Column(
        persisted_enum(Provider, name="ck_integration_connections_provider"),
        nullable=False,
    )
    connection_type = Column(
        persisted_enum(
            ConnectionType,
            name="ck_integration_connections_connection_type",
        ),
        nullable=False,
    )
    external_account_id = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    status = Column(
        persisted_enum(
            ConnectionStatus,
            name="ck_integration_connections_status",
        ),
        nullable=False,
        default=ConnectionStatus.SETUP_REQUIRED,
    )
    capability_report = Column(JSON, nullable=False, default=dict)
    earliest_available_date = Column(Date)
    last_successful_sync_at = Column(DateTime(timezone=True))
    disabled_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    authorization = relationship(
        "IntegrationAuthorization",
        back_populates="connections",
        passive_deletes=True,
    )


class IntegrationOAuthState(Base):
    __tablename__ = "integration_oauth_states"
    __table_args__ = (
        UniqueConstraint(
            "state_hash",
            name="uq_integration_oauth_states_state_hash",
        ),
        CheckConstraint(
            "length(state_hash) = 64",
            name="ck_integration_oauth_states_state_hash_length",
        ),
        CheckConstraint(
            "(return_path = '/app/api-connections' "
            "OR return_path LIKE '/app/api-connections/_%') "
            "AND return_path NOT LIKE '%?%' "
            "AND return_path NOT LIKE '%#%' "
            "AND return_path NOT LIKE '%//%' "
            "AND return_path NOT LIKE '%/../%' "
            "AND return_path NOT LIKE '%/..' "
            "AND return_path NOT LIKE '%/./%' "
            "AND return_path NOT LIKE '%/.' "
            "AND replace(return_path, '\\', '') = return_path "
            "AND replace(return_path, '%', '') = return_path",
            name="ck_integration_oauth_states_return_path",
        ),
        Index("ix_integration_oauth_states_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    state_hash = Column(String(64), nullable=False)
    provider = Column(
        persisted_enum(Provider, name="ck_integration_oauth_states_provider"),
        nullable=False,
    )
    initiating_session_digest = Column(String(64), nullable=False)
    return_path = Column(String(2048), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class IntegrationSecurityAudit(Base):
    __tablename__ = "integration_security_audit"
    __table_args__ = (
        Index("ix_integration_security_audit_created_at", "created_at"),
        Index(
            "ix_integration_security_audit_provider_event_type",
            "provider",
            "event_type",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(100), nullable=False)
    outcome = Column(String(32), nullable=False)
    source_digest = Column(String(64))
    session_digest = Column(String(64))
    provider = Column(
        persisted_enum(Provider, name="ck_integration_security_audit_provider")
    )
    target_type = Column(String(100))
    target_id = Column(String(255))
    summary_code = Column(String(100), nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class IntegrationLoginThrottle(Base):
    __tablename__ = "integration_login_throttles"
    __table_args__ = (
        UniqueConstraint(
            "source_digest",
            name="uq_integration_login_throttles_source_digest",
        ),
        Index("ix_integration_login_throttles_locked_until", "locked_until"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_digest = Column(String(64), nullable=False)
    failure_count = Column(Integer, nullable=False, default=0)
    window_started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    locked_until = Column(DateTime(timezone=True))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


def _json_type():
    """Use native JSONB on PostgreSQL while preserving SQLite test compatibility."""
    return JSON().with_variant(JSONB(), "postgresql")


class IntegrationJob(Base):
    __tablename__ = "integration_jobs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_integration_jobs_dedupe_key"),
        CheckConstraint(
            "length(dedupe_key) = 64",
            name="ck_integration_jobs_dedupe_key_length",
        ),
        CheckConstraint(
            "priority >= 0",
            name="ck_integration_jobs_priority_nonnegative",
        ),
        CheckConstraint(
            "attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts",
            name="ck_integration_jobs_attempt_bounds",
        ),
        Index(
            "ix_integration_jobs_claim",
            "status",
            "available_at",
            "priority",
            "id",
        ),
        Index("ix_integration_jobs_lease_expires_at", "lease_expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(
        persisted_enum(JobType, name="ck_integration_jobs_job_type"),
        nullable=False,
    )
    dedupe_key = Column(String(64), nullable=False)
    payload = Column(_json_type(), nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=0)
    status = Column(
        persisted_enum(JobStatus, name="ck_integration_jobs_status"),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    available_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=6)
    lease_owner = Column(String(255))
    lease_expires_at = Column(DateTime(timezone=True))
    heartbeat_at = Column(DateTime(timezone=True))
    last_error_code = Column(String(100))
    last_error_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    completed_at = Column(DateTime(timezone=True))


class IntegrationWorkerHeartbeat(Base):
    __tablename__ = "integration_worker_heartbeats"
    __table_args__ = (
        UniqueConstraint(
            "worker_id",
            name="uq_integration_worker_heartbeats_worker_id",
        ),
        CheckConstraint(
            "pid > 0",
            name="ck_integration_worker_heartbeats_pid_positive",
        ),
        CheckConstraint(
            "active_job_count >= 0",
            name="ck_integration_worker_heartbeats_active_jobs_nonnegative",
        ),
        Index(
            "ix_integration_worker_heartbeats_last_seen_at",
            "last_seen_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(String(255), nullable=False)
    pid = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    active_job_count = Column(Integer, nullable=False, default=0)
    version = Column(String(100), nullable=False)


class IntegrationSyncCheckpoint(Base):
    __tablename__ = "integration_sync_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "resource_type",
            "window_start",
            "window_end",
            name="uq_integration_sync_checkpoints_connection_resource_window",
        ),
        ForeignKeyConstraint(
            ("connection_id",),
            ("integration_connections.id",),
            name="fk_integration_sync_checkpoints_connection",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="ck_integration_sync_checkpoints_window",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_integration_sync_checkpoints_attempts_nonnegative",
        ),
        Index(
            "ix_integration_sync_checkpoints_due",
            "status",
            "next_retry_at",
        ),
        Index(
            "ix_integration_sync_checkpoints_lease_expires_at",
            "lease_expires_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(Integer, nullable=False)
    resource_type = Column(
        persisted_enum(
            ResourceType,
            name="ck_integration_sync_checkpoints_resource_type",
        ),
        nullable=False,
    )
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    cursor = Column(_json_type())
    watermark_at = Column(DateTime(timezone=True))
    status = Column(
        persisted_enum(
            CheckpointStatus,
            name="ck_integration_sync_checkpoints_status",
        ),
        nullable=False,
        default=CheckpointStatus.PENDING,
    )
    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True))
    lease_owner = Column(String(255))
    lease_expires_at = Column(DateTime(timezone=True))
    heartbeat_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class IntegrationSyncRun(Base):
    __tablename__ = "integration_sync_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("checkpoint_id",),
            ("integration_sync_checkpoints.id",),
            name="fk_integration_sync_runs_checkpoint",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("parent_run_id",),
            ("integration_sync_runs.id",),
            name="fk_integration_sync_runs_parent",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="ck_integration_sync_runs_window",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 1",
            name="ck_integration_sync_runs_progress",
        ),
        CheckConstraint(
            "records_read >= 0 AND records_written >= 0 "
            "AND records_skipped >= 0 AND records_quarantined >= 0",
            name="ck_integration_sync_runs_counts_nonnegative",
        ),
        Index("ix_integration_sync_runs_checkpoint", "checkpoint_id", "started_at"),
        Index("ix_integration_sync_runs_status", "status", "started_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    checkpoint_id = Column(Integer, nullable=False)
    parent_run_id = Column(Integer)
    source = Column(
        persisted_enum(SyncSource, name="ck_integration_sync_runs_source"),
        nullable=False,
    )
    status = Column(
        persisted_enum(SyncStatus, name="ck_integration_sync_runs_status"),
        nullable=False,
        default=SyncStatus.QUEUED,
    )
    resource_type = Column(
        persisted_enum(
            ResourceType,
            name="ck_integration_sync_runs_resource_type",
        ),
        nullable=False,
    )
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    progress = Column(Numeric(20, 6), nullable=False, default=0)
    records_read = Column(Integer, nullable=False, default=0)
    records_written = Column(Integer, nullable=False, default=0)
    records_skipped = Column(Integer, nullable=False, default=0)
    records_quarantined = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    failure_code = Column(String(100))
    failure_summary = Column(Text)


class IntegrationSyncError(Base):
    __tablename__ = "integration_sync_errors"
    __table_args__ = (
        ForeignKeyConstraint(
            ("run_id",),
            ("integration_sync_runs.id",),
            name="fk_integration_sync_errors_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(external_key_hmac) = 64",
            name="ck_integration_sync_errors_external_key_hmac_length",
        ),
        Index("ix_integration_sync_errors_run_id", "run_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    external_key_hmac = Column(String(64), nullable=False)
    error_type = Column(String(100), nullable=False)
    sanitized_summary = Column(Text)
    field_errors = Column(_json_type(), nullable=False, default=list)
    retryable = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class IntegrationArchiveManifest(Base):
    __tablename__ = "integration_archive_manifests"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "page_number",
            name="uq_integration_archive_manifests_run_page",
        ),
        UniqueConstraint(
            "relative_path",
            name="uq_integration_archive_manifests_relative_path",
        ),
        ForeignKeyConstraint(
            ("run_id",),
            ("integration_sync_runs.id",),
            name="fk_integration_archive_manifests_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("connection_id", "provider"),
            ("integration_connections.id", "integration_connections.provider"),
            name="fk_integration_archive_manifests_connection_provider",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="ck_integration_archive_manifests_window",
        ),
        CheckConstraint(
            "page_number >= 0 AND record_count >= 0",
            name="ck_integration_archive_manifests_counts_nonnegative",
        ),
        CheckConstraint(
            "length(sha256) = 64",
            name="ck_integration_archive_manifests_sha256_length",
        ),
        Index("ix_integration_archive_manifests_expires_at", "expires_at"),
        Index("ix_integration_archive_manifests_connection", "connection_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=False)
    provider = Column(
        persisted_enum(
            Provider,
            name="ck_integration_archive_manifests_provider",
        ),
        nullable=False,
    )
    connection_id = Column(Integer, nullable=False)
    resource_type = Column(
        persisted_enum(
            ResourceType,
            name="ck_integration_archive_manifests_resource_type",
        ),
        nullable=False,
    )
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    relative_path = Column(String(2048), nullable=False)
    sha256 = Column(String(64), nullable=False)
    record_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))


class IntegrationExportJob(Base):
    __tablename__ = "integration_export_jobs"
    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_integration_export_jobs_public_id",
        ),
        CheckConstraint(
            "length(requester_session_digest) = 64",
            name="ck_integration_export_jobs_requester_digest_length",
        ),
        CheckConstraint(
            "format IN ('csv', 'xlsx')",
            name="ck_integration_export_jobs_format",
        ),
        CheckConstraint(
            "row_count >= 0",
            name="ck_integration_export_jobs_row_count_nonnegative",
        ),
        Index("ix_integration_export_jobs_status", "status", "created_at"),
        Index("ix_integration_export_jobs_expires_at", "expires_at"),
        Index(
            "ix_integration_export_jobs_requester_session_digest",
            "requester_session_digest",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(36), nullable=False, default=lambda: str(uuid4()))
    requester_session_digest = Column(String(64), nullable=False)
    resource_type = Column(
        persisted_enum(
            ResourceType,
            name="ck_integration_export_jobs_resource_type",
        ),
        nullable=False,
    )
    filters = Column(_json_type(), nullable=False, default=dict)
    format = Column(String(10), nullable=False)
    status = Column(
        persisted_enum(ExportStatus, name="ck_integration_export_jobs_status"),
        nullable=False,
        default=ExportStatus.QUEUED,
    )
    relative_file_path = Column(String(2048))
    row_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String(100))
    error_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)
