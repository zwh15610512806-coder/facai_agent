"""Safe, provider-neutral reporting primitives for the integration center."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from commerce_models import (
    CommerceAdDailyMetric,
    CommerceAdEntity,
    CommerceDailyMetric,
    CommerceOrder,
    CommerceProduct,
    CommerceProductLink,
    CommerceRefund,
)
from integration_models import (
    IntegrationConnection,
    IntegrationSyncCheckpoint,
    IntegrationSyncRun,
)
from integrations.types import (
    AdEntityStatus,
    AdEntityType,
    MetricGranularity,
    OrderStatus,
    ProductStatus,
    Provider,
    RefundStatus,
    ResourceType,
    SyncSource,
    SyncStatus,
)
from models import Product


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_REPORTING_DAYS = 366
MAX_SEARCH_LENGTH = 200
ALLOWED_PAGE_SIZES = frozenset({50, 100, 200})


@dataclass(frozen=True, slots=True)
class ReportingRange:
    """Inclusive Shanghai calendar dates and their UTC-exclusive bounds."""

    date_from: date
    date_to: date
    start_at: datetime
    end_at: datetime
    days: int

    @classmethod
    def from_dates(
        cls,
        *,
        date_from: date | None,
        date_to: date | None,
        today: date,
    ) -> "ReportingRange":
        if not isinstance(today, date) or isinstance(today, datetime):
            raise TypeError("today must be a date")
        selected_to = today if date_to is None else date_to
        selected_from = (
            selected_to - timedelta(days=29)
            if date_from is None
            else date_from
        )
        if not isinstance(selected_from, date) or isinstance(selected_from, datetime):
            raise TypeError("date_from must be a date")
        if not isinstance(selected_to, date) or isinstance(selected_to, datetime):
            raise TypeError("date_to must be a date")
        if selected_from > selected_to:
            raise ValueError("date_from must not be after date_to")
        days = (selected_to - selected_from).days + 1
        if days > MAX_REPORTING_DAYS:
            raise ValueError("reporting range must not exceed 366 days")
        start_local = datetime.combine(selected_from, time.min, tzinfo=SHANGHAI)
        end_local = datetime.combine(
            selected_to + timedelta(days=1),
            time.min,
            tzinfo=SHANGHAI,
        )
        return cls(
            date_from=selected_from,
            date_to=selected_to,
            start_at=start_local.astimezone(UTC),
            end_at=end_local.astimezone(UTC),
            days=days,
        )


@dataclass(frozen=True, slots=True)
class PageResult:
    items: list[dict[str, object]]
    total: int
    page: int
    per_page: int
    total_pages: int

    def as_dict(self) -> dict[str, object]:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "per_page": self.per_page,
            "total_pages": self.total_pages,
        }


def decimal_text(value: Decimal, *, scale: int) -> str:
    """Serialize exact decimals with a caller-selected fixed scale."""

    if not isinstance(value, Decimal):
        raise TypeError("value must be a Decimal")
    if not value.is_finite():
        raise ValueError("value must be finite")
    if type(scale) is not int or not 0 <= scale <= 12:
        raise ValueError("scale must be an integer from 0 through 12")
    quantum = Decimal(1).scaleb(-scale)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), f".{scale}f")


def sanitize_search(value: str | None) -> str | None:
    """Accept only a bounded printable search term for safe business fields."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("search must be a string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("search must not contain control characters")
    selected = value.strip()
    if not selected:
        return None
    if len(selected) > MAX_SEARCH_LENGTH:
        raise ValueError("search must not exceed 200 characters")
    return selected


