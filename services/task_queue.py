"""SQLite-backed task queue for recoverable single-instance background work."""
from __future__ import annotations

import logging
import os
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from database import SessionLocal
from models import DurableTask, JobRun


logger = logging.getLogger("facai.task_queue")
TaskHandler = Callable[[dict], Any]


class DurableTaskQueue:
    def __init__(self, session_factory, *, lease_seconds: int = 15 * 60) -> None:
        self._session_factory = session_factory
        self._lease_seconds = max(30, lease_seconds)
        self._handlers: dict[str, tuple[TaskHandler, str]] = {}
        self._handlers_lock = threading.Lock()
        self.instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:12]}"

    def _ensure_table(self, session) -> None:
        DurableTask.__table__.create(bind=session.get_bind(), checkfirst=True)

    def register(self, task_type: str, handler: TaskHandler, *, queue_group: str = "maintenance") -> None:
        group = "ai" if queue_group == "ai" else "maintenance"
        with self._handlers_lock:
            self._handlers[task_type] = (handler, group)

    def enqueue(
        self,
        task_type: str,
        payload: dict,
        *,
        max_attempts: int = 3,
        queue_group: str | None = None,
        job_run_id: int | None = None,
    ) -> int:
        with self._handlers_lock:
            registered = self._handlers.get(task_type)
        group = queue_group or (registered[1] if registered else "maintenance")
        with self._session_factory() as session:
            self._ensure_table(session)
            task = DurableTask(
                task_type=task_type,
                queue_group="ai" if group == "ai" else "maintenance",
                job_run_id=job_run_id,
                payload=dict(payload or {}),
                status="pending",
                attempt_count=0,
                max_attempts=max(1, max_attempts),
                next_attempt_at=datetime.now(),
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return int(task.id)

    def recover_expired(self, *, recover_all: bool = False) -> int:
        now = datetime.now()
        with self._session_factory() as session:
            self._ensure_table(session)
            query = session.query(DurableTask).filter(DurableTask.status == "running")
            if not recover_all:
                query = query.filter(
                    DurableTask.lease_until.isnot(None),
                    DurableTask.lease_until <= now,
                )
            tasks = query.all()
            for task in tasks:
                task.status = "pending"
                task.lease_until = None
                task.lease_owner = None
                task.heartbeat_at = None
                task.next_attempt_at = now
                if task.job_run_id:
                    job = session.get(JobRun, task.job_run_id)
                    if job is not None and job.status in {"running", "cancelling"}:
                        job.status = "pending"
                        job.message = "服务已恢复，任务等待自动重试"
                        job.heartbeat_at = None
                        job.version = int(job.version or 0) + 1
            session.commit()
            return len(tasks)

    def process_once(self, *, queue_group: str | None = None) -> bool:
        with self._handlers_lock:
            handlers = dict(self._handlers)
        eligible_types = [
            task_type
            for task_type, (_handler, group) in handlers.items()
            if queue_group is None or group == queue_group
        ]
        if not eligible_types:
            return False
        now = datetime.now()
        with self._session_factory() as session:
            self._ensure_table(session)
            task = (
                session.query(DurableTask)
                .filter(
                    DurableTask.status == "pending",
                    DurableTask.next_attempt_at <= now,
                    DurableTask.task_type.in_(eligible_types),
                )
                .order_by(DurableTask.id.asc())
                .first()
            )
            if task is None:
                return False
            job = session.get(JobRun, task.job_run_id) if task.job_run_id else None
            if job is not None and job.status in {"cancelled", "cancelling"}:
                task.status = "cancelled"
                task.completed_at = now
                job.status = "cancelled"
                job.message = "任务已取消"
                job.finished_at = now
                job.version = int(job.version or 0) + 1
                session.commit()
                return True
            task_id = int(task.id)
            task_type = str(task.task_type)
            payload = dict(task.payload or {})
            next_attempt_count = int(task.attempt_count or 0) + 1
            claimed = (
                session.query(DurableTask)
                .filter(DurableTask.id == task_id, DurableTask.status == "pending")
                .update(
                    {
                        DurableTask.status: "running",
                        DurableTask.attempt_count: next_attempt_count,
                        DurableTask.lease_until: now + timedelta(seconds=self._lease_seconds),
                        DurableTask.lease_owner: self.instance_id,
                        DurableTask.heartbeat_at: now,
                    },
                    synchronize_session=False,
                )
            )
            if claimed != 1:
                session.rollback()
                return False
            if task.job_run_id:
                payload.setdefault("_background_job_id", int(task.job_run_id))
            if job is not None:
                job.status = "running"
                job.attempt_count = next_attempt_count
                job.heartbeat_at = now
                job.started_at = job.started_at or now
                job.message = job.message or "任务执行中"
                job.version = int(job.version or 0) + 1
            session.commit()

        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat,
            args=(task_id, heartbeat_stop),
            name=f"task-heartbeat-{task_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            result = handlers[task_type][0](payload)
        except Exception as exc:
            logger.exception("Durable task %s (%s) failed", task_id, task_type)
            with self._session_factory() as session:
                task = session.get(DurableTask, task_id)
                if task is not None:
                    task.last_error = str(exc)[:4000]
                    task.lease_until = None
                    task.lease_owner = None
                    task.heartbeat_at = None
                    job = session.get(JobRun, task.job_run_id) if task.job_run_id else None
                    if task.attempt_count >= task.max_attempts:
                        task.status = "failed"
                        task.completed_at = datetime.now()
                        if job is not None:
                            job.status = "failed"
                            job.error_summary = str(exc)[:4000]
                            job.message = "任务执行失败"
                            job.finished_at = datetime.now()
                    else:
                        task.status = "pending"
                        delay = min(300, 2 ** max(1, task.attempt_count))
                        task.next_attempt_at = datetime.now() + timedelta(seconds=delay)
                        if job is not None:
                            job.status = "pending"
                            job.error_summary = str(exc)[:4000]
                            job.message = f"执行中断，将自动重试（{task.attempt_count}/{task.max_attempts}）"
                    if job is not None:
                        job.heartbeat_at = None
                        job.version = int(job.version or 0) + 1
                    session.commit()
        else:
            with self._session_factory() as session:
                task = session.get(DurableTask, task_id)
                if task is not None:
                    task.status = "succeeded"
                    task.lease_until = None
                    task.lease_owner = None
                    task.heartbeat_at = None
                    task.last_error = None
                    task.completed_at = datetime.now()
                    job = session.get(JobRun, task.job_run_id) if task.job_run_id else None
                    if job is not None:
                        if job.status == "cancelling" and result is None:
                            job.status = "cancelled"
                            job.message = "任务已取消"
                        else:
                            job.status = "succeeded"
                            job.message = "任务已完成"
                            if isinstance(result, dict):
                                job.result_payload = result
                        job.error_summary = None
                        job.heartbeat_at = None
                        job.finished_at = datetime.now()
                        job.version = int(job.version or 0) + 1
                    session.commit()
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=1)
        return True

    def _heartbeat(self, task_id: int, stop: threading.Event) -> None:
        interval = max(5.0, min(30.0, self._lease_seconds / 3))
        while not stop.wait(interval):
            now = datetime.now()
            try:
                with self._session_factory() as session:
                    task = session.get(DurableTask, task_id)
                    if task is None or task.status != "running" or task.lease_owner != self.instance_id:
                        return
                    task.heartbeat_at = now
                    task.lease_until = now + timedelta(seconds=self._lease_seconds)
                    if task.job_run_id:
                        job = session.get(JobRun, task.job_run_id)
                        if job is not None:
                            job.heartbeat_at = now
                    session.commit()
            except Exception:
                logger.exception("Durable task %s heartbeat failed", task_id)


