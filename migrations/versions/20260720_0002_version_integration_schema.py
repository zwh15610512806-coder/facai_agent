"""Move the remaining SQLite startup schema work under Alembic.

Revision ID: 20260720_0002
Revises: 20260713_0001
Create Date: 2026-07-20

The first SQLite baseline intentionally covered the core application only.
Older startup code then repaired the integration parent key and called
``Base.metadata.create_all`` for the remaining integration/commerce tables.
This adoption migration performs that work once, under a versioned revision.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import commerce_models  # noqa: F401
import creator_models  # noqa: F401
import integration_models  # noqa: F401
import models  # noqa: F401
from alembic import op
from database import Base

revision: str = "20260720_0002"
down_revision: str | Sequence[str] | None = "20260713_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARENT_KEY_NAME = "uq_integration_connections_id_provider"
_PARENT_KEY_COLUMNS = ["id", "provider"]


def _valid_parent_key(inspector: sa.Inspector) -> bool:
    for constraint in inspector.get_unique_constraints("integration_connections"):
        if list(constraint.get("column_names") or []) == _PARENT_KEY_COLUMNS:
            return True
    for index in inspector.get_indexes("integration_connections"):
        where = (index.get("dialect_options") or {}).get("sqlite_where")
        if (
            bool(index.get("unique"))
            and where is None
            and list(index.get("column_names") or []) == _PARENT_KEY_COLUMNS
        ):
            return True
    return False


def _ensure_parent_key(connection: sa.Connection) -> None:
    inspector = sa.inspect(connection)
    if "integration_connections" not in set(inspector.get_table_names()):
        return
    if _valid_parent_key(inspector):
        return
    existing_names = {
        item.get("name") for item in inspector.get_indexes("integration_connections")
    }
    if _PARENT_KEY_NAME in existing_names:
        raise RuntimeError(
            "SQLite index uq_integration_connections_id_provider exists with "
            "an incompatible definition; repair it before starting the application."
        )
    connection.exec_driver_sql(
        'CREATE UNIQUE INDEX "uq_integration_connections_id_provider" '
        'ON "integration_connections" ("id", "provider")'
    )


def upgrade() -> None:
    connection = op.get_bind()
    _ensure_parent_key(connection)
    Base.metadata.create_all(bind=connection)


def downgrade() -> None:
    raise RuntimeError("The adoption migration cannot be downgraded destructively")
