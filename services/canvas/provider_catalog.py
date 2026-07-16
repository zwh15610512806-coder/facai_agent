"""Credential-safe Provider catalog and protected configuration mutations."""
from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from canvas_models import ImageModelProfile, ImageProviderConnection
from services.canvas.credentials import (
    ProviderCredentialConfigurationError,
    ProviderCredentialDecryptionError,
    ProviderSecretCodec,
)
from services.canvas.provider_schemas import (
    ModelCapabilities,
    ModelCatalogEntry,
    ModelProfileCreate,
    ModelProfileUpdate,
    ModelProfileView,
    ProviderAvailability,
    ProviderCatalogEntry,
    ProviderCreate,
    ProviderTestResult,
    ProviderUpdate,
    ProviderView,
)
from services.canvas.providers.seedream import resolve_seedream_api_key


class ProviderCatalogNotFound(LookupError):
    pass


class ProviderCatalogValidationError(ValueError):
    pass


class ProviderCatalogConflict(RuntimeError):
    pass


_UNSAFE_PRICE_KEY_MARKERS = (
    "credential",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "environment",
    "base_url",
)


def _safe_public_configuration(value: object, *, field: str) -> dict[str, object]:
    """Canonicalize non-secret configuration and reject credential-shaped keys."""

    if not isinstance(value, dict):
        raise ProviderCatalogValidationError(f"{field} must be an object")

    def clean(item: object) -> object:
        if item is None or isinstance(item, (bool, int, float, str)):
            return item
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            result: dict[str, object] = {}
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    raise ProviderCatalogValidationError(f"{field} has an invalid key")
                normalized = key.lower().replace("-", "_")
                if any(marker in normalized for marker in _UNSAFE_PRICE_KEY_MARKERS):
                    raise ProviderCatalogValidationError(
                        f"{field} must not contain credential-shaped keys"
                    )
                result[key] = clean(child)
            return result
        raise ProviderCatalogValidationError(f"{field} contains an unsupported value")

    return clean(value)  # type: ignore[return-value]


def _credential_available(provider: ImageProviderConnection) -> bool:
    if provider.adapter_type == "seedream":
        return bool(resolve_seedream_api_key())
    # A connection may explicitly be configured for an offline/no-auth local
    # adapter.  The isolated E2E runtime is the only current writer of such a
    # connection; ordinary third-party adapters still require their protected
    # configuration service to activate credentials.
    if (
        provider.auth_type == "none"
        and provider.encrypted_credential is None
        and provider.environment_credential_ref is None
    ):
        return True
    return provider.encrypted_credential is not None


def _availability(
    provider: ImageProviderConnection,
    *,
    model: ImageModelProfile | None = None,
    configuration_valid: bool = True,
) -> tuple[ProviderAvailability, str | None]:
    if not provider.enabled or model is not None and not model.enabled:
        return "disabled", "This Provider or model has been disabled"
    if not configuration_valid:
        return "invalid_configuration", "This model configuration is invalid"
    if not _credential_available(provider):
        return "missing_credential", "A server-side credential is required"
    if (
        model is not None
        and _reference_transfer(model) == "public_url"
        and _max_reference_images(model) > 0
    ):
        return (
            "unsupported_local_reference",
            "This model only accepts public URLs and cannot receive local product references",
        )
    return "available", None


def _reference_transfer(model: ImageModelProfile) -> str | None:
    try:
        document = json.loads(model.capabilities_json)
        value = document.get("reference_transfer") if isinstance(document, dict) else None
        return value if isinstance(value, str) else None
    except json.JSONDecodeError:
        return None


def _max_reference_images(model: ImageModelProfile) -> int:
    try:
        document = json.loads(model.capabilities_json)
        value = document.get("max_reference_images") if isinstance(document, dict) else 0
        return value if type(value) is int else 0
    except json.JSONDecodeError:
        return 0


