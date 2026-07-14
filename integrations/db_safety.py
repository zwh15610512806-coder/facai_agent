"""Fail-closed validation for disposable PostgreSQL test databases."""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import unquote, urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


_ALLOWED_QUERY = {"sslmode": "disable"}
_SAFE_DATABASE_NAME = re.compile(r"[A-Za-z0-9_]+")
_PROTECTED_DATABASE_ENVIRONMENTS = (
    "DATABASE_URL",
    "FACAI_MIGRATION_TEST_DATABASE_URL",
)
_PSYCOPG_TARGET_OVERRIDE_KEYS = frozenset(
    {"host", "port", "dbname", "user", "password"}
)


def _refuse(reason: str) -> RuntimeError:
    return RuntimeError(f"Refusing destructive PostgreSQL target: {reason}")


def _normalized_host(host: str | None, *, require_loopback: bool) -> str:
    if not host:
        raise _refuse("an explicit host is required")

    normalized = host.lower()
    if require_loopback:
        if normalized not in {"127.0.0.1", "::1"}:
            raise _refuse("the host must be a literal loopback address")
        return "loopback"

    if normalized.endswith("."):
        normalized = normalized[:-1]
    if normalized == "localhost":
        return "loopback"

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized

    if address.is_loopback:
        return "loopback"
    return address.compressed


def _decoded_database(url: URL) -> str:
    database = unquote(url.database or "")
    if not database or _SAFE_DATABASE_NAME.fullmatch(database) is None:
        raise _refuse("the database name must use only letters, digits, and underscores")
    return database


def _parse_url(raw_url: str) -> tuple[URL, str]:
    try:
        split_url = urlsplit(raw_url)
        url = make_url(raw_url)
        # Accessing URL.port performs SQLAlchemy's integer validation.
        _ = url.port
    except (ArgumentError, TypeError, ValueError):
        raise _refuse("the database URL is invalid") from None

    if split_url.fragment:
        raise _refuse("URL fragments are not allowed")
    return url, _decoded_database(url)


def _protected_identity(raw_url: str) -> tuple[str, int, str] | None:
    try:
        url, database = _parse_url(raw_url)
    except RuntimeError:
        raise _refuse("a protected database URL could not be compared safely") from None

    if url.get_backend_name() != "postgresql":
        return None
    if _PSYCOPG_TARGET_OVERRIDE_KEYS.intersection(url.query):
        raise _refuse("a protected database URL could not be compared safely")

    host = _normalized_host(url.host, require_loopback=False)
    port = url.port or 5432
    return host, port, database


def _validate_target(raw_url: str, acknowledgement: str) -> tuple[URL, str]:
    url, database = _parse_url(raw_url)

    if url.drivername != "postgresql+psycopg":
        raise _refuse("the postgresql+psycopg driver is required")
    if not url.username:
        raise _refuse("an explicit username is required")
    host = _normalized_host(url.host, require_loopback=True)
    if url.port is None:
        raise _refuse("an explicit port is required")
    if not database.endswith(("_test", "_ci")):
        raise _refuse("the database name must end in _test or _ci")
    if not acknowledgement or acknowledgement != database:
        raise _refuse("the acknowledgement must exactly match the database name")
    if dict(url.query) not in ({}, _ALLOWED_QUERY):
        raise _refuse("only the exact sslmode=disable query is allowed")

    identity = (host, url.port, database)
    for environment_name in _PROTECTED_DATABASE_ENVIRONMENTS:
        protected_url = os.environ.get(environment_name)
        if protected_url and _protected_identity(protected_url) == identity:
            raise _refuse("the target matches a protected database target")

    return url, database


def assert_disposable_postgres(
    *,
    url_env: str,
    acknowledgement_env: str,
) -> str:
    """Validate and connect to a disposable PostgreSQL target before destructive work.

    The returned URL is intended only for the immediately following database command.
    This function never logs or includes the URL or credentials in its exceptions.
    """

    raw_url = os.environ.get(url_env, "")
    acknowledgement = os.environ.get(acknowledgement_env, "")
    if not raw_url:
        raise _refuse("the target URL environment variable is required")

    url, database = _validate_target(raw_url, acknowledgement)
    connection_url = url.set(database=database).render_as_string(hide_password=False)

    engine = None
    try:
        engine = create_engine(connection_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connected_database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()
    except Exception:
        raise RuntimeError(
            "Unable to verify the disposable PostgreSQL target safely"
        ) from None
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                raise RuntimeError(
                    "Unable to verify the disposable PostgreSQL target safely"
                ) from None

    if connected_database != acknowledgement or connected_database != database:
        raise _refuse("the current database does not match the acknowledgement")
    return connection_url