def _enum_value(value: object, enum_type: type) -> str:
    if not isinstance(value, enum_type):
        raise TypeError("normalized enum value is invalid")
    return value.value


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("report timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _display_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("report timestamp must be timezone-aware")
    return value.astimezone(SHANGHAI).date().isoformat()


def order_view(order: object) -> dict[str, object]:
    """Return the explicit order allowlist; buyer fields are never serialized."""

    business_time = (
        getattr(order, "paid_at", None)
        or getattr(order, "ordered_at", None)
        or getattr(order, "platform_updated_at")
    )
    return {
        "id": int(getattr(order, "id")),
        "connection_id": int(getattr(order, "connection_id")),
        "provider": _enum_value(getattr(order, "provider"), Provider),
        "external_order_id": str(getattr(order, "external_order_id")),
        "status": _enum_value(getattr(order, "normalized_status"), OrderStatus),
        "raw_status": str(getattr(order, "raw_status")),
        "currency": str(getattr(order, "currency")),
        "order_amount": decimal_text(getattr(order, "order_amount"), scale=2),
        "paid_amount": decimal_text(getattr(order, "paid_amount"), scale=2),
        "discount_amount": decimal_text(
            getattr(order, "discount_amount"),
            scale=2,
        ),
        "shipping_amount": decimal_text(
            getattr(order, "shipping_amount"),
            scale=2,
        ),
        "ordered_at": _utc_iso(getattr(order, "ordered_at", None)),
        "paid_at": _utc_iso(getattr(order, "paid_at", None)),
        "shipped_at": _utc_iso(getattr(order, "shipped_at", None)),
        "completed_at": _utc_iso(getattr(order, "completed_at", None)),
        "business_time": _utc_iso(business_time),
        "display_date": _display_date(business_time),
    }


def refund_view(refund: object) -> dict[str, object]:
    """Return the explicit refund allowlist without source payloads."""

    business_time = (
        getattr(refund, "completed_at", None)
        or getattr(refund, "refund_updated_at", None)
        or getattr(refund, "refund_created_at", None)
        or getattr(refund, "platform_updated_at")
    )
    return {
        "id": int(getattr(refund, "id")),
        "connection_id": int(getattr(refund, "connection_id")),
        "provider": _enum_value(getattr(refund, "provider"), Provider),
        "external_refund_id": str(getattr(refund, "external_refund_id")),
        "external_order_id": str(getattr(refund, "external_order_id")),
        "status": _enum_value(getattr(refund, "normalized_status"), RefundStatus),
        "raw_status": str(getattr(refund, "raw_status")),
        "amount": decimal_text(getattr(refund, "amount"), scale=2),
        "currency": str(getattr(refund, "currency")),
        "reason_code": getattr(refund, "reason_code", None),
        "created_at": _utc_iso(getattr(refund, "refund_created_at", None)),
        "updated_at": _utc_iso(getattr(refund, "refund_updated_at", None)),
        "completed_at": _utc_iso(getattr(refund, "completed_at", None)),
        "business_time": _utc_iso(business_time),
        "display_date": _display_date(business_time),
    }


def _pagination(page: int, per_page: int) -> tuple[int, int]:
    if type(page) is not int or page <= 0:
        raise ValueError("page must be a positive integer")
    if type(per_page) is not int or per_page not in ALLOWED_PAGE_SIZES:
        raise ValueError("per_page must be 50, 100 or 200")
    return page, per_page


def _page_result(
    *,
    items: list[dict[str, object]],
    total: int,
    page: int,
    per_page: int,
) -> PageResult:
    return PageResult(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, ceil(total / per_page)),
    )


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _common_conditions(
    model,
    *,
    provider: Provider | None,
    connection_id: int | None,
    allowed_connection_ids: Collection[int] | None = None,
) -> list[object]:
    conditions: list[object] = []
    if provider is not None:
        if not isinstance(provider, Provider):
            raise ValueError("provider must be a Provider")
        conditions.append(model.provider == provider)
    if connection_id is not None:
        if type(connection_id) is not int or connection_id <= 0:
            raise ValueError("connection_id must be a positive integer")
        conditions.append(model.connection_id == connection_id)
    if allowed_connection_ids is not None:
        selected_ids = tuple(allowed_connection_ids)
        if any(type(value) is not int or value <= 0 for value in selected_ids):
            raise ValueError("allowed_connection_ids must contain positive integers")
        conditions.append(model.connection_id.in_(selected_ids))
    return conditions


