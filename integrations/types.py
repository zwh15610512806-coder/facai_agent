"""Provider-neutral ecommerce connector types and persisted enum helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, TypeAlias

import sqlalchemy

from integrations.redaction import assert_payload_safe


JsonScalar: TypeAlias = None | bool | int | float | Decimal | str | date | datetime
JsonValue: TypeAlias = (
    JsonScalar
    | list["JsonValue"]
    | tuple["JsonValue", ...]
    | Mapping[str, "JsonValue"]
)


class Provider(str, Enum):
    QIANCHUAN = "qianchuan"
    DOUDIAN = "doudian"
    TAOBAO = "taobao"
    PDD = "pdd"


class ConnectionStatus(str, Enum):
    SETUP_REQUIRED = "setup_required"
    AUTHORIZING = "authorizing"
    ACTIVE = "active"
    PERMISSION_LIMITED = "permission_limited"
    SYNCING = "syncing"
    DEGRADED = "degraded"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    DISABLED = "disabled"


class ConnectionType(str, Enum):
    SHOP = "shop"
    AD_ACCOUNT = "ad_account"


class AuthorizationStatus(str, Enum):
    ACTIVE = "active"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    REVOKED = "revoked"
    DISABLED = "disabled"


class EventIdScope(str, Enum):
    PROVIDER = "provider"
    SUBJECT = "subject"


class EventRoutingStatus(str, Enum):
    PENDING = "pending"
    ROUTED = "routed"
    UNROUTABLE_SUBJECT = "unroutable_subject"
    AMBIGUOUS_SUBJECT = "ambiguous_subject"


class EventProcessingStatus(str, Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    IGNORED = "ignored"


class ResourceType(str, Enum):
    SHOPS = "shops"
    PRODUCTS = "products"
    SKUS = "skus"
    INVENTORY = "inventory"
    ORDERS = "orders"
    ORDER_ITEMS = "order_items"
    REFUNDS = "refunds"
    SHIPMENTS = "shipments"
    SETTLEMENTS = "settlements"
    DAILY_METRICS = "daily_metrics"
    AD_ACCOUNTS = "ad_accounts"
    AD_ENTITIES = "ad_entities"
    AD_DAILY_METRICS = "ad_daily_metrics"
    AD_BALANCE_SNAPSHOTS = "ad_balance_snapshots"
    AD_FINANCE_TRANSACTIONS = "ad_finance_transactions"


class SyncSource(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    EVENT = "event"
    BACKFILL = "backfill"
    RETRY = "retry"


class SyncStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    SYNC_RESOURCE = "sync_resource"
    REFRESH_AUTHORIZATION = "refresh_authorization"
    PROCESS_EVENT = "process_event"
    ARCHIVE_CLEANUP = "archive_cleanup"
    EXPORT = "export"
    PURGE_CONNECTION = "purge_connection"


class JobStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckpointStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETE = "complete"
    FAILED = "failed"


class CapabilityStage(str, Enum):
    DOCS_VERIFIED = "docs_verified"
    OAUTH_VERIFIED = "oauth_verified"
    BACKFILL_VERIFIED = "backfill_verified"
    INCREMENTAL_VERIFIED = "incremental_verified"
    RECONCILED = "reconciled"


class ExportStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CLOSED = "closed"


class ProductStatus(str, Enum):
    UNKNOWN = "unknown"
    ON_SALE = "on_sale"
    OFF_SHELF = "off_shelf"
    DELETED = "deleted"


class AccountStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    INACTIVE = "inactive"
    CLOSED = "closed"


class RefundStatus(str, Enum):
    UNKNOWN = "unknown"
    REQUESTED = "requested"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CLOSED = "closed"


class ShipmentStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class SettlementStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SETTLED = "settled"
    REVERSED = "reversed"


class FinanceTransactionStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class AdEntityStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    DELETED = "deleted"


class AdEntityType(str, Enum):
    ACCOUNT = "account"
    CAMPAIGN = "campaign"
    AD_GROUP = "ad_group"
    CREATIVE = "creative"
    MATERIAL = "material"


class MetricGranularity(str, Enum):
    DAY = "day"


CONNECTION_STATUS_TRANSITIONS = {
    ConnectionStatus.SETUP_REQUIRED: frozenset(
        {ConnectionStatus.AUTHORIZING, ConnectionStatus.DISABLED}
    ),
    ConnectionStatus.AUTHORIZING: frozenset(
        {
            ConnectionStatus.ACTIVE,
            ConnectionStatus.PERMISSION_LIMITED,
            ConnectionStatus.REAUTHORIZATION_REQUIRED,
            ConnectionStatus.DISABLED,
        }
    ),
    ConnectionStatus.ACTIVE: frozenset(
        {
            ConnectionStatus.SYNCING,
            ConnectionStatus.PERMISSION_LIMITED,
            ConnectionStatus.DEGRADED,
            ConnectionStatus.REAUTHORIZATION_REQUIRED,
            ConnectionStatus.DISABLED,
        }
    ),
    ConnectionStatus.SYNCING: frozenset(
        {
            ConnectionStatus.ACTIVE,
            ConnectionStatus.PERMISSION_LIMITED,
            ConnectionStatus.DEGRADED,
            ConnectionStatus.REAUTHORIZATION_REQUIRED,
            ConnectionStatus.DISABLED,
        }
    ),
    ConnectionStatus.PERMISSION_LIMITED: frozenset(
        {
            ConnectionStatus.AUTHORIZING,
            ConnectionStatus.ACTIVE,
            ConnectionStatus.DEGRADED,
            ConnectionStatus.REAUTHORIZATION_REQUIRED,
            ConnectionStatus.DISABLED,
        }
    ),
    ConnectionStatus.DEGRADED: frozenset(
        {
            ConnectionStatus.AUTHORIZING,
            ConnectionStatus.ACTIVE,
            ConnectionStatus.PERMISSION_LIMITED,
            ConnectionStatus.REAUTHORIZATION_REQUIRED,
            ConnectionStatus.DISABLED,
        }
    ),
    ConnectionStatus.REAUTHORIZATION_REQUIRED: frozenset(
        {ConnectionStatus.AUTHORIZING, ConnectionStatus.DISABLED}
    ),
    ConnectionStatus.DISABLED: frozenset(),
}

AUTHORIZATION_STATUS_TRANSITIONS = {
    AuthorizationStatus.ACTIVE: frozenset(
        {
            AuthorizationStatus.REAUTHORIZATION_REQUIRED,
            AuthorizationStatus.REVOKED,
            AuthorizationStatus.DISABLED,
        }
    ),
    AuthorizationStatus.REAUTHORIZATION_REQUIRED: frozenset(
        {
            AuthorizationStatus.ACTIVE,
            AuthorizationStatus.REVOKED,
            AuthorizationStatus.DISABLED,
        }
    ),
    AuthorizationStatus.REVOKED: frozenset(),
    AuthorizationStatus.DISABLED: frozenset(),
}

CHECKPOINT_STATUS_TRANSITIONS = {
    CheckpointStatus.PENDING: frozenset({CheckpointStatus.RUNNING}),
    CheckpointStatus.RUNNING: frozenset(
        {
            CheckpointStatus.COMPLETE,
            CheckpointStatus.RETRY_WAIT,
            CheckpointStatus.FAILED,
        }
    ),
    CheckpointStatus.RETRY_WAIT: frozenset(
        {CheckpointStatus.RUNNING, CheckpointStatus.FAILED}
    ),
    CheckpointStatus.COMPLETE: frozenset(),
    CheckpointStatus.FAILED: frozenset(),
}

SYNC_STATUS_TRANSITIONS = {
    SyncStatus.QUEUED: frozenset({SyncStatus.RUNNING, SyncStatus.CANCELLED}),
    SyncStatus.RUNNING: frozenset(
        {
            SyncStatus.SUCCEEDED,
            SyncStatus.PARTIAL_SUCCESS,
            SyncStatus.RETRY_WAIT,
            SyncStatus.FAILED,
            SyncStatus.CANCELLED,
        }
    ),
    SyncStatus.RETRY_WAIT: frozenset(
        {SyncStatus.RUNNING, SyncStatus.FAILED, SyncStatus.CANCELLED}
    ),
    SyncStatus.SUCCEEDED: frozenset(),
    SyncStatus.PARTIAL_SUCCESS: frozenset(),
    SyncStatus.FAILED: frozenset(),
    SyncStatus.CANCELLED: frozenset(),
}

JOB_STATUS_TRANSITIONS = {
    JobStatus.QUEUED: frozenset({JobStatus.LEASED, JobStatus.CANCELLED}),
    JobStatus.LEASED: frozenset({JobStatus.RUNNING, JobStatus.QUEUED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.RETRY_WAIT,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RETRY_WAIT: frozenset(
        {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.CANCELLED}
    ),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}

CAPABILITY_STAGE_TRANSITIONS = {
    CapabilityStage.DOCS_VERIFIED: frozenset({CapabilityStage.OAUTH_VERIFIED}),
    CapabilityStage.OAUTH_VERIFIED: frozenset(
        {CapabilityStage.DOCS_VERIFIED, CapabilityStage.BACKFILL_VERIFIED}
    ),
    CapabilityStage.BACKFILL_VERIFIED: frozenset(
        {CapabilityStage.DOCS_VERIFIED, CapabilityStage.INCREMENTAL_VERIFIED}
    ),
    CapabilityStage.INCREMENTAL_VERIFIED: frozenset(
        {CapabilityStage.DOCS_VERIFIED, CapabilityStage.RECONCILED}
    ),
    CapabilityStage.RECONCILED: frozenset({CapabilityStage.DOCS_VERIFIED}),
}

EXPORT_STATUS_TRANSITIONS = {
    ExportStatus.QUEUED: frozenset({ExportStatus.RUNNING, ExportStatus.FAILED}),
    ExportStatus.RUNNING: frozenset({ExportStatus.READY, ExportStatus.FAILED}),
    ExportStatus.READY: frozenset({ExportStatus.EXPIRED}),
    ExportStatus.FAILED: frozenset(),
    ExportStatus.EXPIRED: frozenset(),
}


def persisted_enum(enum_type: type[Enum], *, name: str) -> sqlalchemy.Enum:
    """Create a stable value-backed enum CHECK constraint for persisted fields."""
    return sqlalchemy.Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [item.value for item in cls],
    )


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _require_aware_datetime(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError):
        offset = None
    if value.tzinfo is None or offset is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_bounded_text(
    value: object,
    *,
    field_name: str,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed")
    if len(value) > max_length:
        raise ValueError(f"{field_name} is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field_name} contains control characters")
    return value


def _require_safe_request_id(value: object) -> str:
    request_id = _require_bounded_text(
        value,
        field_name="request_id",
        max_length=255,
    )
    if not request_id.isascii() or not request_id.isprintable():
        raise ValueError("request_id must contain printable ASCII only")
    return request_id


def _validate_json_value(
    value: object,
    *,
    field_name: str,
    depth: int = 0,
) -> None:
    if depth > 32:
        raise ValueError(f"{field_name} exceeds the nesting limit")
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} contains a non-finite number")
        return
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{field_name} contains a non-finite number")
        return
    if isinstance(value, datetime):
        _require_aware_datetime(value, field_name=field_name)
        return
    if isinstance(value, date):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(
                item,
                field_name=field_name,
                depth=depth + 1,
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} keys must be strings")
            _validate_json_value(
                item,
                field_name=field_name,
                depth=depth + 1,
            )
        return
    raise TypeError(f"{field_name} contains an unsupported value")


def _freeze_json_value(
    value: JsonValue,
    *,
    depth: int = 0,
    active_containers: set[int] | None = None,
) -> JsonValue:
    if depth > 32:
        raise ValueError("JSON value exceeds the nesting limit")
    if not isinstance(value, (Mapping, list, tuple)):
        return value

    active = set() if active_containers is None else active_containers
    identity = id(value)
    if identity in active:
        raise ValueError("JSON value must not contain cycles")
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            return MappingProxyType(
                {
                    key: _freeze_json_value(
                        item,
                        depth=depth + 1,
                        active_containers=active,
                    )
                    for key, item in value.items()
                }
            )
        return tuple(
            _freeze_json_value(
                item,
                depth=depth + 1,
                active_containers=active,
            )
            for item in value
        )
    finally:
        active.remove(identity)


def _serialization_copy(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {
            key: _serialization_copy(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_serialization_copy(item) for item in value]
    return value


def _safe_serialization_mapping(
    value: Mapping[str, JsonValue],
    *,
    field_name: str,
) -> dict[str, JsonValue]:
    _validate_json_value(value, field_name=field_name)
    assert_payload_safe(value)
    serialized = _serialization_copy(value)
    if not isinstance(serialized, dict):
        raise TypeError(f"{field_name} must serialize to an object")
    return serialized


@dataclass(frozen=True, slots=True)
class TokenBundle:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    access_expires_at: datetime | None
    refresh_expires_at: datetime | None
    scopes: tuple[str, ...]
    external_subject_id: str


@dataclass(frozen=True, slots=True)
class AccountIdentity:
    external_account_id: str
    connection_type: ConnectionType
    display_name: str


@dataclass(frozen=True, slots=True)
class Capability:
    resource: ResourceType
    stage: CapabilityStage


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    capabilities: tuple[Capability, ...]
    probed_at: datetime


@dataclass(frozen=True, slots=True)
class ConnectionContext:
    connection_id: int
    authorization_id: int
    provider: Provider
    connection_type: ConnectionType
    external_account_id: str
    tokens: TokenBundle = field(repr=False)


@dataclass(frozen=True, slots=True)
class RateLimitHint:
    remaining: int | None
    reset_at: datetime | None
    retry_after_seconds: float | None

    def __post_init__(self) -> None:
        if self.remaining is not None and (
            not isinstance(self.remaining, int)
            or isinstance(self.remaining, bool)
            or self.remaining < 0
        ):
            raise ValueError("remaining must be a non-negative integer or None")
        if self.reset_at is not None:
            _require_aware_datetime(self.reset_at, field_name="reset_at")
        if self.retry_after_seconds is not None:
            if (
                isinstance(self.retry_after_seconds, bool)
                or not isinstance(self.retry_after_seconds, (int, float))
            ):
                raise TypeError("retry_after_seconds must be numeric or None")
            if (
                not math.isfinite(self.retry_after_seconds)
                or self.retry_after_seconds < 0
            ):
                raise ValueError(
                    "retry_after_seconds must be finite and non-negative"
                )


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        start_at = _require_aware_datetime(self.start_at, field_name="start_at")
        end_at = _require_aware_datetime(self.end_at, field_name="end_at")
        if end_at <= start_at:
            raise ValueError("end_at must be later than start_at")


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    resource: ResourceType
    external_id: str
    platform_updated_at: datetime
    payload: Mapping[str, JsonValue]
    sanitized_source_payload: Mapping[str, JsonValue] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.resource, ResourceType):
            raise TypeError("resource must be a ResourceType")
        _require_bounded_text(
            self.external_id,
            field_name="external_id",
            max_length=255,
        )
        _require_aware_datetime(
            self.platform_updated_at,
            field_name="platform_updated_at",
        )
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        if not isinstance(self.sanitized_source_payload, Mapping):
            raise TypeError("sanitized_source_payload must be a mapping")
        frozen_payload = _freeze_json_value(self.payload)
        frozen_source_payload = _freeze_json_value(
            self.sanitized_source_payload
        )
        if not isinstance(frozen_payload, Mapping) or not isinstance(
            frozen_source_payload, Mapping
        ):
            raise TypeError("normalized payloads must remain mappings")
        _validate_json_value(frozen_payload, field_name="payload")
        _validate_json_value(
            frozen_source_payload,
            field_name="sanitized_source_payload",
        )
        assert_payload_safe(frozen_payload)
        assert_payload_safe(frozen_source_payload)
        object.__setattr__(self, "payload", frozen_payload)
        object.__setattr__(
            self,
            "sanitized_source_payload",
            frozen_source_payload,
        )

    def payload_for_serialization(self) -> dict[str, JsonValue]:
        """Return a detached payload after reasserting the safety boundary."""

        return _safe_serialization_mapping(
            self.payload,
            field_name="payload",
        )

    def source_payload_for_serialization(self) -> dict[str, JsonValue]:
        """Return detached sanitized source data after another safety check."""

        return _safe_serialization_mapping(
            self.sanitized_source_payload,
            field_name="sanitized_source_payload",
        )


@dataclass(frozen=True, slots=True)
class FetchPage:
    items: tuple[NormalizedRecord, ...]
    next_cursor: str | None
    has_more: bool
    request_id: str | None
    rate_limit_hint: RateLimitHint | None
    watermark: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if any(not isinstance(item, NormalizedRecord) for item in self.items):
            raise TypeError("items must contain only NormalizedRecord values")
        if self.next_cursor is not None:
            _require_bounded_text(
                self.next_cursor,
                field_name="next_cursor",
                max_length=4096,
            )
        if not isinstance(self.has_more, bool):
            raise TypeError("has_more must be a boolean")
        if self.has_more and self.next_cursor is None:
            raise ValueError("has_more requires next_cursor")
        if self.request_id is not None:
            _require_safe_request_id(self.request_id)
        if self.rate_limit_hint is not None and not isinstance(
            self.rate_limit_hint, RateLimitHint
        ):
            raise TypeError("rate_limit_hint must be a RateLimitHint or None")
        if self.watermark is not None:
            _require_aware_datetime(self.watermark, field_name="watermark")


@dataclass(frozen=True, slots=True)
class VerifiedEvent:
    provider: Provider
    external_event_id: str
    external_subject_id: str
    event_id_scope: EventIdScope
    event_type: str
    external_entity_id: str | None
    platform_updated_at: datetime
    sanitized_payload: Mapping[str, JsonValue] = field(repr=False)


@dataclass(frozen=True, slots=True)
class RevokeResult:
    revoked: bool
    request_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.revoked, bool):
            raise TypeError("revoked must be a boolean")
        if self.request_id is not None:
            _require_safe_request_id(self.request_id)
