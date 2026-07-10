"""Persistence helpers for long-running import, scan, match and index jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from database import SessionLocal
from models import JobRun


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _session(db: Session | None) -> tuple[Session, bool]:
    return (db, False) if db is not None else (SessionLocal(), True)


def _ensure_job_run_table(session: Session) -> None:
    JobRun.__table__.create(bind=session.get_bind(), checkfirst=True)


def start_job(
    job_type: str,
    *,
    total: int = 0,
    message: str = "",
    details: dict[str, Any] | None = None,
    db: Session | None = None,
) -> int:
    session, owned = _session(db)
    try:
        _ensure_job_run_table(session)
        job = JobRun(
            job_type=job_type,
            status="running",
            progress_current=0,
            progress_total=max(int(total or 0), 0),
            message=message,
            details=dict(details or {}),
            started_at=_now(),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return int(job.id)
    finally:
        if owned:
            session.close()


def update_job(
    job_id: int,
    *,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    db: Session | None = None,
) -> None:
    session, owned = _session(db)
    try:
        _ensure_job_run_table(session)
        job = session.get(JobRun, int(job_id))
        if job is None:
            return
        if current is not None:
            job.progress_current = max(int(current), 0)
        if total is not None:
            job.progress_total = max(int(total), 0)
        if message is not None:
            job.message = str(message)[:4000]
        if details is not None:
            job.details = dict(details)
        session.commit()
    finally:
        if owned:
            session.close()


def finish_job(
    job_id: int,
    *,
    status: str = "succeeded",
    message: str = "",
    details: dict[str, Any] | None = None,
    error_summary: str | None = None,
    db: Session | None = None,
) -> None:
    if status not in {"succeeded", "failed", "interrupted"}:
        raise ValueError(f"Unsupported terminal job status: {status}")
    session, owned = _session(db)
    try:
        _ensure_job_run_table(session)
        job = session.get(JobRun, int(job_id))
        if job is None:
            return
        job.status = status
        if message:
            job.message = str(message)[:4000]
        if details is not None:
            job.details = dict(details)
        job.error_summary = str(error_summary or "")[:4000] or None
        job.finished_at = _now()
        session.commit()
    finally:
        if owned:
            session.close()


def recover_interrupted_jobs(*, db: Session | None = None) -> int:
    session, owned = _session(db)
    try:
        _ensure_job_run_table(session)
        jobs = session.query(JobRun).filter(JobRun.status == "running").all()
        now = _now()
        for job in jobs:
            job.status = "interrupted"
            job.message = "服务重启，运行中的任务已标记为中断"
            job.error_summary = "process restarted before completion"
            job.finished_at = now
        session.commit()
        return len(jobs)
    finally:
        if owned:
            session.close()


def latest_job(job_type: str, *, db: Session | None = None) -> dict[str, Any] | None:
    session, owned = _session(db)
    try:
        _ensure_job_run_table(session)
        job = (
            session.query(JobRun)
            .filter(JobRun.job_type == job_type)
            .order_by(JobRun.id.desc())
            .first()
        )
        if job is None:
            return None
        as_iso = lambda value: value.isoformat() if value is not None else None
        return {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "progress_current": job.progress_current,
            "progress_total": job.progress_total,
            "message": job.message or "",
            "details": job.details or {},
            "error_summary": job.error_summary or "",
            "created_at": as_iso(job.created_at),
            "started_at": as_iso(job.started_at),
            "finished_at": as_iso(job.finished_at),
            "updated_at": as_iso(job.updated_at),
        }
    finally:
        if owned:
            session.close()
