"""Small SQLite writer-lease helper for cross-lane Canvas transactions."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def begin_immediate_if_sqlite(db: Session) -> None:
    """Acquire SQLite's writer lease before a read-then-write transaction.

    Generation promotion and local composition run on separate worker lanes.
    Under WAL, a deferred read transaction can otherwise fail immediately when
    it upgrades after the other lane commits. PostgreSQL keeps its normal
    transaction behavior.
    """

    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


__all__ = ["begin_immediate_if_sqlite"]
