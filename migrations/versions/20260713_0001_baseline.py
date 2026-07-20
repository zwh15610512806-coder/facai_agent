"""Establish a versioned baseline for the existing SQLite application.

Revision ID: 20260713_0001
Revises:
Create Date: 2026-07-13

The project predates Alembic.  This baseline is deliberately adoption-safe:
new databases receive the complete current metadata, while existing databases
receive only columns, indexes, triggers and tables that may be missing.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa

import creator_models  # noqa: F401
import models  # noqa: F401
from alembic import op
from database import core_sqlite_metadata

revision: str = "20260713_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COMPATIBLE_COLUMNS: dict[str, dict[str, str]] = {
    "products": {"pending_fields": "JSON"},
    "viral_scripts": {"is_high_conversion": "INTEGER DEFAULT 0"},
    "generated_scripts": {
        "ai_model": "VARCHAR(100)",
        "is_high_conversion": "INTEGER DEFAULT 0",
        "source_script_id": "INTEGER",
        "source_script_source": "VARCHAR(20)",
        "source_script_title": "VARCHAR(300)",
        "source_script_content": "TEXT",
    },
    "reference_scripts": {
        "is_high_conversion": "INTEGER DEFAULT 0",
        "embedding_id": "VARCHAR(200)",
    },
    "ai_interface_settings": {
        "provider": "VARCHAR(50) NOT NULL DEFAULT 'deepseek'",
        "model": "VARCHAR(120) NOT NULL DEFAULT 'deepseek-chat'",
        "max_tokens": "INTEGER NOT NULL DEFAULT 2400",
        "api_key_secret": "TEXT",
        "base_url_override": "VARCHAR(500)",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    },
    "ai_usage_records": {"actor_name": "VARCHAR(100)"},
    "product_rag_query_logs": {
        "pipeline_version": "VARCHAR(50) NOT NULL DEFAULT 'product-rag-v3-facets'",
        "index_version": "VARCHAR(100) NOT NULL DEFAULT 'legacy'",
        "query_plan": "JSON",
        "candidate_trace": "JSON",
        "selected_evidence": "JSON",
        "rerank_status": "VARCHAR(30) NOT NULL DEFAULT 'skipped'",
        "answer_mode": "VARCHAR(30) NOT NULL DEFAULT 'fallback'",
    },
    "qianchuan_import_batches": {
        "row_count": "INTEGER DEFAULT 0",
        "imported_count": "INTEGER DEFAULT 0",
        "skipped_count": "INTEGER DEFAULT 0",
        "amount_field": "VARCHAR(100)",
        "created_at": "DATETIME",
    },
    "qianchuan_material_performance": {
        "material_evaluation": "VARCHAR(200)",
        "material_duration": "VARCHAR(50)",
        "material_created_time": "VARCHAR(50)",
        "material_source": "VARCHAR(100)",
        "tags": "VARCHAR(500)",
        "amount_field": "VARCHAR(100)",
        "transaction_amount": "FLOAT DEFAULT 0.0",
        "order_count": "INTEGER DEFAULT 0",
        "user_pay_amount": "FLOAT DEFAULT 0.0",
        "roi": "FLOAT DEFAULT 0.0",
        "impressions": "INTEGER DEFAULT 0",
        "ctr": "FLOAT DEFAULT 0.0",
        "spend": "FLOAT DEFAULT 0.0",
        "clicks": "INTEGER DEFAULT 0",
        "cvr": "FLOAT DEFAULT 0.0",
        "play_3s_rate": "FLOAT DEFAULT 0.0",
        "play_10s_rate": "FLOAT DEFAULT 0.0",
        "avg_watch_seconds": "FLOAT DEFAULT 0.0",
        "completion_rate": "FLOAT DEFAULT 0.0",
        "plan_count": "INTEGER DEFAULT 0",
        "product_count": "INTEGER DEFAULT 0",
        "raw_data": "JSON",
        "created_at": "DATETIME",
    },
    "qianchuan_script_bindings": {"created_at": "DATETIME"},
    "creator_sample_orders": {"request_fingerprint": "VARCHAR(64)"},
}


_CREATOR_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS trg_creators_validate_insert BEFORE INSERT ON creators
    WHEN NEW.stage NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')
    BEGIN SELECT RAISE(ABORT, 'invalid creator stage'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creators_validate_update BEFORE UPDATE OF stage ON creators
    WHEN NEW.stage NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')
    BEGIN SELECT RAISE(ABORT, 'invalid creator stage'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creator_followups_validate_insert BEFORE INSERT ON creator_followups
    WHEN NEW.method NOT IN ('douyin','wechat','phone','offline','other') OR
    (NEW.stage_after IS NOT NULL AND NEW.stage_after NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused'))
    BEGIN SELECT RAISE(ABORT, 'invalid creator followup value'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creator_followups_validate_update BEFORE UPDATE OF method, stage_after ON creator_followups
    WHEN NEW.method NOT IN ('douyin','wechat','phone','offline','other') OR
    (NEW.stage_after IS NOT NULL AND NEW.stage_after NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused'))
    BEGIN SELECT RAISE(ABORT, 'invalid creator followup value'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creator_collaborations_validate_insert BEFORE INSERT ON creator_collaborations
    WHEN NEW.collaboration_type NOT IN ('short_video','live','graphic','other') OR
    NEW.status NOT IN ('planned','in_progress','completed','cancelled') OR NEW.amount_status NOT IN ('pending','confirmed')
    BEGIN SELECT RAISE(ABORT, 'invalid creator collaboration value'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creator_collaborations_validate_update BEFORE UPDATE OF collaboration_type, status, amount_status ON creator_collaborations
    WHEN NEW.collaboration_type NOT IN ('short_video','live','graphic','other') OR
    NEW.status NOT IN ('planned','in_progress','completed','cancelled') OR NEW.amount_status NOT IN ('pending','confirmed')
    BEGIN SELECT RAISE(ABORT, 'invalid creator collaboration value'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creator_sample_orders_validate_insert BEFORE INSERT ON creator_sample_orders
    WHEN NEW.status NOT IN ('pending_shipment','shipped','received','cancelled')
    BEGIN SELECT RAISE(ABORT, 'invalid creator sample order status'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_creator_sample_orders_validate_update BEFORE UPDATE OF status ON creator_sample_orders
    WHEN NEW.status NOT IN ('pending_shipment','shipped','received','cancelled')
    BEGIN SELECT RAISE(ABORT, 'invalid creator sample order status'); END""",
)


