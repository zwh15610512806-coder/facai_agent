"""Per-request identity context propagated into service-layer usage records."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_actor_name: ContextVar[str] = ContextVar("facai_actor_name", default="system")
_request_id: ContextVar[str] = ContextVar("facai_request_id", default="")


def current_actor_name() -> str:
    return _actor_name.get()


def current_request_id() -> str:
    return _request_id.get()


@contextmanager
def request_actor(actor_name: str, request_id: str = "") -> Iterator[None]:
    actor_token = _actor_name.set((actor_name or "system").strip() or "system")
    request_token = _request_id.set((request_id or "").strip())
    try:
        yield
    finally:
        _request_id.reset(request_token)
        _actor_name.reset(actor_token)
