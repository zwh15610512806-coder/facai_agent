"""Idempotent built-in image Provider/Profile bootstrap."""
from __future__ import annotations

import json
from dataclasses import asdict

from canvas_models import ImageModelProfile, ImageProviderConnection
from services.canvas.providers.registry import provider_registry
from services.canvas.providers.seedream import SeedreamAdapter


BUILTIN_SEEDREAM_PROVIDER_ID = "builtin-seedream"
BUILTIN_SEEDREAM_MODEL_PROFILE_ID = "builtin-seedream-5-pro"
BUILTIN_PROVIDER_CONFIG_VERSION = 1
BUILTIN_MODEL_CONFIG_VERSION = 1


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def bootstrap_builtin_image_profiles(db_factory) -> None:
    """Create/upgrade authoritative built-ins without changing enable flags."""

    adapter = SeedreamAdapter()
    with db_factory() as db:
        provider = db.get(ImageProviderConnection, BUILTIN_SEEDREAM_PROVIDER_ID)
        if provider is None:
            provider = ImageProviderConnection(
                id=BUILTIN_SEEDREAM_PROVIDER_ID,
                adapter_type=adapter.adapter_type,
                name="火山方舟 Seedream",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                auth_type="bearer",
                encrypted_credential=None,
                environment_credential_ref="ARK_API_KEY",
                credential_hint="Ark API environment credential",
                enabled=True,
                config_version=BUILTIN_PROVIDER_CONFIG_VERSION,
            )
            db.add(provider)
        else:
            provider.adapter_type = adapter.adapter_type
            provider.name = "火山方舟 Seedream"
            provider.base_url = "https://ark.cn-beijing.volces.com/api/v3"
            provider.auth_type = "bearer"
            provider.encrypted_credential = None
            provider.environment_credential_ref = "ARK_API_KEY"
            provider.credential_hint = "Ark API environment credential"
            provider.config_version = BUILTIN_PROVIDER_CONFIG_VERSION

        # ``SessionLocal`` intentionally disables autoflush.  Persist the
        # provider before adding a profile with its foreign key so cold starts
        # remain valid with SQLite foreign-key enforcement enabled.
        db.flush()
        model = db.get(ImageModelProfile, BUILTIN_SEEDREAM_MODEL_PROFILE_ID)
        if model is None:
            model = ImageModelProfile(
                id=BUILTIN_SEEDREAM_MODEL_PROFILE_ID,
                provider_id=BUILTIN_SEEDREAM_PROVIDER_ID,
                model_id=adapter.MODEL_ID,
                display_name=adapter.DISPLAY_NAME,
                capabilities_json=_json(asdict(adapter.capabilities)),
                config_json=_json(
                    {
                        "outputFormat": "png",
                        "responseFormat": "url",
                        "watermark": False,
                    }
                ),
                enabled=True,
                config_version=BUILTIN_MODEL_CONFIG_VERSION,
            )
            db.add(model)
        else:
            model.provider_id = BUILTIN_SEEDREAM_PROVIDER_ID
            model.model_id = adapter.MODEL_ID
            model.display_name = adapter.DISPLAY_NAME
            model.capabilities_json = _json(asdict(adapter.capabilities))
            model.config_json = _json(
                {
                    "outputFormat": "png",
                    "responseFormat": "url",
                    "watermark": False,
                }
            )
            model.config_version = BUILTIN_MODEL_CONFIG_VERSION
        db.commit()
    provider_registry.register(adapter)


__all__ = [
    "BUILTIN_MODEL_CONFIG_VERSION",
    "BUILTIN_PROVIDER_CONFIG_VERSION",
    "BUILTIN_SEEDREAM_MODEL_PROFILE_ID",
    "BUILTIN_SEEDREAM_PROVIDER_ID",
    "bootstrap_builtin_image_profiles",
]