def list_orders(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
    status: OrderStatus | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
    allowed_connection_ids: Collection[int] | None = None,
) -> PageResult:
    """Page safe order fields using stable business-time/id ordering."""

    selected_page, selected_per_page = _pagination(page, per_page)
    if not isinstance(reporting_range, ReportingRange):
        raise ValueError("reporting_range must be a ReportingRange")
    business_time = func.coalesce(
        CommerceOrder.paid_at,
        CommerceOrder.ordered_at,
        CommerceOrder.platform_updated_at,
    )
    conditions = _common_conditions(
        CommerceOrder,
        provider=provider,
        connection_id=connection_id,
        allowed_connection_ids=allowed_connection_ids,
    )
    conditions.extend(
        (
            business_time >= reporting_range.start_at,
            business_time < reporting_range.end_at,
        )
    )
    if status is not None:
        if not isinstance(status, OrderStatus):
            raise ValueError("status must be an OrderStatus")
        conditions.append(CommerceOrder.normalized_status == status)
    selected_search = sanitize_search(search)
    if selected_search is not None:
        conditions.append(
            CommerceOrder.external_order_id.ilike(
                _like_pattern(selected_search),
                escape="\\",
            )
        )
    base = select(CommerceOrder).where(*conditions)
    total = int(
        db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        or 0
    )
    rows = db.scalars(
        base.order_by(business_time.desc(), CommerceOrder.id.desc())
        .offset((selected_page - 1) * selected_per_page)
        .limit(selected_per_page)
    ).all()
    return _page_result(
        items=[order_view(row) for row in rows],
        total=total,
        page=selected_page,
        per_page=selected_per_page,
    )


def list_refunds(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
    status: RefundStatus | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
    allowed_connection_ids: Collection[int] | None = None,
) -> PageResult:
    selected_page, selected_per_page = _pagination(page, per_page)
    if not isinstance(reporting_range, ReportingRange):
        raise ValueError("reporting_range must be a ReportingRange")
    business_time = func.coalesce(
        CommerceRefund.completed_at,
        CommerceRefund.refund_updated_at,
        CommerceRefund.refund_created_at,
        CommerceRefund.platform_updated_at,
    )
    conditions = _common_conditions(
        CommerceRefund,
        provider=provider,
        connection_id=connection_id,
        allowed_connection_ids=allowed_connection_ids,
    )
    conditions.extend(
        (
            business_time >= reporting_range.start_at,
            business_time < reporting_range.end_at,
        )
    )
    if status is not None:
        if not isinstance(status, RefundStatus):
            raise ValueError("status must be a RefundStatus")
        conditions.append(CommerceRefund.normalized_status == status)
    selected_search = sanitize_search(search)
    if selected_search is not None:
        pattern = _like_pattern(selected_search)
        conditions.append(
            or_(
                CommerceRefund.external_refund_id.ilike(pattern, escape="\\"),
                CommerceRefund.external_order_id.ilike(pattern, escape="\\"),
            )
        )
    base = select(CommerceRefund).where(*conditions)
    total = int(
        db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        or 0
    )
    rows = db.scalars(
        base.order_by(business_time.desc(), CommerceRefund.id.desc())
        .offset((selected_page - 1) * selected_per_page)
        .limit(selected_per_page)
    ).all()
    return _page_result(
        items=[refund_view(row) for row in rows],
        total=total,
        page=selected_page,
        per_page=selected_per_page,
    )


