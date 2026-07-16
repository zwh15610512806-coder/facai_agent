"""Policy contracts for third-party Canvas Provider network access."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch


class ProviderNetworkPolicyTests(unittest.TestCase):
    @staticmethod
    def _policy(**overrides):
        from services.canvas.provider_network import ProviderNetworkPolicy

        values = {
            "allowed_hosts": ("api.vendor.example",),
            "private_allowed_hosts": (),
            "private_allowed_ips": (),
            "allow_insecure_http": False,
            "connect_timeout_seconds": 7,
            "total_timeout_seconds": 45,
            "max_json_bytes": 4096,
        }
        values.update(overrides)
        return ProviderNetworkPolicy(**values)

    def test_public_https_requires_an_exact_administrator_host_and_relative_endpoint(self) -> None:
        from services.canvas.provider_network import (
            ProviderNetworkError,
            validate_provider_base_url,
            validate_relative_endpoint,
        )

        policy = self._policy()
        origin = validate_provider_base_url("https://api.vendor.example/v1", policy=policy)
        self.assertEqual("https", origin.scheme)
        self.assertEqual("api.vendor.example", origin.hostname)
        self.assertEqual("/v1", origin.path_prefix)
        self.assertEqual("/images/generations", validate_relative_endpoint("/images/generations"))
        for value in (
            "http://api.vendor.example/v1",
            "https://other.vendor.example/v1",
            "https://api.vendor.example/v1?token=secret",
            "https://api.vendor.example/v1#fragment",
            "https://user:pass@api.vendor.example/v1",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ProviderNetworkError):
                    validate_provider_base_url(value, policy=policy)
        for value in ("https://api.vendor.example/x", "../images", "images", "/a/../b"):
            with self.subTest(value=value):
                with self.assertRaises(ProviderNetworkError):
                    validate_relative_endpoint(value)

    def test_private_http_needs_flag_exact_host_and_exact_resolved_ip(self) -> None:
        from services.canvas.provider_network import (
            ProviderNetworkError,
            resolve_pinned_target,
            validate_provider_base_url,
        )

        missing_controls = self._policy(
            private_allowed_hosts=("images.internal.example",),
            private_allowed_ips=("10.20.0.8",),
        )
        with self.assertRaises(ProviderNetworkError):
            validate_provider_base_url("http://images.internal.example/v1", policy=missing_controls)

        policy = self._policy(
            private_allowed_hosts=("images.internal.example",),
            private_allowed_ips=("10.20.0.8",),
            allow_insecure_http=True,
        )
        origin = validate_provider_base_url("http://images.internal.example/v1", policy=policy)
        target = resolve_pinned_target(origin, resolver=lambda _host: ("10.20.0.8",), policy=policy)
        self.assertEqual("10.20.0.8", target.pinned_ip)
        for answer in (
            ("10.20.0.9",),
            ("10.20.0.8", "127.0.0.1"),
            ("169.254.169.254",),
            ("93.184.216.34",),
        ):
            with self.subTest(answer=answer):
                with self.assertRaises(ProviderNetworkError):
                    resolve_pinned_target(origin, resolver=lambda _host, answer=answer: answer, policy=policy)

        with self.assertRaises(ValueError):
            self._policy(connect_timeout_seconds=8, total_timeout_seconds=7)

    def test_pinned_transport_accepts_only_an_already_validated_private_http_pin(self) -> None:
        from services.canvas.provider_network import (
            PinnedEndpoint,
            PinnedHttpCoreTransport,
            ProviderNetworkError,
        )

        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200
            headers = [(b"content-type", b"application/json")]

            async def aiter_stream(self):
                yield b"{}"

            async def aclose(self):
                return None

        class FakePool:
            def __init__(self, **kwargs):
                captured["pool"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def request(self, method, url, **kwargs):
                captured.update(method=method, url=url, request=kwargs)
                return FakeResponse()

        url = "http://images.internal.example/v1/images"
        endpoint = PinnedEndpoint(
            url=url,
            hostname="images.internal.example",
            port=80,
            pinned_ip="10.20.0.8",
            private_http=True,
        )
        with patch(
            "services.canvas.provider_network.httpcore.AsyncConnectionPool",
            FakePool,
        ):
            response = asyncio.run(
                PinnedHttpCoreTransport().request(
                    method="POST",
                    url=url,
                    body=b"{}",
                    max_bytes=32,
                    pinned_endpoint=endpoint,
                )
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(url, captured["url"])
        headers = dict(captured["request"]["headers"])
        self.assertEqual(b"images.internal.example", headers[b"Host"])

        loopback = PinnedEndpoint(
            url=url,
            hostname="images.internal.example",
            port=80,
            pinned_ip="127.0.0.1",
            private_http=True,
        )
        with self.assertRaises(ProviderNetworkError):
            asyncio.run(
                PinnedHttpCoreTransport().request(
                    method="GET",
                    url=url,
                    max_bytes=32,
                    pinned_endpoint=loopback,
                )
            )

    def test_public_dns_rebinding_mixed_answers_and_ambiguous_ip_origins_fail_closed(self) -> None:
        from services.canvas.provider_network import (
            ProviderNetworkError,
            resolve_pinned_target,
            validate_provider_base_url,
        )

        policy = self._policy()
        origin = validate_provider_base_url("https://api.vendor.example", policy=policy)
        with self.assertRaises(ProviderNetworkError):
            resolve_pinned_target(
                origin,
                resolver=lambda _host: ("93.184.216.34", "10.0.0.8"),
                policy=policy,
            )
        for value in ("https://127.0.0.1", "https://0x7f000001", "https://2130706433"):
            with self.subTest(value=value):
                with self.assertRaises(ProviderNetworkError):
                    validate_provider_base_url(value, policy=policy)

    def test_safe_client_uses_only_relative_paths_pins_dns_and_caps_json_before_transport(self) -> None:
        from services.canvas.provider_network import (
            NetworkResponse,
            ProviderNetworkError,
            SafeProviderHttpClient,
            validate_provider_base_url,
        )

        class FakeTransport:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []

            async def request(self, **kwargs):
                self.requests.append(kwargs)
                return NetworkResponse(200, {"content-type": "application/json"}, b"{}")

        policy = self._policy(max_json_bytes=24)
        origin = validate_provider_base_url("https://api.vendor.example/v1", policy=policy)
        transport = FakeTransport()
        client = SafeProviderHttpClient(
            origin=origin,
            policy=policy,
            resolver=lambda _host: ("93.184.216.34",),
            transport=transport,  # type: ignore[arg-type]
        )
        response = asyncio.run(client.request(
            method="POST",
            endpoint="/images",
            json_body={"prompt": "safe"},
        ))
        self.assertEqual(200, response.status_code)
        self.assertEqual("https://api.vendor.example/v1/images", transport.requests[0]["url"])
        pin = transport.requests[0]["pinned_endpoint"]
        self.assertEqual("93.184.216.34", pin.pinned_ip)
        self.assertNotIn("json_body", transport.requests[0])
        with self.assertRaises(ProviderNetworkError):
            asyncio.run(client.request(method="POST", endpoint="https://other.example/x"))
        with self.assertRaises(ProviderNetworkError):
            asyncio.run(client.request(
                method="POST", endpoint="/images", json_body={"prompt": "x" * 100}
            ))

    def test_safe_client_only_allows_encoded_controlled_query_fields(self) -> None:
        from services.canvas.provider_network import (
            NetworkResponse,
            ProviderNetworkError,
            SafeProviderHttpClient,
            validate_provider_base_url,
        )

        class FakeTransport:
            async def request(self, **kwargs):
                self.request = kwargs
                return NetworkResponse(200, {"content-type": "application/json"}, b"{}")

        policy = self._policy()
        origin = validate_provider_base_url("https://api.vendor.example/v1", policy=policy)
        transport = FakeTransport()
        client = SafeProviderHttpClient(
            origin=origin, policy=policy, resolver=lambda _host: ("93.184.216.34",),
            transport=transport,  # type: ignore[arg-type]
        )
        asyncio.run(client.request(method="GET", endpoint="/images", query={"key": "a value&more"}))
        self.assertEqual("https://api.vendor.example/v1/images?key=a+value%26more", transport.request["url"])
        for query in ({"bad key": "x"}, {"key": ""}, {"key": "x\r\ny"}):
            with self.subTest(query=query):
                with self.assertRaises(ProviderNetworkError):
                    asyncio.run(client.request(method="GET", endpoint="/images", query=query))


if __name__ == "__main__":
    unittest.main()
