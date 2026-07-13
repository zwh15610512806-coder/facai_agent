import unittest

from pydantic import ValidationError

from creator_schemas import (
    AmountStatus,
    CollaborationStatus,
    CollaborationType,
    CreatorStage,
    FollowupMethod,
    SampleOrderStatus,
    CreatorCreate,
    CreatorUpdate,
    CreatorAddressCreate,
    BdMemberUpdate,
    CreatorAddressUpdate,
    CreatorFollowupUpdate,
    CreatorFollowupCreate,
    CreatorCollaborationUpdate,
    CreatorPortraitUpdate,
    CreatorPortraitCreate,
    CreatorCollaborationCreate,
    CollaborationProductIn,
    CollaborationProductUpdate,
    CreatorSampleOrderCreate,
    SampleOrderItemIn,
    SampleOrderItemUpdate,
)


class CreatorSchemaTests(unittest.TestCase):
    def test_domain_enums_have_the_required_values(self):
        self.assertEqual(
            {item.value for item in CreatorStage},
            {"lead", "contacted", "negotiating", "sampled", "scheduled", "cooperating", "completed", "paused"},
        )
        self.assertEqual({item.value for item in CollaborationType}, {"short_video", "live", "graphic", "other"})
        self.assertEqual({item.value for item in CollaborationStatus}, {"planned", "in_progress", "completed", "cancelled"})
        self.assertEqual({item.value for item in AmountStatus}, {"pending", "confirmed"})
        self.assertEqual({item.value for item in SampleOrderStatus}, {"pending_shipment", "shipped", "received", "cancelled"})
        self.assertEqual({item.value for item in FollowupMethod}, {"douyin", "wechat", "phone", "offline", "other"})

    def test_creator_requires_identity_and_rejects_unknown_fields(self):
        with self.assertRaises(ValidationError):
            CreatorCreate(nickname="没有身份")
        with self.assertRaises(ValidationError):
            CreatorCreate(nickname="达人", douyin_handle="cake", unexpected=True)

        creator = CreatorCreate(nickname="达人", douyin_handle=" @Cake ")
        self.assertEqual("@Cake", creator.douyin_handle)

    def test_portrait_ranges_are_strict(self):
        with self.assertRaises(ValidationError):
            CreatorPortraitUpdate(follower_count=-1)
        with self.assertRaises(ValidationError):
            CreatorPortraitUpdate(fit_score=6)

        portrait = CreatorPortraitUpdate(follower_count=0, fit_score=5)
        self.assertEqual(5, portrait.fit_score)
        self.assertEqual([], CreatorPortraitCreate().primary_categories)

    def test_collaboration_money_and_sample_quantity_are_strict(self):
        with self.assertRaises(ValidationError):
            CreatorCollaborationCreate(
                internal_code="C-1",
                collaboration_type="live",
                collaboration_date="2026-07-13",
                actual_paid_cents=-1,
            )
        with self.assertRaises(ValidationError):
            SampleOrderItemIn(product_id=1, quantity=0)
        with self.assertRaises(ValidationError):
            SampleOrderItemIn(product_id=1, quantity="2")
        with self.assertRaises(ValidationError):
            CreatorCollaborationCreate(
                internal_code="C-typed",
                collaboration_type="live",
                collaboration_date="2026-07-13",
                actual_paid_cents=True,
            )

        collaboration = CreatorCollaborationCreate(
            internal_code="C-1",
            collaboration_type="live",
            collaboration_date="2026-07-13",
            products=[CollaborationProductIn(product_id=1)],
        )
        order = CreatorSampleOrderCreate(
            idempotency_key="7ee19c18-a3fd-43e9-9b2c-77e7f2737d42",
            address_id=1,
            items=[SampleOrderItemIn(product_id=1, quantity=2)],
        )
        self.assertEqual(0, collaboration.actual_paid_cents)
        self.assertEqual(2, order.items[0].quantity)
        self.assertEqual("新规格", CollaborationProductUpdate(note="新规格").note)
        self.assertEqual(3, SampleOrderItemUpdate(quantity=3).quantity)

    def test_partial_updates_reject_explicit_null_for_non_nullable_fields(self):
        cases = (
            (BdMemberUpdate, {"name": None}),
            (BdMemberUpdate, {"active": None}),
            (CreatorUpdate, {"nickname": None}),
            (CreatorUpdate, {"stage": None}),
            (CreatorAddressUpdate, {"recipient_name": None}),
            (CreatorAddressUpdate, {"is_default": None}),
            (CreatorFollowupUpdate, {"method": None}),
            (CreatorFollowupUpdate, {"content": None}),
            (CreatorCollaborationUpdate, {"status": None}),
            (CreatorCollaborationUpdate, {"actual_paid_cents": None}),
            (CreatorPortraitUpdate, {"primary_categories": None}),
            (CreatorPortraitUpdate, {"audience_profile": None}),
        )
        for model, payload in cases:
            with self.subTest(model=model.__name__, payload=payload):
                with self.assertRaises(ValidationError):
                    model.model_validate(payload)

    def test_creator_owner_and_boolean_request_fields_are_strict(self):
        invalid_cases = (
            (CreatorCreate, {"nickname": "达人", "douyin_handle": "strict", "owner_id": "1"}),
            (CreatorFollowupCreate, {"method": "wechat", "content": "跟进", "owner_id": "1"}),
            (CreatorAddressCreate, {"recipient_name": "张三", "phone": "13812345678", "province": "粤", "city": "深", "detail": "地址", "is_default": "true"}),
            (CreatorAddressUpdate, {"is_default": "false"}),
            (BdMemberUpdate, {"active": "false"}),
        )
        for model, payload in invalid_cases:
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