def product_view(
    product: object,
    *,
    link: object | None = None,
    internal_product: object | None = None,
) -> dict[str, object]:
    price = getattr(product, "price", None)
    linked = link is not None
    return {
        "id": int(getattr(product, "id")),
        "connection_id": int(getattr(product, "connection_id")),
        "provider": _enum_value(getattr(product, "provider"), Provider),
        "external_product_id": str(getattr(product, "external_product_id")),
        "external_shop_id": getattr(product, "external_shop_id", None),
        "title": str(getattr(product, "title")),
        "status": _enum_value(
            getattr(product, "normalized_status"),
            ProductStatus,
        ),
        "raw_status": str(getattr(product, "raw_status")),
        "category": getattr(product, "category", None),
        "price": decimal_text(price, scale=2) if price is not None else None,
        "currency": getattr(product, "currency", None),
        "platform_updated_at": _utc_iso(getattr(product, "platform_updated_at")),
        "display_date": _display_date(getattr(product, "platform_updated_at")),
        "link_status": "linked" if linked else "unlinked",
        "product_link": (
            {
                "product_id": int(getattr(link, "product_id")),
                "product_name": str(getattr(internal_product, "name")),
            }
            if linked and internal_product is not None
            else None
        ),
    }


def list_products(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
    status: ProductStatus | None = None,
    search: str | None = None,
    link_status: str | None = None,
    page: int = 1,
    per_page: int = 50,
    allowed_connection_ids: Collection[int] | None = None,
) -> PageResult:
    selected_page, selected_per_page = _pagination(page, per_page)
    if not isinstance(reporting_range, ReportingRange):
        raise ValueError("reporting_range must be a ReportingRange")
    conditions = _common_conditions(
        CommerceProduct,
        provider=provider,
        connection_id=connection_id,
        allowed_connection_ids=allowed_connection_ids,
    )
    conditions.extend(
        (
            CommerceProduct.platform_updated_at >= reporting_range.start_at,
            CommerceProduct.platform_updated_at < reporting_range.end_at,
        )
    )
    if status is not None:
        if not isinstance(status, ProductStatus):
            raise ValueError("status must be a ProductStatus")
        conditions.append(CommerceProduct.normalized_status == status)
    selected_search = sanitize_search(search)
    if selected_search is not None:
        pattern = _like_pattern(selected_search)
        conditions.append(
            or_(
                CommerceProduct.external_product_id.ilike(pattern, escape="\\"),
                CommerceProduct.title.ilike(pattern, escape="\\"),
            )
        )
    if link_status not in {None, "linked", "unlinked"}:
        raise ValueError("link_status must be linked or unlinked")
    if link_status == "linked":
        conditions.append(CommerceProductLink.id.is_not(None))
    elif link_status == "unlinked":
        conditions.append(CommerceProductLink.id.is_(None))

    base = (
        select(CommerceProduct, CommerceProductLink, Product)
        .outerjoin(
            CommerceProductLink,
            CommerceProductLink.commerce_product_id == CommerceProduct.id,
        )
        .outerjoin(Product, Product.id == CommerceProductLink.product_id)
        .where(*conditions)
    )
    total = int(
        db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        or 0
    )
    rows = db.execute(
        base.order_by(
            CommerceProduct.platform_updated_at.desc(),
            CommerceProduct.id.desc(),
        )
        .offset((selected_page - 1) * selected_per_page)
        .limit(selected_per_page)
    ).all()
    return _page_result(
        items=[
            product_view(product, link=link, internal_product=internal_product)
            for product, link, internal_product in rows
        ],
        total=total,
        page=selected_page,
        per_page=selected_per_page,
    )


def ad_entity_view(entity: object) -> dict[str, object]:
    return {
        "id": int(getattr(entity, "id")),
        "connection_id": int(getattr(entity, "connection_id")),
        "provider": _enum_value(getattr(entity, "provider"), Provider),
        "entity_type": _enum_value(getattr(entity, "entity_type"), AdEntityType),
        "external_entity_id": str(getattr(entity, "external_entity_id")),
        "external_parent_id": getattr(entity, "external_parent_id", None),
        "name": str(getattr(entity, "name")),
        "status": _enum_value(
            getattr(entity, "normalized_status"),
            AdEntityStatus,
        ),
        "raw_status": str(getattr(entity, "raw_status")),
        "platform_updated_at": _utc_iso(getattr(entity, "platform_updated_at")),
        "display_date": _display_date(getattr(entity, "platform_updated_at")),
    }


