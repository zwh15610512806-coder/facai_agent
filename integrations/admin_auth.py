"""Authentication primitives for the dedicated integration administrator."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import secrets
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
)
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session
from starlette.requests import Request

from database import get_db
from integration_models import IntegrationLoginThrottle
from integrations.settings import IntegrationSettings, load_integration_settings


_SCRYPT_PARAMETERS = "n=32768,r=8,p=1"
_SCRYPT_N = 32768
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SCRYPT_MAXMEM = 134_217_728
_PASSWORD_MAX_BYTES = 512
_PASSWORD_SALT_BYTES = 16
_DUMMY_SALT = hashlib.sha256(b"facai-integrations/scrypt-dummy/v1").digest()[:16]
_DUMMY_DIGEST = hashlib.sha512(b"facai-integrations/scrypt-dummy/v1").digest()
_SESSION_VERSION = 1
_SESSION_ID_BYTES = 32
_SESSION_LIFETIME = timedelta(hours=8)
_SESSION_FUTURE_SKEW = timedelta(seconds=60)
_UTC = timezone.utc
_TRUSTED_PROXY_ERROR = "Trusted proxy forwarding configuration is invalid"
INTEGRATION_ADMIN_COOKIE = "facai_integrations_session"
SESSION_MAX_AGE_SECONDS = int(_SESSION_LIFETIME.total_seconds())
_THROTTLE_WINDOW = timedelta(minutes=15)
_THROTTLE_LOCK = timedelta(minutes=15)
_THROTTLE_MAX_FAILURES = 5


class InvalidAdminSessionError(ValueError):
    """Raised without cookie or claim details when a session is invalid."""


class LoginContextConfigurationError(ValueError):
    """Raised without forwarding values when transport facts are unusable."""


@dataclass(frozen=True, slots=True)
class AdminSessionClaims:
    sid: str = field(repr=False)
    iat: datetime
    exp: datetime


@dataclass(frozen=True, slots=True)
class LoginRequestContext:
    client_ip: IPv4Address | IPv6Address = field(repr=False)
    effective_scheme: str
    peer_is_trusted_proxy: bool


@dataclass(frozen=True, slots=True)
class AdminLoginResult:
    status_code: int
    detail: str
    cookie: str | None = field(default=None, repr=False)
    claims: AdminSessionClaims | None = field(default=None, repr=False)
    retry_after_seconds: int | None = None


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode_exact(value: str, *, expected_bytes: int) -> bytes:
    expected_length = len(_base64url_encode(b"\0" * expected_bytes))
    if (
        not isinstance(value, str)
        or len(value) != expected_length
        or any(
            character
            not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for character in value
        )
    ):
        raise ValueError("invalid Base64url encoding")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise ValueError("invalid Base64url encoding") from None
    if len(decoded) != expected_bytes or _base64url_encode(decoded) != value:
        raise ValueError("invalid Base64url encoding")
    return decoded


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise TypeError("Password must be a string")
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Password must be valid UTF-8") from None
    if len(encoded) > _PASSWORD_MAX_BYTES:
        raise ValueError("Password must not exceed 512 UTF-8 bytes")
    return encoded


def hash_admin_password(password: str, *, salt: bytes | None = None) -> str:
    """Hash a bounded administrator password using the fixed scrypt contract."""

    password_bytes = _password_bytes(password)
    if not password_bytes:
        raise ValueError("Password must contain at least one UTF-8 byte")
    selected_salt = secrets.token_bytes(_PASSWORD_SALT_BYTES) if salt is None else salt
    if not isinstance(selected_salt, bytes) or len(selected_salt) != _PASSWORD_SALT_BYTES:
        raise ValueError("Password salt must contain exactly 16 bytes")
    digest = hashlib.scrypt(
        password_bytes,
        salt=selected_salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return (
        f"$scrypt${_SCRYPT_PARAMETERS}$"
        f"{_base64url_encode(selected_salt)}${_base64url_encode(digest)}"
    )


def _password_hash_parts(encoded_hash: str) -> tuple[bytes, bytes, bool]:
    salt = _DUMMY_SALT
    expected_digest = _DUMMY_DIGEST
    valid = False
    try:
        parts = encoded_hash.split("$")
        if len(parts) != 5 or parts[:3] != ["", "scrypt", _SCRYPT_PARAMETERS]:
            raise ValueError
        salt = _base64url_decode_exact(parts[3], expected_bytes=_PASSWORD_SALT_BYTES)
        expected_digest = _base64url_decode_exact(
            parts[4], expected_bytes=_SCRYPT_DKLEN
        )
        valid = True
    except (AttributeError, TypeError, ValueError):
        pass
    return salt, expected_digest, valid


def verify_admin_password(password: str, encoded_hash: str) -> bool:
    """Verify a password while keeping malformed hashes on the scrypt path."""

    try:
        password_bytes = _password_bytes(password)
    except (TypeError, ValueError):
        return False
    salt, expected_digest, valid_encoding = _password_hash_parts(encoded_hash)
    computed_digest = hashlib.scrypt(
        password_bytes,
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    digest_matches = hmac.compare_digest(computed_digest, expected_digest)
    return valid_encoding and digest_matches


def _utc_datetime(value: datetime | None) -> datetime:
    selected = datetime.now(_UTC) if value is None else value
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("Session time must be timezone-aware")
    return selected.astimezone(_UTC)


def issue_admin_session(
    *,
    session_secret: bytes,
    now: datetime | None = None,
) -> str:
    """Issue a canonical HMAC-signed version-1 administrator session."""

    issued_at = int(_utc_datetime(now).timestamp())
    claims = {
        "exp": issued_at + int(_SESSION_LIFETIME.total_seconds()),
        "iat": issued_at,
        "sid": _base64url_encode(secrets.token_bytes(_SESSION_ID_BYTES)),
        "v": _SESSION_VERSION,
    }
    payload = json.dumps(
        claims,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    payload_part = _base64url_encode(payload)
    signature = hmac.new(
        session_secret,
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_base64url_encode(signature)}"


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate claim")
        result[key] = value
    return result


def _invalid_session() -> InvalidAdminSessionError:
    return InvalidAdminSessionError("Integration administrator session is invalid")


def verify_admin_session(
    cookie: str,
    *,
    session_secret: bytes,
    now: datetime | None = None,
) -> AdminSessionClaims:
    """Authenticate and validate a session without exposing its contents."""

    try:
        if not isinstance(cookie, str):
            raise ValueError
        parts = cookie.split(".")
        if len(parts) != 2 or not parts[0]:
            raise ValueError
        payload_part, signature_part = parts
        signature = _base64url_decode_exact(signature_part, expected_bytes=32)
        expected_signature = hmac.new(
            session_secret,
            payload_part.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError
        try:
            payload = base64.b64decode(
                payload_part + "=" * (-len(payload_part) % 4),
                altchars=b"-_",
                validate=True,
            )
        except (binascii.Error, ValueError):
            raise ValueError from None
        if _base64url_encode(payload) != payload_part:
            raise ValueError
        claims = json.loads(payload, object_pairs_hook=_unique_json_object)
        if not isinstance(claims, dict) or set(claims) != {"exp", "iat", "sid", "v"}:
            raise ValueError
        if type(claims["v"]) is not int or claims["v"] != _SESSION_VERSION:
            raise ValueError
        if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
            raise ValueError
        _base64url_decode_exact(claims["sid"], expected_bytes=_SESSION_ID_BYTES)
        canonical_payload = json.dumps(
            claims,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        if canonical_payload != payload:
            raise ValueError

        checked_at = _utc_datetime(now)
        issued_at = datetime.fromtimestamp(claims["iat"], tz=_UTC)
        expires_at = datetime.fromtimestamp(claims["exp"], tz=_UTC)
        if issued_at > checked_at + _SESSION_FUTURE_SKEW:
            raise ValueError
        if not checked_at < expires_at:
            raise ValueError
        if expires_at <= issued_at or expires_at > issued_at + _SESSION_LIFETIME:
            raise ValueError
    except (KeyError, TypeError, UnicodeError, ValueError, OverflowError):
        raise _invalid_session() from None
    return AdminSessionClaims(
        sid=claims["sid"],
        iat=issued_at,
        exp=expires_at,
    )


def _address_is_trusted(
    address: IPv4Address | IPv6Address,
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...],
) -> bool:
    return any(
        address.version == network.version and address in network
        for network in trusted_proxy_networks
    )


def _trusted_proxy_failure() -> LoginContextConfigurationError:
    return LoginContextConfigurationError(_TRUSTED_PROXY_ERROR)


def _forwarded_addresses(request: Request) -> list[IPv4Address | IPv6Address]:
    values = request.headers.getlist("x-forwarded-for")
    if len(values) != 1 or not values[0] or len(values[0]) > 4096:
        raise _trusted_proxy_failure()
    items = values[0].split(",")
    if not 1 <= len(items) <= 64:
        raise _trusted_proxy_failure()
    addresses: list[IPv4Address | IPv6Address] = []
    try:
        for item in items:
            selected = item.strip()
            if not selected:
                raise ValueError
            addresses.append(ipaddress.ip_address(selected))
    except ValueError:
        raise _trusted_proxy_failure() from None
    return addresses


def _forwarded_scheme(request: Request) -> str:
    values = request.headers.getlist("x-forwarded-proto")
    if len(values) != 1 or values[0] not in {"http", "https"}:
        raise _trusted_proxy_failure()
    return values[0]


def resolve_login_request_context(
    request: Request,
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...],
) -> LoginRequestContext:
    """Resolve source and scheme from transport facts and trusted proxy headers."""

    client = request.scope.get("client")
    raw_scheme = request.scope.get("scheme")
    try:
        if not isinstance(client, (tuple, list)) or len(client) != 2:
            raise ValueError
        peer = ipaddress.ip_address(client[0])
    except (TypeError, ValueError):
        raise LoginContextConfigurationError("Login transport context is invalid") from None
    if raw_scheme not in {"http", "https"}:
        raise LoginContextConfigurationError("Login transport context is invalid")

    peer_is_trusted = _address_is_trusted(peer, trusted_proxy_networks)
    if not peer_is_trusted:
        return LoginRequestContext(
            client_ip=peer,
            effective_scheme=raw_scheme,
            peer_is_trusted_proxy=False,
        )

    forwarded = _forwarded_addresses(request)
    resolved_client: IPv4Address | IPv6Address | None = None
    for address in reversed([*forwarded, peer]):
        if not _address_is_trusted(address, trusted_proxy_networks):
            resolved_client = address
            break
    if resolved_client is None:
        resolved_client = forwarded[0]

    effective_scheme = "https" if raw_scheme == "https" else _forwarded_scheme(request)
    return LoginRequestContext(
        client_ip=resolved_client,
        effective_scheme=effective_scheme,
        peer_is_trusted_proxy=True,
    )


def derive_login_source_digest(
    *,
    session_secret: bytes,
    client_ip: IPv4Address | IPv6Address,
) -> str:
    """Return the non-reversible persistent throttle key for a resolved source."""

    return hmac.new(
        session_secret,
        b"login-source/v1:" + client_ip.packed,
        hashlib.sha256,
    ).hexdigest()


def admin_session_digest(claims: AdminSessionClaims) -> str:
    """Hash only the random session identifier for audit correlation."""

    return hashlib.sha256(claims.sid.encode("ascii")).hexdigest()


def integration_admin_session_or_none(
    request: Request,
    *,
    settings: IntegrationSettings,
    now: datetime | None = None,
) -> AdminSessionClaims | None:
    """Return verified claims, or ``None`` without disclosing validation details."""

    if not settings.login_ready or settings.session_secret is None:
        return None
    cookie = request.cookies.get(INTEGRATION_ADMIN_COOKIE)
    if not cookie:
        return None
    try:
        return verify_admin_session(
            cookie,
            session_secret=settings.session_secret,
            now=now,
        )
    except InvalidAdminSessionError:
        return None


async def require_integration_admin(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminSessionClaims:
    """Protect only integration-administration routes."""

    del db
    settings = load_integration_settings()
    claims = integration_admin_session_or_none(request, settings=settings)
    if claims is None:
        raise HTTPException(
            status_code=401,
            detail="Integration administrator session required",
        )
    return claims


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=_UTC)
    return value.astimezone(_UTC)


def _retry_after_seconds(*, locked_until: datetime, now: datetime) -> int:
    return max(1, min(900, math.ceil((locked_until - now).total_seconds())))


def authenticate_admin_login(
    db: Session,
    *,
    password: str,
    encoded_password_hash: str,
    session_secret: bytes,
    context: LoginRequestContext,
    now: datetime | None = None,
) -> AdminLoginResult:
    """Authenticate under a PostgreSQL row lock and persist its audit atomically."""

    from integrations.audit import write_security_audit

    checked_at = _utc_datetime(now)
    source_digest = derive_login_source_digest(
        session_secret=session_secret,
        client_ip=context.client_ip,
    )
    insert_statement = (
        postgresql_insert(IntegrationLoginThrottle)
        .values(
            source_digest=source_digest,
            failure_count=0,
            window_started_at=checked_at,
            locked_until=None,
            updated_at=checked_at,
        )
        .on_conflict_do_nothing(index_elements=["source_digest"])
    )
    db.execute(insert_statement)
    throttle = db.execute(
        select(IntegrationLoginThrottle)
        .where(IntegrationLoginThrottle.source_digest == source_digest)
        .with_for_update()
    ).scalar_one()

    window_started_at = _as_aware_utc(throttle.window_started_at)
    locked_until = (
        _as_aware_utc(throttle.locked_until)
        if throttle.locked_until is not None
        else None
    )
    if locked_until is not None and checked_at < locked_until:
        retry_after = _retry_after_seconds(
            locked_until=locked_until,
            now=checked_at,
        )
        write_security_audit(
            db,
            event_type="login_locked",
            outcome="denied",
            source_digest=source_digest,
            summary_code="throttle_locked",
            details={"retry_after_seconds": retry_after},
            created_at=checked_at,
        )
        db.commit()
        return AdminLoginResult(
            status_code=429,
            detail="Integration administrator login is temporarily locked",
            retry_after_seconds=retry_after,
        )

    if checked_at >= window_started_at + _THROTTLE_WINDOW:
        throttle.failure_count = 0
        throttle.window_started_at = checked_at
        throttle.locked_until = None

    password_matches = verify_admin_password(password, encoded_password_hash)
    throttle.updated_at = checked_at
    if password_matches:
        throttle.failure_count = 0
        throttle.window_started_at = checked_at
        throttle.locked_until = None
        cookie = issue_admin_session(session_secret=session_secret, now=checked_at)
        claims = verify_admin_session(
            cookie,
            session_secret=session_secret,
            now=checked_at,
        )
        write_security_audit(
            db,
            event_type="login_succeeded",
            outcome="success",
            source_digest=source_digest,
            session_digest=admin_session_digest(claims),
            summary_code="password_verified",
            details={},
            created_at=checked_at,
        )
        db.commit()
        return AdminLoginResult(
            status_code=200,
            detail="Integration administrator authenticated",
            cookie=cookie,
            claims=claims,
        )

    throttle.failure_count += 1
    if throttle.failure_count >= _THROTTLE_MAX_FAILURES:
        throttle.failure_count = _THROTTLE_MAX_FAILURES
        throttle.locked_until = checked_at + _THROTTLE_LOCK
        retry_after = int(_THROTTLE_LOCK.total_seconds())
        write_security_audit(
            db,
            event_type="login_locked",
            outcome="denied",
            source_digest=source_digest,
            summary_code="throttle_locked",
            details={"retry_after_seconds": retry_after},
            created_at=checked_at,
        )
        db.commit()
        return AdminLoginResult(
            status_code=429,
            detail="Integration administrator login is temporarily locked",
            retry_after_seconds=retry_after,
        )

    write_security_audit(
        db,
        event_type="login_failed",
        outcome="failure",
        source_digest=source_digest,
        summary_code="password_mismatch",
        details={"attempt_count": throttle.failure_count},
        created_at=checked_at,
    )
    db.commit()
    return AdminLoginResult(
        status_code=401,
        detail="Integration administrator password is invalid",
    )


__all__ = [
    "AdminLoginResult",
    "AdminSessionClaims",
    "INTEGRATION_ADMIN_COOKIE",
    "InvalidAdminSessionError",
    "LoginContextConfigurationError",
    "LoginRequestContext",
    "SESSION_MAX_AGE_SECONDS",
    "admin_session_digest",
    "authenticate_admin_login",
    "derive_login_source_digest",
    "hash_admin_password",
    "integration_admin_session_or_none",
    "issue_admin_session",
    "resolve_login_request_context",
    "require_integration_admin",
    "verify_admin_password",
    "verify_admin_session",
]
