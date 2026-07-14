import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    Numeric,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import database
from commerce_models import (
    CommerceAdAccount,
    CommerceAdBalanceSnapshot,
    CommerceAdDailyMetric,
    CommerceAdEntity,
    CommerceAdFinanceTransaction,
    CommerceDailyMetric,
    CommerceEventInbox,
    CommerceInventorySnapshot,
    CommerceOrder,
    CommerceOrderItem,
    CommerceProduct,
    CommerceProductLink,
    CommerceRefund,
    CommerceSettlement,
    CommerceShipment,
    CommerceShop,
    CommerceSku,
)
from database import Base
from integration_models import IntegrationAuthorization, IntegrationConnection
from integrations.types import (
    AccountStatus,
    AdEntityStatus,
    AdEntityType,
    AuthorizationStatus,
    ConnectionStatus,
    ConnectionType,
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
)
from models import Product
from tests.test_integration_models import _require_disposable_postgres_url


COMMERCE_MODELS = (
    CommerceShop,
    CommerceProduct,
    CommerceSku,
    CommerceInventorySnapshot,
    CommerceProductLink,
    CommerceOrder,
    CommerceOrderItem,
    CommerceRefund,
    CommerceShipment,
    CommerceSettlement,
    CommerceDailyMetric,
    CommerceAdAccount,
    CommerceAdEntity,
    CommerceAdDailyMetric,
    CommerceAdBalanceSnapshot,
    CommerceAdFinanceTransaction,
    CommerceEventInbox,
)
COMMERCE_TABLES = tuple(model.__table__ for model in COMMERCE_MODELS)
DEPENDENCY_TABLES = (
    IntegrationAuthorization.__table__,
    IntegrationConnection.__table__,
    Product.__table__,
)
ALL_TEST_TABLES = DEPENDENCY_TABLES + COMMERCE_TABLES

EXPECTED_UNIQUES = {
    "commerce_shops": {
        "uq_commerce_shops_connection_external_shop": (
            "connection_id",
            "external_shop_id",
        )
    },
    "commerce_products": {
        "uq_commerce_products_connection_external_product": (
            "connection_id",
            "external_product_id",
        )
    },
    "commerce_skus": {
        "uq_commerce_skus_connection_external_sku": (
            "connection_id",
            "external_sku_id",
        )
    },
    "commerce_inventory_snapshots": {
        "uq_commerce_inventory_connection_sku_captured": (
            "connection_id",
            "external_sku_id",
            "captured_at",
        )
    },
    "commerce_product_links": {
        "uq_commerce_product_links_commerce_product": ("commerce_product_id",)
    },
    "commerce_orders": {
        "uq_commerce_orders_connection_external_order": (
            "connection_id",
            "external_order_id",
        )
    },
    "commerce_order_items": {
        "uq_commerce_order_items_connection_external_item": (
            "connection_id",
            "external_item_id",
        )
    },
    "commerce_refunds": {
        "uq_commerce_refunds_connection_external_refund": (
            "connection_id",
            "external_refund_id",
        )
    },
    "commerce_shipments": {
        "uq_commerce_shipments_connection_external_shipment": (
            "connection_id",
            "external_shipment_id",
        )
    },
    "commerce_settlements": {
        "uq_commerce_settlements_connection_external_settlement": (
            "connection_id",
            "external_settlement_id",
        )
    },
    "commerce_daily_metrics": {
        "uq_commerce_daily_metrics_connection_date_granularity": (
            "connection_id",
            "stat_date",
            "granularity",
        )
    },
    "commerce_ad_accounts": {
        "uq_commerce_ad_accounts_connection_external_account": (
            "connection_id",
            "external_ad_account_id",
        )
    },
    "commerce_ad_entities": {
        "uq_commerce_ad_entities_connection_type_external": (
            "connection_id",
            "entity_type",
            "external_entity_id",
        )
    },
    "commerce_ad_daily_metrics": {
        "uq_commerce_ad_metrics_connection_entity_date_granularity": (
            "connection_id",
            "entity_type",
            "external_entity_id",
            "stat_date",
            "granularity",
        )
    },
    "commerce_ad_balance_snapshots": {
        "uq_commerce_ad_balances_connection_account_captured": (
            "connection_id",
            "external_ad_account_id",
            "captured_at",
        )
    },
    "commerce_ad_finance_transactions": {
        "uq_commerce_ad_finance_connection_external_transaction": (
            "connection_id",
            "external_transaction_id",
        )
    },
    "commerce_event_inbox": {
        "uq_commerce_event_inbox_dedupe_key": ("dedupe_key",)
    },
}

