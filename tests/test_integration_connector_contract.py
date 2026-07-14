from __future__ import annotations

import gzip
import json as json_module
import logging
import math
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import httpx

from integrations.connectors import (
    AuthenticationFailed,
    ConnectorRegistry,
    ConnectorUnavailable,
    InvalidPlatformResponse,
    OfficialApiClient,
    PermissionDenied,
    RateLimited,
    TransientPlatformError,
    connector_registry,
)
from integrations.redaction import PayloadSafetyError
from integrations.types import (
    AccountIdentity,
    CapabilityReport,
    ConnectionContext,
    FetchPage,
    NormalizedRecord,
    Provider,
    RateLimitHint,
    ResourceType,
    RevokeResult,
    TimeWindow,
    TokenBundle,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _record(**overrides) -> NormalizedRecord:
    values = {
        "resource": ResourceType.ORDERS,
        "external_id": "order-1",
        "platform_updated_at": _now(),
        "payload": {"normalized_status": "paid", "amount": 12.5},
        "sanitized_source_payload": {"order_id": "order-1", "status": "PAID"},
    }
    values.update(overrides)
    return NormalizedRecord(**values)


class _ChunkedAsyncStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes, *, chunk_size: int = 1) -> None:
        self._content = content
        self._chunk_size = chunk_size

    async def __aiter__(self):
        for offset in range(0, len(self._content), self._chunk_size):
            yield self._content[offset : offset + self._chunk_size]


