"""Compatibility helpers for the retired LAN admin login."""
from __future__ import annotations

from fastapi import Request, Response


AUTH_COOKIE_NAME = "facai_admin_token"


def auth_explicitly_enabled() -> bool:
    return False


def auth_enabled() -> bool:
    return False


def auth_configured() -> bool:
    return False


def is_lan_exposed_host(host: str | None) -> bool:
    return False


def assert_startup_security(host: str | None) -> None:
    return None


def is_admin_request(request: Request) -> bool:
    return True


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME)
