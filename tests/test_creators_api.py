import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import creator_models  # noqa: F401
import models  # noqa: F401
from creator_models import Creator, CreatorSampleOrder
from creator_schemas import CreatorSampleOrderUpdate
from database import Base
from models import Product
from routers import creators as creators_router
from services import creator_service
from sqlalchemy.exc import IntegrityError


class CreatorApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        app = FastAPI()

        def override_db():
            yield self.db

        app.dependency_overrides[creators_router.get_db] = override_db
        app.include_router(creators_router.router, prefix="/api/creators")
        self.client = TestClient(app)

        self.product_a = Product(name="法采草莓果酱", category="果酱", price=59, status="active")
        self.product_b = Product(name="法采奶油", category="乳品", price=39, status="active")
        self.db.add_all([self.product_a, self.product_b])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def create_member(self, name="小王"):
        response = self.client.post("/api/creators/bd-members", json={"name": name})
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def create_creator(self, **overrides):
        payload = {
            "nickname": "烘焙小麦",
            "douyin_handle": "@CakeWheat",
            "contact_name": "张麦",
            "contact_phone": "13812345678",
            "wechat_id": "cake_wheat_88",
            "tags": ["烘焙", "教程"],
        }
        payload.update(overrides)
        response = self.client.post("/api/creators", json=payload)
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def test_create_and_update_store_canonical_douyin_handle(self):
        created = self.create_creator(
            nickname="标准抖音号达人",
            douyin_handle="  @CanonicalCreate  ",
        )
        self.assertEqual("CanonicalCreate", created["douyin_handle"])
        self.assertEqual(
            "CanonicalCreate",
            self.db.query(Creator).filter(Creator.id == created["id"]).one().douyin_handle,
        )

        updated = self.client.put(
            f"/api/creators/{created['id']}",
            json={"douyin_handle": " @CanonicalUpdate "},
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual("CanonicalUpdate", updated.json()["douyin_handle"])
        self.assertEqual(
            "CanonicalUpdate",
            self.db.query(Creator).filter(Creator.id == created["id"]).one().douyin_handle,
        )

    def test_creator_crud_duplicate_identity_pagination_and_privacy(self):
        member = self.create_member()
        creator = self.create_creator(owner_id=member["id"])

        duplicate = self.client.post(
            "/api/creators",
            json={"nickname": "重复达人", "douyin_handle": "cakewheat"},
        )
        self.assertEqual(409, duplicate.status_code)

        listed = self.client.get(
            "/api/creators",
            params={"search": "小麦", "stage": "lead", "owner_id": member["id"]},
        )
        self.assertEqual(200, listed.status_code, listed.text)
        data = listed.json()
        self.assertEqual({"items", "total", "page", "per_page", "total_pages"}, set(data))
        self.assertEqual(1, data["total"])
        self.assertEqual("138****5678", data["items"][0]["masked_contact_phone"])
        self.assertNotIn("contact_phone", data["items"][0])

        detail = self.client.get(f"/api/creators/{creator['id']}").json()
        self.assertTrue(detail["masked_wechat_id"].startswith("cake"))
        self.assertNotIn("cake_wheat_88", detail["masked_wechat_id"])
        self.assertNotIn("contact_phone", detail)

        private = self.client.get(f"/api/creators/{creator['id']}/private-contact")
        self.assertEqual("no-store", private.headers["cache-control"])
        self.assertEqual("13812345678", private.json()["contact_phone"])

        archived = self.client.delete(f"/api/creators/{creator['id']}")
        self.assertEqual(200, archived.status_code)
        self.assertEqual(0, self.client.get("/api/creators").json()["total"])

    def test_short_private_values_are_never_fully_exposed_in_masked_responses(self):
        creator = self.create_creator(
            nickname="短联系方式达人",
            douyin_handle="short-contact",
            contact_phone="1234567",
            wechat_id="abcd",
        )
        detail = self.client.get(f"/api/creators/{creator['id']}").json()
        listed = self.client.get("/api/creators", params={"search": "短联系方式"}).json()["items"][0]
        self.assertNotIn("1234567", listed["masked_contact_phone"])
        self.assertNotIn("abcd", detail["masked_wechat_id"])
        self.assertIn("*", listed["masked_contact_phone"])
        self.assertIn("*", detail["masked_wechat_id"])

        single = self.create_creator(
            nickname="单字符达人",
            douyin_handle="single-contact",
            contact_name="张",
            contact_phone="1",
            wechat_id="a",
        )
        single_detail = self.client.get(f"/api/creators/{single['id']}").json()
        self.assertNotIn("张", single_detail["contact_name"])
        self.assertNotIn("1", single_detail["masked_contact_phone"])
        self.assertNotIn("a", single_detail["masked_wechat_id"])

    def test_category_filter_uses_exact_json_membership_and_tier_validation(self):
        family = self.create_creator(nickname="家庭烘焙达人", douyin_handle="family-bake")
        broad = self.create_creator(nickname="家庭达人", douyin_handle="family-only")
        for creator, category, followers in (
            (family, "家庭烘焙", 120000),
            (broad, "家庭", 8000),
        ):
            response = self.client.put(
                f"/api/creators/{creator['id']}/portrait",
                json={"primary_categories": [category], "follower_count": followers},
            )
            self.assertEqual(200, response.status_code, response.text)

        exact = self.client.get("/api/creators", params={"category": "家庭"}).json()
        self.assertEqual(["家庭达人"], [item["nickname"] for item in exact["items"]])
        tier = self.client.get("/api/creators", params={"follower_tier": "100k_500k"}).json()
        self.assertEqual(["家庭烘焙达人"], [item["nickname"] for item in tier["items"]])
        combined = self.client.get(
            "/api/creators",
            params={"category": "家庭", "follower_tier": "under_10k"},
        )
        self.assertEqual(200, combined.status_code, combined.text)
        self.assertEqual(["家庭达人"], [item["nickname"] for item in combined.json()["items"]])
        self.assertEqual(422, self.client.get("/api/creators", params={"follower_tier": "wrong"}).status_code)

    def test_unknown_fields_and_cross_creator_address_use_are_rejected(self):
        unknown = self.client.post(
            "/api/creators",
            json={"nickname": "错误", "douyin_handle": "bad-fields", "secret": "no"},
        )
        self.assertEqual(422, unknown.status_code)
        first = self.create_creator(nickname="甲", douyin_handle="owner-a")
        second = self.create_creator(nickname="乙", douyin_handle="owner-b")
        address = self.client.post(
            f"/api/creators/{first['id']}/addresses",
            json={
                "recipient_name": "甲",
                "phone": "13812345678",
                "province": "广东省",
                "city": "深圳市",
                "detail": "甲地址",
            },
        ).json()
        wrong_owner = self.client.post(
            f"/api/creators/{second['id']}/sample-orders",
            json={
                "idempotency_key": "wrong-owner-address",
                "address_id": address["id"],
                "items": [{"product_id": self.product_a.id, "quantity": 1}],
            },
        )
        self.assertEqual(404, wrong_owner.status_code)

    def test_portrait_followup_updates_stage_and_builds_rule_summary(self):
        member = self.create_member()
        creator = self.create_creator(owner_id=member["id"])

        portrait = self.client.put(
            f"/api/creators/{creator['id']}/portrait",
            json={
                "primary_categories": ["家庭烘焙"],
                "content_formats": ["教程", "直播"],
                "follower_count": 128000,
                "regions": ["华东"],
                "fit_score": 5,
            },
        )
        self.assertEqual(200, portrait.status_code, portrait.text)

        followup = self.client.post(
            f"/api/creators/{creator['id']}/followups",
            json={
                "owner_id": member["id"],
                "method": "wechat",
                "content": "确认可以先寄样，再讨论直播排期",
                "result": "同意寄样",
                "stage_after": "negotiating",
                "next_followup_at": "2026-07-20T10:00:00",
            },
        )
        self.assertEqual(201, followup.status_code, followup.text)

        detail = self.client.get(f"/api/creators/{creator['id']}").json()
        self.assertEqual("negotiating", detail["stage"])
        self.assertIn("家庭烘焙", detail["portrait_summary"])
        self.assertIn("12.8万粉", detail["portrait_summary"])
        self.assertEqual(1, detail["followup_count"])

    def test_portrait_rejects_null_for_non_nullable_json_fields_without_persisting(self):
        creator = self.create_creator()
        initial = self.client.put(
            f"/api/creators/{creator['id']}/portrait",
            json={"primary_categories": ["烘焙"], "audience_profile": {"age": "25-34"}},
        )
        self.assertEqual(200, initial.status_code, initial.text)

        for payload in ({"primary_categories": None}, {"audience_profile": None}):
            with self.subTest(payload=payload):
                response = self.client.put(
                    f"/api/creators/{creator['id']}/portrait", json=payload
                )
                self.assertEqual(422, response.status_code, response.text)

        saved = self.client.get(f"/api/creators/{creator['id']}").json()["portrait"]
        self.assertEqual(["烘焙"], saved["primary_categories"])
        self.assertEqual({"age": "25-34"}, saved["audience_profile"])

    def test_multi_product_collaboration_aggregates_only_confirmed_non_cancelled(self):
        member = self.create_member()
        creator = self.create_creator(owner_id=member["id"])
        first = self.client.post(
            f"/api/creators/{creator['id']}/collaborations",
            json={
                "owner_id": member["id"],
                "internal_code": "COOP-001",
                "collaboration_type": "live",
                "collaboration_date": "2026-07-10",
                "status": "completed",
                "actual_paid_cents": 12860000,
                "amount_status": "confirmed",
                "products": [
                    {"product_id": self.product_a.id},
                    {"product_id": self.product_b.id, "note": "直播主推"},
                ],
            },
        )
        self.assertEqual(201, first.status_code, first.text)
        self.assertEqual(
            ["法采草莓果酱", "法采奶油"],
            [item["product_name_snapshot"] for item in first.json()["products"]],
        )
        repeated_products = self.client.put(
            f"/api/creators/{creator['id']}/collaborations/{first.json()['id']}",
            json={
                "products": [
                    {"product_id": self.product_a.id},
                    {"product_id": self.product_b.id, "note": "直播主推"},
                ]
            },
        )
        self.assertEqual(200, repeated_products.status_code, repeated_products.text)

        cancelled = self.client.post(
            f"/api/creators/{creator['id']}/collaborations",
            json={
                "internal_code": "COOP-002",
                "collaboration_type": "short_video",
                "collaboration_date": "2026-07-11",
                "status": "cancelled",
                "actual_paid_cents": 99900,
                "amount_status": "confirmed",
            },
        )
        self.assertEqual(201, cancelled.status_code, cancelled.text)

        metrics = self.client.get(f"/api/creators/{creator['id']}").json()["metrics"]
        self.assertEqual(12860000, metrics["confirmed_paid_cents"])
        self.assertEqual(1, metrics["confirmed_collaboration_count"])

        corrected = self.client.put(
            f"/api/creators/{creator['id']}/collaborations/{first.json()['id']}",
            json={"actual_paid_cents": 12000000},
        )
        self.assertEqual(200, corrected.status_code, corrected.text)
        metrics = self.client.get(f"/api/creators/{creator['id']}").json()["metrics"]
        self.assertEqual(12000000, metrics["confirmed_paid_cents"])

        illegal = self.client.put(
            f"/api/creators/{creator['id']}/collaborations/{first.json()['id']}",
            json={"status": "in_progress"},
        )
        self.assertEqual(422, illegal.status_code)

    def test_sample_order_snapshots_address_is_idempotent_and_enforces_state_machine(self):
        creator = self.create_creator()
        address = self.client.post(
            f"/api/creators/{creator['id']}/addresses",
            json={
                "recipient_name": "张麦",
                "phone": "13812345678",
                "province": "广东省",
                "city": "深圳市",
                "district": "南山区",
                "detail": "科技园 8 号 1201",
                "is_default": True,
            },
        )
        self.assertEqual(201, address.status_code, address.text)
        address_id = address.json()["id"]

        payload = {
            "idempotency_key": "sample-creator-0001",
            "address_id": address_id,
            "items": [
                {"product_id": self.product_a.id, "specification": "500g", "quantity": 2},
                {"product_id": self.product_b.id, "quantity": 1},
            ],
        }
        created = self.client.post(f"/api/creators/{creator['id']}/sample-orders", json=payload)
        replayed = self.client.post(f"/api/creators/{creator['id']}/sample-orders", json=payload)
        self.assertEqual(201, created.status_code, created.text)
        self.assertEqual(200, replayed.status_code, replayed.text)
        self.assertEqual(created.json()["id"], replayed.json()["id"])
        conflicting_replay = self.client.post(
            f"/api/creators/{creator['id']}/sample-orders",
            json={
                **payload,
                "items": [{"product_id": self.product_b.id, "quantity": 9}],
                "notes": "不同载荷",
            },
        )
        self.assertEqual(409, conflicting_replay.status_code, conflicting_replay.text)
        order_id = created.json()["id"]

        self.client.put(
            f"/api/creators/{creator['id']}/addresses/{address_id}",
            json={"detail": "新地址 99 号"},
        )
        orders = self.client.get(f"/api/creators/{creator['id']}/sample-orders").json()
        self.assertNotIn("科技园", orders[0]["address_detail_snapshot"])
        self.assertNotIn("新地址", orders[0]["address_detail_snapshot"])
        saved_order = self.db.query(CreatorSampleOrder).filter(CreatorSampleOrder.id == order_id).one()
        self.assertIn("科技园", saved_order.address_detail_snapshot)
        self.assertNotIn("新地址", saved_order.address_detail_snapshot)

        missing_shipping = self.client.put(
            f"/api/creators/{creator['id']}/sample-orders/{order_id}",
            json={"status": "shipped"},
        )
        self.assertEqual(422, missing_shipping.status_code)

        shipped = self.client.put(
            f"/api/creators/{creator['id']}/sample-orders/{order_id}",
            json={"status": "shipped", "shipping_company": "顺丰", "tracking_number": "SF123"},
        )
        self.assertEqual(200, shipped.status_code, shipped.text)
        duplicate_shipping_update = self.client.put(
            f"/api/creators/{creator['id']}/sample-orders/{order_id}",
            json={"status": "shipped", "shipping_company": "圆通", "tracking_number": "YT999"},
        )
        self.assertEqual(422, duplicate_shipping_update.status_code, duplicate_shipping_update.text)
        self.db.expire_all()
        unchanged_shipping = self.db.query(CreatorSampleOrder).filter_by(id=order_id).one()
        self.assertEqual("顺丰", unchanged_shipping.shipping_company)
        self.assertEqual("SF123", unchanged_shipping.tracking_number)
        received = self.client.put(
            f"/api/creators/{creator['id']}/sample-orders/{order_id}",
            json={"status": "received"},
        )
        self.assertEqual(200, received.status_code, received.text)
        cancelled_after_received = self.client.put(
            f"/api/creators/{creator['id']}/sample-orders/{order_id}",
            json={"status": "cancelled"},
        )
        self.assertEqual(422, cancelled_after_received.status_code)
        same_terminal_with_note = self.client.put(
            f"/api/creators/{creator['id']}/sample-orders/{order_id}",
            json={"status": "received", "notes": "不应允许修改"},
        )
        self.assertEqual(422, same_terminal_with_note.status_code)

    def test_concurrent_sample_updates_use_compare_and_set(self):
        creator = self.create_creator()
        address = self.client.post(
            f"/api/creators/{creator['id']}/addresses",
            json={
                "recipient_name": "并发收件人",
                "phone": "13812345678",
                "province": "广东省",
                "city": "深圳市",
                "detail": "并发测试地址",
            },
        ).json()
        order = self.client.post(
            f"/api/creators/{creator['id']}/sample-orders",
            json={
                "idempotency_key": "concurrent-sample-order",
                "address_id": address["id"],
                "items": [{"product_id": self.product_a.id}],
            },
        ).json()

        session_a = self.Session()
        session_b = self.Session()
        try:
            stale_order = session_b.query(CreatorSampleOrder).filter_by(id=order["id"]).one()
            session_a.query(CreatorSampleOrder).filter_by(id=order["id"]).update(
                {
                    CreatorSampleOrder.status: "shipped",
                    CreatorSampleOrder.shipping_company: "顺丰",
                    CreatorSampleOrder.tracking_number: "SF-CONCURRENT",
                    CreatorSampleOrder.shipped_at: creator_service._utcnow(),
                },
                synchronize_session=False,
            )
            session_a.commit()
            with patch(
                "services.creator_service._get_sample_order",
                return_value=stale_order,
            ):
                with self.assertRaises(HTTPException) as context:
                    creator_service.update_sample_order(
                        session_b,
                        creator["id"],
                        order["id"],
                        CreatorSampleOrderUpdate(status="cancelled"),
                    )
            self.assertEqual(409, context.exception.status_code)
        finally:
            session_a.close()
            session_b.close()

        self.db.expire_all()
        saved = self.db.query(CreatorSampleOrder).filter_by(id=order["id"]).one()
        self.assertEqual("shipped", saved.status)
        self.assertIsNotNone(saved.shipped_at)

    def test_idempotent_commit_recovers_existing_order_after_unique_race(self):
        existing = SimpleNamespace(
            id=9,
            creator_id=3,
            idempotency_key="race-key",
            request_fingerprint="same-fingerprint",
        )
        pending = SimpleNamespace(
            id=None,
            creator_id=3,
            idempotency_key="race-key",
            request_fingerprint="same-fingerprint",
        )
        db = MagicMock()
        db.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
        db.query.return_value.filter.return_value.first.return_value = existing

        order, created = creator_service._commit_sample_order(db, pending)

        self.assertIs(existing, order)
        self.assertFalse(created)
        db.rollback.assert_called_once()

    def test_main_application_registers_creator_api(self):
        from main import app

        self.assertIn("/api/creators", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