def ad_metric_view(metric: object) -> dict[str, object]:
    def optional_decimal(name: str, scale: int = 6) -> str | None:
        value = getattr(metric, name, None)
        return decimal_text(value, scale=scale) if value is not None else None

    return {
        "id": int(getattr(metric, "id")),
        "connection_id": int(getattr(metric, "connection_id")),
        "provider": _enum_value(getattr(metric, "provider"), Provider),
        "entity_type": _enum_value(getattr(metric, "entity_type"), AdEntityType),
        "external_entity_id": str(getattr(metric, "external_entity_id")),
        "stat_date": getattr(metric, "stat_date").isoformat(),
        "granularity": _enum_value(
            getattr(metric, "granularity"),
            MetricGranularity,
        ),
        "spend": decimal_text(getattr(metric, "spend"), scale=2),
        "impressions": int(getattr(metric, "impressions")),
        "clicks": int(getattr(metric, "clicks")),
        "orders": int(getattr(metric, "orders")),
        "attributed_sales": decimal_text(
            getattr(metric, "attributed_sales"),
            scale=2,
        ),
        "ctr": optional_decimal("ctr"),
        "cvr": optional_decimal("cvr"),
        "roi": optional_decimal("roi"),
        "play_count": getattr(metric, "play_count", None),
        "play_rate": optional_decimal("play_rate"),
        "currency": str(getattr(metric, "currency")),
    }


def list_ad_entities(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
    entity_type: AdEntityType | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
    allowed_connection_ids: Collection[int] | None = None,
) -> PageResult:
    selected_page, selected_per_page = _pagination(page, per_page)
    conditions = _common_conditions(
        CommerceAdEntity,
        provider=provider,
        connection_id=connection_id,
        allowed_connection_ids=allowed_connection_ids,
    )
    conditions.extend(
        (
            CommerceAdEntity.platform_updated_at >= reporting_range.start_at,
            CommerceAdEntity.platform_updated_at < reporting_range.end_at,
        )
    )
    if entity_type is not None:
        if not isinstance(entity_type, AdEntityType):
            raise ValueError("entity_type must be an AdEntityType")
        conditions.append(CommerceAdEntity.entity_type == entity_type)
    selected_search = sanitize_search(search)
    if selected_search is not None:
        pattern = _like_pattern(selected_search)
        conditions.append(
            or_(
                CommerceAdEntity.external_entity_id.ilike(pattern, escape="\\"),
                CommerceAdEntity.name.ilike(pattern, escape="\\"),
            )
        )
    base = select(CommerceAdEntity).where(*conditions)
    total = int(
        db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        or 0
    )
    rows = db.scalars(
        base.order_by(
            CommerceAdEntity.platform_updated_at.desc(),
            CommerceAdEntity.id.desc(),
        )
        .offset((selected_page - 1) * selected_per_page)
        .limit(selected_per_page)
    ).all()
    return _page_result(
        items=[ad_entity_view(row) for row in rows],
        total=total,
        page=selected_page,
        per_page=selected_per_page,
    )


def list_ad_metrics(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
    entity_type: AdEntityType | None = None,
    granularity: MetricGranularity | None = None,
    page: int = 1,
    per_page: int = 50,
    allowed_connection_ids: Collection[int] | None = None,
) -> PageResult:
    selected_page, selected_per_page = _pagination(page, per_page)
    conditions = _common_conditions(
        CommerceAdDailyMetric,
        provider=provider,
        connection_id=connection_id,
        allowed_connection_ids=allowed_connection_ids,
    )
    conditions.extend(
        (
            CommerceAdDailyMetric.stat_date >= reporting_range.date_from,
            CommerceAdDailyMetric.stat_date <= reporting_range.date_to,
        )
    )
    if entity_type is not None:
        if not isinstance(entity_type, AdEntityType):
            raise ValueError("entity_type must be an AdEntityType")
        conditions.append(CommerceAdDailyMetric.entity_type == entity_type)
    if granularity is not None:
        if not isinstance(granularity, MetricGranularity):
            raise ValueError("granularity must be a MetricGranularity")
        conditions.append(CommerceAdDailyMetric.granularity == granularity)
    base = select(CommerceAdDailyMetric).where(*conditions)
    total = int(
        db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        or 0
    )
    rows = db.scalars(
        base.order_by(
            CommerceAdDailyMetric.stat_date.desc(),
            CommerceAdDailyMetric.id.desc(),
        )
        .offset((selected_page - 1) * selected_per_page)
        .limit(selected_per_page)
    ).all()
    return _page_result(
        items=[ad_metric_view(row) for row in rows],
        total=total,
        page=selected_page,
        per_page=selected_per_page,
    )


