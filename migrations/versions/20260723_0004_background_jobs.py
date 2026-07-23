"""Add browser-owned durable background job state.

Revision ID: 20260723_0004
Revises: 20260720_0003
Create Date: 2026-07-23
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260723_0004"
down_revision: str | Sequence[str] | None = "20260720_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _add_missing(table_name: str, columns: list[sa.Column]) -> None:
    existing = _columns(table_name)
    with op.batch_alter_table(table_name) as batch:
        for column in columns:
            if column.name not in existing:
                batch.add_column(column)


def _create_index(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {str(index["name"]) for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    _add_missing(
        "job_runs",
        [
            sa.Column("public_id", sa.String(length=36), nullable=True),
            sa.Column("queue_group", sa.String(length=30), nullable=False, server_default="maintenance"),
            sa.Column("owner_key", sa.String(length=64), nullable=True),
            sa.Column("origin_path", sa.String(length=500), nullable=True),
            sa.Column("source_ref", sa.String(length=200), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("parent_job_id", sa.Integer(), nullable=True),
            sa.Column("request_payload", sa.JSON(), nullable=True),
            sa.Column("partial_result", sa.JSON(), nullable=True),
            sa.Column("result_payload", sa.JSON(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        ],
    )
    _add_missing(
        "durable_tasks",
        [
            sa.Column("queue_group", sa.String(length=30), nullable=False, server_default="maintenance"),
            sa.Column("job_run_id", sa.Integer(), nullable=True),
            sa.Column("lease_owner", sa.String(length=100), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        ],
    )
    _create_index("ix_job_runs_public_id", "job_runs", ["public_id"], unique=True)
    _create_index("ix_job_runs_owner_key", "job_runs", ["owner_key"])
    _create_index("ix_job_runs_queue_group", "job_runs", ["queue_group"])
    _create_index("ix_job_runs_idempotency_key", "job_runs", ["idempotency_key"])
    _create_index("ix_job_runs_parent_job_id", "job_runs", ["parent_job_id"])
    _create_index("ix_durable_tasks_queue_group", "durable_tasks", ["queue_group"])
    _create_index("ix_durable_tasks_job_run_id", "durable_tasks", ["job_run_id"])
    _create_index("ix_durable_tasks_lease_owner", "durable_tasks", ["lease_owner"])
    _create_index("ix_durable_tasks_heartbeat_at", "durable_tasks", ["heartbeat_at"])


def downgrade() -> None:
    raise RuntimeError("The durable background job migration cannot be downgraded destructively")
