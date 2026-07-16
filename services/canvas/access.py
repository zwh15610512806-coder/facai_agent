"""In-memory signed access proofs for paid Product Canvas operations."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, Response, status

import config


CANVAS_ACCESS_COOKIE_NAME = "facai_canvas_access"
CANVAS_ACCESS_COOKIE_PATH = "/api/canvas"
_SESSION_SECRET_ATTRIBUTE = "_product_canvas_access_session_secret"
_SESSION_DOMAIN = b"facai.product-canvas.paid-access.session.v1\x00"
_PROOF_VERSION = 1
_NONCE_BYTES = 16
_SIGNATURE_BYTES = hashlib.sha256().digest_size


@dataclass(frozen=True)
class CanvasAccessStatus:
    configured: bool
    locked: bool


def initialize_canvas_access_session(app: FastAPI) -> None:
    """Install a fresh, process-lifespan-only secret on an application."""

    setattr(app.state, _SESSION_SECRET_ATTRIBUTE, secrets.token_bytes(32))


def clear_canvas_access_session(app: FastAPI) -> None:
    if hasattr(app.state, _SESSION_SECRET_ATTRIBUTE):
        delattr(app.state, _SESSION_SECRET_ATTRIBUTE)


def _configured_token() -> str:
    value = config.CANVAS_ACCESS_TOKEN
    return value if isinstance(value, str) else ""


def _session_secret(request: Request) -> bytes:
    value = getattr(request.app.state, _SESSION_SECRET_ATTRIBUTE, None)
    if not isinstance(value, bytes) or len(value) != 32:
        raise RuntimeError("Canvas access session was not initialized")
    return value


def _signing_key(*, process_secret: bytes, token: str) -> bytes:
    return hmac.new(
        process_secret,
        _SESSION_DOMAIN + token.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    if not value or any(character not in alphabet for character in value):
        raise ValueError("invalid access proof encoding")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _mint_proof(request: Request, *, token: str, ttl_seconds: int) -> str:
    expires_at = int(time.time()) + ttl_seconds
    payload = (
        bytes([_PROOF_VERSION])
        + expires_at.to_bytes(8, "big", signed=False)
        + secrets.token_bytes(_NONCE_BYTES)
    )
    signature = hmac.new(
        _signing_key(process_secret=_session_secret(request), token=token),
        payload,
        hashlib.sha256,
    ).digest()
    return f"{_encode(payload)}.{_encode(signature)}"


def _proof_is_valid(request: Request, *, token: str, proof: str | None) -> bool:
    if not proof:
        return False
    try:
        payload_text, signature_text = proof.split(".", 1)
        payload = _decode(payload_text)
        signature = _decode(signature_text)
        if len(payload) != 1 + 8 + _NONCE_BYTES:
            return False
        if len(signature) != _SIGNATURE_BYTES or payload[0] != _PROOF_VERSION:
            return False
        expected = hmac.new(
            _signing_key(process_secret=_session_secret(request), token=token),
            payload,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        expires_at = int.from_bytes(payload[1:9], "big", signed=False)
        return expires_at > int(time.time())
    except (UnicodeError, ValueError, OverflowError):
        return False


def canvas_access_status(request: Request) -> CanvasAccessStatus:
    token = _configured_token()
    if not token:
        return CanvasAccessStatus(configured=False, locked=True)
    proof = request.cookies.get(CANVAS_ACCESS_COOKIE_NAME)
    return CanvasAccessStatus(
        configured=True,
        locked=not _proof_is_valid(request, token=token, proof=proof),
    )


def unlock_canvas_access(
    request: Request,
    response: Response,
    token: str,
) -> None:
    configured = _configured_token()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canvas paid access is not configured",
        )
    supplied_digest = hashlib.sha256(token.encode("utf-8")).digest()
    configured_digest = hashlib.sha256(configured.encode("utf-8")).digest()
    if not hmac.compare_digest(supplied_digest, configured_digest):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Canvas paid access token is invalid",
        )
    ttl_seconds = config.CANVAS_ACCESS_SESSION_TTL_SECONDS
    proof = _mint_proof(request, token=configured, ttl_seconds=ttl_seconds)
    response.set_cookie(
        CANVAS_ACCESS_COOKIE_NAME,
        proof,
        max_age=ttl_seconds,
        path=CANVAS_ACCESS_COOKIE_PATH,
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="strict",
    )


def lock_canvas_access(response: Response) -> None:
    response.delete_cookie(
        CANVAS_ACCESS_COOKIE_NAME,
        path=CANVAS_ACCESS_COOKIE_PATH,
        httponly=True,
        samesite="strict",
    )


def require_canvas_paid_access(request: Request) -> None:
    access = canvas_access_status(request)
    if not access.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canvas paid access is not configured",
        )
    if access.locked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Canvas paid access is locked",
        )


__all__ = [
    "CANVAS_ACCESS_COOKIE_NAME",
    "CanvasAccessStatus",
    "canvas_access_status",
    "clear_canvas_access_session",
    "initialize_canvas_access_session",
    "lock_canvas_access",
    "require_canvas_paid_access",
    "unlock_canvas_access",
]
