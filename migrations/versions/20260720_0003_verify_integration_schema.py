"""Repair integration and commerce tables omitted by an earlier adopted revision.

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20
"""
from __future__ import annotations

from collections.abc import Sequence

import commerce_models  # noqa: F401
import creator_models  # noqa: F401
import integration_models  # noqa: F401
import models  # noqa: F401
from alembic import op
from database import Base


revision: str = "20260720_0003"
down_revision: str | Sequence[str] | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only tables absent from databases stamped at the prior revision."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("The integration schema repair migration cannot be downgraded destructively")
