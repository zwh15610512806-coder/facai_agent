"""Normalized, provider-neutral ecommerce business models."""

from sqlalchemy import (
    JSON,
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
from sqlalchemy.orm import declared_attr

from database import Base
from integrations.types import (
    AccountStatus,
    AdEntityStatus,
    AdEntityType,
    EventIdScope,
    EventProcessingStatus,
    EventRoutingStatus,
    FinanceTransactionStatus,
    MetricGranularity,
    OrderStatus,
    ProductStatus,
    Provider,
    RefundStatus,
    SettlementStatus,
    ShipmentStatus,
    persisted_enum,
    utc_now,
)


def _json_type():
    return JSON().with_variant(JSONB(), "postgresql")


def _connection_provider_fk(table_name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ("connection_id", "provider"),
        ("integration_connections.id", "integration_connections.provider"),
        name=f"fk_{table_name}_connection_provider",
        ondelete="CASCADE",
    )


def _currency_constraint(table_name: str) -> CheckConstraint:
    return CheckConstraint(
        "length(currency) = 3 "
        "AND substr(currency, 1, 1) BETWEEN 'A' AND 'Z' "
        "AND substr(currency, 2, 1) BETWEEN 'A' AND 'Z' "
        "AND substr(currency, 3, 1) BETWEEN 'A' AND 'Z'",
        name=f"ck_{table_name}_currency_format",
    )


class _CommerceEnvelope:
    connection_id = Column(Integer, nullable=False)

    @declared_attr
    def provider(cls):
        return Column(
            persisted_enum(
                Provider,
                name=f"ck_{cls.__tablename__}_provider",
            ),
            nullable=False,
        )

    platform_updated_at = Column(DateTime(timezone=True), nullable=False)
    platform_metadata = Column(_json_type(), nullable=False, default=dict)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class CommerceShop(_CommerceEnvelope, Base):
    __tablename__ = "commerce_shops"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_shop_id",
            name="uq_commerce_shops_connection_external_shop",
        ),
        _connection_provider_fk("commerce_shops"),
        Index("ix_commerce_shops_provider_status", "provider", "normalized_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_shop_id = Column(String(255), nullable=False)
    name = Column(String(500), nullable=False)
    normalized_status = Column(
        persisted_enum(
            AccountStatus,
            name="ck_commerce_shops_normalized_status",
        ),
        nullable=False,
        default=AccountStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)


class CommerceProduct(_CommerceEnvelope, Base):
    __tablename__ = "commerce_products"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_product_id",
            name="uq_commerce_products_connection_external_product",
        ),
        _connection_provider_fk("commerce_products"),
        _currency_constraint("commerce_products"),
        CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_commerce_products_price_nonnegative",
        ),
        Index(
            "ix_commerce_products_provider_status",
            "provider",
            "normalized_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_product_id = Column(String(255), nullable=False)
    external_shop_id = Column(String(255))
    title = Column(String(1000), nullable=False)
    normalized_status = Column(
        persisted_enum(
            ProductStatus,
            name="ck_commerce_products_normalized_status",
        ),
        nullable=False,
        default=ProductStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    category = Column(String(500))
    price = Column(Numeric(20, 2))
    currency = Column(String(3))


class CommerceSku(_CommerceEnvelope, Base):
    __tablename__ = "commerce_skus"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_sku_id",
            name="uq_commerce_skus_connection_external_sku",
        ),
        _connection_provider_fk("commerce_skus"),
        _currency_constraint("commerce_skus"),
        CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_commerce_skus_price_nonnegative",
        ),
        Index("ix_commerce_skus_product", "connection_id", "external_product_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_sku_id = Column(String(255), nullable=False)
    external_product_id = Column(String(255), nullable=False)
    title = Column(String(1000))
    attributes = Column(_json_type(), nullable=False, default=dict)
    normalized_status = Column(
        persisted_enum(
            ProductStatus,
            name="ck_commerce_skus_normalized_status",
        ),
        nullable=False,
        default=ProductStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    price = Column(Numeric(20, 2))
    currency = Column(String(3))


class CommerceInventorySnapshot(_CommerceEnvelope, Base):
    __tablename__ = "commerce_inventory_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_sku_id",
            "captured_at",
            name="uq_commerce_inventory_connection_sku_captured",
        ),
        _connection_provider_fk("commerce_inventory_snapshots"),
        CheckConstraint(
            "quantity >= 0 AND (available_quantity IS NULL OR available_quantity >= 0)",
            name="ck_commerce_inventory_quantities_nonnegative",
        ),
        Index("ix_commerce_inventory_captured_at", "captured_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_sku_id = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    available_quantity = Column(Integer)
    captured_at = Column(DateTime(timezone=True), nullable=False)


class CommerceProductLink(Base):
    __tablename__ = "commerce_product_links"
    __table_args__ = (
        UniqueConstraint(
            "commerce_product_id",
            name="uq_commerce_product_links_commerce_product",
        ),
        ForeignKeyConstraint(
            ("commerce_product_id",),
            ("commerce_products.id",),
            name="fk_commerce_product_links_commerce_product",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("product_id",),
            ("products.id",),
            name="fk_commerce_product_links_product",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(linked_by_session_digest) = 64",
            name="ck_commerce_product_links_linked_by_session_digest_length",
        ),
        Index("ix_commerce_product_links_product_id", "product_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    commerce_product_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    linked_by_session_digest = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class CommerceOrder(_CommerceEnvelope, Base):
    __tablename__ = "commerce_orders"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_order_id",
            name="uq_commerce_orders_connection_external_order",
        ),
        _connection_provider_fk("commerce_orders"),
        _currency_constraint("commerce_orders"),
        CheckConstraint(
            "length(buyer_digest) = 64",
            name="ck_commerce_orders_buyer_digest_length",
        ),
        CheckConstraint(
            "order_amount >= 0 AND paid_amount >= 0 "
            "AND discount_amount >= 0 AND shipping_amount >= 0",
            name="ck_commerce_orders_amounts_nonnegative",
        ),
        Index("ix_commerce_orders_status", "normalized_status", "ordered_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_order_id = Column(String(255), nullable=False)
    external_shop_id = Column(String(255))
    normalized_status = Column(
        persisted_enum(
            OrderStatus,
            name="ck_commerce_orders_normalized_status",
        ),
        nullable=False,
        default=OrderStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    buyer_digest = Column(String(64))
    province = Column(String(100))
    city = Column(String(100))
    currency = Column(String(3), nullable=False)
    order_amount = Column(Numeric(20, 2), nullable=False)
    paid_amount = Column(Numeric(20, 2), nullable=False)
    discount_amount = Column(Numeric(20, 2), nullable=False)
    shipping_amount = Column(Numeric(20, 2), nullable=False)
    ordered_at = Column(DateTime(timezone=True))
    paid_at = Column(DateTime(timezone=True))
    shipped_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))


class CommerceOrderItem(_CommerceEnvelope, Base):
    __tablename__ = "commerce_order_items"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_item_id",
            name="uq_commerce_order_items_connection_external_item",
        ),
        _connection_provider_fk("commerce_order_items"),
        _currency_constraint("commerce_order_items"),
        CheckConstraint(
            "quantity > 0 AND unit_amount >= 0 AND paid_amount >= 0",
            name="ck_commerce_order_items_amounts_and_quantity",
        ),
        Index("ix_commerce_order_items_order", "connection_id", "external_order_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_item_id = Column(String(255), nullable=False)
    external_order_id = Column(String(255), nullable=False)
    external_product_id = Column(String(255))
    external_sku_id = Column(String(255))
    title = Column(String(1000), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_amount = Column(Numeric(20, 2), nullable=False)
    paid_amount = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), nullable=False)


class CommerceRefund(_CommerceEnvelope, Base):
    __tablename__ = "commerce_refunds"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_refund_id",
            name="uq_commerce_refunds_connection_external_refund",
        ),
        _connection_provider_fk("commerce_refunds"),
        _currency_constraint("commerce_refunds"),
        CheckConstraint(
            "amount >= 0",
            name="ck_commerce_refunds_amount_nonnegative",
        ),
        Index("ix_commerce_refunds_order", "connection_id", "external_order_id"),
        Index("ix_commerce_refunds_status", "normalized_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_refund_id = Column(String(255), nullable=False)
    external_order_id = Column(String(255), nullable=False)
    external_item_id = Column(String(255))
    normalized_status = Column(
        persisted_enum(
            RefundStatus,
            name="ck_commerce_refunds_normalized_status",
        ),
        nullable=False,
        default=RefundStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    amount = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    reason_code = Column(String(255))
    refund_created_at = Column(DateTime(timezone=True))
    refund_updated_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))


class CommerceShipment(_CommerceEnvelope, Base):
    __tablename__ = "commerce_shipments"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_shipment_id",
            name="uq_commerce_shipments_connection_external_shipment",
        ),
        _connection_provider_fk("commerce_shipments"),
        Index("ix_commerce_shipments_order", "connection_id", "external_order_id"),
        Index("ix_commerce_shipments_status", "normalized_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_shipment_id = Column(String(255), nullable=False)
    external_order_id = Column(String(255), nullable=False)
    normalized_status = Column(
        persisted_enum(
            ShipmentStatus,
            name="ck_commerce_shipments_normalized_status",
        ),
        nullable=False,
        default=ShipmentStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    carrier_code = Column(String(255))
    tracking_number = Column(String(255))
    shipped_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))


