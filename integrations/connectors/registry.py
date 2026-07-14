"""Explicit connector registry with no production providers registered by default."""

from __future__ import annotations

import inspect

from integrations.connectors.base import EcommerceConnector, EventCapableConnector
from integrations.types import Provider


_REQUIRED_ASYNC_METHODS = (
    "exchange_code",
    "refresh_tokens",
    "discover_accounts",
    "probe_capabilities",
    "fetch_page",
    "revoke",
)
_MISSING = object()


def _is_async_callable(value: object) -> bool:
    return inspect.iscoroutinefunction(value) or inspect.iscoroutinefunction(
        getattr(value, "__call__", None)
    )


class ConnectorUnavailable(LookupError):
    """Raised without provider or configuration values when no connector exists."""


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[Provider, EcommerceConnector] = {}

    def register(self, connector: EcommerceConnector) -> None:
        provider = getattr(connector, "provider", None)
        if not isinstance(provider, Provider) or not isinstance(
            connector, EcommerceConnector
        ):
            raise TypeError("Connector provider must be a Provider")
        authorization_url = getattr(connector, "authorization_url", None)
        if not callable(authorization_url) or _is_async_callable(
            authorization_url
        ):
            raise TypeError("Connector authorization_url must be synchronous")
        for method_name in _REQUIRED_ASYNC_METHODS:
            method = getattr(connector, method_name, None)
            if not callable(method) or not _is_async_callable(method):
                raise TypeError(
                    f"Connector {method_name} method must be async"
                )
        verify_event = getattr(connector, "verify_event", _MISSING)
        if verify_event is not _MISSING and (
            not callable(verify_event)
            or _is_async_callable(verify_event)
        ):
            raise TypeError("Connector verify_event must be synchronous")
        if provider in self._connectors:
            raise ValueError("Connector provider is already registered")
        self._connectors[provider] = connector

    def get(self, provider: Provider) -> EcommerceConnector:
        if not isinstance(provider, Provider):
            raise TypeError("Connector lookup requires a Provider")
        try:
            return self._connectors[provider]
        except KeyError:
            raise ConnectorUnavailable("Connector is unavailable") from None

    def get_event(self, provider: Provider) -> EventCapableConnector:
        connector = self.get(provider)
        verify_event = getattr(connector, "verify_event", None)
        if (
            not isinstance(connector, EventCapableConnector)
            or not callable(verify_event)
            or _is_async_callable(verify_event)
        ):
            raise ConnectorUnavailable("Event handler is unavailable")
        return connector

    def clear(self) -> None:
        self._connectors.clear()


connector_registry = ConnectorRegistry()


__all__ = ["ConnectorRegistry", "ConnectorUnavailable", "connector_registry"]
