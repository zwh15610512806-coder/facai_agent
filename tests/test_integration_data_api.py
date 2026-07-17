import unittest
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from database import get_db
from integrations.reporting import (
    PageResult,
    ReportingRange,
    decimal_text,
    order_view,
    refund_view,
    sanitize_search,
)
from integrations.schemas import (
    CommonDataQuery,
    ManualSyncRequest,
    OrderDataQuery,
    ProductLinkUpdate,
    PurgeConnectionRequest,
)
from integrations.types import OrderStatus, Provider, RefundStatus
from main import app


UTC = timezone.utc


class ReportingContractTests(unittest.TestCase):
    def test_query_models_are_strict_and_enforce_page_and_range_contracts(self):
        query = CommonDataQuery.model_validate({})
        self.assertEqual(query.page, 1)
        self.assertEqual(query.per_page, 50)
        with self.assertRaises(ValidationError):
            CommonDataQuery.model_validate({"per_page": 51})
        with self.assertRaises(ValidationError):
            CommonDataQuery.model_validate({"unexpected": "rejected"})
        with self.assertRaises(ValidationError):
            CommonDataQuery.model_validate(
                {"date_from": "2025-01-01", "date_to": "2026-07-14"}
            )
        with self.assertRaises(ValidationError):
            OrderDataQuery.model_validate({"status": "not-a-status"})
        for sensitive_search in (
            "13800138000",
            "11010520000101001X",
            "Bearer secret-token",
            "%31%33%38%30%30%31%33%38%30%30%30",
            "client-secret=abc",
            "refresh token=abc",
            "app_secret=abc",
        ):
            with self.subTest(search=sensitive_search), self.assertRaises(
                ValidationError
            ):
                OrderDataQuery.model_validate({"search": sensitive_search})
        with self.assertRaises(ValidationError):
            ProductLinkUpdate.model_validate({"product_id": 0})

        manual = ManualSyncRequest.model_validate(
            {
                "resources": ["orders"],
                "date_from": "2026-07-01",
                "date_to": "2026-07-02",
                "request_id": "018f5ad8-02bd-7f11-8fa0-4d05074b68db",
            }
        )
        self.assertEqual(len(manual.resources), 1)
        with self.assertRaises(ValidationError):
            ManualSyncRequest.model_validate(
                {
                    "resources": ["order_items"],
                    "date_from": "2026-07-02",
                    "date_to": "2026-07-01",
                    "request_id": "not-a-uuid",
                }
            )
        with self.assertRaises(ValidationError) as raised:
            PurgeConnectionRequest.model_validate(
                {"confirmation": "", "extra": 1}
            )
        self.assertIn("confirmation", str(raised.exception))

    def test_default_range_is_thirty_local_days_with_utc_exclusive_bounds(self):
        selected = ReportingRange.from_dates(
            date_from=None,
            date_to=None,
            today=date(2026, 7, 14),
        )

        self.assertEqual(selected.date_from, date(2026, 6, 15))
        self.assertEqual(selected.date_to, date(2026, 7, 14))
        self.assertEqual(
            selected.start_at,
            datetime(2026, 6, 14, 16, 0, tzinfo=UTC),
        )
        self.assertEqual(
            selected.end_at,
            datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
        )

    def test_range_is_inclusive_by_date_and_rejects_more_than_366_days(self):
        selected = ReportingRange.from_dates(
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 1),
            today=date(2026, 7, 14),
        )
        self.assertEqual(selected.days, 1)

        with self.assertRaisesRegex(ValueError, "366"):
            ReportingRange.from_dates(
                date_from=date(2025, 1, 1),
                date_to=date(2026, 7, 14),
                today=date(2026, 7, 14),
            )
        with self.assertRaises(ValueError):
            ReportingRange.from_dates(
                date_from=date(2026, 7, 2),
                date_to=date(2026, 7, 1),
                today=date(2026, 7, 14),
            )

    def test_money_and_ratio_serialization_is_fixed_and_never_float(self):
        self.assertEqual(decimal_text(Decimal("1"), scale=2), "1.00")
        self.assertEqual(decimal_text(Decimal("0.123456"), scale=6), "0.123456")
        with self.assertRaises(TypeError):
            decimal_text(1.2, scale=2)
        with self.assertRaises(ValueError):
            decimal_text(Decimal("NaN"), scale=2)

    def test_search_is_trimmed_bounded_and_control_character_free(self):
        self.assertIsNone(sanitize_search(None))
        self.assertEqual(sanitize_search("  safe-id-001  "), "safe-id-001")
        with self.assertRaises(ValueError):
            sanitize_search("\runsafe")
        with self.assertRaises(ValueError):
            sanitize_search("x" * 201)

    def test_order_and_refund_views_expose_no_buyer_or_raw_platform_payload(self):
        order = SimpleNamespace(
            id=7,
            connection_id=3,
            provider=Provider.DOUDIAN,
            external_order_id="order-007",
            normalized_status=OrderStatus.PAID,
            raw_status="paid",
            currency="CNY",
            order_amount=Decimal("100"),
            paid_amount=Decimal("90"),
            discount_amount=Decimal("10"),
            shipping_amount=Decimal("0"),
            ordered_at=datetime(2026, 7, 13, 1, 0, tzinfo=UTC),
            paid_at=datetime(2026, 7, 13, 1, 5, tzinfo=UTC),
            shipped_at=None,
            completed_at=None,
            platform_updated_at=datetime(2026, 7, 13, 1, 6, tzinfo=UTC),
            buyer_digest="a" * 64,
            platform_metadata={"secret": "must-not-appear"},
        )
        refund = SimpleNamespace(
            id=8,
            connection_id=3,
            provider=Provider.DOUDIAN,
            external_refund_id="refund-008",
            external_order_id="order-007",
            normalized_status=RefundStatus.COMPLETED,
            raw_status="done",
            amount=Decimal("12.30"),
            currency="CNY",
            reason_code="quality",
            refund_created_at=datetime(2026, 7, 13, 2, 0, tzinfo=UTC),
            refund_updated_at=datetime(2026, 7, 13, 2, 5, tzinfo=UTC),
            completed_at=datetime(2026, 7, 13, 2, 5, tzinfo=UTC),
            platform_updated_at=datetime(2026, 7, 13, 2, 6, tzinfo=UTC),
            platform_metadata={"access_token": "must-not-appear"},
        )

        order_payload = order_view(order)
        refund_payload = refund_view(refund)
        encoded = repr({"order": order_payload, "refund": refund_payload}).lower()

        self.assertEqual(order_payload["paid_amount"], "90.00")
        self.assertEqual(refund_payload["amount"], "12.30")
        for forbidden in (
            "buyer",
            "platform_metadata",
            "access_token",
            "must-not-appear",
        ):
            self.assertNotIn(forbidden, encoded)


class ReportingEndpointContractTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_db] = lambda: object()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_orders_route_uses_strict_query_and_repository_page_shape(self):
        empty = PageResult(items=[], total=0, page=1, per_page=50, total_pages=1)
        with patch("routers.integrations.list_orders", return_value=empty, create=True):
            response = self.client.get("/api/operations/orders")
            unknown = self.client.get(
                "/api/operations/orders",
                params={"unexpected": "rejected"},
            )
            legacy = self.client.get("/api/integrations/data/orders")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"items": [], "total": 0, "page": 1, "per_page": 50, "total_pages": 1},
        )
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(legacy.status_code, 404)


if __name__ == "__main__":
    unittest.main()