class CommerceSettlement(_CommerceEnvelope, Base):
    __tablename__ = "commerce_settlements"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_settlement_id",
            name="uq_commerce_settlements_connection_external_settlement",
        ),
        _connection_provider_fk("commerce_settlements"),
        _currency_constraint("commerce_settlements"),
        Index("ix_commerce_settlements_date", "settlement_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_settlement_id = Column(String(255), nullable=False)
    external_order_id = Column(String(255))
    normalized_status = Column(
        persisted_enum(
            SettlementStatus,
            name="ck_commerce_settlements_normalized_status",
        ),
        nullable=False,
        default=SettlementStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False)
    gross_amount = Column(Numeric(20, 2), nullable=False)
    fee_amount = Column(Numeric(20, 2), nullable=False)
    net_amount = Column(Numeric(20, 2), nullable=False)
    settlement_date = Column(Date, nullable=False)


class CommerceDailyMetric(_CommerceEnvelope, Base):
    __tablename__ = "commerce_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "stat_date",
            "granularity",
            name="uq_commerce_daily_metrics_connection_date_granularity",
        ),
        _connection_provider_fk("commerce_daily_metrics"),
        _currency_constraint("commerce_daily_metrics"),
        CheckConstraint(
            "order_count >= 0 AND refund_count >= 0 "
            "AND visitor_count >= 0 AND buyer_count >= 0",
            name="ck_commerce_daily_metrics_counts_nonnegative",
        ),
        Index("ix_commerce_daily_metrics_date", "stat_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    granularity = Column(
        persisted_enum(
            MetricGranularity,
            name="ck_commerce_daily_metrics_granularity",
        ),
        nullable=False,
    )
    actual_sales = Column(Numeric(20, 2), nullable=False)
    order_count = Column(Integer, nullable=False)
    refund_amount = Column(Numeric(20, 2), nullable=False)
    refund_count = Column(Integer, nullable=False)
    visitor_count = Column(Integer, nullable=False)
    buyer_count = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)


