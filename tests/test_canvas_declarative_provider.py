"""Security contracts for the restricted declarative HTTP Canvas adapter."""
from __future__ import annotations

import asyncio
import base64
import json
import unittest


class _FakeSafeClient:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


class DeclarativeHttpAdapterTests(unittest.TestCase):
    @staticmethod
    def _capabilities(**overrides):
        from services.canvas.provider_schemas import ModelCapabilities

        values = dict(
            text_to_image=True, image_to_image=False, mask_edit=False,
            allowed_ratios=(), allowed_sizes=(), min_width=512, max_width=2048,
            min_height=512, max_height=2048, max_quantity=4,
            max_reference_images=0, reference_transfer="none", protocol="both",
            supports_cancel=True, supports_idempotency=True,
            supports_idempotency_lookup=False, concurrency_limit=1, price_metadata=None,
        )
        values.update(overrides)
        return ModelCapabilities(**values)

    @staticmethod
    def _sync_config():
        return {
            "auth": {"type": "bearer"},
            "submit": {
                "method": "POST",
                "endpoint": "/v1/images/generate",
                "format": "json",
                "json": {
                    "model": "{{model_id}}",
                    "prompt": "{{prompt}}",
                    "width": "{{width}}",
                    "height": "{{height}}",
                    "n": "{{quantity}}",
                },
            },
            "result": {"mode": "sync", "imagePath": "data[0].b64_json", "imageType": "base64"},
        }

    def _adapter(self, config=None):
        from services.canvas.providers.declarative_http import DeclarativeHttpAdapter

        return DeclarativeHttpAdapter(
            model_id="vendor-image-pro",
            capabilities=self._capabilities(),
            configuration=config or self._sync_config(),
        )

    def test_json_submit_uses_only_fixed_relative_endpoint_and_controlled_bearer_auth(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderGenerationRequest, ProviderRuntime

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        client = _FakeSafeClient(NetworkResponse(
            200, {"content-type": "application/json"},
            json.dumps({"data": [{"b64_json": encoded}]}).encode("utf-8"),
        ))
        result = asyncio.run(self._adapter().submit(
            ProviderGenerationRequest(
                prompt="soft daylight", size="1024x768", quantity=2,
                upstream_idempotency_key="canvas-request-1",
            ),
            ProviderRuntime(api_key="secret-value", transport=client),
        ))
        self.assertEqual("completed", result.status)
        self.assertEqual(b"image-bytes", result.image.data)
        sent = client.requests[0]
        self.assertEqual("/v1/images/generate", sent["endpoint"])
        self.assertEqual("Bearer secret-value", sent["headers"]["Authorization"])
        self.assertEqual("canvas-request-1", sent["headers"]["Idempotency-Key"])
        self.assertEqual(1024, sent["json_body"]["width"])
        self.assertNotIn("query", sent)

    def test_async_poll_and_cancel_only_substitute_one_encoded_task_id_segment(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderRuntime, ProviderSubmission

        config = self._sync_config()
        config["result"] = {
            "mode": "async", "taskIdPath": "data.task_id",
            "poll": {
                "method": "GET", "endpoint": "/v1/tasks/{external_task_id}",
                "statusPath": "data.status", "pendingValues": ["queued", "running"],
                "completedValues": ["succeeded"], "imagePath": "data.output", "imageType": "url",
            },
            "cancel": {"method": "DELETE", "endpoint": "/v1/tasks/{external_task_id}"},
        }
        client = _FakeSafeClient(
            NetworkResponse(200, {"content-type": "application/json"}, b'{"data":{"status":"succeeded","output":"https://images.example/result.png"}}'),
            NetworkResponse(204, {}, b""),
        )
        adapter = self._adapter(config)
        submission = ProviderSubmission(status="pending", external_task_id="task A")
        polled = asyncio.run(adapter.poll(submission, ProviderRuntime(api_key="secret", transport=client)))
        cancelled = asyncio.run(adapter.cancel(submission, ProviderRuntime(api_key="secret", transport=client)))
        self.assertEqual("completed", polled.kind)
        self.assertEqual("cancelled", cancelled.kind)
        self.assertEqual("/v1/tasks/task%20A", client.requests[0]["endpoint"])
        self.assertEqual("/v1/tasks/task%20A", client.requests[1]["endpoint"])
        self.assertEqual("Bearer secret", client.requests[0]["headers"]["Authorization"])
        self.assertEqual("Bearer secret", client.requests[1]["headers"]["Authorization"])
        self.assertEqual(2, len(client.requests))

    def test_multipart_and_controlled_api_key_query_are_built_without_payload_templates(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderGenerationRequest, ProviderRuntime

        config = self._sync_config()
        config["auth"] = {"type": "api_key_query", "name": "key"}
        config["submit"] = {
            "method": "POST", "endpoint": "/v1/edits", "format": "multipart",
            "fields": {"model": "{{model_id}}", "prompt": "{{prompt}}"},
            "files": {"image": "reference_image_bytes"},
        }
        config["result"] = {"mode": "sync", "imageType": "binary"}
        client = _FakeSafeClient(NetworkResponse(200, {"content-type": "image/png"}, b"png"))
        adapter = self._adapter(config)
        adapter.capabilities = self._capabilities(image_to_image=True, max_reference_images=1, reference_transfer="bytes")
        result = asyncio.run(adapter.submit(
            ProviderGenerationRequest(prompt="studio", size="1024x1024", reference_images=(b"source",)),
            ProviderRuntime(api_key="secret", transport=client),
        ))
        self.assertEqual(b"png", result.image.data)
        sent = client.requests[0]
        self.assertEqual({"key": "secret"}, sent["query"])
        self.assertIn(b"name=\"image\"", sent["body"])
        self.assertIn(b"source", sent["body"])
        self.assertIn("multipart/form-data; boundary=", sent["headers"]["Content-Type"])

    def test_unsafe_templates_paths_headers_and_external_values_fail_closed(self) -> None:
        from services.canvas.providers.declarative_http import DeclarativeConfigurationError

        cases = []
        invalid_variable = self._sync_config(); invalid_variable["submit"]["json"]["x"] = "{{__import__}}"; cases.append(invalid_variable)
        expression = self._sync_config(); expression["submit"]["json"]["x"] = "{{prompt | lower}}"; cases.append(expression)
        external = self._sync_config(); external["submit"]["endpoint"] = "https://evil.example/generate"; cases.append(external)
        injection = self._sync_config(); injection["result"]["imagePath"] = "data.__proto__.url"; cases.append(injection)
        header = self._sync_config(); header["headers"] = {"Authorization": "Bearer {{prompt}}"}; cases.append(header)
        nested_url = self._sync_config(); nested_url["submit"]["json"]["callback"] = "https://evil.example/callback"; cases.append(nested_url)
        for configuration in cases:
            with self.subTest(configuration=configuration):
                with self.assertRaises(DeclarativeConfigurationError):
                    self._adapter(configuration)

    def test_registry_builds_a_declarative_adapter_only_from_its_saved_configuration(self) -> None:
        from services.canvas.providers.registry import provider_registry

        adapter = provider_registry.build(
            "declarative_http", model_id="dynamic-vendor", capabilities=self._capabilities(),
            configuration=self._sync_config(),
        )
        self.assertEqual("declarative_http", adapter.adapter_type)
        self.assertEqual("dynamic-vendor", adapter.model_id)

    def test_encoded_or_path_injection_task_ids_fail_before_any_poll_request(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderError, ProviderRuntime, ProviderSubmission

        config = self._sync_config()
        config["result"] = {"mode": "async", "taskIdPath": "id", "poll": {"method": "GET", "endpoint": "/tasks/{external_task_id}", "statusPath": "state", "pendingValues": ["queued"], "completedValues": ["done"], "imagePath": "url", "imageType": "url"}}
        client = _FakeSafeClient(NetworkResponse(200, {"content-type": "application/json"}, b"{}"))
        adapter = self._adapter(config)
        for task_id in ("../x", "a/b", "a?b", "a#b", "a%2fb", "a%252fb"):
            with self.subTest(task_id=task_id):
                with self.assertRaises(ProviderError) as failure:
                    asyncio.run(adapter.poll(ProviderSubmission(status="pending", external_task_id=task_id), ProviderRuntime(api_key="secret", transport=client)))
                self.assertEqual("provider_task_invalid", failure.exception.code)
        self.assertEqual([], client.requests)


if __name__ == "__main__":
    unittest.main()
