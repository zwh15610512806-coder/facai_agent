"""Contract tests for the safe OpenAI Images-compatible Canvas adapter."""
from __future__ import annotations

import asyncio
import base64
import json
import unittest


class _FakeSafeClient:
    def __init__(self, response) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        return self.response


class OpenAIImagesAdapterTests(unittest.TestCase):
    @staticmethod
    def _capabilities(**overrides):
        from services.canvas.provider_schemas import ModelCapabilities

        value = dict(
            text_to_image=True, image_to_image=False, mask_edit=False,
            allowed_ratios=(), allowed_sizes=(), min_width=512, max_width=2048,
            min_height=512, max_height=2048, max_quantity=1,
            max_reference_images=0, reference_transfer="none", protocol="sync",
            supports_cancel=False, supports_idempotency=True,
            supports_idempotency_lookup=False, concurrency_limit=1, price_metadata=None,
        )
        value.update(overrides)
        return ModelCapabilities(**value)

    def test_text_to_image_uses_safe_relative_endpoint_and_normalizes_b64_or_url_results(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderGenerationRequest, ProviderRuntime
        from services.canvas.providers.openai_images import OpenAIImagesAdapter

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        client = _FakeSafeClient(NetworkResponse(
            200, {"content-type": "application/json"},
            json.dumps({"data": [{"b64_json": encoded}]}).encode(),
        ))
        adapter = OpenAIImagesAdapter(
            model_id="gpt-image-compatible",
            capabilities=self._capabilities(),
        )
        result = asyncio.run(adapter.submit(
            ProviderGenerationRequest(prompt="clean studio", size="1024x1024", upstream_idempotency_key="canvas-key"),
            ProviderRuntime(api_key="secret", transport=client),
        ))
        self.assertEqual("completed", result.status)
        self.assertEqual(b"image-bytes", result.image.data)
        request = client.requests[0]
        self.assertEqual("/images/generations", request["endpoint"])
        self.assertEqual("Bearer secret", request["headers"]["Authorization"])
        self.assertEqual("gpt-image-compatible", request["json_body"]["model"])
        self.assertNotIn("image", request["json_body"])

    def test_capability_and_response_drift_fail_with_safe_errors(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderError, ProviderGenerationRequest, ProviderRuntime
        from services.canvas.providers.openai_images import OpenAIImagesAdapter

        adapter = OpenAIImagesAdapter(model_id="model", capabilities=self._capabilities())
        with self.assertRaises(ProviderError) as unsupported:
            asyncio.run(adapter.submit(
                ProviderGenerationRequest(prompt="x", size="1024x1024", reference_images=(b"product",)),
                ProviderRuntime(api_key="secret", transport=_FakeSafeClient(NetworkResponse(200, {}, b"{}"))),
            ))
        self.assertEqual("provider_reference_unsupported", unsupported.exception.code)

        malformed = _FakeSafeClient(NetworkResponse(200, {"content-type": "application/json"}, b'{"data":[]}'))
        with self.assertRaises(ProviderError) as drift:
            asyncio.run(adapter.submit(
                ProviderGenerationRequest(prompt="x", size="1024x1024"),
                ProviderRuntime(api_key="secret", transport=malformed),
            ))
        self.assertEqual("provider_response_invalid", drift.exception.code)
        self.assertNotIn("secret", str(drift.exception).lower())

    def test_registry_constructs_the_dynamic_adapter_type(self) -> None:
        from services.canvas.providers.registry import provider_registry

        adapter = provider_registry.build(
            "openai_images", model_id="dynamic-model", capabilities=self._capabilities()
        )
        self.assertEqual("openai_images", adapter.adapter_type)
        self.assertEqual("dynamic-model", adapter.model_id)


if __name__ == "__main__":
    unittest.main()