class CommerceAdAccount(_CommerceEnvelope, Base):
    __tablename__ = "commerce_ad_accounts"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_ad_account_id",
            name="uq_commerce_ad_accounts_connection_external_account",
        ),
        _connection_provider_fk("commerce_ad_accounts"),
        _currency_constraint("commerce_ad_accounts"),
        Index("ix_commerce_ad_accounts_status", "normalized_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_ad_account_id = Column(String(255), nullable=False)
    name = Column(String(500), nullable=False)
    normalized_status = Column(
        persisted_enum(
            AccountStatus,
            name="ck_commerce_ad_accounts_normalized_status",
        ),
        nullable=False,
        default=AccountStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False)


class CommerceAdEntity(_CommerceEnvelope, Base):
    __tablename__ = "commerce_ad_entities"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_entity_id",
            name="uq_commerce_ad_entities_connection_type_external",
        ),
        _connection_provider_fk("commerce_ad_entities"),
        Index("ix_commerce_ad_entities_parent", "entity_type", "external_parent_id"),
        Index("ix_commerce_ad_entities_status", "normalized_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(
        persisted_enum(
            AdEntityType,
            name="ck_commerce_ad_entities_entity_type",
        ),
        nullable=False,
    )
    external_entity_id = Column(String(255), nullable=False)
    external_parent_id = Column(String(255))
    name = Column(String(500), nullable=False)
    normalized_status = Column(
        persisted_enum(
            AdEntityStatus,
            name="ck_commerce_ad_entities_normalized_status",
        ),
        nullable=False,
        default=AdEntityStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)


