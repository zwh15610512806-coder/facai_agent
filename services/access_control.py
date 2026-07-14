"""Auditing, rate-limit primitives, and per-actor AI budget accounting."""
from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AIUsageRecord, AuditEvent
from services.security import Principal

CONTROL_SESSION_FACTORY = SessionLocal
REQUEST_LIMITER = None  # initialized after SlidingWindowLimiter is defined


class SlidingWindowLimiter:
    """Small single-process limiter suitable for the supported one-worker runtime."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        if limit <= 0:
            return None
        now = self._clock()
        cutoff = now - max(1, window_seconds)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, math.ceil(events[0] + window_seconds - now))
            events.append(now)
        return None


REQUEST_LIMITER = SlidingWindowLimiter()


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _request_category(method: str, path: str) -> tuple[str, int, int] | None:
    if method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    normalized = path.rstrip("/")
    if (
        normalized.endswith("/reindex")
        or normalized.endswith("/index/start")
        or normalized.endswith("/vector-sync/retry")
        or normalized.endswith("/extract-all-points")
    ):
        return (
            "rebuild",
            _positive_env_int("FACAI_REBUILD_RATE_LIMIT_PER_HOUR", 4),
            3600,
        )
    if any(
        marker in normalized
        for marker in ("/upload", "/import", "/attachments", "/documents", "/scan-local")
    ):
        return (
            "upload",
            _positive_env_int("FACAI_UPLOAD_RATE_LIMIT_PER_MINUTE", 20),
            60,
        )
    if (
        normalized.startswith("/api/scripts/")
        or normalized.startswith("/api/inspiration/chat")
        or normalized.endswith("/rag-chat")
        or normalized.endswith("/extract-points")
        or normalized in {"/api/search-proxy/ai-search", "/api/search-proxy/search-summary"}
    ):
        return (
            "ai",
            _positive_env_int("FACAI_AI_RATE_LIMIT_PER_MINUTE", 30),
            60,
        )
    return None


def request_limit_violation(
    *, principal: Principal, method: str, path: str
) -> tuple[str, int] | None:
    category = _request_category(method, path)
    if category is None:
        return None
    name, limit, window_seconds = category
    retry_after = REQUEST_LIMITER.check(
        f"{principal.name}:{name}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if retry_after is not None:
        return f"{name} rate limit exceeded", retry_after

    daily_budget = _positive_env_int("FACAI_AI_DAILY_TOKEN_BUDGET", 500_000)
    if name != "ai" or daily_budget <= 0:
        return None
    with CONTROL_SESSION_FACTORY() as session:
        remaining = ai_budget_remaining(
            session,
            actor_name=principal.name,
            daily_limit=daily_budget,
            now=datetime.now(),
        )
    if remaining <= 0:
        tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
        return "daily AI token budget exceeded", max(1, int(tomorrow - time.time()))
    return None


def record_audit_event(
    session_factory,
    *,
    principal: Principal,
    method: str,
    path: str,
    status_code: int,
    client_ip: str,
    request_id: str,
) -> None:
    with session_factory() as session:
        session.add(AuditEvent(
            actor_name=principal.name,
            actor_role=principal.role,
            auth_source=principal.auth_source,
            method=method.upper(),
            path=path[:500],
            status_code=int(status_code),
            client_ip=(client_ip or "")[:100],
            request_id=(request_id or "")[:100],
        ))
        session.commit()


def should_audit(method: str, path: str) -> bool:
    if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        return True
    return any(
        marker in path
        for marker in ("/private-contact", "/download", "/preview", "/source-download", "/export")
    )


def record_request_audit(
    *,
    principal: Principal,
    method: str,
    path: str,
    status_code: int,
    client_ip: str,
    request_id: str,
) -> None:
    record_audit_event(
        CONTROL_SESSION_FACTORY,
        principal=principal,
        method=method,
        path=path,
        status_code=status_code,
        client_ip=client_ip,
        request_id=request_id,
    )


def ai_budget_remaining(
    db: Session,
    *,
    actor_name: str,
    daily_limit: int,
    now: datetime,
) -> int:
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        db.query(func.coalesce(func.sum(AIUsageRecord.total_tokens), 0))
        .filter(
            AIUsageRecord.actor_name == actor_name,
            AIUsageRecord.created_at >= start_of_day,
        )
        .scalar()
        or 0
    )
    return max(0, int(daily_limit) - int(used))
