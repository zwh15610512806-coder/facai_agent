"""Bounded thread pool for document parsers and other blocking libraries."""
from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial


class WorkQueueFull(RuntimeError):
    pass


class BoundedExecutor:
    def __init__(self, *, max_workers: int, max_pending: int, thread_name_prefix: str) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix=thread_name_prefix,
        )
        self._slots = threading.BoundedSemaphore(max(1, max_pending))

    async def run(self, function, /, *args, **kwargs):
        if not self._slots.acquire(blocking=False):
            raise WorkQueueFull("Document parser queue is full")
        try:
            future = self._executor.submit(partial(function, *args, **kwargs))
        except Exception:
            self._slots.release()
            raise
        future.add_done_callback(lambda _future: self._slots.release())
        return await asyncio.wrap_future(future)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


DOCUMENT_EXECUTOR = BoundedExecutor(
    max_workers=int(os.getenv("FACAI_DOCUMENT_PARSER_WORKERS", "4")),
    max_pending=int(os.getenv("FACAI_DOCUMENT_PARSER_QUEUE", "8")),
    thread_name_prefix="facai-document",
)


async def run_blocking(function, /, *args, **kwargs):
    return await DOCUMENT_EXECUTOR.run(function, *args, **kwargs)
