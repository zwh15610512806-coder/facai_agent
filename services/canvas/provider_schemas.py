"""Credential-safe DTOs shared by Product Canvas image providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class ModelCapabilities:
    text_to_image: bool
    image_to_image: bool
    mask_edit: bool
    allowed_ratios: tuple[str, ...]
    allowed_sizes: tuple[str, ...]
    min_width: int | None
    max_width: int | None
    min_height: int | None
    max_height: int | None
    max_quantity: int
    max_reference_images: int
    reference_transfer: Literal["none", "bytes", "base64", "public_url"]
    protocol: Literal["sync", "async", "both"]
    supports_cancel: bool
    supports_idempotency: bool
    supports_idempotency_lookup: bool
    concurrency_limit: int
    price_metadata: dict[str, object] | None


@dataclass(frozen=True)
class ProviderGenerationRequest:
    prompt: str
    size: str
    quantity: int = 1
    reference_images: tuple[bytes | str, ...] = ()
    upstream_idempotency_key: str | None = None


class ProviderTransport(Protocol):
    async def request(self, **kwargs: object): ...


@dataclass(frozen=True)
class ProviderRuntime:
    api_key: str = field(repr=False)
    transport: ProviderTransport = field(repr=False)


@dataclass(frozen=True, repr=False)
class ControlledRemoteImage:
    remote_url: str

    def __repr__(self) -> str:
        return "ControlledRemoteImage(remote_url=<redacted>)"


@dataclass(frozen=True, repr=False)
class ControlledImageBytes:
    """Validated-by-boundary image bytes for deterministic fake/local Providers."""

    data: bytes = field(repr=False)

    def __repr__(self) -> str:
        return "ControlledImageBytes(data=<redacted>)"


@dataclass(frozen=True)
class ProviderSubmission:
    status: Literal["pending", "completed"]
    request_id: str | None = None
    external_task_id: str | None = None
    image: ControlledRemoteImage | ControlledImageBytes | None = None


@dataclass(frozen=True)
class ProviderPollResult:
    kind: Literal["pending", "completed", "failed", "unsupported"]
    image: ControlledRemoteImage | ControlledImageBytes | None = None


@dataclass(frozen=True)
class ProviderCancelResult:
    kind: Literal["cancelled", "already_terminal", "unsupported"]


@dataclass(frozen=True)
class ProviderRecoveryFoundPending:
    kind: Literal["found_pending"] = "found_pending"
    submission: ProviderSubmission | None = None


@dataclass(frozen=True)
class ProviderRecoveryFoundCompleted:
    kind: Literal["found_completed"] = "found_completed"
    image: ControlledRemoteImage | None = None


@dataclass(frozen=True)
class ProviderRecoveryNotFound:
    kind: Literal["not_found"] = "not_found"


@dataclass(frozen=True)
class ProviderRecoveryUnsupported:
    kind: Literal["unsupported"] = "unsupported"


ProviderRecoveryResult: TypeAlias = (
    ProviderRecoveryFoundPending
    | ProviderRecoveryFoundCompleted
    | ProviderRecoveryNotFound
    | ProviderRecoveryUnsupported
)


class ProviderError(RuntimeError):
    """A normalized Provider failure containing only operator-safe text."""

    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.status_code = status_code


class ProviderRequestValidationError(ProviderError, ValueError):
    pass


ProviderAvailability = Literal[
    "available",
    "disabled",
    "missing_credential",
    "invalid_configuration",
    "unsupported_local_reference",
]


class _StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


CredentialFields = Annotated[dict[str, str], Field(min_length=1, max_length=32)]
DeclarativeProviderConfiguration: TypeAlias = dict[str, object]


class ProviderCreate(_StrictSchema):
    adapter_type: str = Field(min_length=1, max_length=100, alias="adapterType")
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=2048, alias="baseUrl")
    auth_type: Literal["bearer", "api_key", "none"] = Field(alias="authType")
    credential: CredentialFields | None = None
    credential_hint: str | None = Field(default=None, max_length=200, alias="credentialHint")
    enabled: bool = True

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: CredentialFields | None) -> CredentialFields | None:
        if value is None:
            return None
        for key, secret in value.items():
            if (
                not key
                or len(key) > 100
                or not secret
                or len(secret) > 8192
            ):
                raise ValueError("credential fields must be bounded non-empty strings")
        return value


class ProviderUpdate(_StrictSchema):
    adapter_type: str | None = Field(default=None, min_length=1, max_length=100, alias="adapterType")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048, alias="baseUrl")
    auth_type: Literal["bearer", "api_key", "none"] | None = Field(default=None, alias="authType")
    credential: CredentialFields | None = None
    credential_hint: str | None = Field(default=None, max_length=200, alias="credentialHint")
    enabled: bool | None = None

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: CredentialFields | None) -> CredentialFields | None:
        return ProviderCreate.validate_credential(value)


class ModelProfileCreate(_StrictSchema):
    model_id: str = Field(min_length=1, max_length=200, alias="modelId")
    display_name: str = Field(min_length=1, max_length=200, alias="displayName")
    capabilities: dict[str, object]
    config: dict[str, object] = Field(default_factory=dict)
    enabled: bool = True


class ModelProfileUpdate(_StrictSchema):
    model_id: str | None = Field(default=None, min_length=1, max_length=200, alias="modelId")
    display_name: str | None = Field(default=None, min_length=1, max_length=200, alias="displayName")
    capabilities: dict[str, object] | None = None
    config: dict[str, object] | None = None
    enabled: bool | None = None


class ProviderView(_StrictSchema):
    id: str
    adapter_type: str = Field(alias="adapterType")
    name: str
    base_url: str = Field(alias="baseUrl")
    auth_type: str = Field(alias="authType")
    enabled: bool
    config_version: int = Field(alias="configVersion")
    credential_configured: bool = Field(alias="credentialConfigured")
    credential_hint: str | None = Field(default=None, alias="credentialHint")


class ModelProfileView(_StrictSchema):
    id: str
    provider_id: str = Field(alias="providerId")
    model_id: str = Field(alias="modelId")
    display_name: str = Field(alias="displayName")
    enabled: bool
    config_version: int = Field(alias="configVersion")


class ProviderTestRequest(_StrictSchema):
    allow_paid_probe: bool = Field(default=False, alias="allowPaidProbe")


class ProviderTestResult(_StrictSchema):
    status: Literal["configuration_ready", "disabled", "missing_credential"]
    paid_probe_required: bool = Field(default=False, alias="paidProbeRequired")


class ProviderCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str
    enabled: bool
    availability: ProviderAvailability
    availability_reason: str | None = Field(default=None, alias="availabilityReason")
    config_version: int = Field(alias="configVersion")


class ModelCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    provider_id: str = Field(alias="providerId")
    model_id: str = Field(alias="modelId")
    display_name: str = Field(alias="displayName")
    enabled: bool
    availability: ProviderAvailability
    availability_reason: str | None = Field(default=None, alias="availabilityReason")
    config_version: int = Field(alias="configVersion")
    capabilities: dict[str, object]
    price_metadata: dict[str, object] | None = Field(default=None, alias="priceMetadata")


__all__ = [
    "ControlledRemoteImage",
    "ControlledImageBytes",
    "DeclarativeProviderConfiguration",
    "ModelCapabilities",
    "ModelProfileCreate",
    "ModelProfileUpdate",
    "ModelProfileView",
    "ProviderCancelResult",
    "ProviderCatalogEntry",
    "ProviderCreate",
    "ProviderError",
    "ProviderGenerationRequest",
    "ProviderPollResult",
    "ProviderRecoveryFoundCompleted",
    "ProviderRecoveryFoundPending",
    "ProviderRecoveryNotFound",
    "ProviderRecoveryResult",
    "ProviderRecoveryUnsupported",
    "ProviderRequestValidationError",
    "ProviderRuntime",
    "ProviderSubmission",
    "ProviderTestRequest",
    "ProviderTestResult",
    "ProviderTransport",
    "ProviderUpdate",
    "ProviderView",
    "ModelCatalogEntry",
]