class CommerceAdDailyMetric(_CommerceEnvelope, Base):
    __tablename__ = "commerce_ad_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_entity_id",
            "stat_date",
            "granularity",
            name="uq_commerce_ad_metrics_connection_entity_date_granularity",
        ),
        _connection_provider_fk("commerce_ad_daily_metrics"),
        _currency_constraint("commerce_ad_daily_metrics"),
        CheckConstraint(
            "impressions >= 0 AND clicks >= 0 AND orders >= 0 "
            "AND (play_count IS NULL OR play_count >= 0)",
            name="ck_commerce_ad_daily_metrics_counts_nonnegative",
        ),
        Index("ix_commerce_ad_daily_metrics_date", "stat_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(
        persisted_enum(
            AdEntityType,
            name="ck_commerce_ad_daily_metrics_entity_type",
        ),
        nullable=False,
    )
    external_entity_id = Column(String(255), nullable=False)
    stat_date = Column(Date, nullable=False)
    granularity = Column(
        persisted_enum(
            MetricGranularity,
            name="ck_commerce_ad_daily_metrics_granularity",
        ),
        nullable=False,
    )
    spend = Column(Numeric(20, 2), nullable=False)
    impressions = Column(Integer, nullable=False)
    clicks = Column(Integer, nullable=False)
    orders = Column(Integer, nullable=False)
    attributed_sales = Column(Numeric(20, 2), nullable=False)
    ctr = Column(Numeric(20, 6))
    cvr = Column(Numeric(20, 6))
    roi = Column(Numeric(20, 6))
    play_count = Column(Integer)
    play_rate = Column(Numeric(20, 6))
    currency = Column(String(3), nullable=False)


class CommerceAdBalanceSnapshot(_CommerceEnvelope, Base):
    __tablename__ = "commerce_ad_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_ad_account_id",
            "captured_at",
            name="uq_commerce_ad_balances_connection_account_captured",
        ),
        _connection_provider_fk("commerce_ad_balance_snapshots"),
        _currency_constraint("commerce_ad_balance_snapshots"),
        Index("ix_commerce_ad_balance_snapshots_captured_at", "captured_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_ad_account_id = Column(String(255), nullable=False)
    balance = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)


class CommerceAdFinanceTransaction(_CommerceEnvelope, Base):
    __tablename__ = "commerce_ad_finance_transactions"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_transaction_id",
            name="uq_commerce_ad_finance_connection_external_transaction",
        ),
        _connection_provider_fk("commerce_ad_finance_transactions"),
        _currency_constraint("commerce_ad_finance_transactions"),
        Index("ix_commerce_ad_finance_transaction_at", "transaction_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_transaction_id = Column(String(255), nullable=False)
    external_ad_account_id = Column(String(255), nullable=False)
    transaction_type = Column(String(255), nullable=False)
    amount = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    normalized_status = Column(
        persisted_enum(
            FinanceTransactionStatus,
            name="ck_commerce_ad_finance_transactions_normalized_status",
        ),
        nullable=False,
        default=FinanceTransactionStatus.UNKNOWN,
    )
    raw_status = Column(String(255), nullable=False)
    transaction_at = Column(DateTime(timezone=True), nullable=False)


class CommerceEventInbox(Base):
    __tablename__ = "commerce_event_inbox"
    __table_args__ = (
        UniqueConstraint(
            "dedupe_key",
            name="uq_commerce_event_inbox_dedupe_key",
        ),
        ForeignKeyConstraint(
            ("connection_id", "provider"),
            ("integration_connections.id", "integration_connections.provider"),
            name="fk_commerce_event_inbox_connection_provider",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(dedupe_key) = 64",
            name="ck_commerce_event_inbox_dedupe_key_length",
        ),
        Index(
            "ix_commerce_event_inbox_processing",
            "processing_status",
            "received_at",
        ),
        Index(
            "ix_commerce_event_inbox_subject",
            "provider",
            "external_subject_id",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(Integer)
    provider = Column(
        persisted_enum(Provider, name="ck_commerce_event_inbox_provider"),
        nullable=False,
    )
    external_event_id = Column(String(255), nullable=False)
    external_subject_id = Column(String(255), nullable=False)
    event_id_scope = Column(
        persisted_enum(
            EventIdScope,
            name="ck_commerce_event_inbox_event_id_scope",
        ),
        nullable=False,
    )
    dedupe_key = Column(String(64), nullable=False)
    event_type = Column(String(255), nullable=False)
    external_entity_id = Column(String(255))
    platform_updated_at = Column(DateTime(timezone=True), nullable=False)
    sanitized_payload = Column(_json_type(), nullable=False, default=dict)
    routing_status = Column(
        persisted_enum(
            EventRoutingStatus,
            name="ck_commerce_event_inbox_routing_status",
        ),
        nullable=False,
        default=EventRoutingStatus.PENDING,
    )
    processing_status = Column(
        persisted_enum(
            EventProcessingStatus,
            name="ck_commerce_event_inbox_processing_status",
        ),
        nullable=False,
        default=EventProcessingStatus.RECEIVED,
    )
    received_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    routed_at = Column(DateTime(timezone=True))
    queued_at = Column(DateTime(timezone=True))
    processing_started_at = Column(DateTime(timezone=True))
    processed_at = Column(DateTime(timezone=True))
    last_error_code = Column(String(100))
    last_error_summary = Column(Text)
