"""Passwordless audit actor for trusted-intranet integration operations."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from services.security import request_actor_digest


@dataclass(frozen=True, slots=True)
class IntegrationActor:
    digest: str


def current_integration_actor(request: Request) -> IntegrationActor:
    return IntegrationActor(digest=request_actor_digest(request))


def integration_actor_digest(actor: IntegrationActor) -> str:
    return actor.digest


__all__ = [
    "IntegrationActor",
    "current_integration_actor",
    "integration_actor_digest",
]
