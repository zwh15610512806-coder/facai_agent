"""Readiness report for dependencies that should not drive process restarts."""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from database import SessionLocal, engine


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def build_readiness_report() -> tuple[dict, int]:
    checks: dict[str, dict] = {}
    ready = True

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        ready = False
        checks["database"] = {"status": "error", "detail": str(exc)[:300]}

    try:
        from routers import search_local

        search_local._load_index()
        last_indexed = search_local._state.get("last_indexed")
        total_files = int(search_local._state.get("total_files") or 0)
        last_error = str(search_local._state.get("last_error") or "")
        age_hours = None
        if last_indexed:
            age_hours = max(0.0, (datetime.now() - datetime.fromisoformat(last_indexed)).total_seconds() / 3600)
        max_age = _env_float("FACAI_SEARCH_INDEX_MAX_AGE_HOURS", 72.0)
        search_ok = total_files > 0 and age_hours is not None and age_hours <= max_age and not last_error
        if not search_ok:
            ready = False
        checks["search_index"] = {
            "status": "ok" if search_ok else "stale",
            "last_indexed": last_indexed,
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
            "max_age_hours": max_age,
            "total_files": total_files,
            "is_indexing": bool(search_local._state.get("is_indexing")),
            "last_error": last_error[:300],
        }
    except Exception as exc:
        ready = False
        checks["search_index"] = {"status": "error", "detail": str(exc)[:300]}

    try:
        from services.task_queue import task_worker_status
        from services.vector_sync import vector_sync_status, vector_worker_status

        with SessionLocal() as session:
            queue = vector_sync_status(session)
        vector_worker = vector_worker_status()
        task_worker = task_worker_status()
        heartbeat_limit = _env_float("FACAI_WORKER_HEARTBEAT_MAX_AGE_SECONDS", 30.0)
        vector_worker_ok = bool(vector_worker["alive"]) and (
            vector_worker["heartbeat_age_seconds"] is not None
            and vector_worker["heartbeat_age_seconds"] <= heartbeat_limit
        )
        task_worker_ok = bool(task_worker["alive"]) and (
            task_worker["heartbeat_age_seconds"] is not None
            and task_worker["heartbeat_age_seconds"] <= heartbeat_limit
        )
        worker_ok = vector_worker_ok and task_worker_ok
        if not worker_ok:
            ready = False
        checks["worker"] = {
            "status": "ok" if worker_ok else "error",
            "max_heartbeat_age_seconds": heartbeat_limit,
            "vector_sync": vector_worker,
            "durable_tasks": task_worker,
        }
        checks["vector"] = {
            "status": "degraded" if queue.get("failed") else "ok",
            "pending": queue.get("pending", 0),
            "running": queue.get("running", 0),
            "failed": queue.get("failed", 0),
        }
    except Exception as exc:
        ready = False
        checks["worker"] = {"status": "error", "detail": str(exc)[:300]}
        checks["vector"] = {"status": "unknown"}

    try:
        database_path = engine.url.database
        disk_path = Path(database_path).resolve().parent if database_path and database_path != ":memory:" else Path.cwd()
        usage = shutil.disk_usage(disk_path)
        min_free_bytes = int(_env_float("FACAI_MIN_FREE_DISK_BYTES", 2 * 1024 * 1024 * 1024))
        min_free_percent = _env_float("FACAI_MIN_FREE_DISK_PERCENT", 5.0)
        free_percent = usage.free / usage.total * 100 if usage.total else 0.0
        disk_ok = usage.free >= min_free_bytes and free_percent >= min_free_percent
        if not disk_ok:
            ready = False
        checks["disk"] = {
            "status": "ok" if disk_ok else "low",
            "free_bytes": usage.free,
            "free_percent": round(free_percent, 2),
            "min_free_bytes": min_free_bytes,
            "min_free_percent": min_free_percent,
        }
    except Exception as exc:
        ready = False
        checks["disk"] = {"status": "error", "detail": str(exc)[:300]}

    return {"status": "ready" if ready else "not_ready", "checks": checks}, 200 if ready else 503
