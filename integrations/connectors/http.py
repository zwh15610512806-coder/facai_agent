"""Bounded fixed-host HTTP transport for future official platform adapters."""

from __future__ import annotations

import ipaddress
import json as json_module
import logging
import math
import re
import zlib
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from integrations.connectors.base import (
    AuthenticationFailed,
    ConnectorError,
    InvalidPlatformResponse,
    PermissionDenied,
    RateLimited,
    TransientPlatformError,
)
from integrations.types import JsonValue


_LOGGER = logging.getLogger(__name__)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LEGACY_IP_COMPONENT = re.compile(r"^(?:[0-9]+|0x[0-9a-f]+)$")
_HTTP_METHOD = re.compile(r"^[A-Z]+$")
_HTTP_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_PRESERVE_METHOD_REDIRECTS = frozenset({307, 308})
_SAFE_REDIRECT_METHODS = frozenset({"GET", "HEAD"})
_FIXED_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_REDIRECT_LOCATION_BYTES = 4096
_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        ":authority",
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_SUPPRESS_DEPENDENCY_REQUEST_LOGS: ContextVar[bool] = ContextVar(
    "suppress_official_api_dependency_request_logs",
    default=False,
)


class _StrictJsonError(ValueError):
    pass


class _DependencyRequestLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _SUPPRESS_DEPENDENCY_REQUEST_LOGS.get()


_DEPENDENCY_LOG_FILTER = _DependencyRequestLogFilter()
for _dependency_logger_name in (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_dependency_logger_name).addFilter(_DEPENDENCY_LOG_FILTER)


def _is_exact_dns_host(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if not host or host != host.lower() or host.endswith("."):
        return False
    if len(host) > 253 or "." not in host:
        return False
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False
    labels = host.split(".")
    if all(_LEGACY_IP_COMPONENT.fullmatch(label) for label in labels):
        return False
    return all(_DNS_LABEL.fullmatch(label) for label in labels)


def _validate_allowed_hosts(allowed_hosts: object) -> frozenset[str]:
    if type(allowed_hosts) is not frozenset:
        raise TypeError("allowed_hosts must be a frozenset")
    if not allowed_hosts:
        raise ValueError("allowed_hosts must not be empty")
    if any(not _is_exact_dns_host(host) for host in allowed_hosts):
        raise ValueError("allowed_hosts must contain exact lowercase DNS hosts")
    return allowed_hosts


def _validate_url(url: object, *, allowed_hosts: frozenset[str]) -> str:
    if not isinstance(url, str) or not url:
        raise InvalidPlatformResponse()
    if (
        "\\" in url
        or re.search(r"%5c", url, flags=re.IGNORECASE)
        or any(ord(character) < 32 or ord(character) == 127 for character in url)
    ):
        raise InvalidPlatformResponse()
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise InvalidPlatformResponse() from None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or "#" in url
        or parsed.fragment
        or host is None
        or not _is_exact_dns_host(host)
        or host not in allowed_hosts
        or port not in (None, 443)
        or "%" in parsed.netloc
    ):
        raise InvalidPlatformResponse()

    authority = parsed.netloc
    raw_host = authority[:-4] if authority.endswith(":443") else authority
    if raw_host != host:
        raise InvalidPlatformResponse()
    return host


