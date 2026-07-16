"""Contract tests for the built-in Seedream 5.0 Pro image provider."""
from __future__ import annotations

import importlib.util
import asyncio
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, get_db


ROOT = Path(__file__).resolve().parents[1]


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def _png_bytes(*, width: int = 8, height: int = 8) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), (12, 34, 56, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeTransport:
    def __init__(self, *responses, on_request=None) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []
        self.on_request = on_request

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        if self.on_request is not None:
            self.on_request(kwargs)
        return self.responses.pop(0)


class SeedreamProviderBootstrapContractTests(unittest.TestCase):
    def test_provider_modules_and_exact_dependency_pin_exist(self) -> None:
        required_modules = (
            "services.canvas.provider_schemas",
            "services.canvas.provider_network",
            "services.canvas.remote_images",
            "services.canvas.providers.seedream",
            "services.canvas.providers.bootstrap",
            "services.canvas.provider_catalog",
            "routers.canvas.providers",
        )
        missing = [
            module_name
            for module_name in required_modules
            if not _module_exists(module_name)
        ]
        self.assertEqual([], missing)

        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, requirements.count("httpcore==1.0.9"))

    def test_seedream_profile_uses_the_official_full_model_contract(self) -> None:
        self.assertTrue(_module_exists("services.canvas.providers.seedream"))
        from services.canvas.providers.seedream import SeedreamAdapter

        self.assertEqual("doubao-seedream-5-0-pro-260628", SeedreamAdapter.MODEL_ID)
        self.assertEqual("Seedream 5.0 Pro（完整版）", SeedreamAdapter.DISPLAY_NAME)
        self.assertNotIn("doubao-seedream-5-0-260128", SeedreamAdapter.MODEL_ID)

    def test_remote_image_limit_is_strictly_bounded(self) -> None:
        import importlib.util
        import uuid

        config_path = ROOT / "config.py"

        def load_config(value: str | None):
            environment = os.environ.copy()
            environment.pop("CANVAS_REMOTE_IMAGE_MAX_BYTES", None)
            if value is not None:
                environment["CANVAS_REMOTE_IMAGE_MAX_BYTES"] = value
            spec = importlib.util.spec_from_file_location(
                f"_seedream_config_{uuid.uuid4().hex}", config_path
            )
            module = importlib.util.module_from_spec(spec)
            with patch.dict(os.environ, environment, clear=True), patch(
                "dotenv.load_dotenv", return_value=False
            ):
                spec.loader.exec_module(module)
            return module

        self.assertEqual(26_214_400, load_config(None).CANVAS_REMOTE_IMAGE_MAX_BYTES)
        self.assertEqual(1_048_576, load_config("1048576").CANVAS_REMOTE_IMAGE_MAX_BYTES)
        for invalid in ("0", "-1", "26214401"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "CANVAS_REMOTE_IMAGE_MAX_BYTES"):
                    load_config(invalid)


