import copy
import hashlib
import hmac
import json
import unittest
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import database
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
from database import Base
from integration_models import (
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationJob,
    IntegrationSyncCheckpoint,
    IntegrationSyncError,
    IntegrationSyncRun,
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
from integrations.sync.writer import (
    TABLE_SPECS,
    WriteResult,
    is_cny_aggregatable,
    write_records,
)
from integrations.types import (
    AccountStatus,
    AdEntityStatus,
    AdEntityType,
    AuthorizationStatus,
    CheckpointStatus,
    ConnectionStatus,
    ConnectionType,
    FinanceTransactionStatus,
    MetricGranularity,
    NormalizedRecord,
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
from tests.postgres_test_support import requires_disposable_postgres
from tests.test_integration_models import _require_disposable_postgres_url

NOW = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)

SCHEMA_BY_RESOURCE = {
    ResourceType.SHOPS: NormalizedShop,
    ResourceType.PRODUCTS: NormalizedProduct,
    ResourceType.SKUS: NormalizedSku,
    ResourceType.INVENTORY: NormalizedInventory,
    ResourceType.ORDERS: NormalizedOrder,
    ResourceType.ORDER_ITEMS: NormalizedOrderItem,
    ResourceType.REFUNDS: NormalizedRefund,
    ResourceType.SHIPMENTS: NormalizedShipment,
    ResourceType.SETTLEMENTS: NormalizedSettlement,
    ResourceType.DAILY_METRICS: NormalizedDailyMetric,
    ResourceType.AD_ACCOUNTS: NormalizedAdAccount,
    ResourceType.AD_ENTITIES: NormalizedAdEntity,
    ResourceType.AD_DAILY_METRICS: NormalizedAdDailyMetric,
    ResourceType.AD_BALANCE_SNAPSHOTS: NormalizedAdBalanceSnapshot,
    ResourceType.AD_FINANCE_TRANSACTIONS: NormalizedAdFinanceTransaction,
}

GOLDEN_PAYLOADS = {
    ResourceType.SHOPS: {
        "external_shop_id": "shop-1",
        "name": "Golden shop",
        "normalized_status": AccountStatus.ACTIVE,
        "raw_status": "OPEN",
    },
    ResourceType.PRODUCTS: {
        "external_product_id": "product-1",
        "external_shop_id": "shop-1",
        "title": "Golden product",
        "normalized_status": ProductStatus.ON_SALE,
        "raw_status": "SELLING",
        "category": "cake",
        "price": "19.90",
        "currency": "CNY",
    },
    ResourceType.SKUS: {
        "external_sku_id": "sku-1",
        "external_product_id": "product-1",
        "title": "Golden SKU",
        "attributes": {"size": "small", "tags": ["fresh"]},
        "normalized_status": ProductStatus.ON_SALE,
        "raw_status": "SELLING",
        "price": "18.80",
        "currency": "CNY",
    },
    ResourceType.INVENTORY: {
        "external_sku_id": "sku-1",
        "quantity": 12,
        "available_quantity": 10,
        "captured_at": NOW,
    },
    ResourceType.ORDERS: {
        "external_order_id": "order-1",
        "external_shop_id": "shop-1",
        "normalized_status": OrderStatus.PAID,
        "raw_status": "WAIT_SEND",
        "buyer_digest": "a" * 64,
        "province": "Zhejiang",
        "city": "Hangzhou",
        "currency": "CNY",
        "order_amount": "120.00",
        "paid_amount": "110.00",
        "discount_amount": "10.00",
        "shipping_amount": "0.00",
        "created_at": NOW - timedelta(hours=2),
        "paid_at": NOW - timedelta(hours=1),
        "shipped_at": None,
        "completed_at": None,
    },
    ResourceType.ORDER_ITEMS: {
        "external_item_id": "item-1",
        "external_order_id": "order-1",
        "external_product_id": "product-1",
        "external_sku_id": "sku-1",
        "title": "Golden item",
        "quantity": 1,
        "unit_amount": "120.00",
        "paid_amount": "110.00",
        "currency": "CNY",
    },
    ResourceType.REFUNDS: {
        "external_refund_id": "refund-1",
        "external_order_id": "order-1",
        "external_item_id": "item-1",
        "normalized_status": RefundStatus.PROCESSING,
        "raw_status": "REFUNDING",
        "amount": "20.00",
        "currency": "CNY",
        "reason_code": "customer_request",
        "created_at": NOW - timedelta(minutes=30),
        "updated_at": NOW - timedelta(minutes=10),
        "completed_at": None,
    },
    ResourceType.SHIPMENTS: {
        "external_shipment_id": "shipment-1",
        "external_order_id": "order-1",
        "normalized_status": ShipmentStatus.SHIPPED,
        "raw_status": "PICKED_UP",
        "carrier_code": "SF",
        "tracking_number": "tracking-1",
        "shipped_at": NOW - timedelta(minutes=5),
        "delivered_at": None,
    },
    ResourceType.SETTLEMENTS: {
        "external_settlement_id": "settlement-1",
        "external_order_id": "order-1",
        "normalized_status": SettlementStatus.SETTLED,
        "raw_status": "SETTLED",
        "currency": "CNY",
        "gross_amount": "110.00",
        "fee_amount": "5.00",
        "net_amount": "105.00",
        "settlement_date": date(2026, 7, 14),
    },
    ResourceType.DAILY_METRICS: {
        "stat_date": date(2026, 7, 14),
        "granularity": MetricGranularity.DAY,
        "actual_sales": "110.00",
        "order_count": 1,
        "refund_amount": "0.00",
        "refund_count": 0,
        "visitor_count": 50,
        "buyer_count": 1,
        "currency": "CNY",
    },
    ResourceType.AD_ACCOUNTS: {
        "external_account_id": "ad-account-1",
        "name": "Golden ad account",
        "normalized_status": AccountStatus.ACTIVE,
        "raw_status": "ENABLE",
        "currency": "CNY",
    },
    ResourceType.AD_ENTITIES: {
        "entity_type": AdEntityType.CAMPAIGN,
        "external_entity_id": "campaign-1",
        "external_parent_id": "ad-account-1",
        "name": "Golden campaign",
        "normalized_status": AdEntityStatus.ACTIVE,
        "raw_status": "ENABLE",
    },
    ResourceType.AD_DAILY_METRICS: {
        "entity_type": AdEntityType.CAMPAIGN,
        "external_entity_id": "campaign-1",
        "stat_date": date(2026, 7, 14),
        "granularity": MetricGranularity.DAY,
        "spend": "50.00",
        "impressions": 1000,
        "clicks": 80,
        "orders": 5,
        "attributed_sales": "150.00",
        "ctr": "0.080000",
        "cvr": "0.062500",
        "roi": "3.000000",
        "play_count": 400,
        "play_rate": "0.400000",
        "currency": "CNY",
    },
    ResourceType.AD_BALANCE_SNAPSHOTS: {
        "external_account_id": "ad-account-1",
        "balance": "500.00",
        "currency": "CNY",
        "captured_at": NOW,
    },
    ResourceType.AD_FINANCE_TRANSACTIONS: {
        "external_transaction_id": "finance-1",
        "external_account_id": "ad-account-1",
        "transaction_type": "top_up",
        "amount": "100.00",
        "currency": "CNY",
        "normalized_status": FinanceTransactionStatus.COMPLETED,
        "raw_status": "SUCCESS",
        "transaction_at": NOW - timedelta(minutes=1),
    },
}

MONEY_FIELDS = {
    ResourceType.PRODUCTS: ("price",),
    ResourceType.SKUS: ("price",),
    ResourceType.ORDERS: (
        "order_amount",
        "paid_amount",
        "discount_amount",
        "shipping_amount",
    ),
    ResourceType.ORDER_ITEMS: ("unit_amount", "paid_amount"),
    ResourceType.REFUNDS: ("amount",),
    ResourceType.SETTLEMENTS: ("gross_amount", "fee_amount", "net_amount"),
    ResourceType.DAILY_METRICS: ("actual_sales", "refund_amount"),
    ResourceType.AD_DAILY_METRICS: (
        "spend",
        "attributed_sales",
        "ctr",
        "cvr",
        "roi",
        "play_rate",
    ),
    ResourceType.AD_BALANCE_SNAPSHOTS: ("balance",),
    ResourceType.AD_FINANCE_TRANSACTIONS: ("amount",),
}

MODEL_BY_RESOURCE = {
    ResourceType.SHOPS: CommerceShop,
    ResourceType.PRODUCTS: CommerceProduct,
    ResourceType.SKUS: CommerceSku,
    ResourceType.INVENTORY: CommerceInventorySnapshot,
    ResourceType.ORDERS: CommerceOrder,
    ResourceType.ORDER_ITEMS: CommerceOrderItem,
    ResourceType.REFUNDS: CommerceRefund,
    ResourceType.SHIPMENTS: CommerceShipment,
    ResourceType.SETTLEMENTS: CommerceSettlement,
    ResourceType.DAILY_METRICS: CommerceDailyMetric,
    ResourceType.AD_ACCOUNTS: CommerceAdAccount,
    ResourceType.AD_ENTITIES: CommerceAdEntity,
    ResourceType.AD_DAILY_METRICS: CommerceAdDailyMetric,
    ResourceType.AD_BALANCE_SNAPSHOTS: CommerceAdBalanceSnapshot,
    ResourceType.AD_FINANCE_TRANSACTIONS: CommerceAdFinanceTransaction,
}

CONFLICT_COLUMNS = {
    ResourceType.SHOPS: ("connection_id", "external_shop_id"),
    ResourceType.PRODUCTS: ("connection_id", "external_product_id"),
    ResourceType.SKUS: ("connection_id", "external_sku_id"),
    ResourceType.INVENTORY: ("connection_id", "external_sku_id", "captured_at"),
    ResourceType.ORDERS: ("connection_id", "external_order_id"),
    ResourceType.ORDER_ITEMS: ("connection_id", "external_item_id"),
    ResourceType.REFUNDS: ("connection_id", "external_refund_id"),
    ResourceType.SHIPMENTS: ("connection_id", "external_shipment_id"),
    ResourceType.SETTLEMENTS: ("connection_id", "external_settlement_id"),
    ResourceType.DAILY_METRICS: ("connection_id", "stat_date", "granularity"),
    ResourceType.AD_ACCOUNTS: ("connection_id", "external_ad_account_id"),
    ResourceType.AD_ENTITIES: (
        "connection_id",
        "entity_type",
        "external_entity_id",
    ),
    ResourceType.AD_DAILY_METRICS: (
        "connection_id",
        "entity_type",
        "external_entity_id",
        "stat_date",
        "granularity",
    ),
    ResourceType.AD_BALANCE_SNAPSHOTS: (
        "connection_id",
        "external_ad_account_id",
        "captured_at",
    ),
    ResourceType.AD_FINANCE_TRANSACTIONS: (
        "connection_id",
        "external_transaction_id",
    ),
}

ALIASED_COLUMNS = {
    ResourceType.ORDERS: {"created_at": "ordered_at"},
    ResourceType.REFUNDS: {
        "created_at": "refund_created_at",
        "updated_at": "refund_updated_at",
    },
    ResourceType.AD_ACCOUNTS: {
        "external_account_id": "external_ad_account_id"
    },
    ResourceType.AD_BALANCE_SNAPSHOTS: {
        "external_account_id": "external_ad_account_id"
    },
    ResourceType.AD_FINANCE_TRANSACTIONS: {
        "external_account_id": "external_ad_account_id"
    },
}

OPTIONAL_COLUMNS = {
    ResourceType.SHOPS: frozenset(),
    ResourceType.PRODUCTS: frozenset(
        {"external_shop_id", "category", "price", "currency"}
    ),
    ResourceType.SKUS: frozenset({"title", "price", "currency"}),
    ResourceType.INVENTORY: frozenset({"available_quantity"}),
    ResourceType.ORDERS: frozenset(
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
    ResourceType.ORDER_ITEMS: frozenset(
        {"external_product_id", "external_sku_id"}
    ),
    ResourceType.REFUNDS: frozenset(
        {
            "external_item_id",
            "reason_code",
            "refund_created_at",
            "refund_updated_at",
            "completed_at",
        }
    ),
    ResourceType.SHIPMENTS: frozenset(
        {"carrier_code", "tracking_number", "shipped_at", "delivered_at"}
    ),
    ResourceType.SETTLEMENTS: frozenset({"external_order_id"}),
    ResourceType.DAILY_METRICS: frozenset(),
    ResourceType.AD_ACCOUNTS: frozenset(),
    ResourceType.AD_ENTITIES: frozenset({"external_parent_id"}),
    ResourceType.AD_DAILY_METRICS: frozenset(
        {"ctr", "cvr", "roi", "play_count", "play_rate"}
    ),
    ResourceType.AD_BALANCE_SNAPSHOTS: frozenset(),
    ResourceType.AD_FINANCE_TRANSACTIONS: frozenset(),
}

MUTATION_BY_RESOURCE = {
    ResourceType.SHOPS: ("name", "Updated shop"),
    ResourceType.PRODUCTS: ("title", "Updated product"),
    ResourceType.SKUS: ("title", "Updated SKU"),
    ResourceType.INVENTORY: ("quantity", 20),
    ResourceType.ORDERS: ("city", "Ningbo"),
    ResourceType.ORDER_ITEMS: ("title", "Updated item"),
    ResourceType.REFUNDS: ("reason_code", "quality_issue"),
    ResourceType.SHIPMENTS: ("carrier_code", "YTO"),
    ResourceType.SETTLEMENTS: ("fee_amount", "6.00"),
    ResourceType.DAILY_METRICS: ("order_count", 2),
    ResourceType.AD_ACCOUNTS: ("name", "Updated ad account"),
    ResourceType.AD_ENTITIES: ("name", "Updated campaign"),
    ResourceType.AD_DAILY_METRICS: ("clicks", 90),
    ResourceType.AD_BALANCE_SNAPSHOTS: ("balance", "450.00"),
    ResourceType.AD_FINANCE_TRANSACTIONS: ("amount", "101.00"),
}

ENVELOPE_EXTERNAL_IDS = {
    ResourceType.SHOPS: "shop-1",
    ResourceType.PRODUCTS: "product-1",
    ResourceType.SKUS: "sku-1",
    ResourceType.INVENTORY: "sku-1",
    ResourceType.ORDERS: "order-1",
    ResourceType.ORDER_ITEMS: "item-1",
    ResourceType.REFUNDS: "refund-1",
    ResourceType.SHIPMENTS: "shipment-1",
    ResourceType.SETTLEMENTS: "settlement-1",
    ResourceType.DAILY_METRICS: "2026-07-14:day",
    ResourceType.AD_ACCOUNTS: "ad-account-1",
    ResourceType.AD_ENTITIES: "campaign-1",
    ResourceType.AD_DAILY_METRICS: "campaign:campaign-1:2026-07-14:day",
    ResourceType.AD_BALANCE_SNAPSHOTS: "ad-account-1:2026-07-14T02:00:00Z",
    ResourceType.AD_FINANCE_TRANSACTIONS: "finance-1",
}

STATUS_UNKNOWNS = {
    ResourceType.SHOPS: AccountStatus.UNKNOWN,
    ResourceType.PRODUCTS: ProductStatus.UNKNOWN,
    ResourceType.SKUS: ProductStatus.UNKNOWN,
    ResourceType.ORDERS: OrderStatus.UNKNOWN,
    ResourceType.REFUNDS: RefundStatus.UNKNOWN,
    ResourceType.SHIPMENTS: ShipmentStatus.UNKNOWN,
    ResourceType.SETTLEMENTS: SettlementStatus.UNKNOWN,
    ResourceType.AD_ACCOUNTS: AccountStatus.UNKNOWN,
    ResourceType.AD_ENTITIES: AdEntityStatus.UNKNOWN,
    ResourceType.AD_FINANCE_TRANSACTIONS: FinanceTransactionStatus.UNKNOWN,
}

WRITER_TABLES = (
    IntegrationAuthorization.__table__,
    IntegrationConnection.__table__,
    IntegrationJob.__table__,
    IntegrationSyncCheckpoint.__table__,
    IntegrationSyncRun.__table__,
    IntegrationSyncError.__table__,
) + tuple(model.__table__ for model in MODEL_BY_RESOURCE.values())

QUARANTINE_KEY = b"writer-quarantine-test-key-32-bytes-minimum"


class IntegrationWriterContractTests(unittest.TestCase):
    def test_every_resource_has_one_explicit_table_spec(self):
        self.assertEqual(set(TABLE_SPECS), set(ResourceType))
        for resource, spec in TABLE_SPECS.items():
            with self.subTest(resource=resource):
                self.assertIs(spec.table, MODEL_BY_RESOURCE[resource].__table__)
                self.assertIs(spec.schema, SCHEMA_BY_RESOURCE[resource])
                self.assertEqual(spec.conflict_columns, CONFLICT_COLUMNS[resource])
                self.assertEqual(spec.optional_columns, OPTIONAL_COLUMNS[resource])
                self.assertEqual(
                    set(spec.payload_to_columns),
                    set(SCHEMA_BY_RESOURCE[resource].model_fields),
                )
                for payload_field, column_name in spec.payload_to_columns.items():
                    self.assertEqual(
                        column_name,
                        ALIASED_COLUMNS.get(resource, {}).get(
                            payload_field,
                            payload_field,
                        ),
                    )

    def test_all_fifteen_payload_schemas_are_strict_and_accept_golden_records(self):
        self.assertEqual(set(SCHEMA_BY_RESOURCE), set(ResourceType))
        for resource, schema in SCHEMA_BY_RESOURCE.items():
            with self.subTest(resource=resource):
                self.assertEqual(schema.model_config.get("extra"), "forbid")
                self.assertEqual(
                    set(schema.model_fields),
                    set(GOLDEN_PAYLOADS[resource]),
                )
                parsed = schema.model_validate(GOLDEN_PAYLOADS[resource])
                with self.assertRaises(ValidationError):
                    schema.model_validate(
                        {**GOLDEN_PAYLOADS[resource], "platform_temporary": "x"}
                    )
                with self.assertRaises(ValidationError):
                    schema.model_validate(
                        {**GOLDEN_PAYLOADS[resource], "platform_updated_at": NOW}
                    )
                for field_name in MONEY_FIELDS.get(resource, ()):
                    value = getattr(parsed, field_name)
                    if value is not None:
                        self.assertIsInstance(value, Decimal)

    def test_external_ids_are_strings_and_timestamps_are_aware_utc(self):
        for resource, schema in SCHEMA_BY_RESOURCE.items():
            payload = GOLDEN_PAYLOADS[resource]
            for field_name, value in payload.items():
                if field_name.startswith("external_") and value is not None:
                    with self.subTest(resource=resource, field=field_name):
                        invalid = copy.deepcopy(payload)
                        invalid[field_name] = 123
                        with self.assertRaises(ValidationError):
                            schema.model_validate(invalid)
                if field_name.endswith("_at") and isinstance(value, datetime):
                    for invalid_time in (
                        value.replace(tzinfo=None),
                        value.astimezone(timezone(timedelta(hours=8))),
                    ):
                        with self.subTest(resource=resource, field=field_name):
                            invalid = copy.deepcopy(payload)
                            invalid[field_name] = invalid_time
                            with self.assertRaises(ValidationError):
                                schema.model_validate(invalid)

    def test_count_fields_reject_values_outside_postgres_integer_range(self):
        count_fields = {
            ResourceType.INVENTORY: ("quantity", "available_quantity"),
            ResourceType.ORDER_ITEMS: ("quantity",),
            ResourceType.DAILY_METRICS: (
                "order_count",
                "refund_count",
                "visitor_count",
                "buyer_count",
            ),
            ResourceType.AD_DAILY_METRICS: (
                "impressions",
                "clicks",
                "orders",
                "play_count",
            ),
        }
        for resource, field_names in count_fields.items():
            for field_name in field_names:
                with self.subTest(resource=resource, field=field_name):
                    payload = copy.deepcopy(GOLDEN_PAYLOADS[resource])
                    payload[field_name] = 2_147_483_648
                    with self.assertRaises(ValidationError):
                        SCHEMA_BY_RESOURCE[resource].model_validate(payload)

    def test_status_schemas_preserve_unknown_raw_status_only_via_unknown_enum(self):
        status_cases = {
            ResourceType.SHOPS: AccountStatus.UNKNOWN,
            ResourceType.PRODUCTS: ProductStatus.UNKNOWN,
            ResourceType.SKUS: ProductStatus.UNKNOWN,
            ResourceType.ORDERS: OrderStatus.UNKNOWN,
            ResourceType.REFUNDS: RefundStatus.UNKNOWN,
            ResourceType.SHIPMENTS: ShipmentStatus.UNKNOWN,
            ResourceType.SETTLEMENTS: SettlementStatus.UNKNOWN,
            ResourceType.AD_ACCOUNTS: AccountStatus.UNKNOWN,
            ResourceType.AD_ENTITIES: AdEntityStatus.UNKNOWN,
            ResourceType.AD_FINANCE_TRANSACTIONS: FinanceTransactionStatus.UNKNOWN,
        }
        for resource, unknown in status_cases.items():
            schema = SCHEMA_BY_RESOURCE[resource]
            payload = {
                **GOLDEN_PAYLOADS[resource],
                "normalized_status": unknown,
                "raw_status": "BRAND_NEW_PROVIDER_STATUS",
            }
            parsed = schema.model_validate(payload)
            self.assertIs(parsed.normalized_status, unknown)
            self.assertEqual(parsed.raw_status, "BRAND_NEW_PROVIDER_STATUS")
            with self.assertRaises(ValidationError):
                schema.model_validate(
                    {**payload, "normalized_status": "brand_new_provider_status"}
                )


@requires_disposable_postgres
class IntegrationWriterPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.addClassCleanup(cls._cleanup)
        cls._reset_schema()

    @classmethod
    def _cleanup(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=WRITER_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    @classmethod
    def _reset_schema(cls):
        Base.metadata.drop_all(cls.engine, tables=WRITER_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=WRITER_TABLES, checkfirst=False)

    def setUp(self):
        self._reset_schema()

    def _seed_connection(self, session, *, suffix: str) -> int:
        authorization = IntegrationAuthorization(
            provider=Provider.DOUDIAN,
            external_subject_id=f"writer-subject-{suffix}",
            scopes=["shop.read"],
            access_token_ciphertext="opaque-test-ciphertext",
            access_token_tail="0000",
            status=AuthorizationStatus.ACTIVE,
            last_authorized_at=NOW,
        )
        session.add(authorization)
        session.flush()
        connection = IntegrationConnection(
            authorization_id=authorization.id,
            provider=Provider.DOUDIAN,
            connection_type=ConnectionType.SHOP,
            external_account_id=f"writer-account-{suffix}",
            display_name=f"Writer connection {suffix}",
            status=ConnectionStatus.ACTIVE,
            capability_report={},
        )
        session.add(connection)
        session.flush()
        return connection.id

    def _seed_run(self, session, *, connection_id: int, resource: ResourceType):
        checkpoint = IntegrationSyncCheckpoint(
            connection_id=connection_id,
            resource_type=resource,
            window_start=NOW - timedelta(days=1),
            window_end=NOW,
            status=CheckpointStatus.RUNNING,
            attempts=1,
        )
        session.add(checkpoint)
        session.flush()
        run = IntegrationSyncRun(
            checkpoint_id=checkpoint.id,
            source=SyncSource.MANUAL,
            status=SyncStatus.RUNNING,
            resource_type=resource,
            window_start=checkpoint.window_start,
            window_end=checkpoint.window_end,
            progress=Decimal("0"),
            records_read=0,
            records_written=0,
            records_skipped=0,
            records_quarantined=0,
            started_at=NOW,
        )
        session.add(run)
        session.flush()
        return run

    def _record(
        self,
        resource: ResourceType,
        *,
        payload=None,
        platform_updated_at=NOW,
        external_id=None,
        sanitized_source_payload=None,
    ) -> NormalizedRecord:
        return NormalizedRecord(
            resource=resource,
            external_id=external_id or ENVELOPE_EXTERNAL_IDS[resource],
            platform_updated_at=platform_updated_at,
            payload=copy.deepcopy(payload or GOLDEN_PAYLOADS[resource]),
            sanitized_source_payload=copy.deepcopy(
                sanitized_source_payload
                if sanitized_source_payload is not None
                else {"source_code": "safe"}
            ),
        )

    def _write(self, session, run, *records) -> WriteResult:
        return write_records(
            session,
            run_id=run.id,
            records=records,
            quarantine_hmac_key=QUARANTINE_KEY,
            now=NOW + timedelta(minutes=10),
        )

    def _row_for(self, session, resource, connection_id, payload):
        spec = TABLE_SPECS[resource]
        parsed = spec.schema.model_validate(payload).model_dump(mode="python")
        mapped = {
            spec.payload_to_columns[field_name]: value
            for field_name, value in parsed.items()
        }
        predicates = []
        for column_name in spec.conflict_columns:
            value = connection_id if column_name == "connection_id" else mapped[column_name]
            predicates.append(spec.table.c[column_name] == value)
        return session.execute(
            select(spec.table).where(*predicates)
        ).mappings().one()

    def test_duplicate_pages_are_idempotent_and_write_only_allowlisted_columns(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="all")
            for resource in ResourceType:
                with self.subTest(resource=resource):
                    run = self._seed_run(
                        session,
                        connection_id=connection_id,
                        resource=resource,
                    )
                    record = self._record(resource)
                    first = self._write(session, run, record)
                    second = self._write(session, run, record)
                    self.assertEqual(
                        (first.records_read, first.records_written),
                        (1, 1),
                    )
                    self.assertEqual(
                        (second.records_read, second.records_skipped),
                        (1, 1),
                    )
                    spec = TABLE_SPECS[resource]
                    self.assertEqual(
                        session.scalar(
                            select(func.count())
                            .select_from(spec.table)
                            .where(spec.table.c.connection_id == connection_id)
                        ),
                        1,
                    )
                    row = self._row_for(
                        session,
                        resource,
                        connection_id,
                        GOLDEN_PAYLOADS[resource],
                    )
                    parsed = spec.schema.model_validate(
                        GOLDEN_PAYLOADS[resource]
                    ).model_dump(mode="python")
                    for field_name, column_name in spec.payload_to_columns.items():
                        self.assertEqual(row[column_name], parsed[field_name])
                    self.assertEqual(row["platform_metadata"], {})
                    self.assertEqual(row["platform_updated_at"], NOW)
                    session.refresh(run)
                    self.assertEqual(run.records_read, 2)
                    self.assertEqual(run.records_written, 1)
                    self.assertEqual(run.records_skipped, 1)
                    self.assertEqual(run.records_quarantined, 0)
                    self.assertEqual(run.status, SyncStatus.RUNNING)
            session.commit()
        finally:
            session.close()

    def test_newer_records_update_and_older_records_never_win_for_all_resources(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="newer")
            for resource in ResourceType:
                with self.subTest(resource=resource):
                    run = self._seed_run(
                        session,
                        connection_id=connection_id,
                        resource=resource,
                    )
                    base_payload = copy.deepcopy(GOLDEN_PAYLOADS[resource])
                    field_name, newer_value = MUTATION_BY_RESOURCE[resource]
                    newer_payload = {**base_payload, field_name: newer_value}
                    self._write(session, run, self._record(resource, payload=base_payload))
                    newer = write_records(
                        session,
                        run_id=run.id,
                        records=(
                            self._record(
                                resource,
                                payload=newer_payload,
                                platform_updated_at=NOW + timedelta(minutes=2),
                            ),
                        ),
                        quarantine_hmac_key=QUARANTINE_KEY,
                        now=NOW + timedelta(minutes=11),
                    )
                    older = write_records(
                        session,
                        run_id=run.id,
                        records=(
                            self._record(
                                resource,
                                payload=base_payload,
                                platform_updated_at=NOW + timedelta(minutes=1),
                            ),
                        ),
                        quarantine_hmac_key=QUARANTINE_KEY,
                        now=NOW + timedelta(minutes=12),
                    )
                    self.assertEqual(newer.records_written, 1)
                    self.assertEqual(older.records_skipped, 1)
                    row = self._row_for(
                        session,
                        resource,
                        connection_id,
                        newer_payload,
                    )
                    spec = TABLE_SPECS[resource]
                    expected = getattr(
                        spec.schema.model_validate(newer_payload),
                        field_name,
                    )
                    self.assertEqual(
                        row[spec.payload_to_columns[field_name]],
                        expected,
                    )
                    self.assertEqual(
                        row["platform_updated_at"],
                        NOW + timedelta(minutes=2),
                    )
            session.commit()
        finally:
            session.close()

    def test_equal_identical_is_noop_and_equal_divergent_is_one_safe_conflict(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="equal")
            for resource in ResourceType:
                with self.subTest(resource=resource):
                    run = self._seed_run(
                        session,
                        connection_id=connection_id,
                        resource=resource,
                    )
                    base_payload = copy.deepcopy(GOLDEN_PAYLOADS[resource])
                    field_name, divergent_value = MUTATION_BY_RESOURCE[resource]
                    divergent_payload = {**base_payload, field_name: divergent_value}
                    self._write(session, run, self._record(resource, payload=base_payload))
                    identical = self._write(
                        session,
                        run,
                        self._record(resource, payload=base_payload),
                    )
                    conflict = self._write(
                        session,
                        run,
                        self._record(resource, payload=divergent_payload),
                    )
                    repeated_conflict = self._write(
                        session,
                        run,
                        self._record(resource, payload=divergent_payload),
                    )
                    self.assertEqual(identical.records_skipped, 1)
                    self.assertEqual(conflict.records_quarantined, 1)
                    self.assertEqual(repeated_conflict.records_quarantined, 1)
                    self.assertTrue(conflict.partial_success)
                    self.assertEqual(conflict.refetch_enqueued, 0)
                    self.assertEqual(
                        session.scalar(
                            select(func.count())
                            .select_from(IntegrationSyncError)
                            .where(
                                IntegrationSyncError.run_id == run.id,
                                IntegrationSyncError.error_type
                                == "equal_timestamp_conflict",
                            )
                        ),
                        1,
                    )
                    row = self._row_for(
                        session,
                        resource,
                        connection_id,
                        base_payload,
                    )
                    spec = TABLE_SPECS[resource]
                    expected = getattr(
                        spec.schema.model_validate(base_payload),
                        field_name,
                    )
                    self.assertEqual(
                        row[spec.payload_to_columns[field_name]],
                        expected,
                    )
                    session.refresh(run)
                    self.assertEqual(run.status, SyncStatus.PARTIAL_SUCCESS)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(IntegrationJob)),
                0,
            )
            session.commit()
        finally:
            session.close()

    def test_sparse_newer_and_equal_payloads_preserve_existing_optional_details(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="sparse")
            resource = ResourceType.PRODUCTS
            run = self._seed_run(
                session,
                connection_id=connection_id,
                resource=resource,
            )
            base_payload = copy.deepcopy(GOLDEN_PAYLOADS[resource])
            self._write(session, run, self._record(resource, payload=base_payload))
            sparse_payload = {
                **base_payload,
                "external_shop_id": None,
                "category": None,
                "price": None,
                "currency": None,
            }
            equal_sparse = self._write(
                session,
                run,
                self._record(resource, payload=sparse_payload),
            )
            self.assertEqual(equal_sparse.records_skipped, 1)
            self.assertEqual(equal_sparse.records_quarantined, 0)
            newer_sparse = write_records(
                session,
                run_id=run.id,
                records=(
                    self._record(
                        resource,
                        payload=sparse_payload,
                        platform_updated_at=NOW + timedelta(minutes=1),
                    ),
                ),
                quarantine_hmac_key=QUARANTINE_KEY,
                now=NOW + timedelta(minutes=11),
            )
            self.assertEqual(newer_sparse.records_written, 1)
            row = self._row_for(session, resource, connection_id, base_payload)
            for column_name in OPTIONAL_COLUMNS[resource]:
                field_name = next(
                    field
                    for field, mapped in TABLE_SPECS[resource].payload_to_columns.items()
                    if mapped == column_name
                )
                expected = getattr(
                    TABLE_SPECS[resource].schema.model_validate(base_payload),
                    field_name,
                )
                self.assertEqual(row[column_name], expected)
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(IntegrationSyncError)
                    .where(IntegrationSyncError.run_id == run.id)
                ),
                0,
            )
            session.commit()
        finally:
            session.close()

    def test_same_external_id_is_isolated_by_connection(self):
        session = self.Session()
        try:
            first_connection = self._seed_connection(session, suffix="isolation-a")
            second_connection = self._seed_connection(session, suffix="isolation-b")
            resource = ResourceType.ORDERS
            first_run = self._seed_run(
                session,
                connection_id=first_connection,
                resource=resource,
            )
            second_run = self._seed_run(
                session,
                connection_id=second_connection,
                resource=resource,
            )
            record = self._record(resource)
            self._write(session, first_run, record)
            self._write(session, second_run, record)
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(CommerceOrder.__table__)
                ),
                2,
            )
            self.assertIsNotNone(
                self._row_for(
                    session,
                    resource,
                    first_connection,
                    GOLDEN_PAYLOADS[resource],
                )
            )
            self.assertIsNotNone(
                self._row_for(
                    session,
                    resource,
                    second_connection,
                    GOLDEN_PAYLOADS[resource],
                )
            )
            session.commit()
        finally:
            session.close()

    def test_unknown_normalized_status_and_raw_status_are_preserved(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="unknown")
            for resource, unknown in STATUS_UNKNOWNS.items():
                with self.subTest(resource=resource):
                    run = self._seed_run(
                        session,
                        connection_id=connection_id,
                        resource=resource,
                    )
                    payload = {
                        **GOLDEN_PAYLOADS[resource],
                        "normalized_status": unknown,
                        "raw_status": "BRAND_NEW_PROVIDER_STATUS",
                    }
                    result = self._write(
                        session,
                        run,
                        self._record(resource, payload=payload),
                    )
                    self.assertEqual(result.records_written, 1)
                    row = self._row_for(session, resource, connection_id, payload)
                    self.assertEqual(row["normalized_status"], unknown)
                    self.assertEqual(row["raw_status"], "BRAND_NEW_PROVIDER_STATUS")
            session.commit()
        finally:
            session.close()

    def test_non_cny_is_stored_but_excluded_from_cny_aggregation_seam(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="currency")
            resource = ResourceType.ORDERS
            run = self._seed_run(
                session,
                connection_id=connection_id,
                resource=resource,
            )
            usd_payload = {**GOLDEN_PAYLOADS[resource], "currency": "USD"}
            result = self._write(
                session,
                run,
                self._record(resource, payload=usd_payload),
            )
            self.assertEqual(result.records_written, 1)
            row = self._row_for(session, resource, connection_id, usd_payload)
            self.assertEqual(row["currency"], "USD")
            spec = TABLE_SPECS[resource]
            self.assertFalse(
                is_cny_aggregatable(spec.schema.model_validate(usd_payload))
            )
            self.assertTrue(
                is_cny_aggregatable(
                    spec.schema.model_validate(GOLDEN_PAYLOADS[resource])
                )
            )
            session.commit()
        finally:
            session.close()

    def test_invalid_record_is_safely_quarantined_while_valid_sibling_commits(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="siblings")
            resource = ResourceType.PRODUCTS
            run = self._seed_run(
                session,
                connection_id=connection_id,
                resource=resource,
            )
            invalid_payload = {
                **GOLDEN_PAYLOADS[resource],
                "external_product_id": 123,
            }
            invalid = self._record(
                resource,
                payload=invalid_payload,
                external_id="invalid-product",
            )
            valid = self._record(resource)
            result = self._write(session, run, invalid, valid)
            self.assertEqual(
                (
                    result.records_read,
                    result.records_written,
                    result.records_quarantined,
                ),
                (2, 1, 1),
            )
            self.assertTrue(result.partial_success)
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(CommerceProduct.__table__)
                ),
                1,
            )
            error = session.scalar(
                select(IntegrationSyncError).where(
                    IntegrationSyncError.run_id == run.id
                )
            )
            expected_hmac = hmac.new(
                QUARANTINE_KEY,
                b"products\ninvalid-product",
                hashlib.sha256,
            ).hexdigest()
            self.assertEqual(error.external_key_hmac, expected_hmac)
            self.assertEqual(error.error_type, "validation_error")
            self.assertEqual(
                set(error.field_errors[0]),
                {"field", "code"},
            )
            rendered = json.dumps(
                {
                    "summary": error.sanitized_summary,
                    "fields": error.field_errors,
                }
            )
            self.assertNotIn("invalid-product", rendered)
            self.assertNotIn("123", rendered)
            session.commit()
        finally:
            session.close()

    def test_safe_empty_json_values_are_not_mistaken_for_sensitive_content(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="empty-json")
            resource = ResourceType.SKUS
            run = self._seed_run(
                session,
                connection_id=connection_id,
                resource=resource,
            )
            payload = copy.deepcopy(GOLDEN_PAYLOADS[resource])
            payload["attributes"] = {
                "label": "",
                "nested": {"note": ""},
                "values": [None, ""],
            }
            result = self._write(
                session,
                run,
                self._record(
                    resource,
                    payload=payload,
                    sanitized_source_payload={"source_code": ""},
                ),
            )
            self.assertEqual(
                (result.records_written, result.records_quarantined),
                (1, 0),
            )
            row = self._row_for(session, resource, connection_id, payload)
            self.assertEqual(row["attributes"], payload["attributes"])
            session.commit()
        finally:
            session.close()

    def test_pii_and_secrets_in_allowed_values_or_source_never_reach_sql_or_logs(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="safety")
            resource = ResourceType.PRODUCTS
            run = self._seed_run(
                session,
                connection_id=connection_id,
                resource=resource,
            )
            sentinels = (
                "buyer@example.com",
                "13800138000",
                "440524188001010014",
                "Authorization: Bearer quoted-secret",
                "https://provider.invalid/?clientSecret=query-secret",
            )
            unsafe_records = []
            for index, sentinel in enumerate(sentinels):
                external_id = f"unsafe-product-{index}"
                unsafe_records.append(
                    self._record(
                        resource,
                        payload={
                            **GOLDEN_PAYLOADS[resource],
                            "external_product_id": external_id,
                            "title": sentinel,
                        },
                        external_id=external_id,
                    )
                )
            unsafe_records.append(
                self._record(
                    resource,
                    payload={
                        **GOLDEN_PAYLOADS[resource],
                        "external_product_id": "unsafe-source",
                    },
                    external_id="unsafe-source",
                    sanitized_source_payload={"note": "buyer@example.com"},
                )
            )
            source_marker = "SANITIZED_SOURCE_WHOLESALE_MARKER"
            safe_record = self._record(
                resource,
                payload={
                    **GOLDEN_PAYLOADS[resource],
                    "external_product_id": "safe-source",
                    "title": "Safe source product",
                },
                external_id="safe-source",
                sanitized_source_payload={"source_marker": source_marker},
            )
            with self.assertNoLogs("integrations.sync.writer", level="DEBUG"):
                result = self._write(
                    session,
                    run,
                    *unsafe_records,
                    safe_record,
                )
            self.assertEqual(result.records_written, 1)
            self.assertEqual(result.records_quarantined, len(unsafe_records))
            rows = session.execute(select(CommerceProduct.__table__)).mappings().all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["external_product_id"], "safe-source")
            self.assertEqual(rows[0]["platform_metadata"], {})
            rendered_rows = json.dumps([dict(row) for row in rows], default=str)
            rendered_errors = json.dumps(
                [
                    {
                        "hmac": error.external_key_hmac,
                        "type": error.error_type,
                        "summary": error.sanitized_summary,
                        "fields": error.field_errors,
                    }
                    for error in session.scalars(
                        select(IntegrationSyncError).where(
                            IntegrationSyncError.run_id == run.id
                        )
                    )
                ]
            )
            for sentinel in (*sentinels, source_marker, "query-secret"):
                self.assertNotIn(sentinel, rendered_rows)
                self.assertNotIn(sentinel, rendered_errors)
            session.commit()
        finally:
            session.close()

    def test_envelope_id_mismatch_and_non_utc_platform_time_are_quarantined(self):
        session = self.Session()
        try:
            connection_id = self._seed_connection(session, suffix="envelope")
            resource = ResourceType.PRODUCTS
            run = self._seed_run(
                session,
                connection_id=connection_id,
                resource=resource,
            )
            mismatch = self._record(
                resource,
                payload=GOLDEN_PAYLOADS[resource],
                external_id="different-envelope-id",
            )
            non_utc = self._record(
                resource,
                payload={
                    **GOLDEN_PAYLOADS[resource],
                    "external_product_id": "non-utc-product",
                },
                external_id="non-utc-product",
                platform_updated_at=NOW.astimezone(
                    timezone(timedelta(hours=8))
                ),
            )
            result = self._write(session, run, mismatch, non_utc)
            self.assertEqual(result.records_written, 0)
            self.assertEqual(result.records_quarantined, 2)
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(CommerceProduct.__table__)
                ),
                0,
            )
            session.commit()
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