def _json(value: object, *, field: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ProviderCatalogValidationError(f"{field} must be JSON serializable") from exc


def _capabilities_json(value: dict[str, object]) -> str:
    try:
        normalized = asdict(ModelCapabilities(**value))
    except (TypeError, ValueError) as exc:
        raise ProviderCatalogValidationError("model capabilities are invalid") from exc
    try:
        normalized["price_metadata"] = _safe_price_metadata(
            normalized.get("price_metadata")
        )
    except ValueError as exc:
        raise ProviderCatalogValidationError("model capabilities are invalid") from exc
    return _json(normalized, field="model capabilities")


def _model_configuration_json(
    provider: ImageProviderConnection,
    value: object,
) -> str:
    configuration = _safe_public_configuration(value, field="model config")
    if provider.adapter_type == "declarative_http":
        try:
            from services.canvas.providers.declarative_http import (
                DeclarativeConfigurationError,
                compile_declarative_configuration,
            )

            compile_declarative_configuration(configuration)
        except DeclarativeConfigurationError as exc:
            raise ProviderCatalogValidationError("declarative model config is invalid") from exc
    return _json(configuration, field="model config")


def _provider_view(provider: ImageProviderConnection) -> ProviderView:
    return ProviderView(
        id=provider.id,
        adapterType=provider.adapter_type,
        name=provider.name,
        baseUrl=provider.base_url,
        authType=provider.auth_type,
        enabled=bool(provider.enabled),
        configVersion=provider.config_version,
        credentialConfigured=bool(
            provider.encrypted_credential or provider.environment_credential_ref
        ),
        credentialHint=provider.credential_hint,
    )


def _model_view(model: ImageModelProfile) -> ModelProfileView:
    return ModelProfileView(
        id=model.id,
        providerId=model.provider_id,
        modelId=model.model_id,
        displayName=model.display_name,
        enabled=bool(model.enabled),
        configVersion=model.config_version,
    )


def _provider_or_raise(db: Session, provider_id: str) -> ImageProviderConnection:
    provider = db.get(ImageProviderConnection, provider_id)
    if provider is None:
        raise ProviderCatalogNotFound(provider_id)
    return provider


def _reject_builtin_mutation(provider: ImageProviderConnection) -> None:
    if provider.environment_credential_ref is not None:
        raise ProviderCatalogConflict("Built-in Provider connection details are read-only")


def create_provider(
    db: Session,
    *,
    request: ProviderCreate,
    codec: ProviderSecretCodec | None,
) -> ProviderView:
    if request.auth_type == "none":
        if request.credential is not None:
            raise ProviderCatalogValidationError("no-auth Provider cannot store credentials")
        encrypted_credential = None
    else:
        if request.credential is None:
            raise ProviderCatalogValidationError("Provider credential is required")
        if codec is None:
            raise ProviderCredentialConfigurationError(
                "Canvas Provider secret key is not configured"
            )
        encrypted_credential = codec.encrypt_json(request.credential)
    provider = ImageProviderConnection(
        adapter_type=request.adapter_type,
        name=request.name,
        base_url=request.base_url,
        auth_type=request.auth_type,
        encrypted_credential=encrypted_credential,
        environment_credential_ref=None,
        credential_hint=request.credential_hint,
        enabled=request.enabled,
        config_version=1,
    )
    db.add(provider)
    db.flush()
    return _provider_view(provider)


def update_provider(
    db: Session,
    *,
    provider_id: str,
    request: ProviderUpdate,
    codec: ProviderSecretCodec | None,
) -> ProviderView:
    provider = _provider_or_raise(db, provider_id)
    _reject_builtin_mutation(provider)
    fields = request.model_fields_set
    changed = False
    for field_name, attribute in (
        ("adapter_type", "adapter_type"),
        ("name", "name"),
        ("base_url", "base_url"),
        ("credential_hint", "credential_hint"),
        ("enabled", "enabled"),
    ):
        if field_name in fields:
            value = getattr(request, field_name)
            if getattr(provider, attribute) != value:
                setattr(provider, attribute, value)
                changed = True

    next_auth_type = request.auth_type if "auth_type" in fields else provider.auth_type
    if provider.auth_type != next_auth_type:
        provider.auth_type = next_auth_type
        changed = True
    if next_auth_type == "none":
        if "credential" in fields and request.credential is not None:
            raise ProviderCatalogValidationError("no-auth Provider cannot store credentials")
        if provider.encrypted_credential is not None:
            provider.encrypted_credential = None
            changed = True
    elif "credential" in fields:
        if request.credential is None:
            raise ProviderCatalogValidationError("credential replacement cannot be empty")
        if codec is None:
            raise ProviderCredentialConfigurationError(
                "Canvas Provider secret key is not configured"
            )
        encrypted = codec.encrypt_json(request.credential)
        if provider.encrypted_credential != encrypted:
            provider.encrypted_credential = encrypted
            changed = True
    elif provider.encrypted_credential is None:
        raise ProviderCatalogValidationError("Provider credential is required")

    if changed:
        provider.config_version += 1
        db.flush()
    return _provider_view(provider)


def disable_provider(db: Session, *, provider_id: str) -> ProviderView:
    provider = _provider_or_raise(db, provider_id)
    if provider.enabled:
        provider.enabled = False
        provider.config_version += 1
        db.flush()
    return _provider_view(provider)


def create_model_profile(
    db: Session,
    *,
    provider_id: str,
    request: ModelProfileCreate,
) -> ModelProfileView:
    provider = _provider_or_raise(db, provider_id)
    existing = db.scalar(
        select(ImageModelProfile).where(
            ImageModelProfile.provider_id == provider_id,
            ImageModelProfile.model_id == request.model_id,
        )
    )
    if existing is not None:
        raise ProviderCatalogConflict("Model ID already exists for this Provider")
    model = ImageModelProfile(
        provider_id=provider_id,
        model_id=request.model_id,
        display_name=request.display_name,
        capabilities_json=_capabilities_json(request.capabilities),
        config_json=_model_configuration_json(provider, request.config),
        enabled=request.enabled,
        config_version=1,
    )
    db.add(model)
    db.flush()
    return _model_view(model)


def update_model_profile(
    db: Session,
    *,
    model_profile_id: str,
    request: ModelProfileUpdate,
) -> ModelProfileView:
    model = db.get(ImageModelProfile, model_profile_id)
    if model is None:
        raise ProviderCatalogNotFound(model_profile_id)
    fields = request.model_fields_set
    changed = False
    if "model_id" in fields and model.model_id != request.model_id:
        duplicate = db.scalar(
            select(ImageModelProfile.id).where(
                ImageModelProfile.provider_id == model.provider_id,
                ImageModelProfile.model_id == request.model_id,
                ImageModelProfile.id != model.id,
            )
        )
        if duplicate is not None:
            raise ProviderCatalogConflict("Model ID already exists for this Provider")
        model.model_id = request.model_id  # type: ignore[assignment]
        changed = True
    if "display_name" in fields and model.display_name != request.display_name:
        model.display_name = request.display_name  # type: ignore[assignment]
        changed = True
    if "capabilities" in fields:
        capabilities_json = _capabilities_json(request.capabilities or {})
        if model.capabilities_json != capabilities_json:
            model.capabilities_json = capabilities_json
            changed = True
    if "config" in fields:
        provider = _provider_or_raise(db, model.provider_id)
        config_json = _model_configuration_json(provider, request.config or {})
        if model.config_json != config_json:
            model.config_json = config_json
            changed = True
    if "enabled" in fields and model.enabled != request.enabled:
        model.enabled = request.enabled  # type: ignore[assignment]
        changed = True
    if changed:
        model.config_version += 1
        db.flush()
    return _model_view(model)


def load_provider_credential(
    db: Session,
    *,
    provider_id: str,
    codec: ProviderSecretCodec,
) -> dict[str, str] | None:
    """Decrypt a custom credential, soft-disabling only tampered ciphertext."""

    provider = _provider_or_raise(db, provider_id)
    if provider.encrypted_credential is None:
        return None
    try:
        return codec.decrypt_json(provider.encrypted_credential)
    except ProviderCredentialDecryptionError:
        if provider.enabled:
            provider.enabled = False
            provider.config_version += 1
            db.flush()
        return None


def provider_test_status(
    db: Session,
    *,
    provider_id: str,
    codec: ProviderSecretCodec | None,
) -> ProviderTestResult:
    """Validate stored configuration without issuing a billable Provider request."""

    provider = _provider_or_raise(db, provider_id)
    if not provider.enabled:
        return ProviderTestResult(status="disabled")
    if provider.encrypted_credential is not None:
        if codec is None:
            return ProviderTestResult(status="missing_credential")
        if load_provider_credential(db, provider_id=provider_id, codec=codec) is None:
            return ProviderTestResult(status="disabled")
    elif not _credential_available(provider):
        return ProviderTestResult(status="missing_credential")
    return ProviderTestResult(status="configuration_ready")


def _safe_price_metadata(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("price metadata must be an object")

    def clean(item: object) -> object:
        if item is None or isinstance(item, (bool, int, float, str)):
            return item
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                normalized = str(key).lower()
                if any(marker in normalized for marker in _UNSAFE_PRICE_KEY_MARKERS):
                    raise ValueError("unsafe price metadata")
                result[str(key)] = clean(child)
            return result
        raise ValueError("unsupported price metadata")

    return clean(value)  # type: ignore[return-value]


def _model_payload(model: ImageModelProfile) -> tuple[dict[str, object], dict[str, object] | None]:
    document = json.loads(model.capabilities_json)
    if not isinstance(document, dict):
        raise ValueError("capabilities must be an object")
    capabilities = ModelCapabilities(**document)
    payload = asdict(capabilities)
    price_metadata = _safe_price_metadata(payload.pop("price_metadata", None))
    return payload, price_metadata


def _stored_model_configuration_is_valid(
    provider: ImageProviderConnection,
    model: ImageModelProfile,
) -> bool:
    try:
        configuration = _parse_json_object(model.config_json)
        if provider.adapter_type == "declarative_http":
            from services.canvas.providers.declarative_http import compile_declarative_configuration

            compile_declarative_configuration(configuration)
        return True
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def _parse_json_object(value: str) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("configuration must be an object")
    return decoded


def list_provider_catalog(db: Session) -> list[ProviderCatalogEntry]:
    providers = db.scalars(
        select(ImageProviderConnection).order_by(
            ImageProviderConnection.name.asc(), ImageProviderConnection.id.asc()
        )
    ).all()
    result: list[ProviderCatalogEntry] = []
    for provider in providers:
        availability, reason = _availability(provider)
        result.append(ProviderCatalogEntry(
            id=provider.id,
            name=provider.name,
            enabled=bool(provider.enabled),
            availability=availability,
            availability_reason=reason,
            config_version=provider.config_version,
        ))
    return result


def list_model_catalog(db: Session, *, provider_id: str) -> list[ModelCatalogEntry]:
    provider = db.get(ImageProviderConnection, provider_id)
    if provider is None:
        raise ProviderCatalogNotFound(provider_id)
    models = db.scalars(
        select(ImageModelProfile)
        .where(ImageModelProfile.provider_id == provider_id)
        .order_by(ImageModelProfile.display_name.asc(), ImageModelProfile.id.asc())
    ).all()
    result: list[ModelCatalogEntry] = []
    for model in models:
        try:
            capabilities, price_metadata = _model_payload(model)
            configuration_valid = _stored_model_configuration_is_valid(provider, model)
        except (TypeError, ValueError, json.JSONDecodeError):
            capabilities = {}
            price_metadata = None
            configuration_valid = False
        availability, reason = _availability(
            provider, model=model, configuration_valid=configuration_valid
        )
        result.append(
            ModelCatalogEntry(
                id=model.id,
                provider_id=provider.id,
                model_id=model.model_id,
                display_name=model.display_name,
                enabled=bool(model.enabled),
                availability=availability,
                availability_reason=reason,
                config_version=model.config_version,
                capabilities=capabilities,
                price_metadata=price_metadata,
            )
        )
    return result


__all__ = [
    "ProviderCatalogNotFound",
    "ProviderCatalogConflict",
    "ProviderCatalogValidationError",
    "create_model_profile",
    "create_provider",
    "disable_provider",
    "list_model_catalog",
    "list_provider_catalog",
    "load_provider_credential",
    "provider_test_status",
    "update_model_profile",
    "update_provider",
]
