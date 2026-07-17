import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import database
from commerce_models import (
    CommerceAdDailyMetric,
    CommerceAdEntity,
    CommerceDailyMetric,
    CommerceOrder,
    CommerceProduct,
    CommerceRefund,
)
from database import Base, get_db
from integration_models import (
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationExportJob,
    IntegrationJob,
    IntegrationSecurityAudit,
)
from integrations.audit import write_security_audit
from integrations.actor import IntegrationActor, current_integration_actor
from integrations.exports import (
    ExportRequestConflict,
    ExportWriteError,
    create_export_job,
    expire_export_files,
    generate_export_job,
    write_export_file,
)
from integrations.management import enqueue_manual_sync, list_connection_views
from integrations.purge import purge_connection_data
from integrations.reporting import (
    ReportingRange,
    list_ad_entities,
    list_ad_metrics,
    list_orders,
    list_products,
    list_refunds,
    overview,
)
from integrations.schemas import ExportCreateRequest, ManualSyncRequest
from integrations.types import (
    AdEntityStatus,
    AdEntityType,
    AuthorizationStatus,
    ConnectionStatus,
    ConnectionType,
    ExportStatus,
    MetricGranularity,
    OrderStatus,
    ProductStatus,
    Provider,
    RefundStatus,
)
from models import Product
from main import app
from tests.test_integration_models import _require_disposable_postgres_url


UTC = timezone.utc


class IntegrationFeaturePostgresAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.addClassCleanup(cls._cleanup)

    @classmethod
    def _cleanup(cls):
        try:
            Base.metadata.drop_all(cls.engine, checkfirst=True)
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine, checkfirst=True)
        Base.metadata.create_all(self.engine, checkfirst=False)
        self.now = datetime(2026, 7, 13, 4, 0, tzinfo=UTC)
        with self.Session.begin() as db:
            order_authorization = IntegrationAuthorization(
                provider=Provider.DOUDIAN,
                external_subject_id="subject-orders",
                scopes=["orders.read", "products.read"],
                access_token_ciphertext="opaque-order-token",
                access_token_tail="1234",
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=self.now,
            )
            daily_authorization = IntegrationAuthorization(
                provider=Provider.QIANCHUAN,
                external_subject_id="subject-daily",
                scopes=["reports.read"],
                access_token_ciphertext="opaque-daily-token",
                access_token_tail="5678",
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=self.now,
            )
            db.add_all((order_authorization, daily_authorization))
            db.flush()
            order_connection = IntegrationConnection(
                authorization_id=order_authorization.id,
                provider=Provider.DOUDIAN,
                connection_type=ConnectionType.SHOP,
                external_account_id="shop-orders",
                display_name="订单口径店铺",
                status=ConnectionStatus.ACTIVE,
                capability_report={
                    "verified_resources": [
                        "orders",
                        "products",
                        "refunds",
                        "ad_entities",
                        "ad_daily_metrics",
                    ],
                    "overview_commerce_source": "order_ledger",
                    "overview_ad_entity_type": "campaign",
                },
            )
            daily_connection = IntegrationConnection(
                authorization_id=daily_authorization.id,
                provider=Provider.QIANCHUAN,
                connection_type=ConnectionType.AD_ACCOUNT,
                external_account_id="account-daily",
                display_name="日报口径账户",
                status=ConnectionStatus.ACTIVE,
                capability_report={
                    "verified_resources": ["daily_metrics", "ad_daily_metrics"],
                    "overview_commerce_source": "provider_daily",
                    "overview_ad_entity_type": "campaign",
                },
            )
            db.add_all((order_connection, daily_connection))
            db.flush()
            self.order_connection_id = order_connection.id
            self.daily_connection_id = daily_connection.id
            self.order_authorization_id = order_authorization.id
            self._insert_reporting_rows(db)

    def _envelope(self, connection_id, provider, *, updated_at=None):
        return {
            "connection_id": connection_id,
            "provider": provider,
            "platform_updated_at": updated_at or self.now,
            "platform_metadata": {},
        }

    def _insert_reporting_rows(self, db):
        order_base = self._envelope(self.order_connection_id, Provider.DOUDIAN)
        db.add_all(
            (
                CommerceOrder(
                    **order_base,
                    external_order_id="order-001",
                    normalized_status=OrderStatus.PAID,
                    raw_status="PAID",
                    buyer_digest="a" * 64,
                    currency="CNY",
                    order_amount=Decimal("110.00"),
                    paid_amount=Decimal("100.00"),
                    discount_amount=Decimal("10.00"),
                    shipping_amount=Decimal("0.00"),
                    ordered_at=self.now - timedelta(hours=1),
                    paid_at=self.now,
                ),
                CommerceOrder(
                    **order_base,
                    external_order_id="order-percent-%",
                    normalized_status=OrderStatus.COMPLETED,
                    raw_status="DONE",
                    currency="USD",
                    order_amount=Decimal("25.00"),
                    paid_amount=Decimal("25.00"),
                    discount_amount=Decimal("0.00"),
                    shipping_amount=Decimal("0.00"),
                    ordered_at=self.now,
                    paid_at=self.now,
                ),
                CommerceOrder(
                    **order_base,
                    external_order_id="order-missing-paid-time",
                    normalized_status=OrderStatus.SHIPPED,
                    raw_status="SHIPPED",
                    currency="CNY",
                    order_amount=Decimal("50.00"),
                    paid_amount=Decimal("50.00"),
                    discount_amount=Decimal("0.00"),
                    shipping_amount=Decimal("0.00"),
                    ordered_at=None,
                    paid_at=None,
                ),
                CommerceRefund(
                    **order_base,
                    external_refund_id="refund-001",
                    external_order_id="order-001",
                    normalized_status=RefundStatus.COMPLETED,
                    raw_status="DONE",
                    amount=Decimal("10.00"),
                    currency="CNY",
                    reason_code="quality",
                    refund_created_at=self.now,
                    refund_updated_at=self.now,
                    completed_at=self.now,
                ),
                CommerceProduct(
                    **order_base,
                    external_product_id="product-001",
                    title="安全商品",
                    normalized_status=ProductStatus.ON_SALE,
                    raw_status="ONLINE",
                    category="food",
                    price=Decimal("12.30"),
                    currency="CNY",
                ),
                CommerceAdEntity(
                    **order_base,
                    entity_type=AdEntityType.CAMPAIGN,
                    external_entity_id="campaign-001",
                    name="计划一",
                    normalized_status=AdEntityStatus.ACTIVE,
                    raw_status="ENABLE",
                ),
                CommerceAdDailyMetric(
                    **order_base,
                    entity_type=AdEntityType.CAMPAIGN,
                    external_entity_id="campaign-001",
                    stat_date=date(2026, 7, 13),
                    granularity=MetricGranularity.DAY,
                    spend=Decimal("15.00"),
                    impressions=1000,
                    clicks=100,
                    orders=1,
                    attributed_sales=Decimal("60.00"),
                    ctr=Decimal("0.100000"),
                    cvr=Decimal("0.010000"),
                    roi=Decimal("4.000000"),
                    currency="CNY",
                ),
            )
        )
        daily_base = self._envelope(
            self.daily_connection_id,
            Provider.QIANCHUAN,
        )
        db.add_all(
            (
                CommerceDailyMetric(
                    **daily_base,
                    stat_date=date(2026, 7, 13),
                    granularity=MetricGranularity.DAY,
                    actual_sales=Decimal("200.00"),
                    order_count=2,
                    refund_amount=Decimal("20.00"),
                    refund_count=1,
                    visitor_count=100,
                    buyer_count=2,
                    currency="CNY",
                ),
                CommerceAdDailyMetric(
                    **daily_base,
                    entity_type=AdEntityType.CAMPAIGN,
                    external_entity_id="campaign-002",
                    stat_date=date(2026, 7, 13),
                    granularity=MetricGranularity.DAY,
                    spend=Decimal("25.00"),
                    impressions=2000,
                    clicks=200,
                    orders=2,
                    attributed_sales=Decimal("100.00"),
                    currency="CNY",
                ),
            )
        )

    def _range(self):
        return ReportingRange.from_dates(
            date_from=date(2026, 7, 13),
            date_to=date(2026, 7, 13),
            today=date(2026, 7, 13),
        )

    def test_reporting_queries_and_overview_use_real_postgres_and_safe_fields(self):
        with self.Session() as db:
            orders = list_orders(db, reporting_range=self._range())
            literal_percent = list_orders(
                db,
                reporting_range=self._range(),
                search="%",
            )
            products = list_products(db, reporting_range=self._range())
            refunds = list_refunds(db, reporting_range=self._range())
            ad_entities = list_ad_entities(db, reporting_range=self._range())
            ad_metrics = list_ad_metrics(db, reporting_range=self._range())
            summary = overview(db, reporting_range=self._range())

        self.assertEqual(orders.total, 3)
        self.assertEqual(literal_percent.total, 1)
        self.assertEqual(products.total, 1)
        self.assertEqual(refunds.total, 1)
        self.assertEqual(ad_entities.total, 1)
        self.assertEqual(ad_metrics.total, 2)
        self.assertNotIn("buyer_digest", repr(orders.items))
        self.assertNotIn("platform_metadata", repr(orders.items))
        self.assertEqual(summary["actual_sales"], "300.00")
        self.assertEqual(summary["order_count"], 3)
        self.assertEqual(summary["refund_amount"], "30.00")
        self.assertEqual(summary["ad_spend"], "40.00")
        self.assertEqual(summary["ad_attributed_sales"], "160.00")
        self.assertEqual(
            summary["source_breakdown"],
            {"order_ledger": 1, "provider_daily": 1, "none": 0},
        )
        self.assertEqual(summary["data_quality"]["excluded_currencies"], ["USD"])
        self.assertEqual(summary["data_quality"]["missing_paid_time_orders"], 1)

    def test_manual_sync_is_idempotent_and_management_views_hide_tokens(self):
        request = ManualSyncRequest.model_validate(
            {
                "resources": ["orders"],
                "date_from": "2026-07-13",
                "date_to": "2026-07-13",
                "request_id": "018f5ad8-02bd-7f11-8fa0-4d05074b68db",
            }
        )
        with self.Session.begin() as db:
            enqueue_manual_sync(
                db,
                connection_id=self.order_connection_id,
                request=request,
                now=self.now,
            )
            enqueue_manual_sync(
                db,
                connection_id=self.order_connection_id,
                request=request,
                now=self.now,
            )
        with self.Session() as db:
            job_count = int(db.scalar(select(func.count()).select_from(IntegrationJob)))
            views = list_connection_views(db)

        self.assertEqual(job_count, 1)
        encoded = repr(views)
        self.assertIn("••••1234", encoded)
        self.assertNotIn("opaque-order-token", encoded)
        self.assertNotIn("access_token_ciphertext", encoded)

    def test_export_lifecycle_and_connection_purge_delete_only_contained_data(self):
        export_request = ExportCreateRequest.model_validate(
            {
                "resource_type": "orders",
                "format": "csv",
                "filters": {
                    "connection_id": self.order_connection_id,
                    "date_from": "2026-07-13",
                    "date_to": "2026-07-13",
                },
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            archive_dir = Path(directory)
            with self.Session.begin() as db:
                export_job = create_export_job(
                    db,
                    requester_session_digest="b" * 64,
                    request=export_request,
                    now=self.now,
                )
                export_id = export_job.id
                public_id = export_job.public_id
            with self.Session.begin() as db:
                generated = generate_export_job(
                    db,
                    export_job_id=export_id,
                    archive_dir=archive_dir,
                    now=self.now,
                )
                self.assertEqual(generated.status, ExportStatus.READY)
                self.assertEqual(generated.row_count, 3)
                export_path = archive_dir / generated.relative_file_path
            self.assertTrue(export_path.is_file())
            export_text = export_path.read_text(encoding="utf-8-sig")
            self.assertIn("order-001", export_text)
            self.assertNotIn("opaque-order-token", export_text)

            broad_request = ExportCreateRequest.model_validate(
                {
                    "resource_type": "orders",
                    "format": "csv",
                    "filters": {
                        "date_from": "2026-07-13",
                        "date_to": "2026-07-13",
                    },
                }
            )
            with self.Session.begin() as db:
                broad_job = create_export_job(
                    db,
                    requester_session_digest="d" * 64,
                    request=broad_request,
                    now=self.now,
                )
                broad_id = broad_job.id
            with self.Session.begin() as db:
                broad_job = generate_export_job(
                    db,
                    export_job_id=broad_id,
                    archive_dir=archive_dir,
                    now=self.now,
                )
                broad_path = archive_dir / broad_job.relative_file_path
                self.assertEqual(
                    broad_job.filters["_included_connection_ids"],
                    [self.order_connection_id],
                )
            self.assertTrue(broad_path.is_file())

            with self.Session.begin() as db:
                write_security_audit(
                    db,
                    event_type="connection_disabled",
                    outcome="success",
                    summary_code="connection_disabled",
                    session_digest="c" * 64,
                    provider=Provider.DOUDIAN,
                    target_type="connection",
                    target_id=str(self.order_connection_id),
                    details={},
                )
                result = purge_connection_data(
                    db,
                    connection_id=self.order_connection_id,
                    archive_dir=archive_dir,
                )
            self.assertTrue(result.connection_deleted)
            self.assertTrue(result.authorization_deleted)
            self.assertEqual(result.export_files_deleted, 2)
            self.assertFalse(export_path.exists())
            self.assertFalse(broad_path.exists())

            with self.Session() as db:
                self.assertIsNone(
                    db.get(IntegrationConnection, self.order_connection_id)
                )
                self.assertIsNotNone(
                    db.get(IntegrationConnection, self.daily_connection_id)
                )
                self.assertIsNone(
                    db.get(IntegrationAuthorization, self.order_authorization_id)
                )
                self.assertEqual(
                    int(
                        db.scalar(
                            select(func.count()).select_from(
                                IntegrationSecurityAudit
                            )
                        )
                    ),
                    1,
                )
                self.assertIsNone(db.get(IntegrationExportJob, export_id))
                self.assertIsNone(db.get(IntegrationExportJob, broad_id))
                self.assertEqual(
                    int(db.scalar(select(func.count()).select_from(IntegrationJob))),
                    0,
                )

            with self.Session.begin() as db:
                second = purge_connection_data(
                    db,
                    connection_id=self.order_connection_id,
                    archive_dir=archive_dir,
                )
                expired, retry = expire_export_files(
                    db,
                    archive_dir=archive_dir,
                    now=self.now + timedelta(hours=25),
                )
            self.assertFalse(second.connection_deleted)
            self.assertEqual((expired, retry), (0, 0))

    def test_real_routes_poll_download_audit_and_leave_expiry_for_file_first_cleanup(self):
        claims = IntegrationActor("route-acceptance-session")

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[current_integration_actor] = lambda: claims
        client = TestClient(app)
        try:
            orders = client.get(
                "/api/operations/orders",
                params={"date_from": "2026-07-13", "date_to": "2026-07-13"},
            )
            self.assertEqual(orders.status_code, 200)
            self.assertEqual(orders.json()["total"], 3)
            self.assertNotIn("buyer_digest", orders.text)

            with tempfile.TemporaryDirectory() as directory:
                archive_dir = Path(directory)
                created = client.post(
                    "/api/operations/exports",
                    json={
                        "resource_type": "orders",
                        "format": "csv",
                        "filters": {
                            "connection_id": self.order_connection_id,
                            "date_from": "2026-07-13",
                            "date_to": "2026-07-13",
                        },
                    },
                )
                self.assertEqual(created.status_code, 202)
                public_id = created.json()["id"]
                with self.Session() as db:
                    export_job = db.scalar(
                        select(IntegrationExportJob).where(
                            IntegrationExportJob.public_id == public_id
                        )
                    )
                    export_job_id = export_job.id
                with self.Session.begin() as db:
                    generated = generate_export_job(
                        db,
                        export_job_id=export_job_id,
                        archive_dir=archive_dir,
                        now=self.now,
                    )
                    relative_path = generated.relative_file_path

                polled = client.get(f"/api/operations/exports/{public_id}")
                self.assertEqual(polled.status_code, 200)
                self.assertEqual(polled.json()["status"], "ready")
                with patch(
                    "routers.integrations._credential_settings_or_503",
                    return_value=SimpleNamespace(archive_dir=archive_dir),
                ):
                    downloaded = client.get(
                        f"/api/operations/exports/{public_id}/download"
                    )
                self.assertEqual(downloaded.status_code, 200)
                self.assertEqual(downloaded.headers["cache-control"], "no-store")

                with self.Session.begin() as db:
                    export_job = db.scalar(
                        select(IntegrationExportJob).where(
                            IntegrationExportJob.public_id == public_id
                        )
                    )
                    export_job.expires_at = datetime.now(UTC) - timedelta(minutes=1)
                    self.assertEqual(export_job.status, ExportStatus.READY)
                with patch(
                    "routers.integrations._credential_settings_or_503",
                    return_value=SimpleNamespace(archive_dir=archive_dir),
                ):
                    expired_download = client.get(
                        f"/api/operations/exports/{public_id}/download"
                    )
                self.assertEqual(expired_download.status_code, 410)
                with self.Session.begin() as db:
                    export_job = db.scalar(
                        select(IntegrationExportJob).where(
                            IntegrationExportJob.public_id == public_id
                        )
                    )
                    self.assertEqual(export_job.status, ExportStatus.READY)
                    deleted, retry = expire_export_files(
                        db,
                        archive_dir=archive_dir,
                        now=datetime.now(UTC),
                    )
                self.assertEqual((deleted, retry), (1, 0))
                self.assertFalse((archive_dir / relative_path).exists())

                rejected = client.post(
                    "/api/integrations/connections/999999/sync",
                    json={
                        "resources": ["orders"],
                        "date_from": "2026-07-13",
                        "date_to": "2026-07-13",
                        "request_id": "018f5ad8-02bd-7f11-8fa0-4d05074b68db",
                    },
                )
                self.assertEqual(rejected.status_code, 404)
                self.assertNotIn("999999", rejected.text)
                validation_rejected = client.post(
                    f"/api/integrations/connections/{self.order_connection_id}/sync",
                    json={
                        "resources": ["orders"],
                        "date_from": "2026-07-13",
                        "date_to": "2026-07-13",
                        "request_id": "018f5ad8-02bd-7f11-8fa0-4d05074b68db",
                        "access_token": "must-not-be-echoed-or-audited",
                    },
                )
                self.assertEqual(validation_rejected.status_code, 422)
                self.assertNotIn("must-not-be-echoed-or-audited", validation_rejected.text)
                sensitive_target = "11010520000101001X"
                invalid_path_responses = (
                    client.post(
                        f"/api/integrations/connections/{sensitive_target}/sync",
                        json={
                            "resources": ["orders"],
                            "date_from": "2026-07-13",
                            "date_to": "2026-07-13",
                            "request_id": "018f5ad8-02bd-7f11-8fa0-4d05074b68db",
                        },
                    ),
                    client.delete(
                        f"/api/integrations/connections/{sensitive_target}"
                    ),
                    client.delete(
                        f"/api/integrations/authorizations/{sensitive_target}"
                    ),
                    client.delete(
                        f"/api/operations/products/{sensitive_target}/link"
                    ),
                )
                self.assertTrue(
                    all(response.status_code == 422 for response in invalid_path_responses)
                )
                authorization_rejected = client.post(
                    "/api/integrations/providers/doudian/authorize",
                    json={"return_path": "/app/api-connections"},
                )
                self.assertEqual(authorization_rejected.status_code, 503)

                with self.Session() as db:
                    event_types = db.scalars(
                        select(IntegrationSecurityAudit.event_type).order_by(
                            IntegrationSecurityAudit.id
                        )
                    ).all()
                    self.assertEqual(
                        event_types,
                        [
                            "integration_mutation_rejected",
                            "integration_mutation_rejected",
                            "integration_mutation_rejected",
                            "integration_mutation_rejected",
                            "integration_mutation_rejected",
                            "authorization_start_rejected",
                        ],
                    )
                    rejected_audits = db.scalars(
                        select(IntegrationSecurityAudit).where(
                            IntegrationSecurityAudit.event_type
                            == "integration_mutation_rejected"
                        ).order_by(IntegrationSecurityAudit.id)
                    ).all()
                    self.assertEqual(
                        [audit.details for audit in rejected_audits],
                        [
                            {
                                "operation": "manual_sync",
                                "reason": "connection_not_found",
                            },
                            {
                                "operation": "manual_sync",
                                "reason": "validation_rejected",
                            },
                            {
                                "operation": "manual_sync",
                                "reason": "validation_rejected",
                            },
                            {
                                "operation": "disable_connection",
                                "reason": "validation_rejected",
                            },
                            {
                                "operation": "disable_authorization",
                                "reason": "validation_rejected",
                            },
                        ],
                    )
                    self.assertTrue(
                        all(
                            audit.target_id.endswith(":unknown")
                            for audit in rejected_audits[2:]
                        )
                    )
                    self.assertNotIn(
                        sensitive_target,
                        repr([audit.target_id for audit in rejected_audits]),
                    )
        finally:
            app.dependency_overrides.clear()

    def test_concurrent_connection_purges_remove_the_last_shared_authorization(self):
        with self.Session.begin() as db:
            sibling = IntegrationConnection(
                authorization_id=self.order_authorization_id,
                provider=Provider.DOUDIAN,
                connection_type=ConnectionType.AD_ACCOUNT,
                external_account_id="shared-auth-sibling",
                display_name="共享授权广告账户",
                status=ConnectionStatus.ACTIVE,
                capability_report={},
            )
            db.add(sibling)
            db.flush()
            sibling_id = sibling.id

        with tempfile.TemporaryDirectory() as directory:
            def purge(connection_id):
                with self.Session.begin() as db:
                    return purge_connection_data(
                        db,
                        connection_id=connection_id,
                        archive_dir=directory,
                    )

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(purge, (self.order_connection_id, sibling_id))
                )

        self.assertEqual(sum(result.connection_deleted for result in results), 2)
        self.assertEqual(sum(result.authorization_deleted for result in results), 1)
        with self.Session() as db:
            self.assertIsNone(
                db.get(IntegrationAuthorization, self.order_authorization_id)
            )
            self.assertIsNone(db.get(IntegrationConnection, sibling_id))

    def test_purge_connection_lock_rejects_a_racing_exact_export(self):
        request = ExportCreateRequest.model_validate(
            {
                "resource_type": "orders",
                "format": "csv",
                "filters": {"connection_id": self.order_connection_id},
            }
        )
        with self.Session.begin() as db:
            create_export_job(
                db,
                requester_session_digest="7" * 64,
                request=request,
                now=self.now,
            )
        entered_scan = Event()
        release_scan = Event()

        from integrations import purge as purge_module

        original_contains = purge_module._export_contains_connection

        def paused_contains(export_job, connection):
            entered_scan.set()
            if not release_scan.wait(timeout=5):
                raise AssertionError("purge scan release timed out")
            return original_contains(export_job, connection)

        def purge():
            with self.Session.begin() as db:
                return purge_connection_data(
                    db,
                    connection_id=self.order_connection_id,
                    archive_dir=tempfile.gettempdir(),
                )

        def create_racing_export():
            with self.Session.begin() as db:
                return create_export_job(
                    db,
                    requester_session_digest="8" * 64,
                    request=request,
                    now=self.now,
                )

        with patch(
            "integrations.purge._export_contains_connection",
            side_effect=paused_contains,
        ), ThreadPoolExecutor(max_workers=2) as pool:
            purge_future = pool.submit(purge)
            self.assertTrue(entered_scan.wait(timeout=5))
            export_future = pool.submit(create_racing_export)
            self.assertFalse(export_future.done())
            release_scan.set()
            purge_result = purge_future.result(timeout=5)
            with self.assertRaises(ExportRequestConflict):
                export_future.result(timeout=5)

        self.assertTrue(purge_result.connection_deleted)
        with self.Session() as db:
            self.assertEqual(
                int(db.scalar(select(func.count()).select_from(IntegrationExportJob))),
                0,
            )
            self.assertEqual(
                int(db.scalar(select(func.count()).select_from(IntegrationJob))),
                0,
            )

    def test_expiry_skips_locked_generation_then_deletes_the_committed_file(self):
        request = ExportCreateRequest.model_validate(
            {
                "resource_type": "orders",
                "format": "csv",
                "filters": {
                    "connection_id": self.order_connection_id,
                    "date_from": "2026-07-13",
                    "date_to": "2026-07-13",
                },
            }
        )
        with self.Session.begin() as db:
            export_job = create_export_job(
                db,
                requester_session_digest="9" * 64,
                request=request,
                now=self.now,
            )
            export_job.expires_at = self.now + timedelta(hours=1)
            export_id = export_job.id
        entered_write = Event()
        release_write = Event()

        def paused_write(**kwargs):
            entered_write.set()
            if not release_write.wait(timeout=5):
                raise AssertionError("export write release timed out")
            return write_export_file(**kwargs)

        with tempfile.TemporaryDirectory() as directory:
            def generate():
                with self.Session.begin() as db:
                    job = generate_export_job(
                        db,
                        export_job_id=export_id,
                        archive_dir=directory,
                        now=self.now,
                    )
                    return job.relative_file_path

            with patch(
                "integrations.exports.write_export_file",
                side_effect=paused_write,
            ), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(generate)
                self.assertTrue(entered_write.wait(timeout=5))
                with self.Session.begin() as db:
                    first_cleanup = expire_export_files(
                        db,
                        archive_dir=directory,
                        now=self.now + timedelta(hours=2),
                    )
                self.assertEqual(first_cleanup, (0, 0))
                release_write.set()
                relative_path = future.result(timeout=5)

            committed_path = Path(directory) / relative_path
            self.assertTrue(committed_path.is_file())
            with self.Session.begin() as db:
                second_cleanup = expire_export_files(
                    db,
                    archive_dir=directory,
                    now=self.now + timedelta(hours=2),
                )
            self.assertEqual(second_cleanup, (1, 0))
            self.assertFalse(committed_path.exists())

    def test_export_generation_failure_is_running_until_the_terminal_attempt(self):
        request = ExportCreateRequest.model_validate(
            {
                "resource_type": "orders",
                "format": "csv",
                "filters": {"connection_id": self.order_connection_id},
            }
        )
        with self.Session.begin() as db:
            job = create_export_job(
                db,
                requester_session_digest="6" * 64,
                request=request,
                now=self.now,
            )
            export_id = job.id

        with patch(
            "integrations.exports.write_export_file",
            side_effect=ExportWriteError("closed test failure"),
        ):
            with self.Session.begin() as db:
                retrying = generate_export_job(
                    db,
                    export_job_id=export_id,
                    archive_dir=tempfile.gettempdir(),
                    now=self.now,
                    terminal_failure=False,
                )
                self.assertEqual(retrying.status, ExportStatus.RUNNING)
                self.assertIsNone(retrying.error_code)
                self.assertIsNone(retrying.completed_at)
            with self.Session.begin() as db:
                terminal = generate_export_job(
                    db,
                    export_job_id=export_id,
                    archive_dir=tempfile.gettempdir(),
                    now=self.now + timedelta(minutes=1),
                    terminal_failure=True,
                )
                self.assertEqual(terminal.status, ExportStatus.FAILED)
                self.assertEqual(terminal.error_code, "export_generation_failed")
                self.assertIsNotNone(terminal.completed_at)

    def test_overview_excludes_closed_orders_incomplete_refunds_and_other_ad_levels(self):
        base = self._envelope(self.order_connection_id, Provider.DOUDIAN)
        with self.Session.begin() as db:
            db.add_all(
                (
                    CommerceOrder(
                        **base,
                        external_order_id="closed-order",
                        normalized_status=OrderStatus.CLOSED,
                        raw_status="CLOSED",
                        currency="CNY",
                        order_amount=Decimal("999.00"),
                        paid_amount=Decimal("999.00"),
                        discount_amount=Decimal("0.00"),
                        shipping_amount=Decimal("0.00"),
                        ordered_at=self.now,
                        paid_at=self.now,
                    ),
                    CommerceRefund(
                        **base,
                        external_refund_id="processing-refund",
                        external_order_id="order-001",
                        normalized_status=RefundStatus.PROCESSING,
                        raw_status="PROCESSING",
                        amount=Decimal("888.00"),
                        currency="CNY",
                        refund_created_at=self.now,
                        refund_updated_at=self.now,
                        completed_at=self.now,
                    ),
                    CommerceAdDailyMetric(
                        **base,
                        entity_type=AdEntityType.CREATIVE,
                        external_entity_id="creative-other-level",
                        stat_date=date(2026, 7, 13),
                        granularity=MetricGranularity.DAY,
                        spend=Decimal("777.00"),
                        impressions=1,
                        clicks=1,
                        orders=1,
                        attributed_sales=Decimal("777.00"),
                        currency="CNY",
                    ),
                )
            )
        with self.Session() as db:
            summary = overview(db, reporting_range=self._range())
            empty = overview(
                db,
                reporting_range=self._range(),
                provider=Provider.PDD,
            )

        self.assertEqual(summary["actual_sales"], "300.00")
        self.assertEqual(summary["refund_amount"], "30.00")
        self.assertEqual(summary["ad_spend"], "40.00")
        self.assertEqual(summary["average_order_value"], "100.00")
        self.assertEqual(empty["actual_sales"], "0.00")
        self.assertEqual(empty["order_count"], 0)
        self.assertEqual(empty["average_order_value"], "0.00")

    def test_product_link_routes_round_trip_without_integration_admin_audit(self):
        with self.Session.begin() as db:
            internal = Product(name="内部蛋糕", category="cake", price=88.0)
            db.add(internal)
            db.flush()
            internal_id = internal.id
            commerce_id = db.scalar(
                select(CommerceProduct.id).where(
                    CommerceProduct.connection_id == self.order_connection_id
                )
            )
        claims = IntegrationActor("product-link-session")

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[current_integration_actor] = lambda: claims
        client = TestClient(app)
        try:
            linked = client.put(
                f"/api/operations/products/{commerce_id}/link",
                json={"product_id": internal_id},
            )
            self.assertEqual(linked.status_code, 200)
            products = client.get(
                "/api/operations/products",
                params={
                    "date_from": "2026-07-13",
                    "date_to": "2026-07-13",
                    "link_status": "linked",
                },
            )
            self.assertEqual(products.status_code, 200)
            self.assertEqual(products.json()["total"], 1)
            self.assertEqual(
                products.json()["items"][0]["product_link"]["product_name"],
                "内部蛋糕",
            )
            unlinked = client.delete(
                f"/api/operations/products/{commerce_id}/link"
            )
            self.assertEqual(unlinked.status_code, 200)
        finally:
            app.dependency_overrides.clear()

        with self.Session() as db:
            event_types = db.scalars(
                select(IntegrationSecurityAudit.event_type).order_by(
                    IntegrationSecurityAudit.id
                )
            ).all()
        self.assertEqual(event_types, [])


if __name__ == "__main__":
    unittest.main()