class SeedreamAdapterContractTests(unittest.TestCase):
    def test_capabilities_are_sync_single_image_without_references_or_recovery(self) -> None:
        from services.canvas.provider_schemas import ProviderGenerationRequest
        from services.canvas.providers.seedream import SeedreamAdapter

        adapter = SeedreamAdapter()
        capabilities = adapter.capabilities
        self.assertEqual("sync", capabilities.protocol)
        self.assertEqual(1, capabilities.max_quantity)
        self.assertEqual(0, capabilities.max_reference_images)
        self.assertEqual("none", capabilities.reference_transfer)
        self.assertFalse(capabilities.supports_cancel)
        self.assertFalse(capabilities.supports_idempotency)
        self.assertFalse(capabilities.supports_idempotency_lookup)
        self.assertEqual((), capabilities.allowed_ratios)
        self.assertEqual((), capabilities.allowed_sizes)
        self.assertIsNone(capabilities.min_width)
        self.assertIsNone(capabilities.max_width)
        self.assertIsNone(capabilities.min_height)
        self.assertIsNone(capabilities.max_height)
        adapter.validate_request(
            ProviderGenerationRequest(prompt="warm studio background", size="2048x2048"),
            capabilities,
        )
        for request in (
            ProviderGenerationRequest(prompt="", size="2048x2048"),
            ProviderGenerationRequest(
                prompt="background", size="2048x2048", quantity=2
            ),
            ProviderGenerationRequest(
                prompt="background", size="2048x2048", reference_images=(b"product",)
            ),
            ProviderGenerationRequest(prompt="background", size="not-a-size"),
        ):
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    adapter.validate_request(request, capabilities)

    def test_submit_uses_exact_official_payload_and_redacts_auth(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import (
            ProviderGenerationRequest,
            ProviderRuntime,
        )
        from services.canvas.providers.seedream import SeedreamAdapter

        secret = "ark-secret-must-not-leak"
        signed_url = "https://public.example/result.png?token=result-secret"
        transport = _FakeTransport(
            NetworkResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"data": [{"url": signed_url}], "id": "req-1"}).encode(),
            )
        )
        runtime = ProviderRuntime(api_key=secret, transport=transport)
        submission = asyncio.run(
            SeedreamAdapter().submit(
                ProviderGenerationRequest(
                    prompt="warm studio background only", size="2048x2048"
                ),
                runtime,
            )
        )

        self.assertEqual("completed", submission.status)
        self.assertEqual("req-1", submission.request_id)
        self.assertEqual(signed_url, submission.image.remote_url)
        request = transport.requests[0]
        self.assertEqual("POST", request["method"])
        self.assertEqual(SeedreamAdapter.ENDPOINT, request["url"])
        self.assertEqual(f"Bearer {secret}", request["headers"]["Authorization"])
        self.assertEqual(
            {
                "model": "doubao-seedream-5-0-pro-260628",
                "prompt": "warm studio background only",
                "size": "2048x2048",
                "output_format": "png",
                "response_format": "url",
                "watermark": False,
            },
            request["json_body"],
        )
        forbidden = {
            "sequential_image_generation",
            "sequential_image_generation_options",
            "stream",
            "tools",
            "image",
            "images",
        }
        self.assertTrue(forbidden.isdisjoint(request["json_body"]))
        self.assertNotIn(secret, repr(runtime))
        self.assertNotIn(secret, repr(submission))
        self.assertNotIn("result-secret", repr(submission))

    def test_official_credential_precedes_compatibility_alias(self) -> None:
        from services.canvas.providers.seedream import resolve_seedream_api_key

        with patch.dict(
            os.environ,
            {"ARK_API_KEY": "official", "DOUBAO_API_KEY": "compat"},
            clear=False,
        ):
            self.assertEqual("official", resolve_seedream_api_key())
        with patch.dict(os.environ, {"ARK_API_KEY": "", "DOUBAO_API_KEY": "compat"}):
            self.assertEqual("compat", resolve_seedream_api_key())

    def test_unsupported_operations_return_closed_results_and_errors_are_safe(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import (
            ProviderGenerationRequest,
            ProviderRuntime,
            ProviderSubmission,
        )
        from services.canvas.providers.seedream import SeedreamAdapter

        adapter = SeedreamAdapter()
        runtime = ProviderRuntime(api_key="top-secret", transport=_FakeTransport())
        pending = ProviderSubmission(status="pending", request_id="req")
        self.assertEqual("unsupported", asyncio.run(adapter.poll(pending, runtime)).kind)
        self.assertEqual("unsupported", asyncio.run(adapter.cancel(pending, runtime)).kind)
        self.assertEqual(
            "unsupported",
            asyncio.run(adapter.recover_by_idempotency_key("key", runtime)).kind,
        )

        runtime = ProviderRuntime(
            api_key="top-secret",
            transport=_FakeTransport(
                NetworkResponse(
                    status_code=401,
                    headers={"content-type": "application/json"},
                    body=b'{"error":{"message":"top-secret upstream detail"}}',
                )
            ),
        )
        with self.assertRaises(Exception) as caught:
            asyncio.run(
                adapter.submit(
                    ProviderGenerationRequest(prompt="background", size="2048x2048"),
                    runtime,
                )
            )
        self.assertNotIn("top-secret", str(caught.exception))
        self.assertNotIn("upstream detail", str(caught.exception))

    def test_top_level_and_single_item_generation_errors_are_normalized(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import (
            ProviderError,
            ProviderGenerationRequest,
            ProviderRuntime,
        )
        from services.canvas.providers.seedream import SeedreamAdapter

        query_secret = "signed-query-secret"
        payloads = (
            {
                "error": {
                    "code": "SensitiveUpstreamCode",
                    "message": "credential-secret " + query_secret,
                }
            },
            {
                "data": [
                    {
                        "error": {
                            "code": "SensitiveItemCode",
                            "message": "https://cdn.example/result?token=" + query_secret,
                        }
                    }
                ]
            },
        )
        for payload in payloads:
            with self.subTest(shape=tuple(payload)):
                runtime = ProviderRuntime(
                    api_key="credential-secret",
                    transport=_FakeTransport(
                        NetworkResponse(
                            200,
                            {"content-type": "application/json"},
                            json.dumps(payload).encode(),
                        )
                    ),
                )
                with self.assertRaises(ProviderError) as caught:
                    asyncio.run(
                        SeedreamAdapter().submit(
                            ProviderGenerationRequest(
                                prompt="background", size="2048x2048"
                            ),
                            runtime,
                        )
                    )
                self.assertEqual("provider_generation_failed", caught.exception.code)
                self.assertEqual(
                    "Seedream could not generate the requested image",
                    str(caught.exception),
                )
                self.assertNotIn("credential-secret", repr(caught.exception))
                self.assertNotIn(query_secret, repr(caught.exception))

    def test_submit_redirect_is_not_followed_or_disclosed(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import (
            ProviderError,
            ProviderGenerationRequest,
            ProviderRuntime,
        )
        from services.canvas.providers.seedream import SeedreamAdapter

        secret = "submit-redirect-secret"
        runtime = ProviderRuntime(
            api_key="credential-secret",
            transport=_FakeTransport(
                NetworkResponse(
                    302,
                    {"location": "https://other.example/path?token=" + secret},
                    b"",
                )
            ),
        )
        with self.assertRaises(ProviderError) as caught:
            asyncio.run(
                SeedreamAdapter().submit(
                    ProviderGenerationRequest(prompt="background", size="2048x2048"),
                    runtime,
                )
            )
        self.assertEqual(1, len(runtime.transport.requests))
        self.assertNotIn(secret, repr(caught.exception))


class RemoteImageBoundaryContractTests(unittest.TestCase):
    def test_public_https_validation_rejects_unsafe_addresses(self) -> None:
        from services.canvas.provider_network import (
            ProviderNetworkError,
            resolve_public_https_endpoint,
        )

        with self.assertRaises(ProviderNetworkError):
            resolve_public_https_endpoint("http://cdn.example/a.png", resolver=lambda _: ["93.184.216.34"])
        for address in (
            "127.0.0.1",
            "10.0.0.2",
            "169.254.169.254",
            "224.0.0.1",
            "2001:db8::1",
        ):
            with self.subTest(address=address):
                with self.assertRaises(ProviderNetworkError):
                    resolve_public_https_endpoint(
                        "https://cdn.example/a.png", resolver=lambda _, a=address: [a]
                    )
        endpoint = resolve_public_https_endpoint(
            "https://cdn.example/a.png", resolver=lambda _: ["93.184.216.34"]
        )
        self.assertEqual("cdn.example", endpoint.hostname)
        self.assertEqual("93.184.216.34", endpoint.pinned_ip)

    def test_mixed_dns_and_ipv4_mapped_private_answers_fail_closed(self) -> None:
        from services.canvas.provider_network import (
            ProviderNetworkError,
            resolve_public_https_endpoint,
        )

        for answers in (
            ["93.184.216.34", "10.0.0.8"],
            ["93.184.216.34", "::ffff:127.0.0.1"],
        ):
            with self.subTest(answers=answers):
                with self.assertRaises(ProviderNetworkError):
                    resolve_public_https_endpoint(
                        "https://cdn.example/result.png",
                        resolver=lambda _hostname, a=answers: a,
                    )

    def test_unvalidated_pinned_endpoint_is_rejected_before_pool_creation(self) -> None:
        from services.canvas.provider_network import (
            PinnedEndpoint,
            PinnedHttpCoreTransport,
            ProviderNetworkError,
        )

        endpoint = PinnedEndpoint(
            url="https://cdn.example/result.png",
            hostname="cdn.example",
            port=443,
            pinned_ip="10.0.0.8",
        )
        with patch("services.canvas.provider_network.httpcore.AsyncConnectionPool") as pool:
            with self.assertRaises(ProviderNetworkError):
                asyncio.run(
                    PinnedHttpCoreTransport().request(
                        method="GET",
                        url=endpoint.url,
                        headers={},
                        max_bytes=1024,
                        pinned_endpoint=endpoint,
                    )
                )
        pool.assert_not_called()

    def test_query_bearing_urls_are_redacted_before_transport_debug_logging(self) -> None:
        from services.canvas.provider_network import redact_url_queries

        secret = "signed-result-secret"
        message = (
            "send_request_headers.started headers=(b'Authorization', "
            "b'Bearer credential-secret') "
            "receive_response_headers.complete return_value=(b'HTTP/1.1', 302, "
            "[(b'location', b'https://cdn.example/result.png?token=" + secret + "')])"
        )
        redacted = redact_url_queries(message)
        self.assertNotIn(secret, redacted)
        self.assertNotIn("credential-secret", redacted)
        self.assertIn("?<redacted>", redacted)

    def test_transport_uses_fresh_no_proxy_pool_pinned_ip_original_host_and_sni(self) -> None:
        from services.canvas.provider_network import PinnedEndpoint, PinnedHttpCoreTransport

        created = []

        class FakeResponse:
            status = 200
            headers = []

            async def aiter_stream(self):
                yield b"ok"

            async def aclose(self):
                return None

        class FakePool:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.requests = []
                created.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def request(self, *args, **kwargs):
                self.requests.append((args, kwargs))
                return FakeResponse()

        endpoints = (
            PinnedEndpoint(
                url="https://a.example/result",
                hostname="a.example",
                port=443,
                pinned_ip="93.184.216.34",
            ),
            PinnedEndpoint(
                url="https://b.example/result",
                hostname="b.example",
                port=443,
                pinned_ip="1.1.1.1",
            ),
        )
        with patch(
            "services.canvas.provider_network.httpcore.AsyncConnectionPool",
            side_effect=lambda **kwargs: FakePool(**kwargs),
        ):
            transport = PinnedHttpCoreTransport()
            for endpoint in endpoints:
                asyncio.run(
                    transport.request(
                        method="GET",
                        url=endpoint.url,
                        headers={"Host": "attacker.invalid"},
                        max_bytes=100,
                        pinned_endpoint=endpoint,
                    )
                )

        self.assertEqual(2, len(created))
        for pool, endpoint in zip(created, endpoints, strict=True):
            self.assertIsNone(pool.kwargs["proxy"])
            self.assertEqual(endpoint.pinned_ip, pool.kwargs["network_backend"]._endpoint.pinned_ip)
            _args, kwargs = pool.requests[0]
            self.assertEqual(endpoint.hostname, kwargs["extensions"]["sni_hostname"])
            headers = {name.lower(): value for name, value in kwargs["headers"]}
            self.assertEqual(endpoint.hostname.encode("ascii"), headers[b"host"])

    def test_bounded_stream_and_decoded_image_share_the_configured_cap(self) -> None:
        from services.canvas.provider_network import ProviderNetworkError, collect_bounded_chunks
        from services.canvas.remote_images import RemoteImageValidationError, verify_remote_image

        async def chunks():
            yield b"a" * 6
            yield b"b" * 5

        with self.assertRaises(ProviderNetworkError):
            asyncio.run(collect_bounded_chunks(chunks(), max_bytes=10))

        compressed = _png_bytes(width=100, height=100)
        self.assertLess(len(compressed), 1_000)
        with self.assertRaises(RemoteImageValidationError):
            verify_remote_image(
                compressed,
                declared_mime="image/png",
                max_bytes=1_000,
            )

    def test_remote_download_revalidates_two_redirects_without_credentials(self) -> None:
        from services.canvas.provider_network import NetworkResponse, PinnedEndpoint
        from services.canvas.remote_images import download_remote_image

        image_bytes = _png_bytes()
        transport = _FakeTransport(
            NetworkResponse(302, {"location": "https://b.example/two"}, b""),
            NetworkResponse(307, {"location": "https://c.example/final"}, b""),
            NetworkResponse(200, {"content-type": "image/png"}, image_bytes),
        )
        validated = []

        def validator(url: str):
            validated.append(url)
            hostname = url.split("/", 3)[2]
            return PinnedEndpoint(url=url, hostname=hostname, port=443, pinned_ip="93.184.216.34")

        result = asyncio.run(
            download_remote_image(
                "https://a.example/one",
                transport=transport,
                max_bytes=26_214_400,
                endpoint_validator=validator,
            )
        )
        self.assertEqual(image_bytes, result.data)
        self.assertEqual(
            [
                "https://a.example/one",
                "https://b.example/two",
                "https://c.example/final",
            ],
            validated,
        )
        for request in transport.requests:
            self.assertNotIn("Authorization", request["headers"])

    def test_remote_download_rejects_third_redirect_mime_magic_and_decode_failures(self) -> None:
        from services.canvas.provider_network import NetworkResponse, PinnedEndpoint
        from services.canvas.remote_images import (
            RemoteImageValidationError,
            download_remote_image,
            verify_remote_image,
        )

        validator = lambda url: PinnedEndpoint(
            url=url, hostname="cdn.example", port=443, pinned_ip="93.184.216.34"
        )
        transport = _FakeTransport(
            NetworkResponse(302, {"location": "https://cdn.example/2"}, b""),
            NetworkResponse(302, {"location": "https://cdn.example/3"}, b""),
            NetworkResponse(302, {"location": "https://cdn.example/4"}, b""),
        )
        with self.assertRaises(RemoteImageValidationError):
            asyncio.run(
                download_remote_image(
                    "https://cdn.example/1",
                    transport=transport,
                    max_bytes=26_214_400,
                    endpoint_validator=validator,
                )
            )
        for data, mime in ((b"not an image", "image/png"), (_png_bytes(), "text/html")):
            with self.subTest(mime=mime):
                with self.assertRaises(RemoteImageValidationError):
                    verify_remote_image(data, declared_mime=mime, max_bytes=26_214_400)

    def test_jpeg_and_webp_are_verified_then_normalized_to_single_frame_png(self) -> None:
        from services.canvas.remote_images import RemoteImageValidationError, verify_remote_image

        for image_format, mime in (("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
            buffer = io.BytesIO()
            Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format=image_format)
            normalized = verify_remote_image(
                buffer.getvalue(), declared_mime=mime, max_bytes=26_214_400
            )
            with self.subTest(image_format=image_format):
                self.assertEqual("image/png", normalized.mime_type)
                self.assertTrue(normalized.data.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(image_format.lower(), normalized.source_format)

        animated = io.BytesIO()
        frames = [
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
            Image.new("RGBA", (8, 8), (0, 255, 0, 255)),
        ]
        frames[0].save(
            animated,
            format="PNG",
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )
        with self.assertRaises(RemoteImageValidationError):
            verify_remote_image(
                animated.getvalue(), declared_mime="image/png", max_bytes=26_214_400
            )

    def test_png_is_canonicalized_without_upstream_ancillary_metadata(self) -> None:
        from PIL.PngImagePlugin import PngInfo

        from services.canvas.remote_images import verify_remote_image

        secret = "https://cdn.example/result.png?token=signed-url-secret"
        original = Image.new("RGBA", (3, 2))
        original.putdata(
            [
                (255, 0, 0, 255),
                (0, 255, 0, 128),
                (0, 0, 255, 0),
                (1, 2, 3, 4),
                (10, 20, 30, 40),
                (250, 240, 230, 220),
            ]
        )
        metadata = PngInfo()
        metadata.add_text("signed-source-url", secret)
        metadata.add_text("comment", "untrusted upstream metadata")
        source = io.BytesIO()
        original.save(source, format="PNG", pnginfo=metadata)
        source_bytes = source.getvalue()
        self.assertIn(b"signed-url-secret", source_bytes)

        verified = verify_remote_image(
            source_bytes,
            declared_mime="image/png",
            max_bytes=26_214_400,
        )

        self.assertNotEqual(source_bytes, verified.data)
        self.assertNotIn(b"signed-url-secret", verified.data)
        self.assertNotIn(b"untrusted upstream metadata", verified.data)
        self.assertLessEqual(len(verified.data), 26_214_400)
        self.assertEqual(hashlib.sha256(verified.data).hexdigest(), verified.sha256)
        with Image.open(io.BytesIO(verified.data)) as canonical:
            canonical.load()
            self.assertEqual("PNG", canonical.format)
            self.assertEqual("RGBA", canonical.mode)
            self.assertEqual((3, 2), canonical.size)
            self.assertEqual({}, canonical.info)
            self.assertEqual(original.tobytes(), canonical.tobytes())


class ProviderBootstrapAndCatalogContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'providers.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401

        Base.metadata.create_all(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def test_bootstrap_is_idempotent_exact_and_preserves_user_disable_state(self) -> None:
        from canvas_models import ImageModelProfile, ImageProviderConnection
        from services.canvas.providers.bootstrap import (
            BUILTIN_SEEDREAM_MODEL_PROFILE_ID,
            BUILTIN_SEEDREAM_PROVIDER_ID,
            bootstrap_builtin_image_profiles,
        )
        from services.canvas.providers.registry import provider_registry

        bootstrap_builtin_image_profiles(self.Session)
        bootstrap_builtin_image_profiles(self.Session)
        with self.Session() as db:
            providers = db.scalars(select(ImageProviderConnection)).all()
            models = db.scalars(select(ImageModelProfile)).all()
            self.assertEqual(1, len(providers))
            self.assertEqual(1, len(models))
            self.assertEqual(BUILTIN_SEEDREAM_PROVIDER_ID, providers[0].id)
            self.assertEqual(BUILTIN_SEEDREAM_MODEL_PROFILE_ID, models[0].id)
            self.assertEqual("doubao-seedream-5-0-pro-260628", models[0].model_id)
            self.assertNotIn("doubao-seedream-5-0-260128", models[0].config_json)
            providers[0].enabled = False
            models[0].enabled = True
            db.commit()
        bootstrap_builtin_image_profiles(self.Session)
        with self.Session() as db:
            self.assertFalse(db.get(ImageProviderConnection, BUILTIN_SEEDREAM_PROVIDER_ID).enabled)
            self.assertTrue(db.get(ImageModelProfile, BUILTIN_SEEDREAM_MODEL_PROFILE_ID).enabled)
            db.get(ImageProviderConnection, BUILTIN_SEEDREAM_PROVIDER_ID).enabled = True
            db.get(ImageModelProfile, BUILTIN_SEEDREAM_MODEL_PROFILE_ID).enabled = False
            db.commit()
        bootstrap_builtin_image_profiles(self.Session)
        with self.Session() as db:
            self.assertTrue(db.get(ImageProviderConnection, BUILTIN_SEEDREAM_PROVIDER_ID).enabled)
            self.assertFalse(db.get(ImageModelProfile, BUILTIN_SEEDREAM_MODEL_PROFILE_ID).enabled)
        self.assertEqual("seedream", provider_registry.get("seedream").adapter_type)

    def test_bootstrap_orders_new_provider_before_profile_with_foreign_keys_enabled(self) -> None:
        from services.canvas.providers.bootstrap import bootstrap_builtin_image_profiles

        with self.Session() as db:
            db.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
            self.assertEqual(1, db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one())

        strict_session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        bootstrap_builtin_image_profiles(strict_session)

    def _app(self) -> FastAPI:
        from routers.canvas.providers import router

        app = FastAPI()
        app.include_router(router, prefix="/api/canvas")

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        return app

    def test_catalog_and_protected_management_routes_never_disclose_credentials(self) -> None:
        from canvas_models import ImageModelProfile, ImageProviderConnection
        from services.canvas.providers.bootstrap import bootstrap_builtin_image_profiles

        bootstrap_builtin_image_profiles(self.Session)
        with self.Session() as db:
            provider = db.scalar(select(ImageProviderConnection))
            model = db.scalar(select(ImageModelProfile))
            provider.enabled = True
            model.enabled = True
            db.commit()
            provider_id = provider.id

        with patch.dict(os.environ, {"ARK_API_KEY": "", "DOUBAO_API_KEY": ""}):
            with TestClient(self._app()) as client:
                providers = client.get("/api/canvas/model-providers")
                models = client.get(f"/api/canvas/model-providers/{provider_id}/models")
                missing = client.get("/api/canvas/model-providers/not-found/models")
        self.assertEqual(200, providers.status_code, providers.text)
        self.assertEqual(200, models.status_code, models.text)
        self.assertEqual(404, missing.status_code, missing.text)
        self.assertEqual("missing_credential", providers.json()[0]["availability"])
        self.assertEqual("missing_credential", models.json()[0]["availability"])
        self.assertEqual("doubao-seedream-5-0-pro-260628", models.json()[0]["modelId"])
        self.assertEqual("sync", models.json()[0]["capabilities"]["protocol"])
        catalog_text = providers.text + models.text
        for secret_field in (
            "ARK_API_KEY",
            "DOUBAO_API_KEY",
            "environmentCredentialRef",
            "encryptedCredential",
        ):
            self.assertNotIn(secret_field, catalog_text)

        with patch.dict(os.environ, {"ARK_API_KEY": "official-secret", "DOUBAO_API_KEY": ""}):
            with TestClient(self._app()) as client:
                available = client.get("/api/canvas/model-providers")
        self.assertEqual("available", available.json()[0]["availability"])
        self.assertNotIn("official-secret", available.text)

        methods = {
            (method.upper(), path)
            for path, schema in self._app().openapi()["paths"].items()
            for method in schema
        }
        self.assertEqual(
            {
                ("GET", "/api/canvas/model-providers"),
                ("GET", "/api/canvas/model-providers/{provider_id}/models"),
                ("POST", "/api/canvas/model-providers"),
                ("PATCH", "/api/canvas/model-providers/{provider_id}"),
                ("DELETE", "/api/canvas/model-providers/{provider_id}"),
                ("POST", "/api/canvas/model-providers/{provider_id}/test"),
                ("POST", "/api/canvas/model-providers/{provider_id}/models"),
                ("PATCH", "/api/canvas/models/{model_profile_id}"),
            },
            methods,
        )

    def test_main_bootstraps_profiles_after_database_before_canvas_runtime(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("bootstrap_builtin_image_profiles"),
            source.index("recover_deleting_projects"),
        )
        self.assertLess(source.index("init_db()"), source.index("bootstrap_builtin_image_profiles"))


class ProviderPersistenceSeamContractTests(unittest.TestCase):
    def test_network_awaits_finish_before_short_persistence_transaction_opens(self) -> None:
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ProviderGenerationRequest, ProviderRuntime
        from services.canvas.providers.seedream import SeedreamAdapter
        from services.canvas.remote_images import generate_and_persist_background

        open_sessions = 0

        def assert_no_session(_request):
            self.assertEqual(0, open_sessions)

        transport = _FakeTransport(
            NetworkResponse(
                200,
                {"content-type": "application/json"},
                b'{"data":[{"url":"https://cdn.example/result.png"}],"id":"req"}',
            ),
            NetworkResponse(200, {"content-type": "image/png"}, _png_bytes()),
            on_request=assert_no_session,
        )

        class FakeSession:
            def __enter__(self):
                nonlocal open_sessions
                open_sessions += 1
                return self

            def __exit__(self, *_args):
                nonlocal open_sessions
                open_sessions -= 1

            def commit(self):
                return None

        persisted = Mock(return_value=type("Asset", (), {"id": "asset-1"})())
        validator = lambda url: type(
            "Endpoint",
            (),
            {"url": url, "hostname": "cdn.example", "port": 443, "pinned_ip": "93.184.216.34"},
        )()
        with patch("services.canvas.remote_images.persist_derived_image", persisted):
            asset_id = asyncio.run(
                generate_and_persist_background(
                    adapter=SeedreamAdapter(),
                    request=ProviderGenerationRequest(
                        prompt="background", size="2048x2048"
                    ),
                    runtime=ProviderRuntime(api_key="secret", transport=transport),
                    db_factory=FakeSession,
                    project_id="project-1",
                    source_asset_id=None,
                    metadata={"attemptId": "attempt-1"},
                    endpoint_validator=validator,
                )
            )
        self.assertEqual("asset-1", asset_id)
        self.assertEqual(0, open_sessions)
        self.assertEqual("generated_background", persisted.call_args.kwargs["asset_type"])
        self.assertEqual("image/png", persisted.call_args.kwargs["mime_type"])


if __name__ == "__main__":
    unittest.main()