def overview(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
) -> dict[str, object]:
    """Aggregate reconciled commerce and ads without mixing source families."""

    if not isinstance(reporting_range, ReportingRange):
        raise ValueError("reporting_range must be a ReportingRange")
    connection_conditions: list[object] = []
    if provider is not None:
        if not isinstance(provider, Provider):
            raise ValueError("provider must be a Provider")
        connection_conditions.append(IntegrationConnection.provider == provider)
    if connection_id is not None:
        if type(connection_id) is not int or connection_id <= 0:
            raise ValueError("connection_id must be a positive integer")
        connection_conditions.append(IntegrationConnection.id == connection_id)
    connections = db.scalars(
        select(IntegrationConnection).where(*connection_conditions)
    ).all()

    daily = {
        reporting_range.date_from + timedelta(days=offset): {
            "actual_sales": Decimal("0"),
            "order_count": 0,
            "refund_amount": Decimal("0"),
            "ad_spend": Decimal("0"),
            "ad_attributed_sales": Decimal("0"),
        }
        for offset in range(reporting_range.days)
    }
    source_breakdown = {"order_ledger": 0, "provider_daily": 0, "none": 0}
    excluded_currencies: set[str] = set()
    excluded_currency_rows = 0
    missing_paid_time = 0

    for connection in connections:
        report = connection.capability_report if isinstance(connection.capability_report, dict) else {}
        source = report.get("overview_commerce_source")
        if source == "order_ledger":
            source_breakdown["order_ledger"] += 1
            qualifying = (OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.COMPLETED)
            order_rows = db.scalars(
                select(CommerceOrder).where(
                    CommerceOrder.connection_id == connection.id,
                    CommerceOrder.normalized_status.in_(qualifying),
                    CommerceOrder.paid_at.is_not(None),
                    CommerceOrder.paid_at >= reporting_range.start_at,
                    CommerceOrder.paid_at < reporting_range.end_at,
                )
            ).all()
            for order in order_rows:
                if order.currency != "CNY":
                    excluded_currency_rows += 1
                    excluded_currencies.add(order.currency)
                    continue
                day = order.paid_at.astimezone(SHANGHAI).date()
                if day in daily:
                    daily[day]["actual_sales"] += order.paid_amount
                    daily[day]["order_count"] += 1
            missing_paid_time += int(
                db.scalar(
                    select(func.count()).select_from(CommerceOrder).where(
                        CommerceOrder.connection_id == connection.id,
                        CommerceOrder.normalized_status.in_(qualifying),
                        CommerceOrder.currency == "CNY",
                        CommerceOrder.paid_at.is_(None),
                        CommerceOrder.platform_updated_at >= reporting_range.start_at,
                        CommerceOrder.platform_updated_at < reporting_range.end_at,
                    )
                )
                or 0
            )
            refund_rows = db.scalars(
                select(CommerceRefund).where(
                    CommerceRefund.connection_id == connection.id,
                    CommerceRefund.normalized_status == RefundStatus.COMPLETED,
                    CommerceRefund.completed_at.is_not(None),
                    CommerceRefund.completed_at >= reporting_range.start_at,
                    CommerceRefund.completed_at < reporting_range.end_at,
                )
            ).all()
            for refund in refund_rows:
                if refund.currency != "CNY":
                    excluded_currency_rows += 1
                    excluded_currencies.add(refund.currency)
                    continue
                day = refund.completed_at.astimezone(SHANGHAI).date()
                if day in daily:
                    daily[day]["refund_amount"] += refund.amount
        elif source == "provider_daily":
            source_breakdown["provider_daily"] += 1
            rows = db.scalars(
                select(CommerceDailyMetric).where(
                    CommerceDailyMetric.connection_id == connection.id,
                    CommerceDailyMetric.stat_date >= reporting_range.date_from,
                    CommerceDailyMetric.stat_date <= reporting_range.date_to,
                    CommerceDailyMetric.granularity == MetricGranularity.DAY,
                )
            ).all()
            for metric in rows:
                if metric.currency != "CNY":
                    excluded_currency_rows += 1
                    excluded_currencies.add(metric.currency)
                    continue
                target = daily[metric.stat_date]
                target["actual_sales"] += metric.actual_sales
                target["order_count"] += metric.order_count
                target["refund_amount"] += metric.refund_amount
        else:
            source_breakdown["none"] += 1

        ad_level = report.get("overview_ad_entity_type")
        try:
            selected_ad_level = AdEntityType(ad_level) if ad_level is not None else None
        except ValueError:
            selected_ad_level = None
        if selected_ad_level is None:
            continue
        ad_rows = db.scalars(
            select(CommerceAdDailyMetric).where(
                CommerceAdDailyMetric.connection_id == connection.id,
                CommerceAdDailyMetric.entity_type == selected_ad_level,
                CommerceAdDailyMetric.stat_date >= reporting_range.date_from,
                CommerceAdDailyMetric.stat_date <= reporting_range.date_to,
                CommerceAdDailyMetric.granularity == MetricGranularity.DAY,
            )
        ).all()
        for metric in ad_rows:
            if metric.currency != "CNY":
                excluded_currency_rows += 1
                excluded_currencies.add(metric.currency)
                continue
            target = daily[metric.stat_date]
            target["ad_spend"] += metric.spend
            target["ad_attributed_sales"] += metric.attributed_sales

    actual_sales = sum(
        (values["actual_sales"] for values in daily.values()),
        Decimal("0"),
    )
    order_count = sum(int(values["order_count"]) for values in daily.values())
    refund_amount = sum(
        (values["refund_amount"] for values in daily.values()),
        Decimal("0"),
    )
    ad_spend = sum(
        (values["ad_spend"] for values in daily.values()),
        Decimal("0"),
    )
    ad_attributed_sales = sum(
        (values["ad_attributed_sales"] for values in daily.values()),
        Decimal("0"),
    )
    average_order_value = (
        actual_sales / Decimal(order_count) if order_count else Decimal("0")
    )
    return {
        "actual_sales": decimal_text(actual_sales, scale=2),
        "order_count": order_count,
        "refund_amount": decimal_text(refund_amount, scale=2),
        "average_order_value": decimal_text(average_order_value, scale=2),
        "ad_spend": decimal_text(ad_spend, scale=2),
        "ad_attributed_sales": decimal_text(ad_attributed_sales, scale=2),
        "daily": [
            {
                "date": day.isoformat(),
                "actual_sales": decimal_text(values["actual_sales"], scale=2),
                "order_count": int(values["order_count"]),
                "refund_amount": decimal_text(values["refund_amount"], scale=2),
                "ad_spend": decimal_text(values["ad_spend"], scale=2),
                "ad_attributed_sales": decimal_text(
                    values["ad_attributed_sales"],
                    scale=2,
                ),
            }
            for day, values in sorted(daily.items())
        ],
        "source_breakdown": source_breakdown,
        "data_quality": {
            "missing_paid_time_orders": missing_paid_time,
            "excluded_currency_rows": excluded_currency_rows,
            "excluded_currencies": sorted(excluded_currencies),
        },
    }


