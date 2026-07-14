"""Shared connector seams; provider implementations are deliberately separate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from integrations.types import (
    AccountIdentity,
    CapabilityReport,
    ConnectionContext,
    FetchPage,
    ResourceType,
    RevokeResult,
    TimeWindow,
    TokenBundle,
    VerifiedEvent,
    Provider,
)


class ConnectorError(RuntimeError):
    """Provider-neutral failure that never embeds response or request data."""

    code = "connector_error"
    safe_message = "Connector request failed"
    retryable = False

    def __init__(
        self,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(self.safe_message)


class RateLimited(ConnectorError):
    code = "rate_limited"
    safe_message = "Connector request was rate limited"
    retryable = True


class AuthenticationFailed(ConnectorError):
    code = "authentication_failed"
    safe_message = "Connector authentication failed"


class PermissionDenied(ConnectorError):
    code = "permission_denied"
    safe_message = "Connector permission was denied"


class TransientPlatformError(ConnectorError):
    code = "transient_platform_error"
    safe_message = "Connector platform is temporarily unavailable"
    retryable = True


class InvalidPlatformResponse(ConnectorError):
    code = "invalid_platform_response"
    safe_message = "Connector platform returned an invalid response"


@runtime_checkable
class EcommerceConnector(Protocol):
    provider: Provider

    def authorization_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> TokenBundle: ...

    async def refresh_tokens(self, tokens: TokenBundle) -> TokenBundle: ...

    async def discover_accounts(
        self, tokens: TokenBundle
    ) -> list[AccountIdentity]: ...

    async def probe_capabilities(
        self, connection: ConnectionContext
    ) -> CapabilityReport: ...

    async def fetch_page(
        self,
        *,
        connection: ConnectionContext,
        resource: ResourceType,
        window: TimeWindow | None,
        cursor: str | None,
    ) -> FetchPage: ...

    async def revoke(self, connection: ConnectionContext) -> RevokeResult: ...


@runtime_checkable
class EventCapableConnector(Protocol):
    provider: Provider

    def verify_event(
        self,
        headers: Mapping[str, str],
        body: bytes,
    ) -> VerifiedEvent: ...


__all__ = [
    "AuthenticationFailed",
    "ConnectorError",
    "EcommerceConnector",
    "EventCapableConnector",
    "InvalidPlatformResponse",
    "PermissionDenied",
    "RateLimited",
    "TransientPlatformError",
]