CONNECTION_ENTITY_TABLES = {
    model.__tablename__
    for model in COMMERCE_MODELS
    if model is not CommerceProductLink
}

EXPECTED_ENUMS = {
    (table_name, "provider"): Provider for table_name in CONNECTION_ENTITY_TABLES
}
EXPECTED_ENUMS.update(
    {
        ("commerce_shops", "normalized_status"): AccountStatus,
        ("commerce_products", "normalized_status"): ProductStatus,
        ("commerce_skus", "normalized_status"): ProductStatus,
        ("commerce_orders", "normalized_status"): OrderStatus,
        ("commerce_refunds", "normalized_status"): RefundStatus,
        ("commerce_shipments", "normalized_status"): ShipmentStatus,
        ("commerce_settlements", "normalized_status"): SettlementStatus,
        ("commerce_daily_metrics", "granularity"): MetricGranularity,
        ("commerce_ad_accounts", "normalized_status"): AccountStatus,
        ("commerce_ad_entities", "entity_type"): AdEntityType,
        ("commerce_ad_entities", "normalized_status"): AdEntityStatus,
        ("commerce_ad_daily_metrics", "entity_type"): AdEntityType,
        ("commerce_ad_daily_metrics", "granularity"): MetricGranularity,
        (
            "commerce_ad_finance_transactions",
            "normalized_status",
        ): FinanceTransactionStatus,
        ("commerce_event_inbox", "event_id_scope"): EventIdScope,
        ("commerce_event_inbox", "routing_status"): EventRoutingStatus,
        ("commerce_event_inbox", "processing_status"): EventProcessingStatus,
    }
)

MONEY_COLUMNS = {
    "commerce_products": {"price"},
    "commerce_skus": {"price"},
    "commerce_orders": {
        "order_amount",
        "paid_amount",
        "discount_amount",
        "shipping_amount",
    },
    "commerce_order_items": {"unit_amount", "paid_amount"},
    "commerce_refunds": {"amount"},
    "commerce_settlements": {"gross_amount", "fee_amount", "net_amount"},
    "commerce_daily_metrics": {"actual_sales", "refund_amount"},
    "commerce_ad_daily_metrics": {"spend", "attributed_sales"},
    "commerce_ad_balance_snapshots": {"balance"},
    "commerce_ad_finance_transactions": {"amount"},
}
RATIO_COLUMNS = {
    "commerce_ad_daily_metrics": {"ctr", "cvr", "roi", "play_rate"}
}
CURRENCY_TABLES = {
    table_name for table_name, columns in MONEY_COLUMNS.items() if columns
} | {"commerce_ad_accounts"}

PII_COLUMN_NAMES = {
    "buyer_name",
    "recipient_name",
    "customer_name",
    "real_name",
    "phone",
    "mobile",
    "telephone",
    "id_card",
    "identity_card",
    "address",
    "detailed_address",
    "detail_address",
}