class TransportValueValidationTests(unittest.TestCase):
    def test_token_bundle_still_hides_tokens_without_constructor_validation(self):
        marker = "token-constructor-negative-test-marker"
        tokens = TokenBundle(
            access_token=marker,
            refresh_token=f"refresh-{marker}",
            access_expires_at=datetime.now(),
            refresh_expires_at=None,
            scopes=("orders.read",),
            external_subject_id="",
        )
        self.assertNotIn(marker, repr(tokens))
        self.assertEqual(tokens.access_token, marker)

    def test_time_window_requires_aware_ordered_datetimes(self):
        now = _now()
        valid = TimeWindow(start_at=now, end_at=now + timedelta(seconds=1))
        self.assertEqual(valid.start_at, now)

        invalid_pairs = (
            (datetime.now(), now + timedelta(seconds=1)),
            (now, datetime.now()),
            (now, now),
            (now, now - timedelta(microseconds=1)),
            ("not-a-datetime", now + timedelta(seconds=1)),
        )
        for start_at, end_at in invalid_pairs:
            with self.subTest(start_at=start_at, end_at=end_at):
                with self.assertRaises((TypeError, ValueError)):
                    TimeWindow(start_at=start_at, end_at=end_at)

    def test_rate_limit_hint_rejects_invalid_runtime_values(self):
        now = _now()
        valid = RateLimitHint(remaining=0, reset_at=now, retry_after_seconds=0.25)
        self.assertEqual(valid.remaining, 0)

        invalid_values = (
            {"remaining": -1, "reset_at": now, "retry_after_seconds": None},
            {"remaining": True, "reset_at": now, "retry_after_seconds": None},
            {"remaining": 1, "reset_at": datetime.now(), "retry_after_seconds": None},
            {"remaining": 1, "reset_at": now, "retry_after_seconds": -0.1},
            {"remaining": 1, "reset_at": now, "retry_after_seconds": math.inf},
            {"remaining": 1, "reset_at": now, "retry_after_seconds": True},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError)):
                    RateLimitHint(**values)

    def test_normalized_record_rejects_unsafe_or_malformed_values(self):
        invalid_values = (
            {"resource": "orders"},
            {"external_id": ""},
            {"external_id": " x"},
            {"external_id": "x" * 256},
            {"platform_updated_at": datetime.now()},
            {"payload": []},
            {"payload": {1: "not-a-string-key"}},
            {"payload": {"amount": math.nan}},
            {"payload": {"access_token": "secret"}},
            {"sanitized_source_payload": {"receiver": {"phone": "secret"}}},
        )
        for overrides in invalid_values:
            with self.subTest(overrides=overrides):
                with self.assertRaises((TypeError, ValueError)):
                    _record(**overrides)

        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(ValueError):
            _record(payload={"cycle": cyclic})

    def test_normalized_record_defensively_copies_and_deeply_freezes_payloads(self):
        payload = {
            "nested": {
                "statuses": ["paid"],
            }
        }
        source = {
            "raw": {
                "status": "PAID",
            }
        }
        record = _record(
            payload=payload,
            sanitized_source_payload=source,
        )

        payload["nested"]["statuses"].append("caller-mutated")
        payload["access_token"] = "late-secret"
        source["raw"]["status"] = "CALLER_MUTATED"
        source["refresh_token"] = "late-secret"

        self.assertEqual(record.payload["nested"]["statuses"], ("paid",))
        self.assertNotIn("access_token", record.payload)
        self.assertEqual(
            record.sanitized_source_payload["raw"]["status"],
            "PAID",
        )
        self.assertNotIn("refresh_token", record.sanitized_source_payload)
        with self.assertRaises(TypeError):
            record.payload["new"] = "blocked"
        with self.assertRaises(TypeError):
            record.payload["nested"]["new"] = "blocked"
        with self.assertRaises(AttributeError):
            record.payload["nested"]["statuses"].append("blocked")
        self.assertNotIn("late-secret", repr(record))

    def test_normalized_record_serialization_returns_safe_detached_json(self):
        record = _record(
            payload={"nested": {"statuses": ["paid"]}},
            sanitized_source_payload={"raw": {"status": "PAID"}},
        )
        payload = record.payload_for_serialization()
        source = record.source_payload_for_serialization()
        self.assertEqual(
            json_module.loads(json_module.dumps(payload)),
            {"nested": {"statuses": ["paid"]}},
        )
        self.assertEqual(source, {"raw": {"status": "PAID"}})
        payload["nested"]["statuses"].append("detached")
        self.assertEqual(record.payload["nested"]["statuses"], ("paid",))

        object.__setattr__(
            record,
            "sanitized_source_payload",
            {"access_token": "post-construction-secret"},
        )
        with self.assertRaises(PayloadSafetyError):
            record.source_payload_for_serialization()

    def test_fetch_page_requires_typed_records_and_consistent_cursor(self):
        now = _now()
        rate_hint = RateLimitHint(
            remaining=9,
            reset_at=now + timedelta(minutes=1),
            retry_after_seconds=None,
        )
        page = FetchPage(
            items=(_record(),),
            next_cursor="cursor-2",
            has_more=True,
            request_id="request-1",
            rate_limit_hint=rate_hint,
            watermark=now,
        )
        self.assertEqual(page.items[0].external_id, "order-1")
        self.assertEqual(page.next_cursor, "cursor-2")
        self.assertIs(page.rate_limit_hint, rate_hint)

        invalid_values = (
            {"items": [_record()]},
            {"items": ({"external_id": "raw"},)},
            {"next_cursor": ""},
            {"next_cursor": "x" * 4097},
            {"has_more": 1},
            {"next_cursor": None, "has_more": True},
            {"request_id": ""},
            {"request_id": "x" * 256},
            {"rate_limit_hint": {}},
            {"watermark": datetime.now()},
        )
        base = {
            "items": (_record(),),
            "next_cursor": None,
            "has_more": False,
            "request_id": None,
            "rate_limit_hint": None,
            "watermark": now,
        }
        for overrides in invalid_values:
            values = {**base, **overrides}
            with self.subTest(overrides=overrides):
                with self.assertRaises((TypeError, ValueError)):
                    FetchPage(**values)

    def test_request_ids_are_safe_printable_ascii(self):
        now = _now()
        base = {
            "items": (_record(),),
            "next_cursor": None,
            "has_more": False,
            "rate_limit_hint": None,
            "watermark": now,
        }
        for request_id in ("line\u2028separator", "non-ascii-é", "next\u0085line"):
            with self.subTest(request_id=request_id):
                with self.assertRaises(ValueError):
                    FetchPage(request_id=request_id, **base)
                with self.assertRaises(ValueError):
                    RevokeResult(revoked=True, request_id=request_id)

        page = FetchPage(request_id="request-id_123/ABC", **base)
        revoke = RevokeResult(revoked=True, request_id="request-id_123/ABC")
        self.assertEqual(page.request_id, revoke.request_id)


