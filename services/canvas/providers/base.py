"""Common image Provider adapter protocol."""
from __future__ import annotations

from typing import Protocol

from services.canvas.provider_schemas import (
    ModelCapabilities,
    ProviderCancelResult,
    ProviderGenerationRequest,
    ProviderPollResult,
    ProviderRecoveryResult,
    ProviderRuntime,
    ProviderSubmission,
)


class ImageProviderAdapter(Protocol):
    adapter_type: str
    capabilities: ModelCapabilities

    def validate_request(
        self,
        request: ProviderGenerationRequest,
        capabilities: ModelCapabilities,
    ) -> None: ...

    async def submit(
        self,
        request: ProviderGenerationRequest,
        runtime: ProviderRuntime,
    ) -> ProviderSubmission: ...

    async def poll(
        self,
        submission: ProviderSubmission,
        runtime: ProviderRuntime,
    ) -> ProviderPollResult: ...

    async def cancel(
        self,
        submission: ProviderSubmission,
        runtime: ProviderRuntime,
    ) -> ProviderCancelResult: ...

    async def recover_by_idempotency_key(
        self,
        upstream_key: str,
        runtime: ProviderRuntime,
    ) -> ProviderRecoveryResult: ...


__all__ = ["ImageProviderAdapter"]