def sync_run_view(
    run: IntegrationSyncRun,
    checkpoint: IntegrationSyncCheckpoint,
    connection: IntegrationConnection,
) -> dict[str, object]:
    business_time = run.started_at or run.created_at
    return {
        "id": run.id,
        "parent_run_id": run.parent_run_id,
        "checkpoint_id": checkpoint.id,
        "connection_id": connection.id,
        "provider": connection.provider.value,
        "connection_name": connection.display_name,
        "source": run.source.value,
        "status": run.status.value,
        "resource_type": run.resource_type.value,
        "window_start": _utc_iso(run.window_start),
        "window_end": _utc_iso(run.window_end),
        "progress": decimal_text(run.progress, scale=6),
        "records_read": run.records_read,
        "records_written": run.records_written,
        "records_skipped": run.records_skipped,
        "records_quarantined": run.records_quarantined,
        "has_cursor": checkpoint.cursor is not None,
        "watermark_at": _utc_iso(checkpoint.watermark_at),
        "failure_code": run.failure_code,
        "failure_summary": run.failure_summary,
        "created_at": _utc_iso(run.created_at),
        "started_at": _utc_iso(run.started_at),
        "ended_at": _utc_iso(run.ended_at),
        "display_date": _display_date(business_time),
    }


def list_sync_runs(
    db: Session,
    *,
    reporting_range: ReportingRange,
    provider: Provider | None = None,
    connection_id: int | None = None,
    status: SyncStatus | None = None,
    source: SyncSource | None = None,
    resource_type: ResourceType | None = None,
    page: int = 1,
    per_page: int = 50,
) -> PageResult:
    selected_page, selected_per_page = _pagination(page, per_page)
    business_time = func.coalesce(
        IntegrationSyncRun.started_at,
        IntegrationSyncRun.created_at,
    )
    conditions = [
        business_time >= reporting_range.start_at,
        business_time < reporting_range.end_at,
    ]
    if provider is not None:
        conditions.append(IntegrationConnection.provider == provider)
    if connection_id is not None:
        if type(connection_id) is not int or connection_id <= 0:
            raise ValueError("connection_id must be a positive integer")
        conditions.append(IntegrationConnection.id == connection_id)
    if status is not None:
        if not isinstance(status, SyncStatus):
            raise ValueError("status must be a SyncStatus")
        conditions.append(IntegrationSyncRun.status == status)
    if source is not None:
        if not isinstance(source, SyncSource):
            raise ValueError("source must be a SyncSource")
        conditions.append(IntegrationSyncRun.source == source)
    if resource_type is not None:
        if not isinstance(resource_type, ResourceType):
            raise ValueError("resource_type must be a ResourceType")
        conditions.append(IntegrationSyncRun.resource_type == resource_type)
    base = (
        select(IntegrationSyncRun, IntegrationSyncCheckpoint, IntegrationConnection)
        .join(
            IntegrationSyncCheckpoint,
            IntegrationSyncCheckpoint.id == IntegrationSyncRun.checkpoint_id,
        )
        .join(
            IntegrationConnection,
            IntegrationConnection.id == IntegrationSyncCheckpoint.connection_id,
        )
        .where(*conditions)
    )
    total = int(
        db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        or 0
    )
    rows = db.execute(
        base.order_by(business_time.desc(), IntegrationSyncRun.id.desc())
        .offset((selected_page - 1) * selected_per_page)
        .limit(selected_per_page)
    ).all()
    return _page_result(
        items=[sync_run_view(run, checkpoint, connection) for run, checkpoint, connection in rows],
        total=total,
        page=selected_page,
        per_page=selected_per_page,
    )


__all__ = [
    "ALLOWED_PAGE_SIZES",
    "MAX_REPORTING_DAYS",
    "PageResult",
    "ReportingRange",
    "ad_entity_view",
    "ad_metric_view",
    "decimal_text",
    "list_ad_entities",
    "list_ad_metrics",
    "list_orders",
    "list_products",
    "list_refunds",
    "list_sync_runs",
    "order_view",
    "overview",
    "product_view",
    "refund_view",
    "sanitize_search",
    "sync_run_view",
]
