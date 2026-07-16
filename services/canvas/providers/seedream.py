"""Built-in synchronous Seedream 5.0 Pro (full) background adapter."""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

from services.canvas.provider_network import ProviderNetworkError
from services.canvas.provider_schemas import (
    ControlledRemoteImage,
    ModelCapabilities,
    ProviderCancelResult,
    ProviderError,
    ProviderGenerationRequest,
    ProviderPollResult,
    ProviderRecoveryResult,
    ProviderRecoveryUnsupported,
    ProviderRequestValidationError,
    ProviderRuntime,
    ProviderSubmission,
)


_SIZE_PATTERN = re.compile(r"^(?P<width>[1-9][0-9]{2,4})x(?P<height>[1-9][0-9]{2,4})$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,500}$")
_MAX_PROVIDER_JSON_BYTES = 1_048_576


def resolve_seedream_api_key() -> str:
    """Return the official Ark credential before the legacy app alias."""

    return os.getenv("ARK_API_KEY", "").strip() or os.getenv("DOUBAO_API_KEY", "").strip()


class SeedreamAdapter:
    adapter_type = "seedream"
    MODEL_ID = "doubao-seedream-5-0-pro-260628"
    DISPLAY_NAME = "Seedream 5.0 Pro（完整版）"
    ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    CONFIG_VERSION = 1

    capabilities = ModelCapabilities(
        text_to_image=True,
        image_to_image=False,
        mask_edit=False,
        # The official-current G3 contract does not enumerate a stable size or
        # ratio catalog. Empty/None avoids advertising speculative UI choices;
        # submit still rejects malformed dimension strings.
        allowed_ratios=(),
        allowed_sizes=(),
        min_width=None,
        max_width=None,
        min_height=None,
        max_height=None,
        max_quantity=1,
        max_reference_images=0,
        reference_transfer="none",
        protocol="sync",
        supports_cancel=False,
        supports_idempotency=False,
        supports_idempotency_lookup=False,
        concurrency_limit=1,
        price_metadata=None,
    )

    def validate_request(
        self,
        request: ProviderGenerationRequest,
        capabilities: ModelCapabilities,
    ) -> None:
        prompt = request.prompt.strip() if isinstance(request.prompt, str) else ""
        if not prompt or len(prompt) > 8_000:
            raise ProviderRequestValidationError(
                "provider_prompt_invalid", "A valid background prompt is required"
            )
        if request.quantity != 1 or request.quantity > capabilities.max_quantity:
            raise ProviderRequestValidationError(
                "provider_quantity_unsupported", "This model generates one image per request"
            )
        if request.reference_images or capabilities.max_reference_images != 0:
            raise ProviderRequestValidationError(
                "provider_reference_unsupported",
                "The built-in background model does not accept product references",
            )
        if request.upstream_idempotency_key is not None:
            raise ProviderRequestValidationError(
                "provider_idempotency_unsupported",
                "The built-in background model does not support upstream idempotency",
            )
        match = _SIZE_PATTERN.fullmatch(request.size.strip()) if isinstance(request.size, str) else None
        if match is None:
            raise ProviderRequestValidationError(
                "provider_size_invalid", "A supported image size is required"
            )

    async def submit(
        self,
        request: ProviderGenerationRequest,
        runtime: ProviderRuntime,
    ) -> ProviderSubmission:
        self.validate_request(request, self.capabilities)
        if not runtime.api_key:
            raise ProviderError(
                "provider_missing_credential", "Seedream credential is not configured"
            )
        payload = {
            "model": self.MODEL_ID,
            "prompt": request.prompt.strip(),
            "size": request.size.strip(),
            "output_format": "png",
            "response_format": "url",
            "watermark": False,
        }
        try:
            response = await runtime.transport.request(
                method="POST",
                url=self.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {runtime.api_key}",
                    "Accept": "application/json",
                },
                json_body=payload,
                max_bytes=_MAX_PROVIDER_JSON_BYTES,
            )
        except ProviderError:
            raise
        except ProviderNetworkError:
            raise ProviderError(
                "provider_network_failed",
                "Seedream request could not be completed",
                retryable=True,
            ) from None
        except Exception:
            raise ProviderError(
                "provider_network_failed",
                "Seedream request could not be completed",
                retryable=True,
            ) from None

        if response.status_code < 200 or response.status_code >= 300:
            if response.status_code in {401, 403}:
                code = "provider_authentication_failed"
                message = "Seedream authentication failed"
                retryable = False
            elif response.status_code == 429:
                code = "provider_rate_limited"
                message = "Seedream is temporarily rate limited"
                retryable = True
            else:
                code = "provider_upstream_failed"
                message = "Seedream returned an unsuccessful response"
                retryable = response.status_code >= 500
            raise ProviderError(
                code,
                message,
                retryable=retryable,
                status_code=response.status_code,
            )
        content_type = (response.header("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ProviderError(
                "provider_response_invalid", "Seedream returned an invalid response"
            )
        try:
            document = json.loads(response.body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise ProviderError(
                "provider_response_invalid", "Seedream returned an invalid response"
            ) from None
        if not isinstance(document, dict):
            raise ProviderError(
                "provider_response_invalid", "Seedream returned an invalid response"
            )
        raw_data = document.get("data")
        has_top_level_error = isinstance(document.get("error"), (dict, str))
        has_item_error = (
            isinstance(raw_data, list)
            and len(raw_data) == 1
            and isinstance(raw_data[0], dict)
            and isinstance(raw_data[0].get("error"), (dict, str))
        )
        if has_top_level_error or has_item_error:
            raise ProviderError(
                "provider_generation_failed",
                "Seedream could not generate the requested image",
            )
        try:
            data = document["data"]
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
                raise ValueError
            remote_url = data[0]["url"]
            if not isinstance(remote_url, str) or len(remote_url) > 4096:
                raise ValueError
            parsed = urlsplit(remote_url)
            if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ProviderError(
                "provider_response_invalid", "Seedream returned an invalid response"
            ) from None
        raw_request_id = document.get("id")
        request_id = (
            raw_request_id
            if isinstance(raw_request_id, str) and _SAFE_REQUEST_ID.fullmatch(raw_request_id)
            else None
        )
        return ProviderSubmission(
            status="completed",
            request_id=request_id,
            image=ControlledRemoteImage(remote_url=remote_url),
        )

    async def poll(
        self,
        submission: ProviderSubmission,
        runtime: ProviderRuntime,
    ) -> ProviderPollResult:
        return ProviderPollResult(kind="unsupported")

    async def cancel(
        self,
        submission: ProviderSubmission,
        runtime: ProviderRuntime,
    ) -> ProviderCancelResult:
        return ProviderCancelResult(kind="unsupported")

    async def recover_by_idempotency_key(
        self,
        upstream_key: str,
        runtime: ProviderRuntime,
    ) -> ProviderRecoveryResult:
        return ProviderRecoveryUnsupported()


__all__ = ["SeedreamAdapter", "resolve_seedream_api_key"]
