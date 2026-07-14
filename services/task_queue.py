"""SQLite-backed task queue for recoverable single-instance background work."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from database import SessionLocal
from models import DurableTask

logger = logging.getLogger("facai.task_queue")
TaskHandler = Callable[[dict], None]


class DurableTaskQueue:
    def __init__(self, session_factory, *, lease_seconds: int = 15 * 60) -> None:
        self._session_factory = session_factory
        self._lease_seconds = max(30, lease_seconds)
        self._handlers: dict[str, TaskHandler] = {}
        self._handlers_lock = threading.Lock()

    def _ensure_table(self, session) -> None:
        DurableTask.__table__.create(bind=session.get_bind(), checkfirst=True)

    def register(self, task_type: str, handler: TaskHandler) -> None:
        with self._handlers_lock:
            self._handlers[task_type] = handler

    def enqueue(self, task_type: str, payload: dict, *, max_attempts: int = 3) -> int:
        with self._session_factory() as session:
            self._ensure_table(session)
            task = DurableTask(
                task_type=task_type,
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

    def recover_expired(self) -> int:
        now = datetime.now()
        with self._session_factory() as session:
            self._ensure_table(session)
            recovered = (
                session.query(DurableTask)
                .filter(
                    DurableTask.status == "running",
                    DurableTask.lease_until.isnot(None),
                    DurableTask.lease_until <= now,
                )
                .update(
                    {
                        DurableTask.status: "pending",
                        DurableTask.lease_until: None,
                        DurableTask.next_attempt_at: now,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return int(recovered or 0)

    def process_once(self) -> bool:
        with self._handlers_lock:
            handlers = dict(self._handlers)
        if not handlers:
            return False
        now = datetime.now()
        with self._session_factory() as session:
            self._ensure_table(session)
            task = (
                session.query(DurableTask)
                .filter(
                    DurableTask.status == "pending",
                    DurableTask.next_attempt_at <= now,
                    DurableTask.task_type.in_(handlers),
                )
                .order_by(DurableTask.id.asc())
                .first()
            )
            if task is None:
                return False
            task.status = "running"
            task.attempt_count = int(task.attempt_count or 0) + 1
            task.lease_until = now + timedelta(seconds=self._lease_seconds)
            task_id = int(task.id)
            task_type = str(task.task_type)
            payload = dict(task.payload or {})
            session.commit()

        try:
            handlers[task_type](payload)
        except Exception as exc:
            logger.exception("Durable task %s (%s) failed", task_id, task_type)
            with self._session_factory() as session:
                task = session.get(DurableTask, task_id)
                if task is not None:
                    task.last_error = str(exc)[:4000]
                    task.lease_until = None
                    if task.attempt_count >= task.max_attempts:
                        task.status = "failed"
                        task.completed_at = datetime.now()
                    else:
                        task.status = "pending"
                        delay = min(300, 2 ** max(1, task.attempt_count))
                        task.next_attempt_at = datetime.now() + timedelta(seconds=delay)
                    session.commit()
        else:
            with self._session_factory() as session:
                task = session.get(DurableTask, task_id)
                if task is not None:
                    task.status = "succeeded"
                    task.lease_until = None
                    task.last_error = None
                    task.completed_at = datetime.now()
                    session.commit()
        return True


TASK_QUEUE = DurableTaskQueue(SessionLocal)
_worker_stop = threading.Event()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_worker_last_heartbeat: datetime | None = None


def register_task_handler(task_type: str, handler: TaskHandler) -> None:
    TASK_QUEUE.register(task_type, handler)


def enqueue_task(task_type: str, payload: dict, *, max_attempts: int = 3) -> int:
    return TASK_QUEUE.enqueue(task_type, payload, max_attempts=max_attempts)


def _worker_loop() -> None:
    global _worker_last_heartbeat
    while not _worker_stop.is_set():
        _worker_last_heartbeat = datetime.now()
        processed = TASK_QUEUE.process_once()
        _worker_stop.wait(0.1 if processed else 2.0)


def start_task_worker() -> None:
    global _worker_thread, _worker_last_heartbeat
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        TASK_QUEUE.recover_expired()
        _worker_stop.clear()
        _worker_last_heartbeat = datetime.now()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="durable-task-worker",
            daemon=True,
        )
        _worker_thread.start()


def stop_task_worker() -> None:
    _worker_stop.set()
    thread = _worker_thread
    if thread and thread.is_alive():
        thread.join(timeout=3)


def task_worker_status() -> dict:
    thread = _worker_thread
    age = None
    if _worker_last_heartbeat is not None:
        age = max(0.0, (datetime.now() - _worker_last_heartbeat).total_seconds())
    return {
        "alive": bool(thread and thread.is_alive()),
        "last_heartbeat": _worker_last_heartbeat.isoformat() if _worker_last_heartbeat else None,
        "heartbeat_age_seconds": age,
    }
