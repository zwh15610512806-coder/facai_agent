import ipaddress
import unittest

from starlette.requests import Request

from integrations.request_context import (
    RequestContextConfigurationError,
    resolve_request_context,
)


def _request(*, client, scheme, headers=()):
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": scheme,
            "path": "/api/integrations/providers",
            "raw_path": b"/api/integrations/providers",
            "query_string": b"",
            "headers": list(headers),
            "client": client,
            "server": ("admin.example.test", 443),
        }
    )


class RequestContextTests(unittest.TestCase):
    def setUp(self):
        self.trusted = (ipaddress.ip_network("10.20.0.0/16"),)

    def test_untrusted_peer_ignores_forwarding_headers(self):
        request = _request(
            client=("198.51.100.10", 50000),
            scheme="http",
            headers=(
                (b"x-forwarded-for", b"203.0.113.90"),
                (b"x-forwarded-proto", b"https"),
            ),
        )

        context = resolve_request_context(request, self.trusted)

        self.assertEqual(context.client_ip, ipaddress.ip_address("198.51.100.10"))
        self.assertEqual(context.effective_scheme, "http")
        self.assertFalse(context.peer_is_trusted_proxy)

    def test_trusted_proxy_selects_first_untrusted_hop_from_the_right(self):
        request = _request(
            client=("10.20.0.5", 50000),
            scheme="http",
            headers=(
                (b"x-forwarded-for", b"198.51.100.20, 203.0.113.30, 10.20.0.7"),
                (b"x-forwarded-proto", b"https"),
            ),
        )

        context = resolve_request_context(request, self.trusted)

        self.assertEqual(context.client_ip, ipaddress.ip_address("203.0.113.30"))
        self.assertEqual(context.effective_scheme, "https")
        self.assertTrue(context.peer_is_trusted_proxy)

    def test_all_trusted_forwarded_hops_use_leftmost_address(self):
        request = _request(
            client=("10.20.0.5", 50000),
            scheme="https",
            headers=((b"x-forwarded-for", b"10.20.0.8, 10.20.0.9"),),
        )

        context = resolve_request_context(request, self.trusted)

        self.assertEqual(context.client_ip, ipaddress.ip_address("10.20.0.8"))
        self.assertEqual(context.effective_scheme, "https")

    def test_trusted_proxy_malformed_headers_fail_closed(self):
        for headers in (
            (),
            ((b"x-forwarded-for", b"not-an-ip"), (b"x-forwarded-proto", b"https")),
            ((b"x-forwarded-for", b"198.51.100.2"),),
            ((b"x-forwarded-for", b"198.51.100.2"), (b"x-forwarded-proto", b"https,http")),
        ):
            with self.subTest(headers=headers):
                request = _request(client=("10.20.0.5", 50000), scheme="http", headers=headers)
                with self.assertRaises(RequestContextConfigurationError):
                    resolve_request_context(request, self.trusted)


if __name__ == "__main__":
    unittest.main()