def _add_missing_legacy_columns(connection: sa.Connection) -> None:
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    for table_name, columns in _COMPATIBLE_COLUMNS.items():
        if table_name not in tables:
            continue
        existing = {item["name"] for item in inspector.get_columns(table_name)}
        for column_name, declaration in columns.items():
            if column_name not in existing:
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {declaration}'
                )


def _repair_creator_indexes_and_triggers(connection: sa.Connection) -> None:
    tables = set(sa.inspect(connection).get_table_names())
    if "creator_import_batches" in tables:
        connection.exec_driver_sql(
            "UPDATE creator_import_batches SET status='duplicate' WHERE status='committed' "
            "AND id NOT IN (SELECT MIN(id) FROM creator_import_batches WHERE status='committed' "
            "GROUP BY kind, file_sha256)"
        )
        connection.exec_driver_sql("DROP INDEX IF EXISTS uq_creator_import_committed_file")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_creator_import_committed_file ON creator_import_batches "
            "(kind, file_sha256) WHERE status = 'committed'"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_creator_import_batch_file_lookup ON "
            "creator_import_batches (kind, file_sha256, status)"
        )
    if {"creators", "creator_followups", "creator_collaborations", "creator_sample_orders"}.issubset(tables):
        for ddl in _CREATOR_TRIGGERS:
            match = re.search(r"CREATE TRIGGER IF NOT EXISTS ([A-Za-z0-9_]+)", ddl)
            if match:
                connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{match.group(1)}"')
            connection.exec_driver_sql(ddl)


def upgrade() -> None:
    connection = op.get_bind()
    core_sqlite_metadata().create_all(bind=connection)
    _add_missing_legacy_columns(connection)
    _repair_creator_indexes_and_triggers(connection)


def downgrade() -> None:
    raise RuntimeError("The adoption baseline cannot be downgraded destructively")