def _validated_headers(
    headers: Mapping[str, str] | None,
) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise InvalidPlatformResponse()
    result: dict[str, str] = {}
    seen: set[str] = set()
    try:
        for name, value in headers.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise InvalidPlatformResponse()
            normalized_name = name.casefold()
            if (
                normalized_name in _FORBIDDEN_REQUEST_HEADERS
                or not _HTTP_HEADER_NAME.fullmatch(name)
                or normalized_name in seen
                or not value.isascii()
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in value
                )
            ):
                raise InvalidPlatformResponse()
            if normalized_name == "accept-encoding" and (
                value.strip().casefold() not in {"gzip", "identity"}
            ):
                raise InvalidPlatformResponse()
            seen.add(normalized_name)
            result[name] = value
    except ConnectorError:
        raise
    except Exception:
        raise InvalidPlatformResponse() from None
    return result


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _http_error(response: httpx.Response) -> ConnectorError | None:
    status_code = response.status_code
    if 200 <= status_code < 300:
        return None
    if status_code == 401:
        return AuthenticationFailed(status_code=status_code)
    if status_code == 403:
        return PermissionDenied(status_code=status_code)
    if status_code == 429:
        return RateLimited(
            status_code=status_code,
            retry_after_seconds=_parse_retry_after(
                response.headers.get("Retry-After")
            ),
        )
    if status_code in {408, 425} or 500 <= status_code < 600:
        return TransientPlatformError(status_code=status_code)
    return InvalidPlatformResponse(status_code=status_code)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError("duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _StrictJsonError("non-finite number")


def _assert_outbound_json(
    value: object,
    *,
    depth: int = 0,
    active_containers: set[int] | None = None,
) -> None:
    if depth > 64:
        raise _StrictJsonError("excessive nesting")
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise _StrictJsonError("non-finite number")
        return
    if type(value) is str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise _StrictJsonError("invalid unicode scalar")
        return
    if type(value) not in (dict, list, tuple):
        raise _StrictJsonError("unsupported JSON value")

    active = set() if active_containers is None else active_containers
    identity = id(value)
    if identity in active:
        raise _StrictJsonError("cyclic JSON value")
    active.add(identity)
    try:
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise _StrictJsonError("JSON object keys must be strings")
                _assert_outbound_json(
                    key,
                    depth=depth + 1,
                    active_containers=active,
                )
                _assert_outbound_json(
                    item,
                    depth=depth + 1,
                    active_containers=active,
                )
        else:
            for item in value:
                _assert_outbound_json(
                    item,
                    depth=depth + 1,
                    active_containers=active,
                )
    finally:
        active.remove(identity)


def _encode_outbound_json(value: object) -> bytes:
    try:
        _assert_outbound_json(value)
        rendered = json_module.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return rendered.encode("utf-8", errors="strict")
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeError,
        RecursionError,
    ):
        raise InvalidPlatformResponse() from None


