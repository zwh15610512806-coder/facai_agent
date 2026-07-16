"""End-to-end runtime contracts for dynamic third-party image Providers."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class ThirdPartyProviderExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'providers.db').as_posix()}"
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401
        from database import Base

        Base.metadata.create_all(self.engine)
        self.provider_id = str(uuid4())
        self.model_id = str(uuid4())
        self.secret = "third-party-key-must-never-be-snapshotted"
        self.fernet_key = Fernet.generate_key().decode("ascii")
        self._seed_provider()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    @staticmethod
    def _png_bytes() -> bytes:
        output = io.BytesIO()
        with Image.new("RGB", (256, 256), (20, 80, 140)) as image:
            image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _capabilities() -> dict[str, object]:
        return {
            "text_to_image": True,
            "image_to_image": False,
            "mask_edit": False,
            "allowed_ratios": (),
            "allowed_sizes": (),
            "min_width": None,
            "max_width": None,
            "min_height": None,
            "max_height": None,
            "max_quantity": 1,
            "max_reference_images": 0,
            "reference_transfer": "none",
            "protocol": "sync",
            "supports_cancel": False,
            "supports_idempotency": False,
            "supports_idempotency_lookup": False,
            "concurrency_limit": 1,
            "price_metadata": None,
        }

    def _seed_provider(self) -> None:
        import config
        from canvas_models import ImageProviderConnection
        from services.canvas.credentials import ProviderSecretCodec

        with patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", self.fernet_key):
            encrypted = ProviderSecretCodec.from_env().encrypt_json({"apiKey": self.secret})
        with self.Session() as db:
            db.add(
                ImageProviderConnection(
                    id=self.provider_id,
                    adapter_type="openai_images",
                    name="Approved Images API",
                    base_url="https://api.vendor.example/v1",
                    auth_type="bearer",
                    encrypted_credential=encrypted,
                    enabled=True,
                    config_version=1,
                )
            )
            db.commit()

    def _claim(self):
        from services.canvas.generation.worker import ClaimedAttempt

        return ClaimedAttempt(
            attempt_id=str(uuid4()),
            item_id=str(uuid4()),
            generation_id=str(uuid4()),
            project_id=str(uuid4()),
            claim_token="worker:claim",
            lease_expires_at=datetime(2030, 1, 1),
            status="submitting",
            provider_result_stage="awaiting_provider",
            provider_id=self.provider_id,
            model_profile_id=self.model_id,
            provider_snapshot={
                "id": self.provider_id,
                "adapterType": "openai_images",
                "name": "Approved Images API",
                "baseUrl": "https://api.vendor.example/v1",
                "authType": "bearer",
                "configVersion": 1,
            },
            model_snapshot={
                "id": self.model_id,
                "providerId": self.provider_id,
                "modelId": "vendor-image-v1",
                "displayName": "Vendor Image V1",
                "configVersion": 1,
                "capabilities": self._capabilities(),
                "configuration": {},
            },
            prompt="clean product studio background",
            width=256,
            height=256,
            upstream_idempotency_key="saved-key",
            external_task_id=None,
        )

    @staticmethod
    def _policy():
        from services.canvas.provider_network import ProviderNetworkPolicy

        return ProviderNetworkPolicy(
            allowed_hosts=("api.vendor.example",),
            private_allowed_hosts=(),
            private_allowed_ips=(),
            allow_insecure_http=False,
            connect_timeout_seconds=5,
            total_timeout_seconds=30,
            max_json_bytes=1_000_000,
        )

    def test_dynamic_factory_decrypts_only_in_memory_and_executes_saved_snapshot(self) -> None:
        import config
        from services.canvas.generation.worker import (
            execute_claimed_attempt,
            prepare_provider_execution_context,
        )
        from services.canvas.provider_network import NetworkResponse
        from services.canvas.provider_schemas import ControlledImageBytes
        from services.canvas.providers.registry import provider_registry

        class FakeTransport:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []

            async def request(self, **kwargs):
                self.requests.append(kwargs)
                payload = {
                    "data": [
                        {"b64_json": base64.b64encode(self_png).decode("ascii")}
                    ]
                }
                return NetworkResponse(
                    200,
                    {"content-type": "application/json"},
                    json.dumps(payload).encode("utf-8"),
                )

        self_png = self._png_bytes()
        transport = FakeTransport()
        claim = self._claim()
        with patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", self.fernet_key):
            context = prepare_provider_execution_context(
                claim,
                registry=provider_registry,
                db_factory=self.Session,
                network_policy=self._policy(),
                resolver=lambda _host: ("93.184.216.34",),
                request_transport=transport,
                result_transport=object(),
            )
        result = asyncio.run(
            execute_claimed_attempt(
                claim,
                registry=provider_registry,
                context=context,
            )
        )

        self.assertEqual("completed", result.kind)
        self.assertIsInstance(result.image, ControlledImageBytes)
        self.assertEqual(
            "https://api.vendor.example/v1/images/generations",
            transport.requests[0]["url"],
        )
        self.assertEqual(
            f"Bearer {self.secret}",
            transport.requests[0]["headers"]["Authorization"],
        )
        self.assertNotIn(self.secret, repr(context))
        self.assertNotIn(self.secret, json.dumps(claim.provider_snapshot))
        self.assertNotIn(self.secret, json.dumps(claim.model_snapshot))

    def test_disabled_provider_fails_before_any_request(self) -> None:
        import config
        from canvas_models import ImageProviderConnection
        from services.canvas.generation.worker import prepare_provider_execution_context
        from services.canvas.provider_schemas import ProviderError
        from services.canvas.providers.registry import provider_registry

        with self.Session() as db:
            provider = db.get(ImageProviderConnection, self.provider_id)
            provider.enabled = False
            db.commit()
        with patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", self.fernet_key):
            with self.assertRaises(ProviderError) as raised:
                prepare_provider_execution_context(
                    self._claim(),
                    registry=provider_registry,
                    db_factory=self.Session,
                    network_policy=self._policy(),
                )
        self.assertEqual("provider_unavailable", raised.exception.code)

    def test_tampered_credential_is_soft_disabled_and_never_reaches_network(self) -> None:
        import config
        from canvas_models import ImageProviderConnection
        from services.canvas.generation.worker import prepare_provider_execution_context
        from services.canvas.provider_schemas import ProviderError
        from services.canvas.providers.registry import provider_registry

        with self.Session() as db:
            provider = db.get(ImageProviderConnection, self.provider_id)
            provider.encrypted_credential = "fernet:v1:not-a-valid-token"
            db.commit()
        with patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", self.fernet_key):
            with self.assertRaises(ProviderError) as raised:
                prepare_provider_execution_context(
                    self._claim(),
                    registry=provider_registry,
                    db_factory=self.Session,
                    network_policy=self._policy(),
                )
        self.assertEqual("provider_missing_credential", raised.exception.code)
        with self.Session() as db:
            provider = db.get(ImageProviderConnection, self.provider_id)
            self.assertFalse(provider.enabled)
            self.assertEqual(2, provider.config_version)


if __name__ == "__main__":
    unittest.main()
