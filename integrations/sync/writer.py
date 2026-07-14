"""Conditional PostgreSQL upserts for normalized commerce records.

The caller owns the transaction.  This module stages allowlisted business
rows, safe quarantine signals and sync counters without committing or logging
provider data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from urllib.parse import unquote_plus

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import Table

from commerce_models import (
    CommerceAdAccount,
    CommerceAdBalanceSnapshot,
    CommerceAdDailyMetric,
    CommerceAdEntity,
    CommerceAdFinanceTransaction,
    CommerceDailyMetric,
    CommerceInventorySnapshot,
    CommerceOrder,
    CommerceOrderItem,
    CommerceProduct,
    CommerceRefund,
    CommerceSettlement,
    CommerceShipment,
    CommerceShop,
    CommerceSku,
)
from integration_models import (
    IntegrationConnection,
    IntegrationSyncCheckpoint,
    IntegrationSyncError,
    IntegrationSyncRun,
)
from integrations.redaction import (
    PayloadSafetyError,
    assert_payload_safe,
    normalize_payload_key,
)
from integrations.schemas import (
    NormalizedAdAccount,
    NormalizedAdBalanceSnapshot,
    NormalizedAdDailyMetric,
    NormalizedAdEntity,
    NormalizedAdFinanceTransaction,
    NormalizedDailyMetric,
    NormalizedInventory,
    NormalizedOrder,
    NormalizedOrderItem,
    NormalizedProduct,
    NormalizedRefund,
    NormalizedSettlement,
    NormalizedShipment,
    NormalizedShop,
    NormalizedSku,
)
from integrations.types import NormalizedRecord, Provider, ResourceType, SyncStatus


_SECRET_TEXT = re.compile(
    r"(?ix)"
    r"(?:"
    r"access[\s_-]*token|refresh[\s_-]*token|app[\s_-]*secret|"
    r"client[\s_-]*secret|authorization[\s_-]*code|"
    r"(?:x[\s_-]*)?api[\s_-]*key|proxy[\s_-]*authorization|"
    r"authorization|set[\s_-]*cookie|cookie|token|secret"
    r")"
    r"\s*[\"']?\s*[:=]"
    r"|\bbearer(?:\s|[\"'])+"
)
_EMAIL_TEXT = re.compile(
    r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?![\w.-])"
)
_MAINLAND_PHONE_TEXT = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PRC_ID_TEXT = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")
_SENSITIVE_KEYS = frozenset(
    {
        "auth",
        "authorization",
        "proxyauthorization",
        "apikey",
        "xapikey",
        "credential",
        "credentials",
        "accesstoken",
        "refreshtoken",
        "appsecret",
        "clientsecret",
        "authorizationcode",
        "cookie",
        "setcookie",
        "email",
        "idcard",
        "identitycard",
        "mobile",
        "phone",
        "telephone",
        "address",
        "detailaddress",
        "shippingaddress",
    }
)
_STABLE_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,100}$")
_MAX_SAFE_DEPTH = 32
_MAX_SAFE_STRING_LENGTH = 4096


@dataclass(frozen=True, slots=True)
class TableSpec:
    resource: ResourceType
    table: Table
    schema: type[BaseModel]
    conflict_columns: tuple[str, ...]
    payload_to_columns: Mapping[str, str]
    optional_columns: frozenset[str]
    primary_external_field: str | None
    cny_amount_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WriteResult:
    records_read: int
    records_written: int
    records_skipped: int
    records_quarantined: int
    partial_success: bool
    refetch_enqueued: int = 0


@dataclass(frozen=True, slots=True)
class _RecordIssue(Exception):
    field: str
    code: str


def _table_spec(
    resource: ResourceType,
    model,
    schema: type[BaseModel],
    *,
    conflict_columns: tuple[str, ...],
    payload_to_columns: Mapping[str, str],
    optional_columns: frozenset[str] = frozenset(),
    primary_external_field: str | None = None,
    cny_amount_fields: tuple[str, ...] = (),
) -> TableSpec:
    table = model.__table__
    selected_mapping = dict(payload_to_columns)
    if set(selected_mapping) != set(schema.model_fields):
        raise RuntimeError(f"Incomplete payload mapping for {resource.value}")
    if any(column_name not in table.c for column_name in selected_mapping.values()):
        raise RuntimeError(f"Unknown payload column for {resource.value}")
    if any(column_name not in table.c for column_name in conflict_columns):
        raise RuntimeError(f"Unknown conflict column for {resource.value}")
    if not optional_columns.issubset(set(selected_mapping.values())):
        raise RuntimeError(f"Unknown optional column for {resource.value}")
    return TableSpec(
        resource=resource,
        table=table,
        schema=schema,
        conflict_columns=conflict_columns,
        payload_to_columns=MappingProxyType(selected_mapping),
        optional_columns=optional_columns,
        primary_external_field=primary_external_field,
        cny_amount_fields=cny_amount_fields,
    )


TABLE_SPECS = MappingProxyType(
    {
        ResourceType.SHOPS: _table_spec(
            ResourceType.SHOPS,
            CommerceShop,
            NormalizedShop,
            conflict_columns=("connection_id", "external_shop_id"),
            payload_to_columns={
                "external_shop_id": "external_shop_id",
                "name": "name",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
            },
            primary_external_field="external_shop_id",
        ),
        ResourceType.PRODUCTS: _table_spec(
            ResourceType.PRODUCTS,
            CommerceProduct,
            NormalizedProduct,
            conflict_columns=("connection_id", "external_product_id"),
            payload_to_columns={
                "external_product_id": "external_product_id",
                "external_shop_id": "external_shop_id",
                "title": "title",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "category": "category",
                "price": "price",
                "currency": "currency",
            },
            optional_columns=frozenset(
                {"external_shop_id", "category", "price", "currency"}
            ),
            primary_external_field="external_product_id",
            cny_amount_fields=("price",),
        ),
        ResourceType.SKUS: _table_spec(
            ResourceType.SKUS,
            CommerceSku,
            NormalizedSku,
            conflict_columns=("connection_id", "external_sku_id"),
            payload_to_columns={
                "external_sku_id": "external_sku_id",
                "external_product_id": "external_product_id",
                "title": "title",
                "attributes": "attributes",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "price": "price",
                "currency": "currency",
            },
            optional_columns=frozenset({"title", "price", "currency"}),
            primary_external_field="external_sku_id",
            cny_amount_fields=("price",),
        ),
        ResourceType.INVENTORY: _table_spec(
            ResourceType.INVENTORY,
            CommerceInventorySnapshot,
            NormalizedInventory,
            conflict_columns=("connection_id", "external_sku_id", "captured_at"),
            payload_to_columns={
                "external_sku_id": "external_sku_id",
                "quantity": "quantity",
                "available_quantity": "available_quantity",
                "captured_at": "captured_at",
            },
            optional_columns=frozenset({"available_quantity"}),
            primary_external_field="external_sku_id",
        ),
        ResourceType.ORDERS: _table_spec(
            ResourceType.ORDERS,
            CommerceOrder,
            NormalizedOrder,
            conflict_columns=("connection_id", "external_order_id"),
            payload_to_columns={
                "external_order_id": "external_order_id",
                "external_shop_id": "external_shop_id",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "buyer_digest": "buyer_digest",
                "province": "province",
                "city": "city",
                "currency": "currency",
                "order_amount": "order_amount",
                "paid_amount": "paid_amount",
                "discount_amount": "discount_amount",
                "shipping_amount": "shipping_amount",
                "created_at": "ordered_at",
                "paid_at": "paid_at",
                "shipped_at": "shipped_at",
                "completed_at": "completed_at",
            },
            optional_columns=frozenset(
                {
                    "external_shop_id",
                    "buyer_digest",
                    "province",
                    "city",
                    "ordered_at",
                    "paid_at",
                    "shipped_at",
                    "completed_at",
                }
            ),
            primary_external_field="external_order_id",
            cny_amount_fields=(
                "order_amount",
                "paid_amount",
                "discount_amount",
                "shipping_amount",
            ),
        ),
        ResourceType.ORDER_ITEMS: _table_spec(
            ResourceType.ORDER_ITEMS,
            CommerceOrderItem,
            NormalizedOrderItem,
            conflict_columns=("connection_id", "external_item_id"),
            payload_to_columns={
                "external_item_id": "external_item_id",
                "external_order_id": "external_order_id",
                "external_product_id": "external_product_id",
                "external_sku_id": "external_sku_id",
                "title": "title",
                "quantity": "quantity",
                "unit_amount": "unit_amount",
                "paid_amount": "paid_amount",
                "currency": "currency",
            },
            optional_columns=frozenset(
                {"external_product_id", "external_sku_id"}
            ),
            primary_external_field="external_item_id",
            cny_amount_fields=("unit_amount", "paid_amount"),
        ),
        ResourceType.REFUNDS: _table_spec(
            ResourceType.REFUNDS,
            CommerceRefund,
            NormalizedRefund,
            conflict_columns=("connection_id", "external_refund_id"),
            payload_to_columns={
                "external_refund_id": "external_refund_id",
                "external_order_id": "external_order_id",
                "external_item_id": "external_item_id",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "amount": "amount",
                "currency": "currency",
                "reason_code": "reason_code",
                "created_at": "refund_created_at",
                "updated_at": "refund_updated_at",
                "completed_at": "completed_at",
            },
            optional_columns=frozenset(
                {
                    "external_item_id",
                    "reason_code",
                    "refund_created_at",
                    "refund_updated_at",
                    "completed_at",
                }
            ),
            primary_external_field="external_refund_id",
            cny_amount_fields=("amount",),
        ),
        ResourceType.SHIPMENTS: _table_spec(
            ResourceType.SHIPMENTS,
            CommerceShipment,
            NormalizedShipment,
            conflict_columns=("connection_id", "external_shipment_id"),
            payload_to_columns={
                "external_shipment_id": "external_shipment_id",
                "external_order_id": "external_order_id",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "carrier_code": "carrier_code",
                "tracking_number": "tracking_number",
                "shipped_at": "shipped_at",
                "delivered_at": "delivered_at",
            },
            optional_columns=frozenset(
                {"carrier_code", "tracking_number", "shipped_at", "delivered_at"}
            ),
            primary_external_field="external_shipment_id",
        ),
        ResourceType.SETTLEMENTS: _table_spec(
            ResourceType.SETTLEMENTS,
            CommerceSettlement,
            NormalizedSettlement,
            conflict_columns=("connection_id", "external_settlement_id"),
            payload_to_columns={
                "external_settlement_id": "external_settlement_id",
                "external_order_id": "external_order_id",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "currency": "currency",
                "gross_amount": "gross_amount",
                "fee_amount": "fee_amount",
                "net_amount": "net_amount",
                "settlement_date": "settlement_date",
            },
            optional_columns=frozenset({"external_order_id"}),
            primary_external_field="external_settlement_id",
            cny_amount_fields=("gross_amount", "fee_amount", "net_amount"),
        ),
        ResourceType.DAILY_METRICS: _table_spec(
            ResourceType.DAILY_METRICS,
            CommerceDailyMetric,
            NormalizedDailyMetric,
            conflict_columns=("connection_id", "stat_date", "granularity"),
            payload_to_columns={
                "stat_date": "stat_date",
                "granularity": "granularity",
                "actual_sales": "actual_sales",
                "order_count": "order_count",
                "refund_amount": "refund_amount",
                "refund_count": "refund_count",
                "visitor_count": "visitor_count",
                "buyer_count": "buyer_count",
                "currency": "currency",
            },
            cny_amount_fields=("actual_sales", "refund_amount"),
        ),
        ResourceType.AD_ACCOUNTS: _table_spec(
            ResourceType.AD_ACCOUNTS,
            CommerceAdAccount,
            NormalizedAdAccount,
            conflict_columns=("connection_id", "external_ad_account_id"),
            payload_to_columns={
                "external_account_id": "external_ad_account_id",
                "name": "name",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "currency": "currency",
            },
            primary_external_field="external_account_id",
        ),
        ResourceType.AD_ENTITIES: _table_spec(
            ResourceType.AD_ENTITIES,
            CommerceAdEntity,
            NormalizedAdEntity,
            conflict_columns=(
                "connection_id",
                "entity_type",
                "external_entity_id",
            ),
            payload_to_columns={
                "entity_type": "entity_type",
                "external_entity_id": "external_entity_id",
                "external_parent_id": "external_parent_id",
                "name": "name",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
            },
            optional_columns=frozenset({"external_parent_id"}),
            primary_external_field="external_entity_id",
        ),
        ResourceType.AD_DAILY_METRICS: _table_spec(
            ResourceType.AD_DAILY_METRICS,
            CommerceAdDailyMetric,
            NormalizedAdDailyMetric,
            conflict_columns=(
                "connection_id",
                "entity_type",
                "external_entity_id",
                "stat_date",
                "granularity",
            ),
            payload_to_columns={
                "entity_type": "entity_type",
                "external_entity_id": "external_entity_id",
                "stat_date": "stat_date",
                "granularity": "granularity",
                "spend": "spend",
                "impressions": "impressions",
                "clicks": "clicks",
                "orders": "orders",
                "attributed_sales": "attributed_sales",
                "ctr": "ctr",
                "cvr": "cvr",
                "roi": "roi",
                "play_count": "play_count",
                "play_rate": "play_rate",
                "currency": "currency",
            },
            optional_columns=frozenset(
                {"ctr", "cvr", "roi", "play_count", "play_rate"}
            ),
            cny_amount_fields=("spend", "attributed_sales"),
        ),
        ResourceType.AD_BALANCE_SNAPSHOTS: _table_spec(
            ResourceType.AD_BALANCE_SNAPSHOTS,
            CommerceAdBalanceSnapshot,
            NormalizedAdBalanceSnapshot,
            conflict_columns=(
                "connection_id",
                "external_ad_account_id",
                "captured_at",
            ),
            payload_to_columns={
                "external_account_id": "external_ad_account_id",
                "balance": "balance",
                "currency": "currency",
                "captured_at": "captured_at",
            },
            cny_amount_fields=("balance",),
        ),
        ResourceType.AD_FINANCE_TRANSACTIONS: _table_spec(
            ResourceType.AD_FINANCE_TRANSACTIONS,
            CommerceAdFinanceTransaction,
            NormalizedAdFinanceTransaction,
            conflict_columns=("connection_id", "external_transaction_id"),
            payload_to_columns={
                "external_transaction_id": "external_transaction_id",
                "external_account_id": "external_ad_account_id",
                "transaction_type": "transaction_type",
                "amount": "amount",
                "currency": "currency",
                "normalized_status": "normalized_status",
                "raw_status": "raw_status",
                "transaction_at": "transaction_at",
            },
            primary_external_field="external_transaction_id",
            cny_amount_fields=("amount",),
        ),
    }
)


def is_cny_aggregatable(payload: BaseModel | Mapping[str, object]) -> bool:
    """Return whether a currency-bearing normalized payload may enter CNY sums."""

    if isinstance(payload, BaseModel):
        currency = getattr(payload, "currency", None)
    elif isinstance(payload, Mapping):
        currency = payload.get("currency")
    else:
        return False
    return type(currency) is str and currency == "CNY"


def _require_utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _RecordIssue(field, "timezone_aware_utc_required")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError):
        offset = None
    if offset is None or offset != timezone.utc.utcoffset(value):
        raise _RecordIssue(field, "timezone_aware_utc_required")
    return value.astimezone(timezone.utc)


def _decoded_text(value: str) -> str:
    selected = unicodedata.normalize("NFKC", value)
    for _ in range(min(len(value) + 1, _MAX_SAFE_STRING_LENGTH + 1)):
        decoded = unquote_plus(selected)
        if decoded == selected:
            break
        selected = decoded
    return unicodedata.normalize("NFKC", selected)


def _assert_sensitive_content_absent(
    value: object,
    *,
    field: str,
    depth: int = 0,
) -> None:
    if depth > _MAX_SAFE_DEPTH:
        raise _RecordIssue(field, "unsafe_nested_content")
    if value is None or type(value) in (bool, int, Decimal, date, datetime):
        return
    if type(value) is float:
        return
    if isinstance(value, Enum):
        return
    if type(value) is str:
        if (
            len(value) > _MAX_SAFE_STRING_LENGTH
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
        ):
            raise _RecordIssue(field, "unsafe_string_content")
        decoded = _decoded_text(value)
        if any(
            pattern.search(decoded) is not None
            for pattern in (
                _SECRET_TEXT,
                _EMAIL_TEXT,
                _MAINLAND_PHONE_TEXT,
                _PRC_ID_TEXT,
            )
        ):
            raise _RecordIssue(field, "sensitive_value")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise _RecordIssue(field, "unsafe_key")
            if normalize_payload_key(key) in _SENSITIVE_KEYS:
                raise _RecordIssue(field, "unsafe_key")
            _assert_sensitive_content_absent(
                item,
                field=field,
                depth=depth + 1,
            )
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_sensitive_content_absent(
                item,
                field=field,
                depth=depth + 1,
            )
        return
    raise _RecordIssue(field, "unsupported_value")


def _assert_record_safe(record: NormalizedRecord) -> None:
    try:
        assert_payload_safe(record.payload)
    except PayloadSafetyError:
        raise _RecordIssue("payload", "unsafe_key") from None
    try:
        assert_payload_safe(record.sanitized_source_payload)
    except PayloadSafetyError:
        raise _RecordIssue("sanitized_source_payload", "unsafe_key") from None
    _assert_sensitive_content_absent(record.payload, field="payload")
    _assert_sensitive_content_absent(
        record.sanitized_source_payload,
        field="sanitized_source_payload",
    )


def _safe_error_code(value: object) -> str:
    selected = value if type(value) is str else "validation_error"
    if _STABLE_ERROR_CODE.fullmatch(selected) is None:
        return "validation_error"
    return selected


def _validation_field_errors(
    error: ValidationError,
    *,
    schema: type[BaseModel],
) -> list[dict[str, str]]:
    allowed_fields = frozenset(schema.model_fields)
    selected: set[tuple[str, str]] = set()
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = item.get("loc", ())
        first = location[0] if location else None
        field = first if type(first) is str and first in allowed_fields else "payload"
        selected.add((field, _safe_error_code(item.get("type"))))
    if not selected:
        selected.add(("payload", "validation_error"))
    return [
        {"field": field, "code": code}
        for field, code in sorted(selected)
    ]


def _external_key_hmac(
    key: bytes,
    *,
    resource: ResourceType,
    external_key: str,
) -> str:
    material = f"{resource.value}\n{external_key}".encode(
        "utf-8",
        errors="surrogatepass",
    )
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _record_external_key(record: object, *, index: int) -> str:
    if isinstance(record, NormalizedRecord) and type(record.external_id) is str:
        return record.external_id
    return f"invalid-record-{index}"


def _quarantine(
    db: Session,
    *,
    run_id: int,
    external_key_hmac: str,
    error_type: str,
    field_errors: list[dict[str, str]],
    now: datetime,
) -> None:
    existing = db.scalar(
        select(IntegrationSyncError.id).where(
            IntegrationSyncError.run_id == run_id,
            IntegrationSyncError.external_key_hmac == external_key_hmac,
            IntegrationSyncError.error_type == error_type,
        )
    )
    if existing is not None:
        return
    summary = (
        "equal timestamp normalized payload conflict"
        if error_type == "equal_timestamp_conflict"
        else "normalized record rejected"
    )
    db.add(
        IntegrationSyncError(
            run_id=run_id,
            external_key_hmac=external_key_hmac,
            error_type=error_type,
            sanitized_summary=summary,
            field_errors=field_errors,
            retryable=False,
            created_at=now,
        )
    )
    db.flush()


def _normalized_json(value: object) -> object:
    if value is None or type(value) in (bool, int, str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _normalized_json(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalized_json(item) for item in value]
    raise RuntimeError("Validated payload contained an unsupported value")


def _canonical_hash(values: Mapping[str, object]) -> str:
    rendered = json.dumps(
        _normalized_json(values),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _mapped_payload(spec: TableSpec, payload: BaseModel) -> dict[str, object]:
    selected = payload.model_dump(mode="python")
    return {
        spec.payload_to_columns[field_name]: selected[field_name]
        for field_name in spec.payload_to_columns
    }


def _conflict_predicates(
    spec: TableSpec,
    values: Mapping[str, object],
) -> list[object]:
    return [
        spec.table.c[column_name] == values[column_name]
        for column_name in spec.conflict_columns
    ]


def _upsert_record(
    db: Session,
    *,
    spec: TableSpec,
    connection_id: int,
    provider: Provider,
    platform_updated_at: datetime,
    payload: BaseModel,
    now: datetime,
) -> str:
    mapped = _mapped_payload(spec, payload)
    values: dict[str, object] = {
        "connection_id": connection_id,
        "provider": provider,
        "platform_updated_at": platform_updated_at,
        "platform_metadata": {},
        "ingested_at": now,
        "updated_at": now,
        **mapped,
    }
    insert_statement = postgres_insert(spec.table).values(**values)
    excluded = insert_statement.excluded
    update_values: dict[str, object] = {
        "platform_updated_at": excluded.platform_updated_at,
        "updated_at": now,
    }
    for column_name in spec.payload_to_columns.values():
        if column_name in spec.conflict_columns:
            continue
        update_values[column_name] = (
            func.coalesce(excluded[column_name], spec.table.c[column_name])
            if column_name in spec.optional_columns
            else excluded[column_name]
        )
    statement = (
        insert_statement.on_conflict_do_update(
            index_elements=[spec.table.c[name] for name in spec.conflict_columns],
            set_=update_values,
            where=(
                excluded.platform_updated_at
                > spec.table.c.platform_updated_at
            ),
        )
        .returning(spec.table.c.platform_updated_at)
    )
    written_at = db.execute(statement).scalar_one_or_none()
    if written_at is not None:
        return "written"

    comparison_columns = tuple(dict.fromkeys(spec.payload_to_columns.values()))
    existing = db.execute(
        select(
            spec.table.c.platform_updated_at,
            *(spec.table.c[name] for name in comparison_columns),
        )
        .where(*_conflict_predicates(spec, values))
        .with_for_update()
    ).mappings().one()
    existing_updated_at = existing["platform_updated_at"]
    if platform_updated_at < existing_updated_at:
        return "skipped"
    if platform_updated_at > existing_updated_at:
        raise RuntimeError("Newer normalized record was not upserted")

    effective_incoming = {
        column_name: (
            existing[column_name]
            if column_name in spec.optional_columns and mapped[column_name] is None
            else mapped[column_name]
        )
        for column_name in comparison_columns
    }
    existing_values = {
        column_name: existing[column_name]
        for column_name in comparison_columns
    }
    if _canonical_hash(effective_incoming) == _canonical_hash(existing_values):
        return "skipped"
    return "conflict"


def _load_run_context(
    db: Session,
    *,
    run_id: int,
) -> tuple[IntegrationSyncRun, int, Provider, ResourceType]:
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("run_id must be a positive integer")
    run = db.scalar(
        select(IntegrationSyncRun)
        .where(IntegrationSyncRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise ValueError("run_id does not reference a sync run")
    if run.status not in (SyncStatus.RUNNING, SyncStatus.PARTIAL_SUCCESS):
        raise ValueError("sync run is not writable")
    checkpoint = db.get(IntegrationSyncCheckpoint, run.checkpoint_id)
    if checkpoint is None or checkpoint.resource_type is not run.resource_type:
        raise ValueError("sync run checkpoint is invalid")
    connection = db.get(IntegrationConnection, checkpoint.connection_id)
    if connection is None or not isinstance(connection.provider, Provider):
        raise ValueError("sync run connection is invalid")
    return run, connection.id, connection.provider, run.resource_type


def write_records(
    db: Session,
    *,
    run_id: int,
    records: Iterable[NormalizedRecord],
    quarantine_hmac_key: bytes,
    now: datetime,
) -> WriteResult:
    """Stage one page of valid siblings and safe per-record quarantine signals."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    if type(quarantine_hmac_key) is not bytes or len(quarantine_hmac_key) < 32:
        raise ValueError("quarantine_hmac_key must contain at least 32 bytes")
    selected_now = _require_utc(now, field="now")
    try:
        selected_records = tuple(records)
    except TypeError:
        raise ValueError("records must be iterable") from None

    run, connection_id, provider, resource = _load_run_context(db, run_id=run_id)
    spec = TABLE_SPECS[resource]
    written = 0
    skipped = 0
    quarantined = 0

    for index, record in enumerate(selected_records):
        external_key = _record_external_key(record, index=index)
        external_key_digest = _external_key_hmac(
            quarantine_hmac_key,
            resource=resource,
            external_key=external_key,
        )
        try:
            if not isinstance(record, NormalizedRecord):
                raise _RecordIssue("record", "normalized_record_required")
            if record.resource is not resource:
                raise _RecordIssue("resource", "resource_mismatch")
            platform_updated_at = _require_utc(
                record.platform_updated_at,
                field="platform_updated_at",
            )
            _assert_record_safe(record)
            payload = spec.schema.model_validate(record.payload_for_serialization())
            if spec.primary_external_field is not None and record.external_id != getattr(
                payload,
                spec.primary_external_field,
            ):
                raise _RecordIssue("external_id", "external_id_mismatch")
            outcome = _upsert_record(
                db,
                spec=spec,
                connection_id=connection_id,
                provider=provider,
                platform_updated_at=platform_updated_at,
                payload=payload,
                now=selected_now,
            )
        except ValidationError as error:
            quarantined += 1
            _quarantine(
                db,
                run_id=run.id,
                external_key_hmac=external_key_digest,
                error_type="validation_error",
                field_errors=_validation_field_errors(error, schema=spec.schema),
                now=selected_now,
            )
            continue
        except _RecordIssue as error:
            quarantined += 1
            _quarantine(
                db,
                run_id=run.id,
                external_key_hmac=external_key_digest,
                error_type="validation_error",
                field_errors=[
                    {
                        "field": error.field,
                        "code": _safe_error_code(error.code),
                    }
                ],
                now=selected_now,
            )
            continue

        if outcome == "written":
            written += 1
        elif outcome == "skipped":
            skipped += 1
        elif outcome == "conflict":
            quarantined += 1
            _quarantine(
                db,
                run_id=run.id,
                external_key_hmac=external_key_digest,
                error_type="equal_timestamp_conflict",
                field_errors=[
                    {
                        "field": "platform_updated_at",
                        "code": "equal_timestamp_conflict",
                    }
                ],
                now=selected_now,
            )
        else:  # pragma: no cover - private helper has a closed result set
            raise RuntimeError("Unknown writer outcome")

    counter_values: dict[str, object] = {
        "records_read": IntegrationSyncRun.records_read + len(selected_records),
        "records_written": IntegrationSyncRun.records_written + written,
        "records_skipped": IntegrationSyncRun.records_skipped + skipped,
        "records_quarantined": (
            IntegrationSyncRun.records_quarantined + quarantined
        ),
    }
    if quarantined:
        counter_values["status"] = SyncStatus.PARTIAL_SUCCESS
    db.execute(
        update(IntegrationSyncRun)
        .where(IntegrationSyncRun.id == run.id)
        .values(**counter_values)
    )
    db.flush()
    db.refresh(run)
    return WriteResult(
        records_read=len(selected_records),
        records_written=written,
        records_skipped=skipped,
        records_quarantined=quarantined,
        partial_success=(run.status is SyncStatus.PARTIAL_SUCCESS),
        refetch_enqueued=0,
    )


__all__ = [
    "TABLE_SPECS",
    "TableSpec",
    "WriteResult",
    "is_cny_aggregatable",
    "write_records",
]
