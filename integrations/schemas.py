"""Strict request and response schemas for integration administration."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from urllib.parse import unquote_plus
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from integrations.redaction import assert_payload_safe
from integrations.types import (
    AccountStatus,
    AdEntityStatus,
    AdEntityType,
    FinanceTransactionStatus,
    MetricGranularity,
    OrderStatus,
    ProductStatus,
    Provider,
    RefundStatus,
    ResourceType,
    SettlementStatus,
    ShipmentStatus,
    SyncSource,
    SyncStatus,
)


_SENSITIVE_SEARCH_MARKERS = (
    "bearer_",
    "access_token",
    "refresh_token",
    "app_secret",
    "client_secret",
    "sk_",
)


def _search_contains_sensitive_value(value: str) -> bool:
    decoded = value
    for _ in range(3):
        next_value = unquote_plus(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    normalized = unicodedata.normalize("NFKC", decoded).casefold()
    canonical_markers = re.sub(r"[\s_-]+", "_", normalized)
    digits = re.sub(r"\D", "", normalized)
    identity_characters = re.sub(r"[^0-9x]", "", normalized)
    return bool(
        re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", normalized)
        or re.search(r"1[3-9]\d{9}", digits)
        or re.search(r"\d{17}[0-9x]", identity_characters)
        or "authorization:" in normalized
        or any(
            marker in canonical_markers
            for marker in _SENSITIVE_SEARCH_MARKERS
        )
    )


def _decimal_from_value(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("value must be a finite decimal")
    if isinstance(value, str) and (not value or value != value.strip()):
        raise ValueError("value must be a finite decimal")
    try:
        selected = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("value must be a finite decimal") from None
    if not selected.is_finite():
        raise ValueError("value must be a finite decimal")
    return selected


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _business_date(value: object) -> object:
    if isinstance(value, datetime):
        raise ValueError("business date must not be a datetime")
    return value


def _validate_json_object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("attributes must be a JSON object")

    def visit(item: object, *, depth: int) -> None:
        if depth > 16:
            raise ValueError("attributes exceed the nesting limit")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("attributes contain a non-finite number")
            return
        if type(item) is list:
            for child in item:
                visit(child, depth=depth + 1)
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("attributes must use string keys")
                visit(child, depth=depth + 1)
            return
        raise ValueError("attributes contain a non-JSON value")

    visit(value, depth=0)
    assert_payload_safe(value)
    return value


ExternalId = Annotated[str, Field(strict=True, min_length=1, max_length=255)]
Text100 = Annotated[str, Field(strict=True, min_length=1, max_length=100)]
Text255 = Annotated[str, Field(strict=True, min_length=1, max_length=255)]
Text500 = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
Text1000 = Annotated[str, Field(strict=True, min_length=1, max_length=1000)]
Currency = Annotated[str, Field(strict=True, pattern=r"^[A-Z]{3}$")]
Digest64 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
AwareUtcDateTime = Annotated[datetime, AfterValidator(_aware_utc)]
BusinessDate = Annotated[date, BeforeValidator(_business_date)]
Decimal2 = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_value),
    Field(max_digits=20, decimal_places=2),
]
NonnegativeMoney = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_value),
    Field(ge=0, max_digits=20, decimal_places=2),
]
NonnegativeRatio = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_value),
    Field(ge=0, max_digits=20, decimal_places=6),
]
NonnegativeCount = Annotated[
    int,
    Field(strict=True, ge=0, le=2_147_483_647),
]
PositiveCount = Annotated[
    int,
    Field(strict=True, gt=0, le=2_147_483_647),
]
SafeJsonObject = Annotated[dict[str, Any], BeforeValidator(_validate_json_object)]


class _NormalizedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    @field_validator("*", mode="after")
    @classmethod
    def strings_are_trimmed_and_control_free(cls, value):
        if isinstance(value, str) and (
            value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("string fields must be trimmed and control-free")
        return value


class NormalizedShop(_NormalizedPayload):
    external_shop_id: ExternalId
    name: Text500
    normalized_status: AccountStatus
    raw_status: Text255


class NormalizedProduct(_NormalizedPayload):
    external_product_id: ExternalId
    external_shop_id: ExternalId | None = None
    title: Text1000
    normalized_status: ProductStatus
    raw_status: Text255
    category: Text500 | None = None
    price: NonnegativeMoney | None = None
    currency: Currency | None = None


class NormalizedSku(_NormalizedPayload):
    external_sku_id: ExternalId
    external_product_id: ExternalId
    title: Text1000 | None = None
    attributes: SafeJsonObject
    normalized_status: ProductStatus
    raw_status: Text255
    price: NonnegativeMoney | None = None
    currency: Currency | None = None


class NormalizedInventory(_NormalizedPayload):
    external_sku_id: ExternalId
    quantity: NonnegativeCount
    available_quantity: NonnegativeCount | None = None
    captured_at: AwareUtcDateTime


class NormalizedOrder(_NormalizedPayload):
    external_order_id: ExternalId
    external_shop_id: ExternalId | None = None
    normalized_status: OrderStatus
    raw_status: Text255
    buyer_digest: Digest64 | None = None
    province: Text100 | None = None
    city: Text100 | None = None
    currency: Currency = "CNY"
    order_amount: NonnegativeMoney
    paid_amount: NonnegativeMoney
    discount_amount: NonnegativeMoney
    shipping_amount: NonnegativeMoney
    created_at: AwareUtcDateTime | None = None
    paid_at: AwareUtcDateTime | None = None
    shipped_at: AwareUtcDateTime | None = None
    completed_at: AwareUtcDateTime | None = None


class NormalizedOrderItem(_NormalizedPayload):
    external_item_id: ExternalId
    external_order_id: ExternalId
    external_product_id: ExternalId | None = None
    external_sku_id: ExternalId | None = None
    title: Text1000
    quantity: PositiveCount
    unit_amount: NonnegativeMoney
    paid_amount: NonnegativeMoney
    currency: Currency


class NormalizedRefund(_NormalizedPayload):
    external_refund_id: ExternalId
    external_order_id: ExternalId
    external_item_id: ExternalId | None = None
    normalized_status: RefundStatus
    raw_status: Text255
    amount: NonnegativeMoney
    currency: Currency
    reason_code: Text255 | None = None
    created_at: AwareUtcDateTime | None = None
    updated_at: AwareUtcDateTime | None = None
    completed_at: AwareUtcDateTime | None = None


class NormalizedShipment(_NormalizedPayload):
    external_shipment_id: ExternalId
    external_order_id: ExternalId
    normalized_status: ShipmentStatus
    raw_status: Text255
    carrier_code: Text255 | None = None
    tracking_number: Text255 | None = None
    shipped_at: AwareUtcDateTime | None = None
    delivered_at: AwareUtcDateTime | None = None


class NormalizedSettlement(_NormalizedPayload):
    external_settlement_id: ExternalId
    external_order_id: ExternalId | None = None
    normalized_status: SettlementStatus
    raw_status: Text255
    currency: Currency
    gross_amount: Decimal2
    fee_amount: Decimal2
    net_amount: Decimal2
    settlement_date: BusinessDate


class NormalizedDailyMetric(_NormalizedPayload):
    stat_date: BusinessDate
    granularity: MetricGranularity
    actual_sales: NonnegativeMoney
    order_count: NonnegativeCount
    refund_amount: NonnegativeMoney
    refund_count: NonnegativeCount
    visitor_count: NonnegativeCount
    buyer_count: NonnegativeCount
    currency: Currency


class NormalizedAdAccount(_NormalizedPayload):
    external_account_id: ExternalId
    name: Text500
    normalized_status: AccountStatus
    raw_status: Text255
    currency: Currency


class NormalizedAdEntity(_NormalizedPayload):
    entity_type: AdEntityType
    external_entity_id: ExternalId
    external_parent_id: ExternalId | None = None
    name: Text500
    normalized_status: AdEntityStatus
    raw_status: Text255


class NormalizedAdDailyMetric(_NormalizedPayload):
    entity_type: AdEntityType
    external_entity_id: ExternalId
    stat_date: BusinessDate
    granularity: MetricGranularity
    spend: NonnegativeMoney
    impressions: NonnegativeCount
    clicks: NonnegativeCount
    orders: NonnegativeCount
    attributed_sales: NonnegativeMoney
    ctr: NonnegativeRatio | None = None
    cvr: NonnegativeRatio | None = None
    roi: NonnegativeRatio | None = None
    play_count: NonnegativeCount | None = None
    play_rate: NonnegativeRatio | None = None
    currency: Currency


class NormalizedAdBalanceSnapshot(_NormalizedPayload):
    external_account_id: ExternalId
    balance: Decimal2
    currency: Currency
    captured_at: AwareUtcDateTime


class NormalizedAdFinanceTransaction(_NormalizedPayload):
    external_transaction_id: ExternalId
    external_account_id: ExternalId
    transaction_type: Text255
    amount: Decimal2
    currency: Currency
    normalized_status: FinanceTransactionStatus
    raw_status: Text255
    transaction_at: AwareUtcDateTime


class AppConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(min_length=1, max_length=200)
    app_secret: SecretStr | None = Field(
        default=None,
        min_length=1,
        max_length=4096,
    )
    clear_secret: StrictBool = False

    @model_validator(mode="after")
    def secret_update_is_unambiguous(self):
        if self.app_secret is not None and self.clear_secret:
            raise ValueError(
                "app_secret and clear_secret cannot be supplied together"
            )
        return self


class AppConfigView(BaseModel):
    provider: Provider
    app_id: str | None
    secret_configured: bool
    secret_mask: str | None
    status: str
    updated_at: datetime | None


class ProviderIntegrationView(BaseModel):
    provider: Provider
    documented: bool
    configured: bool
    live_verified: bool
    live_status: Literal["pending"]
    app_config: AppConfigView


class ProviderListResponse(BaseModel):
    providers: list[ProviderIntegrationView]


class AuthorizationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_path: str = Field(
        default="/app/api-connections",
        min_length=1,
        max_length=2048,
    )


class AuthorizationStartResponse(BaseModel):
    authorization_url: str


class CommonDataQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider | None = None
    connection_id: StrictInt | None = Field(default=None, gt=0)
    date_from: date | None = None
    date_to: date | None = None
    page: StrictInt = Field(default=1, gt=0)
    per_page: Literal[50, 100, 200] = 50

    @model_validator(mode="after")
    def reporting_dates_are_ordered_and_bounded(self):
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must not be after date_to")
            if (self.date_to - self.date_from).days + 1 > 366:
                raise ValueError("reporting range must not exceed 366 days")
        return self


class _SearchDataQuery(CommonDataQuery):
    search: str | None = Field(default=None, max_length=200)

    @field_validator("search")
    @classmethod
    def search_has_no_control_characters(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("search must not contain control characters")
        selected = value.strip()
        if selected and _search_contains_sensitive_value(selected):
            raise ValueError("search contains a sensitive value")
        return selected or None


class OrderDataQuery(_SearchDataQuery):
    status: OrderStatus | None = None


class ProductDataQuery(_SearchDataQuery):
    status: ProductStatus | None = None
    link_status: Literal["linked", "unlinked"] | None = None


class RefundDataQuery(_SearchDataQuery):
    status: RefundStatus | None = None


class AdEntityDataQuery(_SearchDataQuery):
    entity_type: AdEntityType | None = None


class AdMetricDataQuery(CommonDataQuery):
    entity_type: AdEntityType | None = None
    granularity: MetricGranularity | None = None


class SyncRunDataQuery(CommonDataQuery):
    status: SyncStatus | None = None
    source: SyncSource | None = None
    resource_type: ResourceType | None = None


class ProductLinkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: StrictInt = Field(gt=0)


class ManualSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resources: list[ResourceType] = Field(min_length=1, max_length=15)
    date_from: date
    date_to: date
    request_id: UUID

    @model_validator(mode="after")
    def manual_window_and_resources_are_safe(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        if (self.date_to - self.date_from).days + 1 > 366:
            raise ValueError("manual sync range must not exceed 366 days")
        if len(self.resources) != len(set(self.resources)):
            raise ValueError("resources must be unique")
        if ResourceType.ORDER_ITEMS in self.resources:
            raise ValueError("order_items is emitted by orders")
        return self


class ReauthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_path: str = Field(
        default="/app/api-connections",
        min_length=1,
        max_length=2048,
    )


class RetryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class PurgeConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=255)


class ExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider | None = None
    connection_id: StrictInt | None = Field(default=None, gt=0)
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = Field(default=None, max_length=64)
    search: str | None = Field(default=None, max_length=200)
    entity_type: AdEntityType | None = None
    granularity: MetricGranularity | None = None
    link_status: Literal["linked", "unlinked"] | None = None

    @model_validator(mode="after")
    def export_filter_values_are_safe(self):
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must not be after date_to")
            if (self.date_to - self.date_from).days + 1 > 366:
                raise ValueError("export range must not exceed 366 days")
        for value in (self.status, self.search):
            if value is not None and any(
                ord(character) < 32 or ord(character) == 127 for character in value
            ):
                raise ValueError("export filters must not contain control characters")
        if self.search is not None:
            if _search_contains_sensitive_value(self.search):
                raise ValueError("export search contains a sensitive value")
        return self


class ExportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: ResourceType
    format: Literal["csv", "xlsx"]
    filters: ExportFilters = Field(default_factory=ExportFilters)

    @model_validator(mode="after")
    def resource_is_available_in_the_data_center(self):
        exportable = {
            ResourceType.ORDERS,
            ResourceType.PRODUCTS,
            ResourceType.REFUNDS,
            ResourceType.AD_ENTITIES,
            ResourceType.AD_DAILY_METRICS,
        }
        if self.resource_type not in exportable:
            raise ValueError("resource is not exportable")
        common = {"provider", "connection_id", "date_from", "date_to"}
        resource_filters = {
            ResourceType.ORDERS: {"status", "search"},
            ResourceType.PRODUCTS: {"status", "search", "link_status"},
            ResourceType.REFUNDS: {"status", "search"},
            ResourceType.AD_ENTITIES: {"entity_type", "search"},
            ResourceType.AD_DAILY_METRICS: {"entity_type", "granularity"},
        }
        if self.filters.model_fields_set - (
            common | resource_filters[self.resource_type]
        ):
            raise ValueError("filter is not available for this export resource")
        status_types = {
            ResourceType.ORDERS: OrderStatus,
            ResourceType.PRODUCTS: ProductStatus,
            ResourceType.REFUNDS: RefundStatus,
        }
        if self.filters.status is not None:
            status_type = status_types.get(self.resource_type)
            if status_type is None:
                raise ValueError("status is not available for this export resource")
            try:
                status_type(self.filters.status)
            except ValueError:
                raise ValueError("status is invalid for this export resource") from None
        return self


__all__ = [
    "AdEntityDataQuery",
    "AdMetricDataQuery",
    "AppConfigUpdate",
    "AppConfigView",
    "AuthorizationStartRequest",
    "AuthorizationStartResponse",
    "CommonDataQuery",
    "ExportCreateRequest",
    "ExportFilters",
    "ManualSyncRequest",
    "NormalizedAdAccount",
    "NormalizedAdBalanceSnapshot",
    "NormalizedAdDailyMetric",
    "NormalizedAdEntity",
    "NormalizedAdFinanceTransaction",
    "NormalizedDailyMetric",
    "NormalizedInventory",
    "NormalizedOrder",
    "NormalizedOrderItem",
    "NormalizedProduct",
    "NormalizedRefund",
    "NormalizedSettlement",
    "NormalizedShipment",
    "NormalizedShop",
    "NormalizedSku",
    "OrderDataQuery",
    "ProductDataQuery",
    "ProductLinkUpdate",
    "PurgeConnectionRequest",
    "ProviderIntegrationView",
    "ProviderListResponse",
    "RefundDataQuery",
    "ReauthorizationRequest",
    "RetryRunRequest",
    "SyncRunDataQuery",
]
