"""Runtime authentication and role-based access control for LAN deployments.

Authentication is intentionally enabled by default.  A trusted-loopback-only
deployment may opt out with ``FACAI_AUTH_ENABLED=0``; public/LAN binds are
refused when authentication is disabled or no administrator token exists.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from dataclasses import dataclass

from fastapi import Request, Response

AUTH_COOKIE_NAME = "facai_session_token"
AUTH_HEADER_NAME = "x-facai-session-token"
DEFAULT_SESSION_SECONDS = 12 * 60 * 60
# Public-bind values are detected here so startup can reject unsafe configuration.
PUBLIC_BIND_HOSTS = {"", "0.0.0.0", "::"}  # nosec B104
LOCAL_BIND_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver", "testclient"}
ROLE_TOKEN_ENV = (
    ("admin", "FACAI_ADMIN_TOKEN"),
    ("operator", "FACAI_OPERATOR_TOKEN"),
    ("viewer", "FACAI_VIEWER_TOKEN"),
)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    auth_source: str


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def auth_explicitly_enabled() -> bool:
    return _truthy(os.getenv("FACAI_AUTH_ENABLED"), default=True)


def auth_enabled() -> bool:
    """Return whether application authentication is active (default: yes)."""

    return auth_explicitly_enabled()


def configured_role_tokens() -> tuple[tuple[str, str], ...]:
    return tuple(
        (role, value)
        for role, env_name in ROLE_TOKEN_ENV
        if (value := os.getenv(env_name, "").strip())
    )


def auth_configured() -> bool:
    return any(role == "admin" for role, _token in configured_role_tokens())


def is_lan_exposed_host(host: str | None) -> bool:
    normalized = (host or "").strip().strip("[]").lower()
    if normalized in PUBLIC_BIND_HOSTS:
        return True
    if normalized in LOCAL_BIND_HOSTS:
        return False
    try:
        return not ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return True


def assert_startup_security(host: str | None) -> None:
    """Refuse an unsafe public bind before Uvicorn starts accepting traffic."""

    if not is_lan_exposed_host(host):
        return
    if not auth_enabled():
        raise RuntimeError(
            "FACAI authentication cannot be disabled when binding to a LAN/public host"
        )
    if not auth_configured():
        raise RuntimeError(
            "FACAI_ADMIN_TOKEN must be configured before binding the app to "
            # Diagnostic text only; this value is not passed to a socket API.
            f"{host or '0.0.0.0'}"  # nosec B104
        )


def principal_from_token(candidate: str | None, *, source: str = "token") -> Principal | None:
    if not candidate:
        return None
    candidate = candidate.strip()
    for role, expected in configured_role_tokens():
        if hmac.compare_digest(candidate, expected):
            return Principal(name=role, role=role, auth_source=source)
    return None


def _session_signing_key() -> bytes | None:
    for role, token in configured_role_tokens():
        if role == "admin":
            return hashlib.sha256(("facai-session-v1:" + token).encode("utf-8")).digest()
    return None


def create_session_token(principal: Principal) -> str:
    key = _session_signing_key()
    if key is None:
        raise RuntimeError("FACAI_ADMIN_TOKEN is required to sign sessions")
    max_age = int(os.getenv("FACAI_AUTH_SESSION_SECONDS", str(DEFAULT_SESSION_SECONDS)))
    payload = {
        "v": 1,
        "role": principal.role,
        "name": principal.name,
        "exp": int(time.time()) + max(60, max_age),
        "nonce": secrets.token_urlsafe(12),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=")
    signature = hmac.new(key, encoded, hashlib.sha256).digest()
    signed = encoded + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")
    return signed.decode("ascii")


def principal_from_session(candidate: str | None) -> Principal | None:
    key = _session_signing_key()
    if not candidate or key is None:
        return None
    try:
        encoded, supplied_signature = candidate.encode("ascii").split(b".", 1)
        padding = b"=" * (-len(supplied_signature) % 4)
        signature = base64.urlsafe_b64decode(supplied_signature + padding)
        expected = hmac.new(key, encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        padding = b"=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        role = str(payload.get("role") or "")
        name = str(payload.get("name") or role)
        if payload.get("v") != 1 or int(payload.get("exp") or 0) < int(time.time()):
            return None
        if role not in {configured_role for configured_role, _token in configured_role_tokens()}:
            return None
        return Principal(name=name, role=role, auth_source="cookie")
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeError):
        return None


def token_from_request(request: Request) -> tuple[str, str]:
    header_token = request.headers.get(AUTH_HEADER_NAME, "").strip()
    if header_token:
        return header_token, "header"

    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip(), "bearer"

    return request.cookies.get(AUTH_COOKIE_NAME, "").strip(), "cookie"


def request_actor_digest(request: Request) -> str:
    """Return a stable, irreversible owner key for the active system credential."""
    principal = principal_from_request(request)
    key = _session_signing_key()
    if principal is not None and key is not None:
        role_credential = next(
            (
                token
                for role, token in configured_role_tokens()
                if role == principal.role
            ),
            None,
        )
        if role_credential:
            message = (
                f"facai-operations-v1:{principal.role}:{role_credential}"
            ).encode("utf-8")
            return hmac.new(key, message, hashlib.sha256).hexdigest()

    principal = principal or getattr(request.state, "principal", None)
    fallback = (
        f"facai-operations-v1:disabled:"
        f"{getattr(principal, 'role', 'anonymous')}:"
        f"{getattr(principal, 'name', 'anonymous')}"
    )
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def principal_from_request(request: Request) -> Principal | None:
    token, source = token_from_request(request)
    if source == "cookie":
        return principal_from_session(token)
    return principal_from_token(token, source=source)


def is_admin_request(request: Request) -> bool:
    principal = principal_from_request(request)
    return bool(principal and principal.role == "admin")


def set_session_cookie(response: Response, principal: Principal) -> None:
    max_age = int(os.getenv("FACAI_AUTH_SESSION_SECONDS", str(DEFAULT_SESSION_SECONDS)))
    response.set_cookie(
        AUTH_COOKIE_NAME,
        create_session_token(principal),
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=_truthy(os.getenv("FACAI_AUTH_COOKIE_SECURE")),
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME)


def is_public_path(path: str) -> bool:
    if path in {"/", "/healthz", "/app/login"}:
        return True
    if path.startswith("/static/"):
        return True
    if re.fullmatch(
        r"/integrations/(?:oauth/callback|events)/(?:qianchuan|doudian|taobao|pdd)",
        path.rstrip("/"),
    ):
        return True
    return path in {"/api/auth/login", "/api/auth/logout", "/api/auth/status"}


def _creator_read_is_sensitive(path: str) -> bool:
    if path in {"/api/creators", "/api/creators/", "/api/creators/bd-members"}:
        return False
    return re.fullmatch(r"/api/creators/\d+", path.rstrip("/")) is None


def required_roles(method: str, path: str) -> frozenset[str]:
    """Return the roles allowed to perform one authenticated request."""

    method = method.upper()
    normalized = path.rstrip("/") or "/"

    if normalized.startswith("/api/integrations"):
        return frozenset({"admin", "operator", "viewer"})
    if normalized.startswith("/api/operations/exports"):
        return frozenset({"admin", "operator"})
    if re.fullmatch(r"/api/operations/products/\d+/link", normalized):
        return frozenset({"admin", "operator"})
    if normalized.startswith("/api/ai-config"):
        return frozenset({"admin"})
    if method == "DELETE":
        return frozenset({"admin"})
    if normalized.endswith("/reindex") or normalized.endswith("/index/start"):
        return frozenset({"admin"})
    if normalized.endswith("/vector-sync/retry"):
        return frozenset({"admin"})
    if normalized.startswith("/api/search-proxy/files/"):
        return frozenset({"admin", "operator"})
    if normalized.startswith("/api/products/source-download"):
        return frozenset({"admin", "operator"})
    if normalized.startswith("/api/creators") and method in SAFE_METHODS:
        if _creator_read_is_sensitive(normalized):
            return frozenset({"admin", "operator"})
    if "/import" in normalized or normalized.endswith("/export"):
        return frozenset({"admin", "operator"})
    if method in SAFE_METHODS:
        return frozenset({"admin", "operator", "viewer"})
    return frozenset({"admin", "operator"})


def role_is_allowed(role: str, method: str, path: str) -> bool:
    return role in required_roles(method, path)


def request_uses_cookie_auth(request: Request) -> bool:
    _token, source = token_from_request(request)
    return source == "cookie" and bool(request.cookies.get(AUTH_COOKIE_NAME))
