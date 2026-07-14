"""Provider-neutral connector contracts and an intentionally empty registry."""

from integrations.connectors.base import (
    AuthenticationFailed,
    ConnectorError,
    EcommerceConnector,
    EventCapableConnector,
    InvalidPlatformResponse,
    PermissionDenied,
    RateLimited,
    TransientPlatformError,
)
from integrations.connectors.http import OfficialApiClient
from integrations.connectors.registry import (
    ConnectorRegistry,
    ConnectorUnavailable,
    connector_registry,
)

__all__ = [
    "AuthenticationFailed",
    "ConnectorError",
    "ConnectorRegistry",
    "ConnectorUnavailable",
    "EcommerceConnector",
    "EventCapableConnector",
    "InvalidPlatformResponse",
    "OfficialApiClient",
    "PermissionDenied",
    "RateLimited",
    "TransientPlatformError",
    "connector_registry",
]
