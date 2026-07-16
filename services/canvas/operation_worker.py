"""Dedicated leased worker loops for Product Canvas local operation lanes."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from typing import Any

from config import CANVAS_LOCAL_OPERATION_WORKERS, CANVAS_REMBG_WORKERS
from services.canvas import operations


logger = logging.getLogger(__name__)

OperationHandler = Callable[[operations.ClaimedOperation], None]


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CanvasOperationWorker:
    """Claim one lane in short transactions and execute handlers off-thread."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Any],
        lane: operations.OperationLane,
        worker_id: str,
        handlers: Mapping[str, OperationHandler],
        max_workers: int | None = None,
        poll_interval_seconds: float = 0.25,
        heartbeat_interval_seconds: float = 30.0,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if lane not in operations.OPERATION_LANE_TYPES:
            raise ValueError("lane must be rembg or local")
        if not callable(db_factory):
            raise TypeError("db_factory must be callable")
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        allowed_types = set(operations.OPERATION_LANE_TYPES[lane])
        normalized_handlers = dict(handlers)
        if not normalized_handlers:
            raise ValueError("at least one operation handler is required")
        if not set(normalized_handlers).issubset(allowed_types):
            raise ValueError("operation handlers must belong to the worker lane")
        if any(not callable(handler) for handler in normalized_handlers.values()):
            raise TypeError("every operation handler must be callable")
        configured_workers = (
            CANVAS_REMBG_WORKERS if lane == "rembg" else CANVAS_LOCAL_OPERATION_WORKERS
        )
        worker_count = configured_workers if max_workers is None else max_workers
        if type(worker_count) is not int or worker_count <= 0:
            raise ValueError("max_workers must be a positive integer")
        if lane == "rembg" and worker_count != 1:
            raise ValueError("rembg lane must use exactly one worker")
        if poll_interval_seconds <= 0 or heartbeat_interval_seconds <= 0:
            raise ValueError("worker intervals must be positive")

        self._db_factory = db_factory
        self.lane = lane
        self.worker_id = worker_id.strip()
        self._handlers = normalized_handlers
        self._max_workers = worker_count
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._heartbeat_interval_seconds = float(heartbeat_interval_seconds)
        self._clock = clock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._current_lock = threading.Lock()
        self._current_claim: operations.ClaimedOperation | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Canvas operation worker has already been started")
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix=f"canvas-{self.lane}-cpu",
        )
        self._thread = threading.Thread(
            target=self._run,
            name=f"canvas-{self.lane}-dispatcher",
            daemon=True,
        )
        self._thread.start()

    def request_stop(self) -> None:
        with self._current_lock:
            self._stop_event.set()

    def join(self, *, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def stop(self, *, graceful_timeout_seconds: float = 30.0) -> bool:
        if graceful_timeout_seconds < 0:
            raise ValueError("graceful_timeout_seconds must not be negative")
        self.request_stop()
        if self.join(timeout=graceful_timeout_seconds):
            return True
        self._interrupt_current_claim()
        return self.join(timeout=self._heartbeat_interval_seconds + 1.0)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _recover(self) -> None:
        with self._db_factory() as db:
            try:
                operations.recover_expired_operations(
                    db,
                    lane=self.lane,
                    now=self._clock(),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _claim(self) -> operations.ClaimedOperation | None:
        with self._db_factory() as db:
            try:
                claimed = operations.claim_next_operation(
                    db,
                    worker_id=self.worker_id,
                    lane=self.lane,
                    now=self._clock(),
                )
                db.commit()
                return claimed
            except Exception:
                db.rollback()
                raise

    def _heartbeat(self, claimed: operations.ClaimedOperation) -> bool:
        with self._db_factory() as db:
            try:
                current = operations.heartbeat_claimed_operation(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    now=self._clock(),
                )
                db.commit()
                return current
            except Exception:
                db.rollback()
                raise

    def _mark_unhandled_failure(self, claimed: operations.ClaimedOperation) -> None:
        with self._db_factory() as db:
            try:
                operations.mark_claimed_operation_failed(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    safe_error={
                        "code": "local_operation_failed",
                        "message": "Local Canvas processing could not be completed",
                        "retryable": True,
                    },
                    now=self._clock(),
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Canvas worker could not persist a safe failure")

    def _release_unstarted_claim(self, claimed: operations.ClaimedOperation) -> None:
        with self._db_factory() as db:
            try:
                released = operations.release_claimed_operation(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    now=self._clock(),
                )
                db.commit()
                if not released:
                    logger.warning("Canvas worker could not release a stale unstarted claim")
            except Exception:
                db.rollback()
                logger.exception("Canvas worker could not release an unstarted claim")

    def _interrupt_current_claim(self) -> None:
        with self._current_lock:
            claimed = self._current_claim
        if claimed is None:
            return
        with self._db_factory() as db:
            try:
                operations.mark_claimed_operation_interrupted(
                    db,
                    operation_id=claimed.id,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                    now=self._clock(),
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Canvas worker could not interrupt its current claim")

    def _execute_claim(self, claimed: operations.ClaimedOperation) -> None:
        handler = self._handlers.get(claimed.operation_type)
        if handler is None:
            self._mark_unhandled_failure(claimed)
            return
        executor = self._executor
        if executor is None:
            raise RuntimeError("Canvas worker executor is unavailable")
        future = executor.submit(handler, claimed)
        claim_is_current = True
        while True:
            try:
                future.result(timeout=self._heartbeat_interval_seconds)
                return
            except FutureTimeoutError:
                if claim_is_current:
                    try:
                        claim_is_current = self._heartbeat(claimed)
                    except Exception:
                        logger.exception("Canvas worker heartbeat failed")
                        claim_is_current = False
            except Exception:
                if claim_is_current:
                    self._mark_unhandled_failure(claimed)
                return

    def _run(self) -> None:
        try:
            try:
                self._recover()
            except Exception:
                logger.exception("Canvas worker startup lease recovery failed")
            while not self._stop_event.is_set():
                try:
                    self._recover()
                except Exception:
                    logger.exception("Canvas worker periodic lease recovery failed")
                if self._stop_event.is_set():
                    break
                try:
                    claimed = self._claim()
                except Exception:
                    logger.exception("Canvas worker claim failed")
                    self._stop_event.wait(self._poll_interval_seconds)
                    continue
                if claimed is None:
                    self._stop_event.wait(self._poll_interval_seconds)
                    continue
                release_unstarted = False
                with self._current_lock:
                    if self._stop_event.is_set():
                        release_unstarted = True
                    else:
                        self._current_claim = claimed
                if release_unstarted:
                    self._release_unstarted_claim(claimed)
                    break
                try:
                    try:
                        self._execute_claim(claimed)
                    except Exception:
                        logger.exception("Canvas worker execution supervision failed")
                        self._mark_unhandled_failure(claimed)
                finally:
                    with self._current_lock:
                        self._current_claim = None
        finally:
            executor = self._executor
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)


__all__ = ["CanvasOperationWorker", "OperationHandler"]
