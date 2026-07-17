"""Passwordless trusted-intranet request identity helpers.

The application deliberately has no login boundary. This module provides a
non-secret local actor only so rate limits, audit records, and per-request
ownership keys keep working independently of authentication.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    auth_source: str


def principal_for_request(request: Request) -> Principal:
    client_ip = request.client.host if request.client else "unknown"
    return Principal(
        name=f"intranet:{client_ip}",
        role="trusted-intranet",
        auth_source="network",
    )


def request_actor_digest(request: Request) -> str:
    """Return a stable non-secret owner key for one reachable intranet client."""

    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        principal = principal_for_request(request)
    material = f"facai-operations-v2:{principal.name}:{principal.role}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


__all__ = ["Principal", "principal_for_request", "request_actor_digest"]
