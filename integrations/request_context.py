"""Trusted-proxy-aware request network context parsing."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

from starlette.requests import Request


_TRUSTED_PROXY_ERROR = "Trusted proxy forwarding configuration is invalid"


class RequestContextConfigurationError(ValueError):
    """Raised without forwarding values when transport facts are unusable."""


@dataclass(frozen=True, slots=True)
class RequestNetworkContext:
    client_ip: IPv4Address | IPv6Address = field(repr=False)
    effective_scheme: str
    peer_is_trusted_proxy: bool


def _address_is_trusted(
    address: IPv4Address | IPv6Address,
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...],
) -> bool:
    return any(
        address.version == network.version and address in network
        for network in trusted_proxy_networks
    )


def _trusted_proxy_failure() -> RequestContextConfigurationError:
    return RequestContextConfigurationError(_TRUSTED_PROXY_ERROR)


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


def resolve_request_context(
    request: Request,
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...],
) -> RequestNetworkContext:
    client = request.scope.get("client")
    raw_scheme = request.scope.get("scheme")
    try:
        if not isinstance(client, (tuple, list)) or len(client) != 2:
            raise ValueError
        peer = ipaddress.ip_address(client[0])
    except (TypeError, ValueError):
        raise RequestContextConfigurationError("Request transport context is invalid") from None
    if raw_scheme not in {"http", "https"}:
        raise RequestContextConfigurationError("Request transport context is invalid")

    peer_is_trusted = _address_is_trusted(peer, trusted_proxy_networks)
    if not peer_is_trusted:
        return RequestNetworkContext(peer, raw_scheme, False)

    forwarded = _forwarded_addresses(request)
    resolved_client = next(
        (
            address
            for address in reversed([*forwarded, peer])
            if not _address_is_trusted(address, trusted_proxy_networks)
        ),
        forwarded[0],
    )
    effective_scheme = "https" if raw_scheme == "https" else _forwarded_scheme(request)
    return RequestNetworkContext(resolved_client, effective_scheme, True)


__all__ = [
    "RequestContextConfigurationError",
    "RequestNetworkContext",
    "resolve_request_context",
]
