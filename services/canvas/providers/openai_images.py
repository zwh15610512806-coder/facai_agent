"""Safe OpenAI Images-compatible adapter for approved custom origins."""
from __future__ import annotations

import base64
import binascii
import json
import re
from urllib.parse import urlsplit

from services.canvas.provider_network import ProviderNetworkError
from services.canvas.provider_schemas import (
    ControlledImageBytes,
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


_SIZE = re.compile(r"^[1-9][0-9]{2,4}x[1-9][0-9]{2,4}$")


class OpenAIImagesAdapter:
    adapter_type = "openai_images"

    def __init__(self, *, model_id: str, capabilities: ModelCapabilities) -> None:
        if not isinstance(model_id, str) or not model_id or len(model_id) > 200:
            raise ValueError("OpenAI-compatible model ID is invalid")
        self.model_id = model_id
        self.capabilities = capabilities

    def validate_request(
        self,
        request: ProviderGenerationRequest,
        capabilities: ModelCapabilities,
    ) -> None:
        if not isinstance(request.prompt, str) or not request.prompt.strip() or len(request.prompt) > 8_000:
            raise ProviderRequestValidationError("provider_prompt_invalid", "A valid background prompt is required")
        if not isinstance(request.size, str) or _SIZE.fullmatch(request.size.strip()) is None:
            raise ProviderRequestValidationError("provider_size_invalid", "A supported image size is required")
        if request.quantity != 1 or request.quantity > capabilities.max_quantity:
            raise ProviderRequestValidationError("provider_quantity_unsupported", "This model generates one image per request")
        if request.reference_images:
            if not capabilities.image_to_image or capabilities.max_reference_images <= 0:
                raise ProviderRequestValidationError(
                    "provider_reference_unsupported",
                    "This model cannot accept protected product references",
                )
            raise ProviderRequestValidationError(
                "provider_reference_protected",
                "Protected product references require an explicitly approved edit workflow",
            )
        if request.upstream_idempotency_key is not None and not capabilities.supports_idempotency:
            raise ProviderRequestValidationError("provider_idempotency_unsupported", "This model does not support upstream idempotency")

    async def submit(self, request: ProviderGenerationRequest, runtime: ProviderRuntime) -> ProviderSubmission:
        self.validate_request(request, self.capabilities)
        if not runtime.api_key:
            raise ProviderError("provider_missing_credential", "Image Provider credential is not configured")
        headers = {"Authorization": f"Bearer {runtime.api_key}", "Accept": "application/json"}
        if request.upstream_idempotency_key is not None:
            headers["Idempotency-Key"] = request.upstream_idempotency_key
        payload = {
            "model": self.model_id,
            "prompt": request.prompt.strip(),
            "n": 1,
            "size": request.size.strip(),
            "response_format": "b64_json",
        }
        try:
            response = await runtime.transport.request(
                method="POST",
                endpoint="/images/generations",
                headers=headers,
                json_body=payload,
            )
        except ProviderNetworkError:
            raise ProviderError("provider_network_failed", "Image Provider request could not be completed", retryable=True) from None
        except Exception:
            raise ProviderError("provider_network_failed", "Image Provider request could not be completed", retryable=True) from None
        if response.status_code < 200 or response.status_code >= 300:
            if response.status_code in {401, 403}:
                raise ProviderError("provider_authentication_failed", "Image Provider authentication failed", status_code=response.status_code)
            if response.status_code == 429:
                raise ProviderError("provider_rate_limited", "Image Provider is temporarily rate limited", retryable=True, status_code=429)
            raise ProviderError("provider_upstream_failed", "Image Provider returned an unsuccessful response", retryable=response.status_code >= 500, status_code=response.status_code)
        if (response.header("content-type") or "").split(";", 1)[0].strip().lower() != "application/json":
            raise ProviderError("provider_response_invalid", "Image Provider returned an invalid response")
        try:
            document = json.loads(response.body.decode("utf-8"))
            data = document["data"] if isinstance(document, dict) else None
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
                raise ValueError
            item = data[0]
            if isinstance(item.get("b64_json"), str):
                from config import CANVAS_REMOTE_IMAGE_MAX_BYTES

                decoded = base64.b64decode(item["b64_json"], validate=True)
                if not decoded or len(decoded) > CANVAS_REMOTE_IMAGE_MAX_BYTES:
                    raise ValueError
                image = ControlledImageBytes(data=decoded)
            elif isinstance(item.get("url"), str):
                parsed = urlsplit(item["url"])
                if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError
                image = ControlledRemoteImage(remote_url=item["url"])
            else:
                raise ValueError
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, binascii.Error):
            raise ProviderError("provider_response_invalid", "Image Provider returned an invalid response") from None
        return ProviderSubmission(status="completed", image=image)

    async def poll(self, submission: ProviderSubmission, runtime: ProviderRuntime) -> ProviderPollResult:
        return ProviderPollResult(kind="unsupported")

    async def cancel(self, submission: ProviderSubmission, runtime: ProviderRuntime) -> ProviderCancelResult:
        return ProviderCancelResult(kind="unsupported")

    async def recover_by_idempotency_key(self, upstream_key: str, runtime: ProviderRuntime) -> ProviderRecoveryResult:
        return ProviderRecoveryUnsupported()


__all__ = ["OpenAIImagesAdapter"]
