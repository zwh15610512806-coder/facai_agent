"""Validated, non-fail-fast configuration for the integration center."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import os
import re
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network
from pathlib import Path
from typing import Mapping
from urllib.parse import SplitResult, urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


ADMIN_PASSWORD_HASH_ENV = "FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH"
SESSION_SECRET_ENV = "FACAI_INTEGRATIONS_SESSION_SECRET"
MASTER_KEY_ENV = "FACAI_INTEGRATIONS_MASTER_KEY"
INTERNAL_BASE_URL_ENV = "FACAI_INTEGRATIONS_INTERNAL_BASE_URL"
PUBLIC_BASE_URL_ENV = "FACAI_INTEGRATIONS_PUBLIC_BASE_URL"
ARCHIVE_DIR_ENV = "FACAI_INTEGRATION_ARCHIVE_DIR"
TRUSTED_PROXY_CIDRS_ENV = "FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS"
WORKER_CONCURRENCY_ENV = "FACAI_INTEGRATION_WORKER_CONCURRENCY"
DATABASE_URL_ENV = "DATABASE_URL"

_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DNS_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


@dataclass(frozen=True, slots=True)
class IntegrationSettings:
    admin_password_hash: str | None
    session_secret: bytes | None
    master_key: bytes | None
    internal_base_url: str | None
    public_base_url: str | None
    archive_dir: Path | None
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...]
    worker_concurrency: int
    login_ready: bool
    credential_ready: bool
    errors: tuple[str, ...]


def _append_error(errors: list[str], key: str) -> None:
    if key not in errors:
        errors.append(key)


def _nonempty(values: Mapping[str, str], key: str, errors: list[str]) -> str | None:
    raw = values.get(key)
    if raw is None or not raw.strip() or raw != raw.strip():
        _append_error(errors, key)
        return None
    return raw


def _decode_base64url_secret(
    values: Mapping[str, str],
    key: str,
    errors: list[str],
    *,
    exact_bytes: int | None = None,
    minimum_bytes: int | None = None,
) -> bytes | None:
    raw = _nonempty(values, key, errors)
    if raw is None or not _BASE64URL_RE.fullmatch(raw):
        _append_error(errors, key)
        return None
    try:
        decoded = base64.b64decode(
            raw + "=" * (-len(raw) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        _append_error(errors, key)
        return None
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != raw:
        _append_error(errors, key)
        return None
    if exact_bytes is not None and len(decoded) != exact_bytes:
        _append_error(errors, key)
        return None
    if minimum_bytes is not None and len(decoded) < minimum_bytes:
        _append_error(errors, key)
        return None
    return decoded


def _hostname_is_loopback(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _canonical_hostname(hostname: str) -> tuple[str, str]:
    try:
        return "ip", ipaddress.ip_address(hostname).compressed
    except ValueError:
        return "dns", hostname.casefold()


def _effective_origin_port(parts: SplitResult) -> int:
    return parts.port or (443 if parts.scheme.lower() == "https" else 80)


def _valid_hostname(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return _DNS_HOST_RE.fullmatch(hostname) is not None


def _origin_parts(raw: str) -> SplitResult | None:
    if any(
        ord(character) <= 0x20 or ord(character) == 0x7F
        for character in raw
    ) or any(character in raw for character in ("?", "#", "\\")):
        return None
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.netloc.endswith(":")
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != ""
        or parsed.query
        or parsed.fragment
        or not _valid_hostname(hostname)
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None
    if parsed.scheme.lower() == "http" and not _hostname_is_loopback(hostname):
        return None
    return parsed


def _parse_origin(
    values: Mapping[str, str], key: str, errors: list[str]
) -> tuple[str | None, SplitResult | None]:
    raw = _nonempty(values, key, errors)
    if raw is None:
        return None, None
    parsed = _origin_parts(raw)
    if parsed is None:
        _append_error(errors, key)
        return None, None
    return raw, parsed


def _parse_archive_dir(
    values: Mapping[str, str], errors: list[str]
) -> Path | None:
    raw = _nonempty(values, ARCHIVE_DIR_ENV, errors)
    if raw is None:
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            _append_error(errors, ARCHIVE_DIR_ENV)
            return None
        resolved = candidate.resolve(strict=False)
        if resolved.exists() and not resolved.is_dir():
            _append_error(errors, ARCHIVE_DIR_ENV)
            return None
    except (OSError, RuntimeError, ValueError):
        _append_error(errors, ARCHIVE_DIR_ENV)
        return None
    return resolved


def _parse_trusted_proxy_networks(
    values: Mapping[str, str], errors: list[str]
) -> tuple[IPv4Network | IPv6Network, ...]:
    raw = values.get(TRUSTED_PROXY_CIDRS_ENV, "")
    if not raw.strip():
        return ()
    if raw != raw.strip():
        _append_error(errors, TRUSTED_PROXY_CIDRS_ENV)
        return ()

    parsed: list[IPv4Network | IPv6Network] = []
    try:
        for item in raw.split(","):
            if not item or item != item.strip() or "/" not in item:
                raise ValueError("CIDR must be explicit")
            network = ipaddress.ip_network(item, strict=True)
            if item != str(network) or network.prefixlen == 0:
                raise ValueError("CIDR must be canonical and bounded")
            if network not in parsed:
                parsed.append(network)
    except ValueError:
        _append_error(errors, TRUSTED_PROXY_CIDRS_ENV)
        return ()
    return tuple(parsed)


def _parse_worker_concurrency(
    values: Mapping[str, str], errors: list[str]
) -> int:
    raw = values.get(WORKER_CONCURRENCY_ENV, "4")
    try:
        concurrency = int(raw)
        if concurrency < 1 or str(concurrency) != raw:
            raise ValueError
    except (TypeError, ValueError):
        _append_error(errors, WORKER_CONCURRENCY_ENV)
        return 4
    return concurrency


def _valid_postgres_url(values: Mapping[str, str], errors: list[str]) -> bool:
    raw = _nonempty(values, DATABASE_URL_ENV, errors)
    if raw is None:
        return False
    try:
        parsed = make_url(raw)
        port = parsed.port
    except (ArgumentError, ValueError):
        _append_error(errors, DATABASE_URL_ENV)
        return False
    if (
        parsed.drivername != "postgresql+psycopg"
        or not parsed.host
        or not parsed.host.strip()
        or not parsed.database
        or not parsed.database.strip()
        or (port is not None and not 1 <= port <= 65535)
    ):
        _append_error(errors, DATABASE_URL_ENV)
        return False
    return True


def _validate_integration_settings(values: Mapping[str, str]) -> IntegrationSettings:
    errors: list[str] = []
    admin_password_hash = _nonempty(values, ADMIN_PASSWORD_HASH_ENV, errors)
    session_secret = _decode_base64url_secret(
        values,
        SESSION_SECRET_ENV,
        errors,
        minimum_bytes=32,
    )
    master_key = _decode_base64url_secret(
        values,
        MASTER_KEY_ENV,
        errors,
        exact_bytes=32,
    )
    internal_base_url, internal_parts = _parse_origin(
        values, INTERNAL_BASE_URL_ENV, errors
    )
    public_base_url, public_parts = _parse_origin(values, PUBLIC_BASE_URL_ENV, errors)
    if internal_parts is not None and public_parts is not None:
        internal_hostname = internal_parts.hostname or ""
        public_hostname = public_parts.hostname or ""
        same_hostname = _canonical_hostname(
            internal_hostname
        ) == _canonical_hostname(public_hostname)
        both_loopback = _hostname_is_loopback(
            internal_hostname
        ) and _hostname_is_loopback(public_hostname)
        same_authority = same_hostname and _effective_origin_port(
            internal_parts
        ) == _effective_origin_port(public_parts)
        loopback_ports_are_explicit_nondefault = (
            internal_parts.port is not None
            and public_parts.port is not None
            and internal_parts.port
            != (443 if internal_parts.scheme.lower() == "https" else 80)
            and public_parts.port
            != (443 if public_parts.scheme.lower() == "https" else 80)
        )
        if same_hostname and (
            not both_loopback
            or same_authority
            or not loopback_ports_are_explicit_nondefault
        ):
            _append_error(errors, PUBLIC_BASE_URL_ENV)

    archive_dir = _parse_archive_dir(values, errors)
    trusted_proxy_networks = _parse_trusted_proxy_networks(values, errors)
    worker_concurrency = _parse_worker_concurrency(values, errors)
    database_ready = _valid_postgres_url(values, errors)

    login_ready = admin_password_hash is not None and session_secret is not None
    credential_keys = {
        MASTER_KEY_ENV,
        INTERNAL_BASE_URL_ENV,
        PUBLIC_BASE_URL_ENV,
        ARCHIVE_DIR_ENV,
        TRUSTED_PROXY_CIDRS_ENV,
        WORKER_CONCURRENCY_ENV,
        DATABASE_URL_ENV,
    }
    credential_ready = (
        login_ready
        and master_key is not None
        and internal_base_url is not None
        and public_base_url is not None
        and archive_dir is not None
        and database_ready
        and not any(key in errors for key in credential_keys)
    )
    return IntegrationSettings(
        admin_password_hash=admin_password_hash,
        session_secret=session_secret,
        master_key=master_key,
        internal_base_url=internal_base_url,
        public_base_url=public_base_url,
        archive_dir=archive_dir,
        trusted_proxy_networks=trusted_proxy_networks,
        worker_concurrency=worker_concurrency,
        login_ready=login_ready,
        credential_ready=credential_ready,
        errors=tuple(errors),
    )


def load_integration_settings(
    environ: Mapping[str, str] | None = None,
) -> IntegrationSettings:
    """Load integration-only settings without failing unrelated application imports."""

    values = os.environ if environ is None else environ
    return _validate_integration_settings(values)


__all__ = ["IntegrationSettings", "load_integration_settings"]
