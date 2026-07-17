import dataclasses
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

import commerce_models
import database
from database import Base
from integration_models import (
    IntegrationAppConfig,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationOAuthState,
    IntegrationSecurityAudit,
)
from integrations.types import (
    AccountIdentity,
    AccountStatus,
    AdEntityStatus,
    AuthorizationStatus,
    AUTHORIZATION_STATUS_TRANSITIONS,
    Capability,
    CapabilityReport,
    CapabilityStage,
    CAPABILITY_STAGE_TRANSITIONS,
    CheckpointStatus,
    CHECKPOINT_STATUS_TRANSITIONS,
    ConnectionContext,
    ConnectionStatus,
    CONNECTION_STATUS_TRANSITIONS,
    ConnectionType,
    EventIdScope,
    ExportStatus,
    EXPORT_STATUS_TRANSITIONS,
    FetchPage,
    FinanceTransactionStatus,
    JobStatus,
    JOB_STATUS_TRANSITIONS,
    JobType,
    NormalizedRecord,
    OrderStatus,
    ProductStatus,
    Provider,
    RateLimitHint,
    RefundStatus,
    ResourceType,
    RevokeResult,
    SettlementStatus,
    ShipmentStatus,
    SyncSource,
    SyncStatus,
    SYNC_STATUS_TRANSITIONS,
    TimeWindow,
    TokenBundle,
    persisted_enum,
    utc_now,
)


CONTROL_MODELS = (
    IntegrationAppConfig,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationOAuthState,
    IntegrationSecurityAudit,
)
CONTROL_TABLES = tuple(model.__table__ for model in CONTROL_MODELS)
OPAQUE_CIPHERTEXT = "opaque-encrypted-payload"
EXPECTED_POSTGRES_TEST_DATABASE = "facai_ecommerce_test"


def _require_disposable_postgres_url() -> str:
    raw_url = os.environ.get("FACAI_TEST_DATABASE_URL", "")
    acknowledgement = os.environ.get("FACAI_DESTRUCTIVE_TEST_DATABASE_ACK", "")
    if not raw_url:
        raise RuntimeError(
            "FACAI_TEST_DATABASE_URL is required for the PostgreSQL integration model tests"
        )
    url = make_url(raw_url)
    expected = {
        "driver": "postgresql+psycopg",
        "username": "facai_test",
        "host": "127.0.0.1",
        "port": 55432,
        "database": EXPECTED_POSTGRES_TEST_DATABASE,
        "acknowledgement": EXPECTED_POSTGRES_TEST_DATABASE,
    }
    actual = {
        "driver": url.drivername,
        "username": url.username,
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "acknowledgement": acknowledgement,
    }
    if actual != expected or url.password is not None or url.query:
        raise RuntimeError(
            "Refusing destructive PostgreSQL model tests: expected the guarded "
            "loopback facai_ecommerce_test database and exact acknowledgement"
        )
    return raw_url


