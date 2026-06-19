"""Small runtime access-control helpers for LAN deployments."""
from __future__ import annotations

import hmac
import os

from fastapi import Request, Response


AUTH_COOKIE_NAME = "facai_admin_token"
AUTH_HEADER_NAME = "x-facai-admin-token"
DEFAULT_SESSION_SECONDS = 12 * 60 * 60


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def admin_token() -> str:
    return os.getenv("FACAI_ADMIN_TOKEN", "").strip()


def auth_enabled() -> bool:
    return bool(admin_token()) or _truthy(os.getenv("FACAI_AUTH_ENABLED"))


def auth_configured() -> bool:
    return bool(admin_token())


def verify_admin_token(candidate: str | None) -> bool:
    expected = admin_token()
    if not expected or not candidate:
        return False
    return hmac.compare_digest(candidate.strip(), expected)


def token_from_request(request: Request) -> str:
    header_token = request.headers.get(AUTH_HEADER_NAME, "").strip()
    if header_token:
        return header_token

    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return request.cookies.get(AUTH_COOKIE_NAME, "").strip()


def is_admin_request(request: Request) -> bool:
    return verify_admin_token(token_from_request(request))


def set_admin_cookie(response: Response, token: str) -> None:
    max_age = int(os.getenv("FACAI_AUTH_SESSION_SECONDS", str(DEFAULT_SESSION_SECONDS)))
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_truthy(os.getenv("FACAI_AUTH_COOKIE_SECURE")),
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME)