class CommerceModelMetadataTests(unittest.TestCase):
    def test_persisted_dimension_and_event_enum_values_are_stable(self):
        expected = {
            MetricGranularity: ["day"],
            AdEntityType: ["account", "campaign", "ad_group", "creative", "material"],
            EventRoutingStatus: [
                "pending",
                "routed",
                "unroutable_subject",
                "ambiguous_subject",
            ],
            EventProcessingStatus: [
                "received",
                "queued",
                "processing",
                "succeeded",
                "failed",
                "ignored",
            ],
        }
        for enum_type, values in expected.items():
            with self.subTest(enum_type=enum_type.__name__):
                self.assertEqual([item.value for item in enum_type], values)

    def test_all_normalized_commerce_tables_are_registered(self):
        self.assertEqual(
            {table.name for table in COMMERCE_TABLES},
            set(EXPECTED_UNIQUES),
        )

    def test_commerce_models_do_not_declare_pii_columns(self):
        declared = {
            column.name.lower()
            for table in COMMERCE_TABLES
            for column in table.columns
        }
        self.assertTrue(PII_COLUMN_NAMES.isdisjoint(declared))
        self.assertIn("buyer_digest", CommerceOrder.__table__.c)
        self.assertIn("province", CommerceOrder.__table__.c)
        self.assertIn("city", CommerceOrder.__table__.c)

    def test_every_platform_entity_has_safe_envelope_columns(self):
        for table in COMMERCE_TABLES:
            if table is CommerceProductLink.__table__:
                continue
            with self.subTest(table=table.name):
                self.assertIn("provider", table.c)
                self.assertIn("platform_updated_at", table.c)
                if table is CommerceEventInbox.__table__:
                    self.assertIn("sanitized_payload", table.c)
                else:
                    self.assertIn("platform_metadata", table.c)

    def test_json_columns_compile_to_jsonb_on_postgresql(self):
        json_columns = [
            column
            for table in COMMERCE_TABLES
            for column in table.columns
            if column.name in {"platform_metadata", "attributes", "sanitized_payload"}
        ]
        self.assertGreaterEqual(len(json_columns), len(COMMERCE_TABLES))
        for column in json_columns:
            with self.subTest(table=column.table.name, column=column.name):
                self.assertIsInstance(
                    column.type.dialect_impl(postgresql.dialect()),
                    JSONB,
                )

    def test_money_ratios_and_timestamps_use_exact_types(self):
        for table_name, column_names in MONEY_COLUMNS.items():
            for column_name in column_names:
                column = Base.metadata.tables[table_name].c[column_name]
                with self.subTest(table=table_name, column=column_name):
                    self.assertIsInstance(column.type, Numeric)
                    self.assertEqual((column.type.precision, column.type.scale), (20, 2))
        for table_name, column_names in RATIO_COLUMNS.items():
            for column_name in column_names:
                column = Base.metadata.tables[table_name].c[column_name]
                with self.subTest(table=table_name, column=column_name):
                    self.assertIsInstance(column.type, Numeric)
                    self.assertEqual((column.type.precision, column.type.scale), (20, 6))
        for table in COMMERCE_TABLES:
            for column in table.columns:
                if isinstance(column.type, DateTime):
                    with self.subTest(table=table.name, column=column.name):
                        self.assertTrue(column.type.timezone)

    def test_named_uniques_match_every_idempotency_contract(self):
        actual = {}
        for table in COMMERCE_TABLES:
            expected = EXPECTED_UNIQUES[table.name]
            actual[table.name] = {
                constraint.name: tuple(column.name for column in constraint.columns)
                for constraint in table.constraints
                if isinstance(constraint, UniqueConstraint)
                and constraint.name in expected
            }
        self.assertEqual(actual, EXPECTED_UNIQUES)

    def test_product_link_session_digest_has_exact_named_length_check(self):
        checks = {
            constraint.name: str(constraint.sqltext).replace(" ", "")
            for constraint in CommerceProductLink.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertEqual(
            checks.get("ck_commerce_product_links_linked_by_session_digest_length"),
            "length(linked_by_session_digest)=64",
        )

    def test_every_persisted_enum_has_an_exact_named_check(self):
        actual = {}
        for table in COMMERCE_TABLES:
            for column in table.columns:
                if isinstance(column.type, SqlEnum):
                    actual[(table.name, column.name)] = column.type.enum_class
                    self.assertEqual(
                        column.type.name,
                        f"ck_{table.name}_{column.name}",
                    )
                    self.assertFalse(column.type.native_enum)
                    self.assertTrue(column.type.create_constraint)
        self.assertEqual(actual, EXPECTED_ENUMS)


class PostgresCommerceModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine)
        cls.addClassCleanup(cls._cleanup)
        cls._reset_schema()

    @classmethod
    def _cleanup(cls):
        Base.metadata.drop_all(cls.engine, tables=ALL_TEST_TABLES, checkfirst=True)
        cls.engine.dispose()

    @classmethod
    def _reset_schema(cls):
        Base.metadata.drop_all(cls.engine, tables=ALL_TEST_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=ALL_TEST_TABLES, checkfirst=False)

    def setUp(self):
        self._reset_schema()
        session = self.Session()
        try:
            authorization = IntegrationAuthorization(
                provider=Provider.DOUDIAN,
                external_subject_id="subject-commerce",
                scopes=["shop.read"],
                access_token_ciphertext="opaque-ciphertext",
                access_token_tail="0000",
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=datetime.now(timezone.utc),
            )
            session.add(authorization)
            session.flush()
            connection = IntegrationConnection(
                authorization_id=authorization.id,
                provider=Provider.DOUDIAN,
                connection_type=ConnectionType.SHOP,
                external_account_id="shop-commerce",
                display_name="Commerce test shop",
                status=ConnectionStatus.ACTIVE,
                capability_report={},
            )
            product = Product(name="Existing product", category="test", price=10.0)
            session.add_all((connection, product))
            session.commit()
            self.connection_id = connection.id
            self.product_id = product.id
        finally:
            session.close()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).replace(microsecond=0)

    def _base(self):
        return {
            "connection_id": self.connection_id,
            "provider": Provider.DOUDIAN.value,
            "platform_updated_at": self._now(),
            "platform_metadata": {},
        }

    def _values(self, table_name: str, suffix: str):
        now = self._now()
        base = self._base()
        values = {
            "commerce_shops": {
                **base,
                "external_shop_id": f"shop-{suffix}",
                "name": "Test shop",
                "normalized_status": AccountStatus.ACTIVE.value,
                "raw_status": "OPEN",
            },
            "commerce_products": {
                **base,
                "external_product_id": f"product-{suffix}",
                "external_shop_id": "shop-commerce",
                "title": "Platform product",
                "normalized_status": ProductStatus.ON_SALE.value,
                "raw_status": "ONLINE",
                "category": "food",
                "price": Decimal("12.34"),
                "currency": "CNY",
            },
            "commerce_skus": {
                **base,
                "external_sku_id": f"sku-{suffix}",
                "external_product_id": f"product-{suffix}",
                "title": "SKU",
                "attributes": {"size": "small"},
                "normalized_status": ProductStatus.ON_SALE.value,
                "raw_status": "ONLINE",
                "price": Decimal("12.34"),
                "currency": "CNY",
            },
            "commerce_inventory_snapshots": {
                **base,
                "external_sku_id": f"sku-{suffix}",
                "quantity": 10,
                "available_quantity": 8,
                "captured_at": now,
            },
            "commerce_orders": {
                **base,
                "external_order_id": f"order-{suffix}",
                "external_shop_id": "shop-commerce",
                "normalized_status": OrderStatus.PAID.value,
                "raw_status": "PAID",
                "buyer_digest": "b" * 64,
                "province": "Guangdong",
                "city": "Shenzhen",
                "currency": "CNY",
                "order_amount": Decimal("12.34"),
                "paid_amount": Decimal("12.34"),
                "discount_amount": Decimal("0.00"),
                "shipping_amount": Decimal("0.00"),
                "ordered_at": now,
                "paid_at": now,
            },
            "commerce_order_items": {
                **base,
                "external_item_id": f"item-{suffix}",
                "external_order_id": f"order-{suffix}",
                "external_product_id": f"product-{suffix}",
                "external_sku_id": f"sku-{suffix}",
                "title": "Order item",
                "quantity": 1,
                "unit_amount": Decimal("12.34"),
                "paid_amount": Decimal("12.34"),
                "currency": "CNY",
            },
            "commerce_refunds": {
                **base,
                "external_refund_id": f"refund-{suffix}",
                "external_order_id": f"order-{suffix}",
                "external_item_id": f"item-{suffix}",
                "normalized_status": RefundStatus.REQUESTED.value,
                "raw_status": "APPLY",
                "amount": Decimal("2.00"),
                "currency": "CNY",
                "reason_code": "OTHER",
                "refund_created_at": now,
            },
            "commerce_shipments": {
                **base,
                "external_shipment_id": f"shipment-{suffix}",
                "external_order_id": f"order-{suffix}",
                "normalized_status": ShipmentStatus.SHIPPED.value,
                "raw_status": "SHIPPED",
                "carrier_code": "TEST",
                "tracking_number": f"tracking-{suffix}",
                "shipped_at": now,
            },
            "commerce_settlements": {
                **base,
                "external_settlement_id": f"settlement-{suffix}",
                "external_order_id": f"order-{suffix}",
                "normalized_status": SettlementStatus.SETTLED.value,
                "raw_status": "SETTLED",
                "currency": "CNY",
                "gross_amount": Decimal("12.34"),
                "fee_amount": Decimal("1.00"),
                "net_amount": Decimal("11.34"),
                "settlement_date": date(2026, 7, 13),
            },
            "commerce_daily_metrics": {
                **base,
                "stat_date": date(2026, 7, 13),
                "granularity": MetricGranularity.DAY.value,
                "actual_sales": Decimal("100.00"),
                "order_count": 10,
                "refund_amount": Decimal("2.00"),
                "refund_count": 1,
                "visitor_count": 100,
                "buyer_count": 9,
                "currency": "CNY",
            },
            "commerce_ad_accounts": {
                **base,
                "external_ad_account_id": f"ad-account-{suffix}",
                "name": "Ad account",
                "normalized_status": AccountStatus.ACTIVE.value,
                "raw_status": "ENABLE",
                "currency": "CNY",
            },
            "commerce_ad_entities": {
                **base,
                "entity_type": AdEntityType.CAMPAIGN.value,
                "external_entity_id": f"campaign-{suffix}",
                "external_parent_id": None,
                "name": "Campaign",
                "normalized_status": AdEntityStatus.ACTIVE.value,
                "raw_status": "ENABLE",
            },
            "commerce_ad_daily_metrics": {
                **base,
                "entity_type": AdEntityType.CAMPAIGN.value,
                "external_entity_id": f"campaign-{suffix}",
                "stat_date": date(2026, 7, 13),
                "granularity": MetricGranularity.DAY.value,
                "spend": Decimal("10.00"),
                "impressions": 1000,
                "clicks": 50,
                "orders": 3,
                "attributed_sales": Decimal("30.00"),
                "ctr": Decimal("0.050000"),
                "cvr": Decimal("0.060000"),
                "roi": Decimal("3.000000"),
                "play_count": 500,
                "play_rate": Decimal("0.500000"),
                "currency": "CNY",
            },
            "commerce_ad_balance_snapshots": {
                **base,
                "external_ad_account_id": f"ad-account-{suffix}",
                "balance": Decimal("99.00"),
                "currency": "CNY",
                "captured_at": now,
            },
            "commerce_ad_finance_transactions": {
                **base,
                "external_transaction_id": f"transaction-{suffix}",
                "external_ad_account_id": f"ad-account-{suffix}",
                "transaction_type": "recharge",
                "amount": Decimal("100.00"),
                "currency": "CNY",
                "normalized_status": FinanceTransactionStatus.COMPLETED.value,
                "raw_status": "SUCCESS",
                "transaction_at": now,
            },
            "commerce_event_inbox": {
                "connection_id": self.connection_id,
                "provider": Provider.DOUDIAN.value,
                "external_event_id": f"event-{suffix}",
                "external_subject_id": "subject-commerce",
                "event_id_scope": EventIdScope.SUBJECT.value,
                "dedupe_key": (suffix * 64)[:64],
                "event_type": "order.updated",
                "external_entity_id": f"order-{suffix}",
                "platform_updated_at": now,
                "sanitized_payload": {"status": "PAID"},
                "routing_status": EventRoutingStatus.ROUTED.value,
                "processing_status": EventProcessingStatus.RECEIVED.value,
                "received_at": now,
            },
        }
        return values[table_name]

    def _insert(self, model, suffix: str):
        with self.engine.begin() as connection:
            return connection.execute(
                model.__table__.insert()
                .values(**self._values(model.__tablename__, suffix))
                .returning(model.id)
            ).scalar_one()

    def test_database_has_exact_named_unique_constraints(self):
        inspector = inspect(self.engine)
        for table_name, expected in EXPECTED_UNIQUES.items():
            actual = {
                item["name"]: tuple(item["column_names"])
                for item in inspector.get_unique_constraints(table_name)
                if item["name"] in expected
            }
            self.assertEqual(actual, expected, table_name)

    def test_each_idempotency_key_rejects_a_duplicate(self):
        for model in COMMERCE_MODELS:
            if model is CommerceProductLink:
                commerce_product_id = self._insert(CommerceProduct, "link")
                values = {
                    "commerce_product_id": commerce_product_id,
                    "product_id": self.product_id,
                    "linked_by_session_digest": "d" * 64,
                    "created_at": self._now(),
                    "updated_at": self._now(),
                }
            else:
                values = self._values(model.__tablename__, "u")
            with self.subTest(table=model.__tablename__):
                with self.engine.begin() as connection:
                    connection.execute(model.__table__.insert().values(**values))
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(model.__table__.insert().values(**values))

    def test_every_connection_owned_table_has_named_composite_fk(self):
        inspector = inspect(self.engine)
        for table_name in CONNECTION_ENTITY_TABLES:
            expected_name = f"fk_{table_name}_connection_provider"
            foreign_keys = {
                item["name"]: item for item in inspector.get_foreign_keys(table_name)
            }
            with self.subTest(table=table_name):
                self.assertIn(expected_name, foreign_keys)
                item = foreign_keys[expected_name]
                self.assertEqual(
                    tuple(item["constrained_columns"]),
                    ("connection_id", "provider"),
                )
                self.assertEqual(item["referred_table"], "integration_connections")
                self.assertEqual(tuple(item["referred_columns"]), ("id", "provider"))
                self.assertEqual((item.get("options") or {}).get("ondelete"), "CASCADE")

    def test_every_connection_fk_rejects_a_missing_or_mismatched_parent(self):
        for model in COMMERCE_MODELS:
            if model is CommerceProductLink:
                continue
            values = self._values(model.__tablename__, "f")
            values["connection_id"] = 999999
            with self.subTest(table=model.__tablename__), self.assertRaises(
                IntegrityError
            ):
                with self.engine.begin() as connection:
                    connection.execute(model.__table__.insert().values(**values))

        for model in (CommerceOrder, CommerceEventInbox, CommerceAdEntity):
            values = self._values(model.__tablename__, "p")
            values["provider"] = Provider.PDD.value
            with self.subTest(table=model.__tablename__, mismatch=True), self.assertRaises(
                IntegrityError
            ):
                with self.engine.begin() as connection:
                    connection.execute(model.__table__.insert().values(**values))

    def test_product_link_fk_cascades_only_the_link(self):
        commerce_product_id = self._insert(CommerceProduct, "cascade-product")
        with self.engine.begin() as connection:
            link_id = connection.execute(
                CommerceProductLink.__table__.insert()
                .values(
                    commerce_product_id=commerce_product_id,
                    product_id=self.product_id,
                    linked_by_session_digest="a" * 64,
                    created_at=self._now(),
                    updated_at=self._now(),
                )
                .returning(CommerceProductLink.id)
            ).scalar_one()
            connection.execute(
                Product.__table__.delete().where(Product.id == self.product_id)
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT count(*) FROM commerce_product_links WHERE id=:id"),
                    {"id": link_id},
                ).scalar_one(),
                0,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT count(*) FROM commerce_products WHERE id=:id"),
                    {"id": commerce_product_id},
                ).scalar_one(),
                1,
            )

    def test_many_platform_products_may_link_to_one_existing_product(self):
        first = self._insert(CommerceProduct, "many-1")
        second = self._insert(CommerceProduct, "many-2")
        now = self._now()
        with self.engine.begin() as connection:
            connection.execute(
                CommerceProductLink.__table__.insert(),
                [
                    {
                        "commerce_product_id": first,
                        "product_id": self.product_id,
                        "linked_by_session_digest": "1" * 64,
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "commerce_product_id": second,
                        "product_id": self.product_id,
                        "linked_by_session_digest": "2" * 64,
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            count = connection.execute(
                text("SELECT count(*) FROM commerce_product_links WHERE product_id=:id"),
                {"id": self.product_id},
            ).scalar_one()
        self.assertEqual(count, 2)

    def test_product_link_session_digest_rejects_non_64_raw_value(self):
        commerce_product_id = self._insert(CommerceProduct, "digest-length")
        now = self._now()
        with self.engine.begin() as connection:
            link_id = connection.execute(
                CommerceProductLink.__table__.insert()
                .values(
                    commerce_product_id=commerce_product_id,
                    product_id=self.product_id,
                    linked_by_session_digest="d" * 64,
                    created_at=now,
                    updated_at=now,
                )
                .returning(CommerceProductLink.id)
            ).scalar_one()
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE commerce_product_links "
                        "SET linked_by_session_digest=:digest WHERE id=:id"
                    ),
                    {"digest": "x" * 63, "id": link_id},
                )

    def test_database_enum_checks_reject_every_invalid_raw_value(self):
        row_ids = {}
        for model in COMMERCE_MODELS:
            if model is CommerceProductLink:
                continue
            row_ids[model.__tablename__] = self._insert(model, f"enum-{model.__tablename__}")

        inspector = inspect(self.engine)
        for (table_name, column_name), enum_type in EXPECTED_ENUMS.items():
            constraint_name = f"ck_{table_name}_{column_name}"
            constraints = {
                item["name"]: item["sqltext"]
                for item in inspector.get_check_constraints(table_name)
            }
            with self.subTest(table=table_name, column=column_name):
                self.assertIn(constraint_name, constraints)
                for member in enum_type:
                    self.assertIn(member.value, constraints[constraint_name])
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(
                            text(
                                f'UPDATE "{table_name}" '
                                f'SET "{column_name}"=:invalid WHERE id=:id'
                            ),
                            {
                                "invalid": "x",
                                "id": row_ids[table_name],
                            },
                        )

    def test_currency_checks_require_three_uppercase_characters(self):
        row_ids = {}
        model_by_table = {model.__tablename__: model for model in COMMERCE_MODELS}
        for table_name in CURRENCY_TABLES:
            row_ids[table_name] = self._insert(model_by_table[table_name], f"currency-{table_name}")
        inspector = inspect(self.engine)
        for table_name in CURRENCY_TABLES:
            constraint_name = f"ck_{table_name}_currency_format"
            constraints = {
                item["name"] for item in inspector.get_check_constraints(table_name)
            }
            with self.subTest(table=table_name):
                self.assertIn(constraint_name, constraints)
                for invalid in ("CN", "cny", "1NY"):
                    with self.assertRaises(IntegrityError):
                        with self.engine.begin() as connection:
                            connection.execute(
                                text(
                                    f'UPDATE "{table_name}" SET currency=:currency '
                                    "WHERE id=:id"
                                ),
                                {"currency": invalid, "id": row_ids[table_name]},
                            )

    def test_postgresql_round_trips_numeric_scale_and_aware_timestamp(self):
        order_id = self._insert(CommerceOrder, "roundtrip")
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT paid_amount, platform_updated_at "
                    "FROM commerce_orders WHERE id=:id"
                ),
                {"id": order_id},
            ).one()
        self.assertEqual(row.paid_amount, Decimal("12.34"))
        self.assertIsNotNone(row.platform_updated_at.tzinfo)
        self.assertIsNotNone(row.platform_updated_at.utcoffset())


if __name__ == "__main__":
    unittest.main()