class SharedTypeContractTests(unittest.TestCase):
    def test_provider_values_are_stable(self):
        self.assertEqual(
            [item.value for item in Provider],
            ["qianchuan", "doudian", "taobao", "pdd"],
        )

    def test_control_enum_values_are_stable(self):
        expected = {
            ConnectionStatus: [
                "setup_required",
                "authorizing",
                "active",
                "permission_limited",
                "syncing",
                "degraded",
                "reauthorization_required",
                "disabled",
            ],
            ConnectionType: ["shop", "ad_account"],
            AuthorizationStatus: [
                "active",
                "reauthorization_required",
                "revoked",
                "disabled",
            ],
            EventIdScope: ["provider", "subject"],
            ResourceType: [
                "shops",
                "products",
                "skus",
                "inventory",
                "orders",
                "order_items",
                "refunds",
                "shipments",
                "settlements",
                "daily_metrics",
                "ad_accounts",
                "ad_entities",
                "ad_daily_metrics",
                "ad_balance_snapshots",
                "ad_finance_transactions",
            ],
            SyncSource: ["scheduled", "manual", "event", "backfill", "retry"],
            SyncStatus: [
                "queued",
                "running",
                "retry_wait",
                "succeeded",
                "partial_success",
                "failed",
                "cancelled",
            ],
            JobType: [
                "sync_resource",
                "refresh_authorization",
                "process_event",
                "archive_cleanup",
                "export",
                "purge_connection",
            ],
            JobStatus: [
                "queued",
                "leased",
                "running",
                "retry_wait",
                "succeeded",
                "failed",
                "cancelled",
            ],
            CheckpointStatus: ["pending", "running", "retry_wait", "complete", "failed"],
            CapabilityStage: [
                "docs_verified",
                "oauth_verified",
                "backfill_verified",
                "incremental_verified",
                "reconciled",
            ],
            ExportStatus: ["queued", "running", "ready", "failed", "expired"],
        }
        for enum_type, values in expected.items():
            with self.subTest(enum_type=enum_type.__name__):
                self.assertEqual([item.value for item in enum_type], values)

    def test_normalized_business_status_values_are_stable(self):
        expected = {
            OrderStatus: [
                "unknown",
                "pending_payment",
                "paid",
                "shipped",
                "completed",
                "closed",
            ],
            ProductStatus: ["unknown", "on_sale", "off_shelf", "deleted"],
            AccountStatus: ["unknown", "active", "inactive", "closed"],
            RefundStatus: [
                "unknown",
                "requested",
                "processing",
                "approved",
                "rejected",
                "completed",
                "closed",
            ],
            ShipmentStatus: [
                "unknown",
                "pending",
                "shipped",
                "in_transit",
                "delivered",
                "returned",
                "cancelled",
            ],
            SettlementStatus: ["unknown", "pending", "settled", "reversed"],
            FinanceTransactionStatus: [
                "unknown",
                "pending",
                "completed",
                "failed",
                "reversed",
            ],
            AdEntityStatus: ["unknown", "active", "paused", "ended", "deleted"],
        }
        for enum_type, values in expected.items():
            with self.subTest(enum_type=enum_type.__name__):
                self.assertEqual([item.value for item in enum_type], values)

    def test_state_transition_contracts_are_stable(self):
        self.assertEqual(
            CONNECTION_STATUS_TRANSITIONS,
            {
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
            },
        )
        self.assertEqual(
            AUTHORIZATION_STATUS_TRANSITIONS,
            {
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
            },
        )
        self.assertEqual(
            CHECKPOINT_STATUS_TRANSITIONS,
            {
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
            },
        )
        self.assertEqual(
            SYNC_STATUS_TRANSITIONS,
            {
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
            },
        )
        self.assertEqual(
            JOB_STATUS_TRANSITIONS,
            {
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
            },
        )
        self.assertEqual(
            CAPABILITY_STAGE_TRANSITIONS,
            {
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
            },
        )
        self.assertEqual(
            EXPORT_STATUS_TRANSITIONS,
            {
                ExportStatus.QUEUED: frozenset({ExportStatus.RUNNING, ExportStatus.FAILED}),
                ExportStatus.RUNNING: frozenset({ExportStatus.READY, ExportStatus.FAILED}),
                ExportStatus.READY: frozenset({ExportStatus.EXPIRED}),
                ExportStatus.FAILED: frozenset(),
                ExportStatus.EXPIRED: frozenset(),
            },
        )

    def test_connector_transport_records_are_frozen_and_slotted(self):
        records = (
            TokenBundle,
            AccountIdentity,
            Capability,
            CapabilityReport,
            ConnectionContext,
            RateLimitHint,
            TimeWindow,
            NormalizedRecord,
            FetchPage,
            RevokeResult,
        )
        for record in records:
            with self.subTest(record=record.__name__):
                self.assertTrue(dataclasses.is_dataclass(record))
                self.assertTrue(record.__dataclass_params__.frozen)
                self.assertIn("__slots__", vars(record))

    def test_sensitive_transport_values_are_excluded_from_repr(self):
        now = datetime.now(timezone.utc)
        access_marker = "opaque-access-marker"
        refresh_marker = "opaque-refresh-marker"
        source_marker = "sanitized-source-private-marker"
        tokens = TokenBundle(
            access_token=access_marker,
            refresh_token=refresh_marker,
            access_expires_at=now,
            refresh_expires_at=now,
            scopes=("report.read",),
            external_subject_id="subject-1",
        )
        context = ConnectionContext(
            connection_id=1,
            authorization_id=1,
            provider=Provider.QIANCHUAN,
            connection_type=ConnectionType.AD_ACCOUNT,
            external_account_id="account-1",
            tokens=tokens,
        )
        record = NormalizedRecord(
            resource=ResourceType.ORDERS,
            external_id="order-1",
            platform_updated_at=now,
            payload={"normalized_status": "paid", "raw_status": "PAID"},
            sanitized_source_payload={"marker": source_marker},
        )

        self.assertNotIn("access_token=", repr(tokens))
        self.assertNotIn("refresh_token=", repr(tokens))
        self.assertNotIn(access_marker, repr(tokens))
        self.assertNotIn(refresh_marker, repr(tokens))
        self.assertNotIn("tokens=", repr(context))
        self.assertNotIn(access_marker, repr(context))
        self.assertNotIn("sanitized_source_payload=", repr(record))
        self.assertNotIn(source_marker, repr(record))

    def test_program_defined_transport_fields_are_stable(self):
        self.assertEqual(
            [field.name for field in dataclasses.fields(NormalizedRecord)],
            [
                "resource",
                "external_id",
                "platform_updated_at",
                "payload",
                "sanitized_source_payload",
            ],
        )
        self.assertEqual(
            [field.name for field in dataclasses.fields(FetchPage)],
            [
                "items",
                "next_cursor",
                "has_more",
                "request_id",
                "rate_limit_hint",
                "watermark",
            ],
        )
    def test_utc_now_is_timezone_aware(self):
        value = utc_now()
        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.utcoffset(), timedelta(0))

    def test_persisted_enum_uses_values_and_named_check_constraints(self):
        enum_type = persisted_enum(Provider, name="ck_example_provider")
        self.assertFalse(enum_type.native_enum)
        self.assertTrue(enum_type.create_constraint)
        self.assertTrue(enum_type.validate_strings)
        self.assertEqual(enum_type.name, "ck_example_provider")
        self.assertEqual(enum_type.enums, [item.value for item in Provider])


class IntegrationModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = database.create_database_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=CONTROL_TABLES)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _add_authorization(self, session, *, subject="subject-1"):
        authorization = IntegrationAuthorization(
            provider=Provider.QIANCHUAN,
            external_subject_id=subject,
            scopes=["report.read"],
            access_token_ciphertext=OPAQUE_CIPHERTEXT,
            access_token_tail="0000",
            status=AuthorizationStatus.ACTIVE,
            last_authorized_at=datetime.now(timezone.utc),
        )
        session.add(authorization)
        session.flush()
        return authorization

    def _add_connection(
        self,
        session,
        authorization,
        *,
        account="account-1",
        provider=Provider.QIANCHUAN,
    ):
        connection = IntegrationConnection(
            authorization_id=authorization.id,
            provider=provider,
            connection_type=ConnectionType.AD_ACCOUNT,
            external_account_id=account,
            display_name="Test account",
            status=ConnectionStatus.ACTIVE,
            capability_report={},
            earliest_available_date=date(2026, 1, 1),
        )
        session.add(connection)
        session.flush()
        return connection

    def test_metadata_retains_exactly_the_five_foundation_control_tables(self):
        self.assertEqual(
            sorted(table.name for table in CONTROL_TABLES),
            [
                "integration_app_configs",
                "integration_authorizations",
                "integration_connections",
                "integration_oauth_states",
                "integration_security_audit",
            ],
        )

    def test_duplicate_provider_app_configs_fail(self):
        session = self.Session()
        try:
            session.add_all(
                [
                    IntegrationAppConfig(
                        provider=Provider.QIANCHUAN,
                        app_id="app-1",
                        status="configured",
                    ),
                    IntegrationAppConfig(
                        provider=Provider.QIANCHUAN,
                        app_id="app-2",
                        status="configured",
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                session.commit()
        finally:
            session.rollback()
            session.close()

    def test_duplicate_provider_connection_type_and_account_fail(self):
        session = self.Session()
        try:
            authorization = self._add_authorization(session)
            self._add_connection(session, authorization)
            session.commit()

            with self.assertRaises(IntegrityError):
                self._add_connection(session, authorization)
        finally:
            session.rollback()
            session.close()

    def test_connection_provider_must_match_authorization_provider(self):
        session = self.Session()
        try:
            authorization = self._add_authorization(session)
            with self.assertRaises(IntegrityError):
                self._add_connection(
                    session,
                    authorization,
                    provider=Provider.DOUDIAN,
                )
        finally:
            session.rollback()
            session.close()

    def test_duplicate_oauth_state_hashes_fail(self):
        session = self.Session()
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            state_hash = "a" * 64
            session.add_all(
                [
                    IntegrationOAuthState(
                        state_hash=state_hash,
                        provider=Provider.DOUDIAN,
                        initiating_session_digest="b" * 64,
                        return_path="/app/api-connections",
                        expires_at=expires_at,
                    ),
                    IntegrationOAuthState(
                        state_hash=state_hash,
                        provider=Provider.DOUDIAN,
                        initiating_session_digest="c" * 64,
                        return_path="/app/api-connections",
                        expires_at=expires_at,
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                session.commit()
        finally:
            session.rollback()
            session.close()

    def test_connection_has_no_credential_columns(self):
        names = {column.name for column in IntegrationConnection.__table__.columns}
        self.assertFalse(
            names & {"access_token", "refresh_token", "app_secret", "token_ciphertext"}
        )
        self.assertFalse(any("ciphertext" in name or "secret" in name for name in names))

    def test_credential_columns_are_encrypted_text_fields_only_on_expected_records(self):
        expected = {
            "integration_app_configs": {"app_secret_ciphertext"},
            "integration_authorizations": {
                "access_token_ciphertext",
                "refresh_token_ciphertext",
            },
        }
        for table in CONTROL_TABLES:
            ciphertext_columns = {
                column.name for column in table.columns if "ciphertext" in column.name
            }
            self.assertEqual(ciphertext_columns, expected.get(table.name, set()))
            for name in ciphertext_columns:
                self.assertIsInstance(table.c[name].type, Text)

    def test_credential_tail_columns_are_limited_to_four_characters(self):
        for model, columns in (
            (IntegrationAppConfig, ("app_secret_tail",)),
            (
                IntegrationAuthorization,
                ("access_token_tail", "refresh_token_tail"),
            ),
        ):
            for name in columns:
                with self.subTest(model=model.__name__, column=name):
                    self.assertEqual(model.__table__.c[name].type.length, 4)

    def test_all_datetime_columns_are_timezone_aware(self):
        for table in CONTROL_TABLES:
            for column in table.columns:
                if isinstance(column.type, DateTime):
                    with self.subTest(table=table.name, column=column.name):
                        self.assertTrue(column.type.timezone)

    def test_app_config_status_is_intentionally_a_bounded_plain_string(self):
        status = IntegrationAppConfig.__table__.c.status
        self.assertNotIsInstance(status.type, SqlEnum)
        self.assertEqual(status.type.length, 32)
        self.assertFalse(status.nullable)
        self.assertEqual(status.default.arg, "configured")

    def test_authorization_connection_fk_is_named_and_restricts_delete(self):
        foreign_keys = [
            constraint
            for constraint in IntegrationConnection.__table__.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        ]
        self.assertEqual(len(foreign_keys), 1)
        foreign_key = foreign_keys[0]
        self.assertEqual(
            foreign_key.name,
            "fk_integration_connections_authorization_provider",
        )
        self.assertEqual(foreign_key.ondelete, "RESTRICT")
        self.assertEqual(
            [element.parent.name for element in foreign_key.elements],
            ["authorization_id", "provider"],
        )
        self.assertEqual(
            [element.target_fullname for element in foreign_key.elements],
            [
                "integration_authorizations.id",
                "integration_authorizations.provider",
            ],
        )
        self.assertTrue(IntegrationAuthorization.connections.property.passive_deletes)
        self.assertTrue(IntegrationConnection.authorization.property.passive_deletes)

    def test_authorization_declares_composite_connection_reference_key(self):
        unique_keys = {
            constraint.name: tuple(column.name for column in constraint.columns)
            for constraint in IntegrationAuthorization.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        self.assertEqual(
            unique_keys["uq_integration_authorizations_id_provider"],
            ("id", "provider"),
        )

    def test_authorization_cannot_be_deleted_while_connection_exists(self):
        session = self.Session()
        try:
            authorization = self._add_authorization(session)
            self._add_connection(session, authorization)
            session.commit()

            with self.assertRaises(IntegrityError):
                session.delete(authorization)
                session.commit()
        finally:
            session.rollback()
            session.close()

    def test_uniqueness_constraints_foreign_keys_and_indexes_are_named(self):
        for table in CONTROL_TABLES:
            for constraint in table.constraints:
                if constraint.__class__.__name__ in {"UniqueConstraint", "ForeignKeyConstraint"}:
                    with self.subTest(table=table.name, constraint=str(constraint)):
                        self.assertIsNotNone(constraint.name)
            for index in table.indexes:
                with self.subTest(table=table.name, index=str(index)):
                    self.assertIsNotNone(index.name)

    def test_every_persisted_enum_has_its_named_value_check(self):
        expected_enum_columns = {
            "integration_app_configs": {"provider"},
            "integration_authorizations": {"provider", "status"},
            "integration_connections": {"provider", "connection_type", "status"},
            "integration_oauth_states": {"provider"},
            "integration_security_audit": {"provider"},
            "integration_login_throttles": set(),
        }
        for table in CONTROL_TABLES:
            actual = {
                column.name for column in table.columns if isinstance(column.type, SqlEnum)
            }
            self.assertEqual(actual, expected_enum_columns[table.name])
            check_names = {
                constraint.name
                for constraint in table.constraints
                if isinstance(constraint, CheckConstraint)
            }
            for column_name in actual:
                column = table.c[column_name]
                expected_name = f"ck_{table.name}_{column_name}"
                with self.subTest(table=table.name, column=column_name):
                    self.assertFalse(column.type.native_enum)
                    self.assertTrue(column.type.create_constraint)
                    self.assertTrue(column.type.validate_strings)
                    self.assertEqual(column.type.name, expected_name)
                    self.assertEqual(
                        column.type.enums,
                        [item.value for item in column.type.enum_class],
                    )
                    self.assertIn(expected_name, check_names)

    def test_postgresql_ddl_uses_enum_values_in_named_check_constraints(self):
        for table in CONTROL_TABLES:
            ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
            for column in table.columns:
                if not isinstance(column.type, SqlEnum):
                    continue
                constraint_name = f"ck_{table.name}_{column.name}"
                with self.subTest(table=table.name, column=column.name):
                    self.assertIn(f"CONSTRAINT {constraint_name} CHECK", ddl)
                    for member in column.type.enum_class:
                        self.assertIn(f"'{member.value}'", ddl)
                        if member.name != member.value:
                            self.assertNotIn(f"'{member.name}'", ddl)

    def test_raw_invalid_persisted_enum_values_are_rejected(self):
        session = self.Session()
        try:
            app = IntegrationAppConfig(
                provider=Provider.QIANCHUAN,
                app_id="app-1",
                status="configured",
            )
            session.add(app)
            authorization = self._add_authorization(session)
            connection = self._add_connection(session, authorization)
            session.commit()
            identifiers = {
                "app_id": app.id,
                "authorization_id": authorization.id,
                "connection_id": connection.id,
            }
        finally:
            session.close()

        statements = (
            ("UPDATE integration_app_configs SET provider = 'invalid' WHERE id = :id", "app_id"),
            (
                "UPDATE integration_authorizations SET status = 'invalid' WHERE id = :id",
                "authorization_id",
            ),
            (
                "UPDATE integration_connections SET connection_type = 'invalid' WHERE id = :id",
                "connection_id",
            ),
            (
                "UPDATE integration_connections SET status = 'invalid' WHERE id = :id",
                "connection_id",
            ),
        )
        for sql, identifier_name in statements:
            with self.subTest(sql=sql):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(text(sql), {"id": identifiers[identifier_name]})

    def test_oauth_state_hash_must_be_64_characters(self):
        session = self.Session()
        try:
            session.add(
                IntegrationOAuthState(
                    state_hash="short",
                    provider=Provider.TAOBAO,
                    initiating_session_digest="e" * 64,
                    return_path="/app/api-connections",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                )
            )
            with self.assertRaises(IntegrityError):
                session.commit()
        finally:
            session.rollback()
            session.close()

    def test_oauth_state_accepts_only_safe_connection_return_paths(self):
        valid_paths = (
            "/app/api-connections",
            "/app/api-connections/qianchuan",
            "/app/api-connections/qianchuan/complete",
        )
        session = self.Session()
        try:
            for index, return_path in enumerate(valid_paths, start=1):
                session.add(
                    IntegrationOAuthState(
                        state_hash=f"{index:064x}",
                        provider=Provider.QIANCHUAN,
                        initiating_session_digest="f" * 64,
                        return_path=return_path,
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                    )
                )
            session.commit()
        finally:
            session.close()

        invalid_paths = (
            "https://example.invalid/app/api-connections",
            "//example.invalid/app/api-connections",
            "app/api-connections",
            "/app/api-connections/",
            "/app/api-connections/qianchuan?next=/admin",
            "/app/api-connections/qianchuan#complete",
            "/app/api-connections/../admin",
            "/app/api-connections/%2e%2e/admin",
            "/app/api-connections\\..\\admin",
            "/app/other",
        )
        for index, return_path in enumerate(invalid_paths, start=100):
            with self.subTest(return_path=return_path):
                session = self.Session()
                try:
                    session.add(
                        IntegrationOAuthState(
                            state_hash=f"{index:064x}",
                            provider=Provider.PDD,
                            initiating_session_digest="a" * 64,
                            return_path=return_path,
                            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                        )
                    )
                    with self.assertRaises(IntegrityError):
                        session.commit()
                finally:
                    session.rollback()
                    session.close()

    def test_oauth_return_path_check_is_named(self):
        check_names = {
            constraint.name
            for constraint in IntegrationOAuthState.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertIn("ck_integration_oauth_states_return_path", check_names)

    def test_commerce_models_register_the_normalized_domain(self):
        declared_models = [
            value
            for value in vars(commerce_models).values()
            if isinstance(value, type)
            and value is not Base
            and issubclass(value, Base)
        ]
        self.assertEqual(
            {model.__tablename__ for model in declared_models},
            {
                "commerce_shops",
                "commerce_products",
                "commerce_skus",
                "commerce_inventory_snapshots",
                "commerce_product_links",
                "commerce_orders",
                "commerce_order_items",
                "commerce_refunds",
                "commerce_shipments",
                "commerce_settlements",
                "commerce_daily_metrics",
                "commerce_ad_accounts",
                "commerce_ad_entities",
                "commerce_ad_daily_metrics",
                "commerce_ad_balance_snapshots",
                "commerce_ad_finance_transactions",
                "commerce_event_inbox",
            },
        )

    def test_init_db_imports_both_new_model_modules_unconditionally(self):
        imported = []
        real_import = __import__

        def recording_import(name, *args, **kwargs):
            imported.append(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=recording_import), patch.object(
            database.Base.metadata, "create_all"
        ), patch.object(database, "_schema_migration_required", return_value=False), patch.object(
            database, "_ensure_creator_indexes"
        ), patch.object(database, "_ensure_compatible_columns"), patch.object(
            database, "_ensure_creator_integrity_triggers"
        ):
            database.init_db()

        self.assertIn("integration_models", imported)
        self.assertIn("commerce_models", imported)


class DisposablePostgresGuardTests(unittest.TestCase):
    def test_missing_postgres_environment_fails_clearly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FACAI_TEST_DATABASE_URL is required"):
                _require_disposable_postgres_url()

    def test_unsafe_postgres_environment_fails_closed(self):
        unsafe = {
            "FACAI_TEST_DATABASE_URL": "postgresql+psycopg://admin@db.example/prod",
            "FACAI_DESTRUCTIVE_TEST_DATABASE_ACK": "prod",
        }
        with patch.dict(os.environ, unsafe, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Refusing destructive PostgreSQL"):
                _require_disposable_postgres_url()

    def test_postgres_query_and_fragment_overrides_fail_before_engine_creation(self):
        base_url = (
            "postgresql+psycopg://facai_test@127.0.0.1:55432/"
            "facai_ecommerce_test"
        )
        unsafe_suffixes = (
            "?host=db.example&port=5432&dbname=prod",
            "?sslmode=require",
            "#fragment",
        )
        for suffix in unsafe_suffixes:
            with self.subTest(suffix=suffix), patch.dict(
                os.environ,
                {
                    "FACAI_TEST_DATABASE_URL": f"{base_url}{suffix}",
                    "FACAI_DESTRUCTIVE_TEST_DATABASE_ACK": EXPECTED_POSTGRES_TEST_DATABASE,
                },
                clear=True,
            ), patch.object(database, "create_database_engine") as create_engine:
                try:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "Refusing destructive PostgreSQL",
                    ):
                        guarded_url = _require_disposable_postgres_url()
                        database.create_database_engine(guarded_url)
                finally:
                    create_engine.assert_not_called()


class PostgresIntegrationModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        try:
            Base.metadata.drop_all(cls.engine, tables=CONTROL_TABLES, checkfirst=True)
            Base.metadata.create_all(cls.engine, tables=CONTROL_TABLES, checkfirst=False)
        except Exception:
            Base.metadata.drop_all(cls.engine, tables=CONTROL_TABLES, checkfirst=True)
            cls.engine.dispose()
            raise
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=CONTROL_TABLES, checkfirst=True)
            remaining = set(inspect(cls.engine).get_table_names()) & {
                table.name for table in CONTROL_TABLES
            }
            if remaining:
                raise AssertionError(
                    f"PostgreSQL control-table cleanup left tables behind: {sorted(remaining)}"
                )
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine, tables=CONTROL_TABLES, checkfirst=True)
        Base.metadata.create_all(self.engine, tables=CONTROL_TABLES, checkfirst=False)

    def _seed_contract_rows(self):
        session = self.Session()
        try:
            app = IntegrationAppConfig(
                provider=Provider.QIANCHUAN,
                app_id="postgres-app",
                status="configured",
            )
            authorization = IntegrationAuthorization(
                provider=Provider.QIANCHUAN,
                external_subject_id="postgres-subject",
                scopes=["report.read"],
                access_token_ciphertext=OPAQUE_CIPHERTEXT,
                access_token_tail="0000",
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=datetime.now(timezone.utc),
            )
            session.add_all((app, authorization))
            session.flush()
            connection = IntegrationConnection(
                authorization_id=authorization.id,
                provider=Provider.QIANCHUAN,
                connection_type=ConnectionType.AD_ACCOUNT,
                external_account_id="postgres-account",
                display_name="PostgreSQL test account",
                status=ConnectionStatus.ACTIVE,
                capability_report={},
            )
            session.add(connection)
            session.commit()
            return app.id, authorization.id, connection.id
        finally:
            session.close()

    def test_postgres_rejects_raw_invalid_enum_values(self):
        app_id, authorization_id, connection_id = self._seed_contract_rows()
        statements = (
            (
                "UPDATE integration_app_configs SET provider = 'invalid' WHERE id = :id",
                app_id,
            ),
            (
                "UPDATE integration_authorizations SET status = 'invalid' WHERE id = :id",
                authorization_id,
            ),
            (
                "UPDATE integration_connections SET connection_type = 'invalid' WHERE id = :id",
                connection_id,
            ),
            (
                "UPDATE integration_connections SET status = 'invalid' WHERE id = :id",
                connection_id,
            ),
        )
        for sql, identifier in statements:
            with self.subTest(sql=sql):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(text(sql), {"id": identifier})

    def test_postgres_rejects_connection_provider_mismatch(self):
        _, _, connection_id = self._seed_contract_rows()
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE integration_connections SET provider = 'doudian' "
                        "WHERE id = :id"
                    ),
                    {"id": connection_id},
                )

    def test_postgres_rejects_unsafe_oauth_return_paths(self):
        invalid_paths = (
            "https://example.invalid/app/api-connections",
            "//example.invalid/app/api-connections",
            "/app/api-connections/qianchuan?next=/admin",
            "/app/api-connections/qianchuan#complete",
            "/app/api-connections/../admin",
            "/app/api-connections\\..\\admin",
        )
        for index, return_path in enumerate(invalid_paths, start=1):
            with self.subTest(return_path=return_path):
                session = self.Session()
                try:
                    session.add(
                        IntegrationOAuthState(
                            state_hash=f"{index + 1000:064x}",
                            provider=Provider.DOUDIAN,
                            initiating_session_digest="c" * 64,
                            return_path=return_path,
                            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                        )
                    )
                    with self.assertRaises(IntegrityError):
                        session.commit()
                finally:
                    session.rollback()
                    session.close()


if __name__ == "__main__":
    unittest.main()