def _assert_finite_json(value: Any, *, depth: int = 0) -> None:
    if depth > 64:
        raise _StrictJsonError("excessive nesting")
    if isinstance(value, float) and not math.isfinite(value):
        raise _StrictJsonError("non-finite number")
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise _StrictJsonError("invalid unicode scalar")
        return
    if isinstance(value, list):
        for item in value:
            _assert_finite_json(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite_json(key, depth=depth + 1)
            _assert_finite_json(item, depth=depth + 1)


def _decode_json(body: bytes) -> JsonValue:
    try:
        decoded = body.decode("utf-8", errors="strict")
        value = json_module.loads(
            decoded,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
        _assert_finite_json(value)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise InvalidPlatformResponse() from None
    return value


def _safe_log(*, method: str, outcome: str, status_code: int | None) -> None:
    _LOGGER.info(
        "official_api_request outcome=%s method=%s status_code=%s",
        outcome,
        method,
        status_code if status_code is not None else "none",
    )


class OfficialApiClient:
    """Make bounded JSON requests only to an immutable official host allowlist."""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._allowed_hosts = _validate_allowed_hosts(allowed_hosts)
        if (
            not isinstance(max_response_bytes, int)
            or isinstance(max_response_bytes, bool)
            or max_response_bytes <= 0
        ):
            raise ValueError("max_response_bytes must be a positive integer")
        self._max_response_bytes = max_response_bytes
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=_FIXED_TIMEOUT,
            transport=transport,
        )

    async def __aenter__(self) -> OfficialApiClient:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _read_identity_bounded(self, response: httpx.Response) -> bytes:
        if response.is_stream_consumed:
            try:
                body = response.content
            except httpx.ResponseNotRead:
                raise InvalidPlatformResponse(
                    status_code=response.status_code
                ) from None
            if len(body) > self._max_response_bytes:
                raise InvalidPlatformResponse(status_code=response.status_code)
            return body
        chunks: list[bytes] = []
        byte_count = 0
        async for chunk in response.aiter_raw():
            byte_count += len(chunk)
            if byte_count > self._max_response_bytes:
                raise InvalidPlatformResponse(status_code=response.status_code)
            chunks.append(chunk)
        return b"".join(chunks)

    async def _read_gzip_bounded(self, response: httpx.Response) -> bytes:
        if response.is_stream_consumed:
            raise InvalidPlatformResponse(status_code=response.status_code)
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        chunks: list[bytes] = []
        decoded_count = 0
        try:
            async for raw_chunk in response.aiter_raw():
                pending = raw_chunk
                while pending:
                    remaining = self._max_response_bytes - decoded_count
                    before_length = len(pending)
                    decoded = decompressor.decompress(pending, remaining + 1)
                    if len(decoded) > remaining:
                        raise InvalidPlatformResponse(
                            status_code=response.status_code
                        )
                    if decoded:
                        chunks.append(decoded)
                        decoded_count += len(decoded)
                    if decompressor.unused_data:
                        raise InvalidPlatformResponse(
                            status_code=response.status_code
                        )
                    pending = decompressor.unconsumed_tail
                    if pending and len(pending) == before_length and not decoded:
                        raise InvalidPlatformResponse(
                            status_code=response.status_code
                        )

            remaining = self._max_response_bytes - decoded_count
            tail = decompressor.flush(remaining + 1)
        except zlib.error:
            raise InvalidPlatformResponse(status_code=response.status_code) from None
        if len(tail) > remaining:
            raise InvalidPlatformResponse(status_code=response.status_code)
        if tail:
            chunks.append(tail)
        if (
            not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
        ):
            raise InvalidPlatformResponse(status_code=response.status_code)
        return b"".join(chunks)

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        content_encoding = response.headers.get("Content-Encoding")
        if content_encoding is None:
            return await self._read_identity_bounded(response)
        normalized_encoding = content_encoding.strip().casefold()
        if normalized_encoding == "identity":
            return await self._read_identity_bounded(response)
        if normalized_encoding == "gzip":
            return await self._read_gzip_bounded(response)
        raise InvalidPlatformResponse(status_code=response.status_code)

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        json: JsonValue | None = None,
        follow_same_host_redirect: bool = False,
    ) -> JsonValue:
        if not isinstance(method, str):
            raise InvalidPlatformResponse()
        safe_method = method.upper()
        if method != safe_method or not _HTTP_METHOD.fullmatch(safe_method):
            raise InvalidPlatformResponse()
        if not isinstance(follow_same_host_redirect, bool):
            raise InvalidPlatformResponse()

        current_url = url
        current_host = _validate_url(
            current_url,
            allowed_hosts=self._allowed_hosts,
        )
        current_params = params
        redirects_followed = 0
        safe_headers = _validated_headers(headers)
        outbound_body = None if json is None else _encode_outbound_json(json)
        if outbound_body is not None and not any(
            name.casefold() == "content-type" for name in safe_headers
        ):
            safe_headers["Content-Type"] = "application/json"
        if not any(name.casefold() == "accept-encoding" for name in safe_headers):
            safe_headers["Accept-Encoding"] = "gzip"

        while True:
            log_suppression_token = _SUPPRESS_DEPENDENCY_REQUEST_LOGS.set(True)
            try:
                async with self._client.stream(
                    safe_method,
                    current_url,
                    headers=safe_headers,
                    params=current_params,
                    content=outbound_body,
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if (
                            not follow_same_host_redirect
                            or redirects_followed >= 1
                            or not location
                            or len(location.encode("utf-8"))
                            > _MAX_REDIRECT_LOCATION_BYTES
                            or (
                                safe_method not in _SAFE_REDIRECT_METHODS
                                and response.status_code
                                not in _PRESERVE_METHOD_REDIRECTS
                            )
                        ):
                            raise InvalidPlatformResponse(
                                status_code=response.status_code
                            )
                        redirected_url = urljoin(
                            str(response.request.url),
                            location,
                        )
                        redirected_host = _validate_url(
                            redirected_url,
                            allowed_hosts=self._allowed_hosts,
                        )
                        if redirected_host != current_host:
                            raise InvalidPlatformResponse(
                                status_code=response.status_code
                            )
                        current_url = redirected_url
                        current_params = None
                        redirects_followed += 1
                        continue

                    error = _http_error(response)
                    if error is not None:
                        raise error
                    body = await self._read_bounded(response)
                    result = _decode_json(body)
                    _safe_log(
                        method=safe_method,
                        outcome="succeeded",
                        status_code=response.status_code,
                    )
                    return result
            except ConnectorError as error:
                _safe_log(
                    method=safe_method,
                    outcome=error.code,
                    status_code=error.status_code,
                )
                raise
            except httpx.DecodingError:
                error = InvalidPlatformResponse()
                _safe_log(
                    method=safe_method,
                    outcome=error.code,
                    status_code=None,
                )
                raise error from None
            except httpx.LocalProtocolError:
                error = InvalidPlatformResponse()
                _safe_log(
                    method=safe_method,
                    outcome=error.code,
                    status_code=None,
                )
                raise error from None
            except httpx.RequestError:
                error = TransientPlatformError()
                _safe_log(
                    method=safe_method,
                    outcome=error.code,
                    status_code=None,
                )
                raise error from None
            except (TypeError, ValueError, OverflowError, UnicodeError):
                error = InvalidPlatformResponse()
                _safe_log(
                    method=safe_method,
                    outcome=error.code,
                    status_code=None,
                )
                raise error from None
            finally:
                _SUPPRESS_DEPENDENCY_REQUEST_LOGS.reset(log_suppression_token)


__all__ = ["OfficialApiClient"]
