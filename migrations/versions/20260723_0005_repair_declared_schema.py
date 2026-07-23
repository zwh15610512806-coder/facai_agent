"""Repair tables missing from databases stamped at the current revision.

Revision ID: 20260723_0005
Revises: 20260723_0004
Create Date: 2026-07-23
"""
from __future__ import annotations

from collections.abc import Sequence

import commerce_models  # noqa: F401
import creator_models  # noqa: F401
import integration_models  # noqa: F401
import models  # noqa: F401
from alembic import op
from database import Base


revision: str = "20260723_0005"
down_revision: str | Sequence[str] | None = "20260723_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only declared tables missing from an earlier stamped database."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("The schema repair migration cannot be downgraded destructively")
