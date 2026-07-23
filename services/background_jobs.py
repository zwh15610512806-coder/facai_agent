"""Browser-owned durable jobs shared by AI and maintenance workflows."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import DurableTask, JobRun
from services.task_queue import register_task_handler


ACTIVE_STATUSES = {"pending", "running", "cancelling"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
ALL_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES
BackgroundHandler = Callable[[dict[str, Any], int], dict[str, Any] | None]


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def browser_owner_key(actor_digest: str, client_id: str) -> str:
    normalized = str(uuid.UUID(str(client_id)))
    return hashlib.sha256(f"facai-job-owner-v1:{actor_digest}:{normalized}".encode("utf-8")).hexdigest()


def _bounded_json(value: Any, *, max_bytes: int = 256_000) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"任务数据超过 {max_bytes} 字节限制")
    return json.loads(encoded.decode("utf-8"))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def job_to_dict(job: JobRun, *, include_payload: bool = True) -> dict[str, Any]:
    total = int(job.progress_total or 0)
    current = int(job.progress_current or 0)
    progress = round(min(100.0, max(0.0, current / total * 100)), 1) if total else None
    result = {
        "public_id": job.public_id,
        "job_type": job.job_type,
        "queue_group": job.queue_group,
        "status": job.status,
        "origin_path": job.origin_path or "",
        "source_ref": job.source_ref or "",
        "progress_current": current,
        "progress_total": total,
        "progress": progress,
        "message": job.message or "",
        "error_summary": job.error_summary or "",
        "attempt_count": int(job.attempt_count or 0),
        "max_attempts": int(job.max_attempts or 1),
        "version": int(job.version or 1),
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "updated_at": _iso(job.updated_at),
    }
    if include_payload:
        result.update({
            "request": job.request_payload or {},
            "partial_result": job.partial_result or {},
            "result": job.result_payload or {},
            "details": job.details or {},
        })
    return result


def create_background_job(
    db: Session,
    *,
    owner_key: str,
    job_type: str,
    request_payload: dict[str, Any],
    origin_path: str,
    source_ref: str = "",
    queue_group: str = "maintenance",
    idempotency_key: str = "",
    max_attempts: int = 1,
    message: str = "任务等待执行",
) -> tuple[JobRun, bool]:
    group = "ai" if queue_group == "ai" else "maintenance"
    bounded_request = _bounded_json(request_payload)
    if idempotency_key:
        existing = (
            db.query(JobRun)
            .filter(
                JobRun.owner_key == owner_key,
                JobRun.job_type == job_type,
                JobRun.idempotency_key == idempotency_key[:128],
                JobRun.status.in_(list(ACTIVE_STATUSES | {"succeeded"})),
            )
            .order_by(JobRun.id.desc())
            .first()
        )
        if existing is not None:
            return existing, False
    now = now_utc()
    job = JobRun(
        public_id=str(uuid.uuid4()),
        owner_key=owner_key,
        job_type=job_type[:60],
        queue_group=group,
        origin_path=str(origin_path or "")[:500],
        source_ref=str(source_ref or "")[:200],
        idempotency_key=str(idempotency_key or "")[:128] or None,
        status="pending",
        message=str(message or "任务等待执行")[:4000],
        request_payload=bounded_request,
        partial_result={},
        result_payload={},
        details={},
        version=1,
        attempt_count=0,
        max_attempts=max(1, int(max_attempts)),
        created_at=now,
    )
    db.add(job)
    db.flush()
    task = DurableTask(
        task_type=job_type,
        queue_group=group,
        job_run_id=job.id,
        payload={"request": bounded_request},
        status="pending",
        attempt_count=0,
        max_attempts=job.max_attempts,
        next_attempt_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(job)
    return job, True


def register_background_handler(
    job_type: str,
    handler: BackgroundHandler,
    *,
    queue_group: str = "maintenance",
) -> None:
    def wrapped(payload: dict[str, Any]):
        job_id = int(payload.get("_background_job_id") or 0)
        if not job_id:
            raise RuntimeError("Background task is missing job id")
        if is_cancel_requested(job_id):
            mark_cancelling(job_id)
            return None
        return handler(dict(payload.get("request") or {}), job_id)

    register_task_handler(job_type, wrapped, queue_group=queue_group)


def get_owned_job(db: Session, owner_key: str, public_id: str) -> JobRun | None:
    return (
        db.query(JobRun)
        .filter(JobRun.owner_key == owner_key, JobRun.public_id == public_id)
        .first()
    )


def list_owned_jobs(
    db: Session,
    owner_key: str,
    *,
    statuses: set[str] | None = None,
    job_type: str | None = None,
    limit: int = 50,
) -> list[JobRun]:
    query = db.query(JobRun).filter(JobRun.owner_key == owner_key)
    if statuses:
        query = query.filter(JobRun.status.in_(sorted(statuses)))
    if job_type:
        query = query.filter(JobRun.job_type == job_type)
    return query.order_by(JobRun.id.desc()).limit(max(1, min(int(limit), 100))).all()


def sync_integration_export_jobs(db: Session, *, owner_key: str, actor_digest: str) -> int:
    """Mirror the existing integration export queue without replacing its worker."""
    try:
        from integration_models import IntegrationExportJob
    except Exception:
        return 0
    try:
        exports = (
            db.query(IntegrationExportJob)
            .filter(IntegrationExportJob.requester_session_digest == actor_digest)
            .order_by(IntegrationExportJob.id.desc())
            .limit(50)
            .all()
        )
    except Exception:
        db.rollback()
        return 0
    if not exports:
        return 0
    refs = [f"integration-export:{item.public_id}" for item in exports]
    existing = {
        item.source_ref: item
        for item in db.query(JobRun).filter(
            JobRun.owner_key == owner_key,
            JobRun.job_type == "integration.adapter.export",
            JobRun.source_ref.in_(refs),
        ).all()
    }
    changed = 0
    for export in exports:
        ref = f"integration-export:{export.public_id}"
        raw_status = getattr(export.status, "value", str(export.status))
        mapped_status = {
            "queued": "pending",
            "running": "running",
            "ready": "succeeded",
            "failed": "failed",
            "expired": "cancelled",
        }.get(raw_status, "pending")
        resource_type = getattr(export.resource_type, "value", str(export.resource_type))
        result = {
            "row_count": int(export.row_count or 0),
            "format": export.format,
        }
        if mapped_status == "succeeded":
            result["download_url"] = f"/api/operations/exports/{export.public_id}/download"
        job = existing.get(ref)
        if job is None:
            job = JobRun(
                public_id=str(uuid.uuid4()),
                owner_key=owner_key,
                job_type="integration.adapter.export",
                queue_group="maintenance",
                origin_path="/app/operations",
                source_ref=ref,
                request_payload={"resource_type": resource_type, "format": export.format},
                max_attempts=1,
                created_at=export.created_at,
            )
            db.add(job)
        elif (
            job.status == mapped_status
            and job.message == ("集成数据导出完成" if mapped_status == "succeeded" else (export.error_summary or "集成数据导出中"))
            and job.error_summary == (export.error_summary if mapped_status == "failed" else None)
            and int(job.progress_current or 0) == int(export.row_count or 0)
            and (job.result_payload or {}) == result
        ):
            continue
        job.status = mapped_status
        job.message = "集成数据导出完成" if mapped_status == "succeeded" else (export.error_summary or "集成数据导出中")
        job.error_summary = export.error_summary if mapped_status == "failed" else None
        job.progress_current = int(export.row_count or 0)
        job.result_payload = result
        job.started_at = export.started_at
        job.finished_at = export.completed_at
        job.version = int(job.version or 0) + 1
        changed += 1
    db.commit()
    return changed


def sync_integration_sync_jobs(db: Session, *, owner_key: str) -> int:
    """Mirror browser-owned manual integration sync parents from the existing queue."""
    try:
        from integration_models import IntegrationJob
    except Exception:
        return 0
    parents = (
        db.query(JobRun)
        .filter(
            JobRun.owner_key == owner_key,
            JobRun.job_type == "integration.adapter.sync",
            JobRun.source_ref.like("integration-sync:%"),
            JobRun.status.in_(list(ACTIVE_STATUSES)),
        )
        .order_by(JobRun.id.desc())
        .limit(50)
        .all()
    )
    if not parents:
        return 0
    try:
        candidates = (
            db.query(IntegrationJob)
            .filter(IntegrationJob.job_type == "sync_resource")
            .order_by(IntegrationJob.id.desc())
            .limit(500)
            .all()
        )
    except Exception:
        db.rollback()
        return 0
    by_request: dict[str, list[Any]] = {}
    for item in candidates:
        payload = item.payload if isinstance(item.payload, dict) else {}
        request_id = str(payload.get("manual_request_id") or "")
        if request_id:
            by_request.setdefault(request_id, []).append(item)
    changed = 0
    for parent in parents:
        request_id = parent.source_ref.split(":", 1)[-1]
        children = by_request.get(request_id, [])
        if not children:
            continue
        raw_statuses = [getattr(item.status, "value", str(item.status)) for item in children]
        active = {"leased", "running"}
        waiting = {"queued", "retry_wait"}
        if any(status in active for status in raw_statuses):
            mapped_status = "running"
            message = "集成同步正在运行"
        elif any(status in waiting for status in raw_statuses):
            mapped_status = "pending"
            message = "集成同步等待执行"
        elif any(status == "failed" for status in raw_statuses):
            mapped_status = "failed"
            message = "集成同步失败"
        elif all(status == "cancelled" for status in raw_statuses):
            mapped_status = "cancelled"
            message = "集成同步已取消"
        else:
            mapped_status = "succeeded"
            message = "集成同步完成"
        completed = sum(status in {"succeeded", "failed", "cancelled"} for status in raw_statuses)
        failures = [str(item.last_error_summary or "") for item in children if getattr(item.status, "value", str(item.status)) == "failed"]
        error_summary = next((value for value in failures if value), "")
        result = {
            "request_id": request_id,
            "sync_units": len(children),
            "succeeded": raw_statuses.count("succeeded"),
            "failed": raw_statuses.count("failed"),
            "cancelled": raw_statuses.count("cancelled"),
        }
        if (
            parent.status == mapped_status
            and parent.message == message
            and int(parent.progress_current or 0) == completed
            and int(parent.progress_total or 0) == len(children)
            and (parent.error_summary or "") == error_summary
            and (parent.result_payload or {}) == result
        ):
            continue
        now = now_utc()
        parent.status = mapped_status
        parent.message = message
        parent.progress_current = completed
        parent.progress_total = len(children)
        parent.error_summary = error_summary or None
        parent.attempt_count = max(int(item.attempts or 0) for item in children)
        parent.started_at = parent.started_at or (now if mapped_status == "running" else None)
        if mapped_status in TERMINAL_STATUSES:
            parent.finished_at = now
            parent.result_payload = result
        parent.version = int(parent.version or 0) + 1
        changed += 1
    if changed:
        db.commit()
    return changed


def update_background_job(
    job_id: int,
    *,
    partial_result: dict[str, Any] | None = None,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, int(job_id))
        if job is None:
            return
        if partial_result is not None:
            job.partial_result = _bounded_json(partial_result)
        if current is not None:
            job.progress_current = max(0, int(current))
        if total is not None:
            job.progress_total = max(0, int(total))
        if message is not None:
            job.message = str(message)[:4000]
        if details is not None:
            job.details = _bounded_json(details)
        job.version = int(job.version or 0) + 1
        job.heartbeat_at = now_utc()
        db.commit()


def is_cancel_requested(job_id: int) -> bool:
    with SessionLocal() as db:
        job = db.get(JobRun, int(job_id))
        return bool(job and job.status in {"cancelling", "cancelled"})


def mark_cancelling(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, int(job_id))
        if job is not None and job.status not in TERMINAL_STATUSES:
            job.status = "cancelling"
            job.message = "正在取消任务"
            job.cancel_requested_at = job.cancel_requested_at or now_utc()
            job.version = int(job.version or 0) + 1
            db.commit()


def cancel_owned_job(db: Session, job: JobRun) -> JobRun:
    now = now_utc()
    if job.status == "pending":
        job.status = "cancelled"
        job.message = "任务已取消"
        job.cancel_requested_at = now
        job.finished_at = now
        (
            db.query(DurableTask)
            .filter(DurableTask.job_run_id == job.id, DurableTask.status == "pending")
            .update({DurableTask.status: "cancelled", DurableTask.completed_at: now}, synchronize_session=False)
        )
    elif job.status == "running":
        job.status = "cancelling"
        job.message = "正在取消任务"
        job.cancel_requested_at = now
    job.version = int(job.version or 0) + 1
    db.commit()
    db.refresh(job)
    return job


def retry_owned_job(db: Session, job: JobRun) -> JobRun:
    if job.status not in {"failed", "cancelled"}:
        raise ValueError("只有失败或已取消的任务可以重试")
    now = now_utc()
    job.status = "pending"
    job.message = "任务等待重试"
    job.error_summary = None
    job.cancel_requested_at = None
    job.finished_at = None
    job.partial_result = {}
    job.result_payload = {}
    job.max_attempts = max(int(job.max_attempts or 1), int(job.attempt_count or 0) + 1)
    job.version = int(job.version or 0) + 1
    db.add(DurableTask(
        task_type=job.job_type,
        queue_group=job.queue_group,
        job_run_id=job.id,
        payload={"request": job.request_payload or {}},
        status="pending",
        attempt_count=0,
        max_attempts=1,
        next_attempt_at=now,
    ))
    db.commit()
    db.refresh(job)
    return job


def queue_metrics() -> dict[str, Any]:
    counts = {"ai": {"pending": 0, "running": 0}, "maintenance": {"pending": 0, "running": 0}}
    try:
        with SessionLocal() as db:
            rows = (
                db.query(DurableTask.queue_group, DurableTask.status, func.count(DurableTask.id))
                .filter(DurableTask.status.in_(["pending", "running"]))
                .group_by(DurableTask.queue_group, DurableTask.status)
                .all()
            )
            for group, status, count in rows:
                normalized = "ai" if group == "ai" else "maintenance"
                counts[normalized][status] = int(count)
            oldest = (
                db.query(DurableTask)
                .filter(DurableTask.status == "pending")
                .order_by(DurableTask.created_at.asc())
                .first()
            )
            age = None
            if oldest and oldest.created_at:
                age = max(0.0, (now_utc() - oldest.created_at).total_seconds())
            return {"queues": counts, "oldest_pending_age_seconds": age}
    except Exception:
        # Startup/readiness tests may probe before the migration has created the
        # optional queue tables. Worker health remains the authoritative gate.
        return {"queues": counts, "oldest_pending_age_seconds": None}
