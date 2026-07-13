import unittest

from sqlalchemy import CheckConstraint, Index

import models  # noqa: F401 - register existing product table metadata
from database import Base
from creator_models import normalize_douyin_handle, normalize_platform_uid


class CreatorModelTests(unittest.TestCase):
    def test_metadata_registers_all_creator_domain_tables(self):
        self.assertGreaterEqual(
            set(Base.metadata.tables),
            {
                "bd_members",
                "creators",
                "creator_portraits",
                "creator_addresses",
                "creator_followups",
                "creator_collaborations",
                "creator_collaboration_products",
                "creator_sample_orders",
                "creator_sample_order_items",
                "creator_import_batches",
            },
        )

    def test_creator_identity_and_relationship_constraints_are_declared(self):
        creators = Base.metadata.tables["creators"]
        creator_checks = {
            constraint.name
            for constraint in creators.constraints
            if isinstance(constraint, CheckConstraint)
        }
        creator_indexes = {index.name: index for index in creators.indexes if isinstance(index, Index)}

        self.assertIn("ck_creators_identity_present", creator_checks)
        identity_sql = str(
            next(
                constraint.sqltext
                for constraint in creators.constraints
                if isinstance(constraint, CheckConstraint)
                and constraint.name == "ck_creators_identity_present"
            )
        ).lower()
        self.assertIn("length(trim(platform_uid_normalized))", identity_sql)
        self.assertIn("length(trim(douyin_handle_normalized))", identity_sql)
        self.assertTrue(creator_indexes["uq_creators_platform_uid"].unique)
        self.assertTrue(creator_indexes["uq_creators_douyin_handle"].unique)
        self.assertEqual(
            "SET NULL",
            next(iter(creators.c.owner_id.foreign_keys)).ondelete,
        )

    def test_money_quantity_and_delete_policies_are_declared(self):
        collaborations = Base.metadata.tables["creator_collaborations"]
        sample_items = Base.metadata.tables["creator_sample_order_items"]
        collaboration_products = Base.metadata.tables["creator_collaboration_products"]

        collaboration_checks = {
            constraint.name
            for constraint in collaborations.constraints
            if isinstance(constraint, CheckConstraint)
        }
        sample_checks = {
            constraint.name
            for constraint in sample_items.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertIn("ck_creator_collaborations_paid_nonnegative", collaboration_checks)
        self.assertIn("ck_creator_sample_items_quantity_positive", sample_checks)
        self.assertEqual(
            "SET NULL",
            next(iter(collaboration_products.c.product_id.foreign_keys)).ondelete,
        )
        self.assertEqual(
            "CASCADE",
            next(iter(sample_items.c.sample_order_id.foreign_keys)).ondelete,
        )

        internal_code_checks = {
            constraint.name
            for constraint in collaborations.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertIn("ck_creator_collaborations_internal_code_nonblank", internal_code_checks)

    def test_all_cross_domain_foreign_keys_have_explicit_delete_policy(self):
        expected = {
            ("creators", "owner_id"): "SET NULL",
            ("creator_portraits", "creator_id"): "CASCADE",
            ("creator_addresses", "creator_id"): "CASCADE",
            ("creator_followups", "creator_id"): "CASCADE",
            ("creator_followups", "owner_id"): "SET NULL",
            ("creator_collaborations", "creator_id"): "CASCADE",
            ("creator_collaborations", "owner_id"): "SET NULL",
            ("creator_collaboration_products", "collaboration_id"): "CASCADE",
            ("creator_collaboration_products", "product_id"): "SET NULL",
            ("creator_sample_orders", "creator_id"): "CASCADE",
            ("creator_sample_orders", "address_id"): "SET NULL",
            ("creator_sample_orders", "collaboration_id"): "SET NULL",
            ("creator_sample_order_items", "sample_order_id"): "CASCADE",
            ("creator_sample_order_items", "product_id"): "SET NULL",
        }
        actual = {}
        for table_name, table in Base.metadata.tables.items():
            if table_name not in {name for name, _ in expected}:
                continue
            for column in table.columns:
                if column.foreign_keys:
                    actual[(table_name, column.name)] = next(iter(column.foreign_keys)).ondelete
        self.assertEqual(expected, actual)

    def test_import_batch_uses_lookup_index_not_global_sha_uniqueness(self):
        table = Base.metadata.tables["creator_import_batches"]
        indexes = {index.name: index for index in table.indexes}
        self.assertIn("ix_creator_import_batch_file_lookup", indexes)
        self.assertFalse(indexes["ix_creator_import_batch_file_lookup"].unique)
        self.assertFalse(table.c.file_sha256.unique or False)

    def test_all_required_checks_and_operational_indexes_are_locked(self):
        expected_checks = {
            "bd_members": {"ck_bd_members_name_nonblank"},
            "creators": {"ck_creators_identity_present"},
            "creator_followups": {
                "ck_creator_followups_method",
                "ck_creator_followups_stage_after",
            },
            "creator_portraits": {
                "ck_creator_portraits_followers",
                "ck_creator_portraits_fit",
            },
            "creator_collaborations": {
                "ck_creator_collaborations_paid_nonnegative",
                "ck_creator_collaborations_internal_code_nonblank",
                "ck_creator_collaborations_type",
                "ck_creator_collaborations_status",
                "ck_creator_collaborations_amount_status",
            },
            "creator_sample_orders": {"ck_creator_sample_orders_status"},
            "creator_sample_order_items": {"ck_creator_sample_items_quantity_positive"},
        }
        for table_name, expected in expected_checks.items():
            actual = {
                constraint.name
                for constraint in Base.metadata.tables[table_name].constraints
                if isinstance(constraint, CheckConstraint)
            }
            self.assertGreaterEqual(actual, expected, table_name)

        creator_checks = {
            constraint.name
            for constraint in Base.metadata.tables["creators"].constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertIn("ck_creators_stage", creator_checks)

        expected_indexes = {
            "creators": {
                "uq_creators_platform_uid",
                "uq_creators_douyin_handle",
                "ix_creators_stage_owner_archived",
            },
            "creator_collaborations": {
                "uq_creator_collaboration_external",
                "ix_creator_collaborations_creator_date_status",
            },
            "creator_sample_orders": {"ix_creator_sample_orders_creator_status"},
            "creator_followups": {"ix_creator_followups_creator_time"},
            "creator_import_batches": {
                "ix_creator_import_batch_file_lookup",
                "uq_creator_import_committed_file",
            },
        }
        for table_name, expected in expected_indexes.items():
            actual = {index.name for index in Base.metadata.tables[table_name].indexes}
            self.assertGreaterEqual(actual, expected, table_name)

    def test_identity_helpers_normalize_only_identity_values(self):
        self.assertEqual(normalize_platform_uid("  User-ABC  "), "user-abc")
        self.assertEqual(normalize_douyin_handle("  @Cake达人  "), "Cake达人")
        self.assertEqual(normalize_douyin_handle("  @@@Cake达人  "), "Cake达人")
        self.assertIsNone(normalize_platform_uid("  "))
        self.assertIsNone(normalize_douyin_handle(" @ "))


if __name__ == "__main__":
    unittest.main()