TASK_QUEUE = DurableTaskQueue(SessionLocal)
_worker_stop = threading.Event()
_worker_threads: list[threading.Thread] = []
_worker_lock = threading.Lock()
_worker_last_heartbeat: datetime | None = None


def register_task_handler(task_type: str, handler: TaskHandler, *, queue_group: str = "maintenance") -> None:
    TASK_QUEUE.register(task_type, handler, queue_group=queue_group)


def enqueue_task(
    task_type: str,
    payload: dict,
    *,
    max_attempts: int = 3,
    queue_group: str | None = None,
    job_run_id: int | None = None,
) -> int:
    return TASK_QUEUE.enqueue(
        task_type,
        payload,
        max_attempts=max_attempts,
        queue_group=queue_group,
        job_run_id=job_run_id,
    )


def _worker_loop(queue_group: str) -> None:
    global _worker_last_heartbeat
    while not _worker_stop.is_set():
        _worker_last_heartbeat = datetime.now()
        processed = TASK_QUEUE.process_once(queue_group=queue_group)
        _worker_stop.wait(0.1 if processed else 2.0)


def start_task_worker() -> None:
    global _worker_threads, _worker_last_heartbeat
    with _worker_lock:
        if any(thread.is_alive() for thread in _worker_threads):
            return
        TASK_QUEUE.recover_expired(recover_all=True)
        _worker_stop.clear()
        _worker_last_heartbeat = datetime.now()
        groups = ["ai", "ai", "maintenance"]
        _worker_threads = [
            threading.Thread(
                target=_worker_loop,
                args=(group,),
                name=f"durable-task-worker-{group}-{index + 1}",
                daemon=True,
            )
            for index, group in enumerate(groups)
        ]
        for thread in _worker_threads:
            thread.start()


def stop_task_worker() -> None:
    _worker_stop.set()
    for thread in list(_worker_threads):
        if thread.is_alive():
            thread.join(timeout=3)


def task_worker_status() -> dict:
    threads = list(_worker_threads)
    age = None
    if _worker_last_heartbeat is not None:
        age = max(0.0, (datetime.now() - _worker_last_heartbeat).total_seconds())
    return {
        "alive": bool(threads) and all(thread.is_alive() for thread in threads),
        "workers": {
            "ai": sum(1 for thread in threads if thread.is_alive() and "-ai-" in thread.name),
            "maintenance": sum(1 for thread in threads if thread.is_alive() and "-maintenance-" in thread.name),
        },
        "last_heartbeat": _worker_last_heartbeat.isoformat() if _worker_last_heartbeat else None,
        "heartbeat_age_seconds": age,
    }