class CompleteConnector:
    provider = Provider.PDD

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        return f"https://authorization.example.invalid/start?state={state}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
        raise NotImplementedError

    async def refresh_tokens(self, tokens: TokenBundle) -> TokenBundle:
        raise NotImplementedError

    async def discover_accounts(self, tokens: TokenBundle) -> list[AccountIdentity]:
        raise NotImplementedError

    async def probe_capabilities(
        self, connection: ConnectionContext
    ) -> CapabilityReport:
        raise NotImplementedError

    async def fetch_page(
        self,
        *,
        connection: ConnectionContext,
        resource: ResourceType,
        window: TimeWindow | None,
        cursor: str | None,
    ) -> FetchPage:
        raise NotImplementedError

    async def revoke(self, connection: ConnectionContext) -> RevokeResult:
        raise NotImplementedError


class ConnectorRegistryContractTests(unittest.TestCase):
    def test_production_registry_remains_empty(self):
        for provider in Provider:
            with self.subTest(provider=provider):
                with self.assertRaises(ConnectorUnavailable):
                    connector_registry.get(provider)

    def test_complete_async_connector_can_be_registered(self):
        registry = ConnectorRegistry()
        connector = CompleteConnector()
        registry.register(connector)
        self.assertIs(registry.get(Provider.PDD), connector)

    def test_registry_rejects_sync_implementation_of_async_method(self):
        class SyncExchangeConnector(CompleteConnector):
            def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
                raise NotImplementedError

        with self.assertRaisesRegex(TypeError, "async"):
            ConnectorRegistry().register(SyncExchangeConnector())

    def test_registry_rejects_async_implementation_of_sync_method(self):
        class AsyncAuthorizationConnector(CompleteConnector):
            async def authorization_url(
                self,
                *,
                state: str,
                redirect_uri: str,
            ) -> str:
                return "https://authorization.example.invalid/start"

        with self.assertRaisesRegex(TypeError, "authorization_url"):
            ConnectorRegistry().register(AsyncAuthorizationConnector())

    def test_event_verification_must_remain_synchronous_at_register_and_get(self):
        class AsyncEventConnector(CompleteConnector):
            async def verify_event(self, headers, body):
                return None

        with self.assertRaisesRegex(TypeError, "verify_event"):
            ConnectorRegistry().register(AsyncEventConnector())

        class AsyncCallableVerifier:
            async def __call__(self, headers, body):
                return None

        class AsyncCallableEventConnector(CompleteConnector):
            verify_event = AsyncCallableVerifier()

        with self.assertRaisesRegex(TypeError, "verify_event"):
            ConnectorRegistry().register(AsyncCallableEventConnector())

        class MutableEventConnector(CompleteConnector):
            def verify_event(self, headers, body):
                return None

        connector = MutableEventConnector()
        registry = ConnectorRegistry()
        registry.register(connector)

        async def async_verify(headers, body):
            return None

        connector.verify_event = async_verify
        with self.assertRaises(ConnectorUnavailable):
            registry.get_event(Provider.PDD)


