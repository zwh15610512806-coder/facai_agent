"""Bounded retention for operational records that can contain business context."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import AIUsageRecord, AuditEvent, DurableTask, JobRun, ProductRagQueryLog


@dataclass(frozen=True)
class RetentionResult:
    ai_usage: int
    rag_queries: int
    audit_events: int
    completed_tasks: int


def _days(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    return max(1, min(value, 3650))


def apply_data_retention(db: Session, *, now: datetime | None = None) -> RetentionResult:
    current = now or datetime.now()
    ai_cutoff = current - timedelta(days=_days("FACAI_AI_USAGE_RETENTION_DAYS", 90))
    rag_cutoff = current - timedelta(days=_days("FACAI_RAG_LOG_RETENTION_DAYS", 30))
    audit_cutoff = current - timedelta(days=_days("FACAI_AUDIT_RETENTION_DAYS", 180))
    task_cutoff = current - timedelta(days=_days("FACAI_TASK_RETENTION_DAYS", 30))

    result = RetentionResult(
        ai_usage=db.query(AIUsageRecord)
        .filter(AIUsageRecord.created_at < ai_cutoff)
        .delete(synchronize_session=False),
        rag_queries=db.query(ProductRagQueryLog)
        .filter(ProductRagQueryLog.created_at < rag_cutoff)
        .delete(synchronize_session=False),
        audit_events=db.query(AuditEvent)
        .filter(AuditEvent.created_at < audit_cutoff)
        .delete(synchronize_session=False),
        completed_tasks=(
            db.query(DurableTask)
            .filter(
                DurableTask.status.in_(("succeeded", "failed", "cancelled")),
                DurableTask.completed_at < task_cutoff,
            )
            .delete(synchronize_session=False)
            + db.query(JobRun)
            .filter(
                JobRun.status.in_(("succeeded", "failed", "cancelled", "interrupted")),
                JobRun.finished_at < task_cutoff,
            )
            .delete(synchronize_session=False)
        ),
    )
    db.commit()
    return result
