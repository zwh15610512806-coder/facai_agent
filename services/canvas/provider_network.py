"""Fail-closed public HTTPS transport for image Provider traffic."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
from threading import Lock
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpcore
from httpcore._backends.auto import AutoBackend
from httpcore._backends.base import AsyncNetworkBackend, AsyncNetworkStream, SOCKET_OPTION


Resolver = Callable[[str], Iterable[str]]
_QUERY_URL_PATTERN = re.compile(r"(https://[^\s'\"?<>]+)\?[^\s'\"<>]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"(Bearer\s+)[^\s'\"<>\]\),]+", re.IGNORECASE)
_LOG_FILTER_LOCK = Lock()
_LOG_FILTER_INSTALLED = False


class ProviderNetworkError(RuntimeError):
    """Network boundary failure whose message never contains a requested URL."""


def redact_url_queries(message: str) -> str:
    """Remove credentials and signed query material from transport debug output."""

    without_queries = _QUERY_URL_PATTERN.sub(r"\1?<redacted>", str(message))
    return _BEARER_PATTERN.sub(r"\1<redacted>", without_queries)


class _RedactProviderQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        record.msg = redact_url_queries(rendered)
        record.args = ()
        return True


def _install_httpcore_query_filter() -> None:
    global _LOG_FILTER_INSTALLED
    with _LOG_FILTER_LOCK:
        if _LOG_FILTER_INSTALLED:
            return
        redactor = _RedactProviderQueryFilter()
        for logger_name in (
            "httpcore.connection",
            "httpcore.connection_pool",
            "httpcore.http11",
            "httpcore.http2",
        ):
            logging.getLogger(logger_name).addFilter(redactor)
        _LOG_FILTER_INSTALLED = True


@dataclass(frozen=True, repr=False)
class PinnedEndpoint:
    url: str = field(repr=False)
    hostname: str
    port: int
    pinned_ip: str
    private_http: bool = False

    def __repr__(self) -> str:
        return (
            "PinnedEndpoint(hostname="
            f"{self.hostname!r}, port={self.port!r}, pinned_ip={self.pinned_ip!r})"
        )


@dataclass(frozen=True)
class NetworkResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes = field(repr=False)

    def header(self, name: str) -> str | None:
        expected = name.lower()
        for key, value in self.headers.items():
            if str(key).lower() == expected:
                return str(value)
        return None


@dataclass(frozen=True)
class ProviderNetworkPolicy:
    """Administrator-controlled origin and transport limits for custom Providers."""

    allowed_hosts: tuple[str, ...]
    private_allowed_hosts: tuple[str, ...]
    private_allowed_ips: tuple[str, ...]
    allow_insecure_http: bool
    connect_timeout_seconds: int
    total_timeout_seconds: int
    max_json_bytes: int

    def __post_init__(self) -> None:
        if (
            self.connect_timeout_seconds <= 0
            or self.total_timeout_seconds < self.connect_timeout_seconds
            or self.max_json_bytes <= 0
        ):
            raise ValueError("Provider network policy limits are invalid")

    @classmethod
    def from_config(cls) -> "ProviderNetworkPolicy":
        import config

        return cls(
            allowed_hosts=tuple(config.CANVAS_PROVIDER_ALLOWED_HOSTS),
            private_allowed_hosts=tuple(config.CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS),
            private_allowed_ips=tuple(config.CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS),
            allow_insecure_http=bool(config.CANVAS_ALLOW_INSECURE_PROVIDER_HTTP),
            connect_timeout_seconds=int(config.CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS),
            total_timeout_seconds=int(config.CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS),
            max_json_bytes=int(config.CANVAS_PROVIDER_MAX_JSON_BYTES),
        )


@dataclass(frozen=True, repr=False)
class ValidatedOrigin:
    url: str = field(repr=False)
    scheme: str
    hostname: str
    port: int
    path_prefix: str

    def __repr__(self) -> str:
        return (
            "ValidatedOrigin(scheme="
            f"{self.scheme!r}, hostname={self.hostname!r}, port={self.port!r}, "
            f"path_prefix={self.path_prefix!r})"
        )


PinnedTarget = PinnedEndpoint


def _policy_hostname(value: str) -> str:
    try:
        hostname = value.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise ProviderNetworkError("Provider hostname is invalid") from None
    if not hostname or "%" in hostname:
        raise ProviderNetworkError("Provider hostname is invalid")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ProviderNetworkError("Provider hostname must not be an IP address")
    if re.fullmatch(r"[0-9a-fx.]+", hostname):
        raise ProviderNetworkError("Provider hostname is ambiguous")
    return hostname


def validate_provider_base_url(
    value: str,
    *,
    policy: ProviderNetworkPolicy,
) -> ValidatedOrigin:
    """Validate an administrator-chosen Provider origin before any DNS lookup."""

    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ProviderNetworkError("Provider base URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError:
        raise ProviderNetworkError("Provider base URL is invalid") from None
    scheme = parsed.scheme.lower()
    if (
        scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise ProviderNetworkError("Provider base URL is invalid")
    hostname = _policy_hostname(parsed.hostname)
    path_prefix = parsed.path.rstrip("/")
    if "//" in parsed.path or any(segment in {".", ".."} for segment in parsed.path.split("/")):
        raise ProviderNetworkError("Provider base URL path is invalid")
    if scheme == "https":
        if hostname not in set(policy.allowed_hosts):
            raise ProviderNetworkError("Provider hostname is not allowed")
    elif not (
        policy.allow_insecure_http
        and hostname in set(policy.private_allowed_hosts)
        and policy.private_allowed_ips
    ):
        raise ProviderNetworkError("Private Provider HTTP is not allowed")
    normalized_authority = hostname if port == (443 if scheme == "https" else 80) else f"{hostname}:{port}"
    return ValidatedOrigin(
        url=f"{scheme}://{normalized_authority}{path_prefix}",
        scheme=scheme,
        hostname=hostname,
        port=port,
        path_prefix=path_prefix,
    )


def validate_relative_endpoint(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ProviderNetworkError("Provider endpoint is invalid")
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or any(segment in {".", ".."} for segment in parsed.path.split("/"))
    ):
        raise ProviderNetworkError("Provider endpoint must be a relative path")
    return parsed.path


def _safe_private_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False
    if not address.is_private:
        return False
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    return not (mapped is not None and not _safe_private_address(mapped))


def resolve_pinned_target(
    origin: ValidatedOrigin,
    *,
    resolver: Resolver | None = None,
    policy: ProviderNetworkPolicy,
) -> PinnedTarget:
    """Resolve every DNS answer and pin a policy-compliant address."""

    raw_addresses = tuple((resolver or _default_resolver)(origin.hostname))
    if not raw_addresses:
        raise ProviderNetworkError("Provider hostname resolution returned no addresses")
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw_address in raw_addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            raise ProviderNetworkError("Provider hostname returned an invalid address") from None
        if origin.scheme == "https":
            _normalized_public_address(str(address))
        else:
            if str(address) not in set(policy.private_allowed_ips) or not _safe_private_address(address):
                raise ProviderNetworkError("Private Provider address is not allowed")
        addresses.append(address)
    chosen = sorted(addresses, key=lambda value: (value.version, int(value)))[0]
    return PinnedEndpoint(
        url=origin.url,
        hostname=origin.hostname,
        port=origin.port,
        pinned_ip=str(chosen),
        private_http=origin.scheme == "http",
    )


def _default_resolver(hostname: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        raise ProviderNetworkError("Provider hostname resolution failed") from None
    return tuple({str(record[4][0]) for record in records})


def _normalized_public_address(raw_address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError:
        raise ProviderNetworkError("Provider hostname returned an invalid address") from None
    classified = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    effective = classified or address
    if (
        not effective.is_global
        or effective.is_private
        or effective.is_loopback
        or effective.is_link_local
        or effective.is_multicast
        or effective.is_reserved
        or effective.is_unspecified
    ):
        raise ProviderNetworkError("Provider address is not public")
    return address


def resolve_public_https_endpoint(
    url: str,
    *,
    resolver: Resolver | None = None,
) -> PinnedEndpoint:
    """Resolve all A/AAAA records and pin one only if every result is public."""

    if not isinstance(url, str) or not url or len(url) > 4096:
        raise ProviderNetworkError("Provider URL is invalid")
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError:
        raise ProviderNetworkError("Provider URL is invalid") from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise ProviderNetworkError("Provider URL must use public HTTPS")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise ProviderNetworkError("Provider hostname is invalid") from None
    if not hostname or "%" in hostname:
        raise ProviderNetworkError("Provider hostname is invalid")
    raw_addresses = tuple((resolver or _default_resolver)(hostname))
    if not raw_addresses:
        raise ProviderNetworkError("Provider hostname resolution returned no addresses")
    # Fail the whole origin when any A or AAAA record is unsafe. Choosing a safe
    # sibling while ignoring an unsafe one would leave a DNS-rebinding bypass.
    addresses = tuple(_normalized_public_address(value) for value in raw_addresses)
    chosen = sorted(addresses, key=lambda value: (value.version, int(value)))[0]
    return PinnedEndpoint(
        url=url,
        hostname=hostname,
        port=port,
        pinned_ip=str(chosen),
    )


async def collect_bounded_chunks(
    chunks: AsyncIterable[bytes],
    *,
    max_bytes: int,
) -> bytes:
    if max_bytes <= 0:
        raise ProviderNetworkError("Provider response size limit is invalid")
    collected = bytearray()
    async for chunk in chunks:
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise ProviderNetworkError("Provider response contained invalid bytes")
        if len(collected) + len(chunk) > max_bytes:
            raise ProviderNetworkError("Provider response exceeded the size limit")
        collected.extend(chunk)
    return bytes(collected)


class _PinnedAsyncBackend(AsyncNetworkBackend):
    def __init__(self, endpoint: PinnedEndpoint) -> None:
        self._endpoint = endpoint
        self._delegate = AutoBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        if host.lower().rstrip(".") != self._endpoint.hostname or port != self._endpoint.port:
            raise ProviderNetworkError("Provider connection origin changed")
        return await self._delegate.connect_tcp(
            self._endpoint.pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        raise ProviderNetworkError("Provider Unix sockets are disabled")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class PinnedHttpCoreTransport:
    """One fresh no-proxy httpcore pool, pinned address, and SNI per request."""

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        _install_httpcore_query_filter()
        self._resolver = resolver
        self._timeout_seconds = timeout_seconds

    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
        body: bytes | None = None,
        max_bytes: int,
        pinned_endpoint: PinnedEndpoint | None = None,
    ) -> NetworkResponse:
        endpoint = pinned_endpoint or resolve_public_https_endpoint(
            url, resolver=self._resolver
        )
        try:
            parsed = urlsplit(url)
            scheme = parsed.scheme.lower()
            if scheme not in {"https", "http"}:
                raise ProviderNetworkError("Provider pinned endpoint is invalid")
            expected_host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
            expected_port = parsed.port or (443 if scheme == "https" else 80)
            if scheme == "https":
                if endpoint.private_http:
                    raise ProviderNetworkError("Provider pinned endpoint is invalid")
                _normalized_public_address(endpoint.pinned_ip)
            else:
                private_address = ipaddress.ip_address(endpoint.pinned_ip)
                if not endpoint.private_http or not _safe_private_address(private_address):
                    raise ProviderNetworkError("Provider pinned endpoint is invalid")
        except (AttributeError, UnicodeError, ValueError, ProviderNetworkError):
            raise ProviderNetworkError("Provider pinned endpoint is invalid") from None
        if (
            endpoint.url != url
            or endpoint.hostname != expected_host
            or endpoint.port != expected_port
        ):
            raise ProviderNetworkError("Provider pinned endpoint does not match request")
        if json_body is not None and body is not None:
            raise ProviderNetworkError("Provider request body is ambiguous")
        request_body = body
        if json_body is not None:
            try:
                request_body = json.dumps(
                    json_body,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError):
                raise ProviderNetworkError("Provider JSON request is invalid") from None

        outgoing: list[tuple[bytes, bytes]] = []
        supplied_names: set[str] = set()
        for raw_name, raw_value in (headers or {}).items():
            name = str(raw_name).strip()
            value = str(raw_value).strip()
            if not name or "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise ProviderNetworkError("Provider request header is invalid")
            if name.lower() == "host":
                # Host is authoritative from the validated origin; callers
                # cannot decouple HTTP routing from the pinned TLS identity.
                continue
            supplied_names.add(name.lower())
            outgoing.append((name.encode("ascii"), value.encode("latin-1")))
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        host_header = endpoint.hostname if endpoint.port == default_port else f"{endpoint.hostname}:{endpoint.port}"
        outgoing.append((b"Host", host_header.encode("ascii")))
        if json_body is not None and "content-type" not in supplied_names:
            outgoing.append((b"Content-Type", b"application/json"))
        if "accept" not in supplied_names:
            outgoing.append((b"Accept", b"*/*"))

        timeout = {
            "connect": self._timeout_seconds,
            "read": self._timeout_seconds,
            "write": self._timeout_seconds,
            "pool": self._timeout_seconds,
        }
        pool = httpcore.AsyncConnectionPool(
            proxy=None,
            retries=0,
            max_connections=1,
            max_keepalive_connections=0,
            network_backend=_PinnedAsyncBackend(endpoint),
        )
        response = None
        try:
            async with pool:
                response = await pool.request(
                    method.upper(),
                    url,
                    headers=outgoing,
                    content=request_body or b"",
                    extensions={
                        "sni_hostname": endpoint.hostname,
                        "timeout": timeout,
                    },
                )
                content_length = None
                normalized_headers: dict[str, str] = {}
                for raw_name, raw_value in response.headers:
                    name = raw_name.decode("latin-1").lower()
                    value = raw_value.decode("latin-1")
                    normalized_headers[name] = value
                    if name == "content-length":
                        content_length = value
                if content_length is not None:
                    try:
                        if int(content_length) > max_bytes:
                            raise ProviderNetworkError(
                                "Provider response exceeded the size limit"
                            )
                    except ValueError:
                        raise ProviderNetworkError(
                            "Provider response Content-Length is invalid"
                        ) from None
                response_body = await collect_bounded_chunks(
                    response.aiter_stream(), max_bytes=max_bytes
                )
                await response.aclose()
                return NetworkResponse(
                    status_code=response.status,
                    headers=normalized_headers,
                    body=response_body,
                )
        except ProviderNetworkError:
            raise
        except Exception:
            raise ProviderNetworkError("Provider network request failed") from None
        finally:
            if response is not None:
                try:
                    await response.aclose()
                except Exception:
                    pass


class SafeProviderHttpClient:
    """Policy-bound custom Provider client with pinned DNS and no redirects."""

    def __init__(
        self,
        *,
        origin: ValidatedOrigin,
        policy: ProviderNetworkPolicy,
        resolver: Resolver | None = None,
        transport: PinnedHttpCoreTransport | None = None,
    ) -> None:
        self._origin = origin
        self._policy = policy
        self._resolver = resolver
        self._transport = transport or PinnedHttpCoreTransport(
            resolver=resolver,
            timeout_seconds=policy.connect_timeout_seconds,
        )

    @property
    def origin(self) -> ValidatedOrigin:
        return self._origin

    async def request(
        self,
        *,
        method: str,
        endpoint: str,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
        body: bytes | None = None,
        max_bytes: int | None = None,
    ) -> NetworkResponse:
        relative = validate_relative_endpoint(endpoint)
        if json_body is not None and body is not None:
            raise ProviderNetworkError("Provider request body is ambiguous")
        payload = body
        outgoing = dict(headers or {})
        if json_body is not None:
            try:
                payload = json.dumps(
                    json_body,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError):
                raise ProviderNetworkError("Provider JSON request is invalid") from None
            if len(payload) > self._policy.max_json_bytes:
                raise ProviderNetworkError("Provider JSON request exceeded the size limit")
            outgoing.setdefault("Content-Type", "application/json")
        encoded_query = ""
        if query:
            pairs: list[tuple[str, str]] = []
            for raw_key, raw_value in query.items():
                key = str(raw_key)
                value = str(raw_value)
                if (
                    not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", key)
                    or not value
                    or len(value) > 8192
                    or "\r" in key
                    or "\n" in key
                    or "\r" in value
                    or "\n" in value
                ):
                    raise ProviderNetworkError("Provider request query is invalid")
                pairs.append((key, value))
            encoded_query = urlencode(pairs, doseq=False, safe="")
        url = f"{self._origin.url}{relative}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        target = resolve_pinned_target(
            self._origin,
            resolver=self._resolver,
            policy=self._policy,
        )
        endpoint_pin = PinnedEndpoint(
            url=url,
            hostname=target.hostname,
            port=target.port,
            pinned_ip=target.pinned_ip,
            private_http=target.private_http,
        )
        response_cap = max_bytes if max_bytes is not None else self._policy.max_json_bytes
        if response_cap <= 0:
            raise ProviderNetworkError("Provider response size limit is invalid")
        try:
            async with asyncio.timeout(self._policy.total_timeout_seconds):
                return await self._transport.request(
                    method=method,
                    url=url,
                    headers=outgoing,
                    body=payload,
                    max_bytes=response_cap,
                    pinned_endpoint=endpoint_pin,
                )
        except TimeoutError:
            raise ProviderNetworkError("Provider network request timed out") from None


__all__ = [
    "NetworkResponse",
    "PinnedEndpoint",
    "PinnedTarget",
    "PinnedHttpCoreTransport",
    "ProviderNetworkPolicy",
    "ProviderNetworkError",
    "SafeProviderHttpClient",
    "ValidatedOrigin",
    "collect_bounded_chunks",
    "resolve_pinned_target",
    "resolve_public_https_endpoint",
    "redact_url_queries",
    "validate_provider_base_url",
    "validate_relative_endpoint",
]
