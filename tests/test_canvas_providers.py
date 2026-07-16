"""Encrypted third-party Canvas Provider management contracts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import config
from database import Base, get_db
from routers.canvas import router as canvas_router


ACCESS_TOKEN = "canvas-provider-management-test-token"
SECRET = "provider-secret-that-must-not-leak"
CAPABILITIES = {
    "text_to_image": True,
    "image_to_image": True,
    "mask_edit": False,
    "allowed_ratios": ["1:1"],
    "allowed_sizes": ["1024x1024"],
    "min_width": 512,
    "max_width": 2048,
    "min_height": 512,
    "max_height": 2048,
    "max_quantity": 1,
    "max_reference_images": 4,
    "reference_transfer": "bytes",
    "protocol": "sync",
    "supports_cancel": False,
    "supports_idempotency": True,
    "supports_idempotency_lookup": True,
    "concurrency_limit": 2,
    "price_metadata": {"currency": "CNY", "unit": "image"},
}


class ProviderSecretCodecTests(unittest.TestCase):
    def test_encrypts_versioned_json_without_plaintext_and_rejects_bad_master_keys(self) -> None:
        from services.canvas.credentials import (
            ProviderCredentialConfigurationError,
            ProviderSecretCodec,
        )

        key = Fernet.generate_key().decode("ascii")
        with patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", key, create=True):
            codec = ProviderSecretCodec.from_env()
        encrypted = codec.encrypt_json({"apiKey": SECRET})
        self.assertTrue(encrypted.startswith("fernet:v1:"))
        self.assertNotIn(SECRET, encrypted)
        self.assertEqual({"apiKey": SECRET}, codec.decrypt_json(encrypted))

        for value in ("", "not-a-fernet-key", Fernet.generate_key().decode("ascii")[:-1]):
            with self.subTest(value=value):
                with patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", value, create=True):
                    with self.assertRaises(ProviderCredentialConfigurationError):
                        ProviderSecretCodec.from_env()


class CanvasProviderCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401 - register Canvas metadata.

        Base.metadata.create_all(bind=self.engine)
        from services.canvas.credentials import ProviderSecretCodec

        self.codec = ProviderSecretCodec(Fernet(Fernet.generate_key()))

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _provider_create(self, **overrides):
        from services.canvas.provider_schemas import ProviderCreate

        payload = {
            "adapterType": "openai-images-compatible",
            "name": "Vendor One",
            "baseUrl": "https://api.vendor.example/v1",
            "authType": "bearer",
            "credential": {"apiKey": SECRET},
            "credentialHint": "managed API key",
        }
        payload.update(overrides)
        return ProviderCreate.model_validate(payload)

    def _model_create(self, **overrides):
        from services.canvas.provider_schemas import ModelProfileCreate

        payload = {
            "modelId": "vendor-image-pro",
            "displayName": "Vendor Image Pro",
            "capabilities": CAPABILITIES,
            "config": {"responseFormat": "url"},
        }
        payload.update(overrides)
        return ModelProfileCreate.model_validate(payload)

    def test_create_update_disable_and_model_versions_keep_credentials_encrypted(self) -> None:
        from canvas_models import ImageProviderConnection
        from services.canvas.provider_catalog import (
            create_model_profile,
            create_provider,
            disable_provider,
            update_model_profile,
            update_provider,
        )
        from services.canvas.provider_schemas import ModelProfileUpdate, ProviderUpdate

        with self.Session() as db:
            provider = create_provider(db, request=self._provider_create(), codec=self.codec)
            db.commit()
            row = db.get(ImageProviderConnection, provider.id)
            assert row is not None
            first_ciphertext = row.encrypted_credential
            self.assertTrue(first_ciphertext.startswith("fernet:v1:"))
            self.assertNotIn(SECRET, first_ciphertext)
            self.assertTrue(provider.credential_configured)
            self.assertEqual("managed API key", provider.credential_hint)
            self.assertNotIn("environmentCredentialRef", provider.model_dump(by_alias=True))

            unchanged = update_provider(
                db,
                provider_id=provider.id,
                request=ProviderUpdate.model_validate({"name": "Vendor One Renamed"}),
                codec=self.codec,
            )
            self.assertEqual(2, unchanged.config_version)
            self.assertEqual(first_ciphertext, row.encrypted_credential)

            replaced = update_provider(
                db,
                provider_id=provider.id,
                request=ProviderUpdate.model_validate(
                    {"credential": {"apiKey": SECRET + "-rotated"}}
                ),
                codec=self.codec,
            )
            self.assertEqual(3, replaced.config_version)
            self.assertNotEqual(first_ciphertext, row.encrypted_credential)

            model = create_model_profile(
                db, provider_id=provider.id, request=self._model_create()
            )
            self.assertEqual(1, model.config_version)
            changed_model = update_model_profile(
                db,
                model_profile_id=model.id,
                request=ModelProfileUpdate.model_validate({"enabled": False}),
            )
            self.assertFalse(changed_model.enabled)
            self.assertEqual(2, changed_model.config_version)
            disabled = disable_provider(db, provider_id=provider.id)
            self.assertFalse(disabled.enabled)
            self.assertEqual(4, disabled.config_version)
            db.commit()

    def test_bad_ciphertext_soft_disables_without_overwriting_the_evidence(self) -> None:
        from canvas_models import ImageProviderConnection
        from services.canvas.credentials import ProviderSecretCodec
        from services.canvas.provider_catalog import (
            create_provider,
            load_provider_credential,
        )

        with self.Session() as db:
            provider = create_provider(db, request=self._provider_create(), codec=self.codec)
            db.commit()
            row = db.get(ImageProviderConnection, provider.id)
            assert row is not None
            ciphertext = row.encrypted_credential
            other_codec = ProviderSecretCodec(Fernet(Fernet.generate_key()))
            self.assertIsNone(load_provider_credential(db, provider_id=provider.id, codec=other_codec))
            self.assertFalse(row.enabled)
            self.assertEqual(ciphertext, row.encrypted_credential)

    def test_public_url_only_references_are_visible_as_unsupported_for_local_products(self) -> None:
        from services.canvas.provider_catalog import (
            create_model_profile,
            create_provider,
            list_model_catalog,
        )

        with self.Session() as db:
            provider = create_provider(db, request=self._provider_create(), codec=self.codec)
            create_model_profile(
                db,
                provider_id=provider.id,
                request=self._model_create(
                    capabilities={**CAPABILITIES, "reference_transfer": "public_url"}
                ),
            )
            catalog = list_model_catalog(db, provider_id=provider.id)
        self.assertEqual("unsupported_local_reference", catalog[0].availability)
        self.assertIn("local product", catalog[0].availability_reason)

    def test_model_configuration_and_price_metadata_cannot_become_plaintext_secret_storage(self) -> None:
        from canvas_models import ImageModelProfile
        from services.canvas.provider_catalog import (
            ProviderCatalogValidationError,
            create_model_profile,
            create_provider,
        )

        with self.Session() as db:
            provider = create_provider(db, request=self._provider_create(), codec=self.codec)
            for request in (
                self._model_create(config={"apiKey": SECRET}),
                self._model_create(
                    capabilities={
                        **CAPABILITIES,
                        "price_metadata": {"authorization": SECRET},
                    }
                ),
            ):
                with self.subTest(request=request.model_dump(by_alias=True, exclude={"credential"})):
                    with self.assertRaises(ProviderCatalogValidationError):
                        create_model_profile(db, provider_id=provider.id, request=request)
            self.assertEqual([], db.query(ImageModelProfile).all())

    def test_declarative_model_configuration_is_validated_before_persistence(self) -> None:
        from services.canvas.provider_catalog import (
            ProviderCatalogValidationError,
            create_model_profile,
            create_provider,
        )

        configuration = {
            "auth": {"type": "bearer"},
            "submit": {
                "method": "POST", "endpoint": "/v1/images", "format": "json",
                "json": {"model": "{{model_id}}", "prompt": "{{prompt}}"},
            },
            "result": {"mode": "sync", "imagePath": "data[0].url", "imageType": "url"},
        }
        with self.Session() as db:
            provider = create_provider(
                db,
                request=self._provider_create(adapterType="declarative_http"),
                codec=self.codec,
            )
            accepted = create_model_profile(
                db, provider_id=provider.id, request=self._model_create(config=configuration)
            )
            self.assertTrue(accepted.id)
            configuration["submit"]["endpoint"] = "https://evil.example/images"
            with self.assertRaises(ProviderCatalogValidationError):
                create_model_profile(
                    db,
                    provider_id=provider.id,
                    request=self._model_create(modelId="unsafe", config=configuration),
                )

    def test_builtin_environment_credentials_are_read_only_to_management_mutations(self) -> None:
        from services.canvas.provider_catalog import ProviderCatalogConflict, update_provider
        from services.canvas.provider_schemas import ProviderUpdate
        from services.canvas.providers.bootstrap import (
            BUILTIN_SEEDREAM_PROVIDER_ID,
            bootstrap_builtin_image_profiles,
        )

        bootstrap_builtin_image_profiles(self.Session)
        with self.Session() as db:
            with self.assertRaises(ProviderCatalogConflict):
                update_provider(
                    db,
                    provider_id=BUILTIN_SEEDREAM_PROVIDER_ID,
                    request=ProviderUpdate.model_validate({"name": "not allowed"}),
                    codec=self.codec,
                )


class CanvasProviderRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import canvas_models  # noqa: F401 - register Canvas metadata.

        Base.metadata.create_all(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(canvas_router, prefix="/api/canvas")

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        return app

    @staticmethod
    def _payload() -> dict[str, object]:
        return {
            "adapterType": "openai-images-compatible",
            "name": "Route Vendor",
            "baseUrl": "https://api.route-vendor.example/v1",
            "authType": "bearer",
            "credential": {"apiKey": SECRET},
            "credentialHint": "route key",
        }

    def test_paid_routes_redact_credentials_and_reject_environment_variable_fields(self) -> None:
        master_key = Fernet.generate_key().decode("ascii")
        with (
            patch.object(config, "CANVAS_ACCESS_TOKEN", ACCESS_TOKEN, create=True),
            patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", master_key, create=True),
            patch.object(config, "CANVAS_PROVIDER_ALLOWED_HOSTS", ("api.route-vendor.example",), create=True),
            TestClient(self._app()) as client,
        ):
            locked = client.post("/api/canvas/model-providers", json=self._payload())
            self.assertEqual(401, locked.status_code, locked.text)
            for method, path, payload in (
                ("post", "/api/canvas/model-providers/not-found/models", {
                    "modelId": "locked-model", "displayName": "Locked", "capabilities": CAPABILITIES,
                }),
                ("patch", "/api/canvas/models/not-found", {"enabled": False}),
                ("post", "/api/canvas/model-providers/not-found/test", {}),
                ("delete", "/api/canvas/model-providers/not-found", None),
            ):
                with self.subTest(method=method, path=path):
                    request = getattr(client, method)
                    response = request(path) if payload is None else request(path, json=payload)
                    self.assertEqual(401, response.status_code, response.text)
            self.assertEqual(200, client.post(
                "/api/canvas/access/unlock", json={"token": ACCESS_TOKEN}
            ).status_code)
            invalid = client.post(
                "/api/canvas/model-providers",
                json={**self._payload(), "environmentCredentialRef": "AWS_SECRET_ACCESS_KEY"},
            )
            self.assertEqual(422, invalid.status_code, invalid.text)
            rejected_host = client.post(
                "/api/canvas/model-providers",
                json={**self._payload(), "baseUrl": "https://unapproved.example/v1"},
            )
            self.assertEqual(422, rejected_host.status_code, rejected_host.text)
            created = client.post("/api/canvas/model-providers", json=self._payload())
            self.assertEqual(201, created.status_code, created.text)
            provider = created.json()
            self.assertTrue(provider["credentialConfigured"])
            self.assertEqual("route key", provider["credentialHint"])
            serialized = json.dumps(provider, ensure_ascii=False)
            self.assertNotIn(SECRET, serialized)
            self.assertNotIn("environmentCredentialRef", serialized)

            provider_id = provider["id"]
            updated = client.patch(
                f"/api/canvas/model-providers/{provider_id}",
                json={"name": "Route Vendor Updated"},
            )
            self.assertEqual(200, updated.status_code, updated.text)
            tested = client.post(
                f"/api/canvas/model-providers/{provider_id}/test", json={}
            )
            self.assertEqual(200, tested.status_code, tested.text)
            self.assertEqual("configuration_ready", tested.json()["status"])
            deleted = client.delete(f"/api/canvas/model-providers/{provider_id}")
            self.assertEqual(200, deleted.status_code, deleted.text)
            self.assertFalse(deleted.json()["enabled"])

    def test_missing_master_key_refuses_credential_save_without_creating_a_plaintext_row(self) -> None:
        with (
            patch.object(config, "CANVAS_ACCESS_TOKEN", ACCESS_TOKEN, create=True),
            patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", "", create=True),
            patch.object(config, "CANVAS_PROVIDER_ALLOWED_HOSTS", ("api.route-vendor.example",), create=True),
            TestClient(self._app()) as client,
        ):
            self.assertEqual(200, client.post(
                "/api/canvas/access/unlock", json={"token": ACCESS_TOKEN}
            ).status_code)
            refused = client.post("/api/canvas/model-providers", json=self._payload())
            self.assertEqual(503, refused.status_code, refused.text)
            self.assertNotIn(SECRET, refused.text)
            self.assertEqual([], client.get("/api/canvas/model-providers").json())

    def test_missing_master_key_still_allows_an_administrator_to_disable_existing_provider(self) -> None:
        from services.canvas.credentials import ProviderSecretCodec
        from services.canvas.provider_catalog import create_provider
        from services.canvas.provider_schemas import ProviderCreate

        codec = ProviderSecretCodec(Fernet(Fernet.generate_key()))
        with self.Session() as db:
            provider = create_provider(
                db,
                request=ProviderCreate.model_validate(self._payload()),
                codec=codec,
            )
            db.commit()
            provider_id = provider.id

        with (
            patch.object(config, "CANVAS_ACCESS_TOKEN", ACCESS_TOKEN, create=True),
            patch.object(config, "CANVAS_PROVIDER_SECRET_KEY", "", create=True),
            TestClient(self._app()) as client,
        ):
            self.assertEqual(200, client.post(
                "/api/canvas/access/unlock", json={"token": ACCESS_TOKEN}
            ).status_code)
            disabled = client.delete(f"/api/canvas/model-providers/{provider_id}")
        self.assertEqual(200, disabled.status_code, disabled.text)
        self.assertFalse(disabled.json()["enabled"])

    def test_backup_documentation_covers_key_database_assets_and_restore_checks(self) -> None:
        document = (Path(__file__).resolve().parents[1] / "docs" / "canvas-backup-and-provider-operations.md").read_text(encoding="utf-8")
        for required in (
            "CANVAS_PROVIDER_SECRET_KEY",
            "SQLite",
            "data/canvas_projects/",
            "rembg",
            "SHA",
            "decrypt",
            "paid",
        ):
            with self.subTest(required=required):
                self.assertIn(required, document)


if __name__ == "__main__":
    unittest.main()