class OfficialApiClientTests(unittest.IsolatedAsyncioTestCase):
    host = "api.contract.invalid"

    async def _request(
        self,
        handler,
        *,
        url: str | None = None,
        method: str = "GET",
        max_response_bytes: int = 4096,
        follow_same_host_redirect: bool = False,
        headers=None,
        params=None,
        json=None,
    ):
        transport = httpx.MockTransport(handler)
        async with OfficialApiClient(
            allowed_hosts=frozenset({self.host}),
            transport=transport,
            max_response_bytes=max_response_bytes,
        ) as client:
            return await client.request_json(
                method,
                url or f"https://{self.host}/resource",
                follow_same_host_redirect=follow_same_host_redirect,
                headers=headers,
                params=params,
                json=json,
            )

    async def test_client_uses_fixed_timeout_disables_redirects_and_environment(self):
        with patch(
            "integrations.connectors.http.httpx.AsyncClient",
            wraps=httpx.AsyncClient,
        ) as constructor:
            client = OfficialApiClient(
                allowed_hosts=frozenset({self.host}),
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"ok": True})
                ),
            )
            try:
                kwargs = constructor.call_args.kwargs
                self.assertFalse(kwargs["follow_redirects"])
                self.assertFalse(kwargs["trust_env"])
                self.assertEqual(kwargs["timeout"].connect, 10.0)
                self.assertEqual(kwargs["timeout"].read, 30.0)
                self.assertEqual(kwargs["timeout"].write, 30.0)
                self.assertEqual(kwargs["timeout"].pool, 30.0)
            finally:
                await client.aclose()

    async def test_host_allowlist_must_be_nonempty_exact_lowercase_dns_frozenset(self):
        invalid_host_sets = (
            set([self.host]),
            frozenset(),
            frozenset({"API.contract.invalid"}),
            frozenset({"api.contract.invalid."}),
            frozenset({"*.contract.invalid"}),
            frozenset({"127.0.0.1"}),
            frozenset({"127.1"}),
            frozenset({"0177.0.0.1"}),
            frozenset({"0x7f.0.0.1"}),
            frozenset({"0x7f.01"}),
            frozenset({"localhost"}),
        )
        for allowed_hosts in invalid_host_sets:
            with self.subTest(allowed_hosts=allowed_hosts):
                with self.assertRaises((TypeError, ValueError)):
                    OfficialApiClient(
                        allowed_hosts=allowed_hosts,
                        transport=httpx.MockTransport(
                            lambda request: httpx.Response(200, json={})
                        ),
                    )

    async def test_rejects_unsafe_url_before_transport(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"unexpected": True})

        invalid_urls = (
            f"http://{self.host}/resource",
            "https://other.contract.invalid/resource",
            f"https://user:password@{self.host}/resource",
            f"https://{self.host}/resource#fragment",
            f"https://{self.host}\\@other.contract.invalid/resource",
            f"https://{self.host}./resource",
            f"https://{self.host}:444/resource",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(InvalidPlatformResponse):
                    await self._request(handler, url=url)
        self.assertEqual(calls, [])

    async def test_accepts_explicit_https_port_443_and_returns_json(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"ok": True})

        result = await self._request(
            handler,
            url=f"https://{self.host}:443/resource",
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(requests[0].content, b"")

    async def test_rejects_authority_and_hop_by_hop_headers_before_transport(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"unexpected": True})

        forbidden_headers = (
            {"Host": "other.contract.invalid"},
            {":authority": "other.contract.invalid"},
            {"Connection": "keep-alive"},
            {"Keep-Alive": "timeout=5"},
            {"Proxy-Authenticate": "sentinel"},
            {"Proxy-Authorization": "sentinel"},
            {"Proxy-Connection": "keep-alive"},
            {"TE": "trailers"},
            {"Trailer": "X-Sentinel"},
            {"Transfer-Encoding": "chunked"},
            {"Upgrade": "h2c"},
            {"Content-Length": "0"},
            {"Accept-Encoding": "br"},
        )
        for headers in forbidden_headers:
            with self.subTest(headers=tuple(headers)):
                with self.assertRaises(InvalidPlatformResponse):
                    await self._request(
                        handler,
                        method="POST",
                        headers=headers,
                        json={"safe": True},
                    )
        self.assertEqual(calls, [])

    async def test_redirect_is_rejected_unless_explicit_and_same_host(self):
        def disabled_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"Location": "/second"})

        with self.assertRaises(InvalidPlatformResponse):
            await self._request(disabled_handler)

        with self.assertRaises(InvalidPlatformResponse):
            await self._request(
                disabled_handler,
                follow_same_host_redirect=True,
                url=f"https://{self.host}/first",
            )

        calls = []

        def same_host_handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if request.url.path == "/first":
                return httpx.Response(302, headers={"Location": "/second"})
            return httpx.Response(200, json={"ok": True})

        result = await self._request(
            same_host_handler,
            follow_same_host_redirect=True,
            url=f"https://{self.host}/first",
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 2)

    async def test_redirect_to_other_allowed_host_and_second_redirect_are_rejected(self):
        other = "api-two.contract.invalid"

        def cross_host(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                307,
                headers={"Location": f"https://{other}/resource"},
            )

        transport = httpx.MockTransport(cross_host)
        async with OfficialApiClient(
            allowed_hosts=frozenset({self.host, other}),
            transport=transport,
        ) as client:
            with self.assertRaises(InvalidPlatformResponse):
                await client.request_json(
                    "GET",
                    f"https://{self.host}/resource",
                    follow_same_host_redirect=True,
                )

        calls = 0

        def redirect_loop(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(307, headers={"Location": "/again"})

        with self.assertRaises(InvalidPlatformResponse):
            await self._request(
                redirect_loop,
                follow_same_host_redirect=True,
            )
        self.assertEqual(calls, 2)

    async def test_non_safe_method_follows_only_307_or_308(self):
        with self.assertRaises(InvalidPlatformResponse):
            await self._request(
                lambda request: httpx.Response(302, headers={"Location": "/next"}),
                method="POST",
                follow_same_host_redirect=True,
                json={"safe": True},
            )

        methods = []

        def handler(request: httpx.Request) -> httpx.Response:
            methods.append(request.method)
            if len(methods) == 1:
                return httpx.Response(307, headers={"Location": "/next"})
            return httpx.Response(200, json={"ok": True})

        result = await self._request(
            handler,
            method="POST",
            follow_same_host_redirect=True,
            json={"safe": True},
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(methods, ["POST", "POST"])

    async def test_response_limit_applies_after_decompression(self):
        decoded = b'{"value":"' + (b"x" * 200) + b'"}'
        compressed = gzip.compress(decoded)
        self.assertLess(len(compressed), 100)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=httpx.ByteStream(compressed),
                headers={"Content-Encoding": "gzip"},
            )

        with self.assertRaises(InvalidPlatformResponse):
            await self._request(handler, max_response_bytes=100)

        small_decoded = b'{"ok":true}'
        result = await self._request(
            lambda request: httpx.Response(
                200,
                stream=_ChunkedAsyncStream(gzip.compress(small_decoded)),
                headers={"Content-Encoding": "gzip"},
            ),
            max_response_bytes=len(small_decoded),
        )
        self.assertEqual(result, {"ok": True})

    async def test_malformed_or_unsupported_content_encoding_is_not_retryable(self):
        cases = (
            (b"not-a-gzip-stream", "gzip"),
            (b'{"ok":true}', "br"),
            (gzip.compress(b'{"ok":true}'), "gzip, identity"),
            (gzip.compress(b'{"ok":true}')[:-3], "gzip"),
            (
                gzip.compress(b'{"first":true}')
                + gzip.compress(b'{"second":true}'),
                "gzip",
            ),
        )
        for body, content_encoding in cases:
            with self.subTest(content_encoding=content_encoding):
                with self.assertRaises(InvalidPlatformResponse):
                    await self._request(
                        lambda request, body=body, encoding=content_encoding: (
                            httpx.Response(
                                200,
                                stream=httpx.ByteStream(body),
                                headers={"Content-Encoding": encoding},
                            )
                        )
                    )

    async def test_outbound_json_is_strict_and_never_emits_on_local_failure(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"unexpected": True})

        cycle = []
        cycle.append(cycle)
        invalid_payloads = (
            {"value": math.nan},
            {"value": math.inf},
            {"value": Decimal("1.25")},
            {"value": object()},
            {"value": "invalid-surrogate-\ud800"},
            {"value": cycle},
        )
        for payload in invalid_payloads:
            with self.subTest(value_type=type(payload["value"]).__name__):
                with self.assertRaises(InvalidPlatformResponse):
                    await self._request(
                        handler,
                        method="POST",
                        json=payload,
                    )
        self.assertEqual(calls, [])

    async def test_valid_outbound_json_is_encoded_once_without_header_override(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"ok": True})

        result = await self._request(
            handler,
            method="POST",
            headers={"Authorization": "safe-test-token"},
            json={"items": [1, 2.5, True, None], "name": "测试"},
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            json_module.loads(requests[0].content),
            {"items": [1, 2.5, True, None], "name": "测试"},
        )
        self.assertEqual(requests[0].headers["Content-Type"], "application/json")
        self.assertEqual(requests[0].headers["Accept-Encoding"], "gzip")

    async def test_json_is_strict_and_all_numbers_are_finite(self):
        invalid_bodies = (
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":1e999}',
            b'{"duplicate":1,"duplicate":2}',
            b'{"unterminated":',
            b"\xff",
            (b"[" * 1100) + b"0" + (b"]" * 1100),
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                with self.assertRaises(InvalidPlatformResponse):
                    await self._request(
                        lambda request, body=body: httpx.Response(200, content=body)
                    )

        oversized_integer = b'{"value":' + (b"9" * 5000) + b"}"
        with self.assertRaises(InvalidPlatformResponse):
            await self._request(
                lambda request: httpx.Response(200, content=oversized_integer),
                max_response_bytes=10_000,
            )

    async def test_http_and_transport_failures_map_to_safe_typed_errors(self):
        cases = (
            (401, AuthenticationFailed),
            (403, PermissionDenied),
            (429, RateLimited),
            (408, TransientPlatformError),
            (500, TransientPlatformError),
            (400, InvalidPlatformResponse),
        )
        for status_code, expected in cases:
            with self.subTest(status_code=status_code):
                with self.assertRaises(expected) as raised:
                    await self._request(
                        lambda request, status_code=status_code: httpx.Response(
                            status_code,
                            content=b'sensitive-response-body',
                            headers={"Retry-After": "7.5"},
                        )
                    )
                self.assertNotIn("sensitive-response-body", str(raised.exception))
                if status_code == 429:
                    self.assertEqual(raised.exception.retry_after_seconds, 7.5)

        def network_failure(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                "network-exception-secret",
                request=request,
            )

        with self.assertRaises(TransientPlatformError) as raised:
            await self._request(network_failure)
        self.assertNotIn("network-exception-secret", str(raised.exception))

    async def test_logs_never_include_url_query_headers_body_or_exception_text(self):
        sentinels = (
            "secret-path-marker",
            "secret-query-marker",
            "secret-header-marker",
            "secret-body-marker",
            "secret-exception-marker",
        )

        logger = logging.getLogger("integrations.connectors.http")
        def success_handler(request: httpx.Request) -> httpx.Response:
            logging.getLogger("httpcore.connection").debug(
                "dependency exception=%s",
                sentinels[-1],
            )
            return httpx.Response(200, json={"ok": True})

        with self.assertLogs(level="DEBUG") as captured:
            result = await self._request(
                success_handler,
                url=(
                    f"https://{self.host}/{sentinels[0]}"
                    f"?token={sentinels[1]}"
                ),
                headers={"Authorization": sentinels[2]},
                json={"secret": sentinels[3]},
            )
        self.assertEqual(result, {"ok": True})
        rendered = "\n".join(captured.output)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, rendered)

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(sentinels[-1], request=request)

        with self.assertLogs(logger, level="INFO") as captured_failure:
            with self.assertRaises(TransientPlatformError):
                await self._request(
                    handler,
                    url=(
                        f"https://{self.host}/{sentinels[0]}"
                        f"?token={sentinels[1]}"
                    ),
                    headers={"Authorization": sentinels[2]},
                    json={"secret": sentinels[3]},
                )
        rendered = "\n".join(captured_failure.output)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, rendered)


if __name__ == "__main__":
    unittest.main()
