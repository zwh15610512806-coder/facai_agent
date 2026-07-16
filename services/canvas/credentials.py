"""Versioned encryption boundary for third-party Canvas Provider secrets."""
from __future__ import annotations

import json
from collections.abc import Mapping

from cryptography.fernet import Fernet, InvalidToken

import config


_CREDENTIAL_PREFIX = "fernet:v1:"


class ProviderCredentialConfigurationError(RuntimeError):
    """The server master key is absent or not a valid Fernet key."""


class ProviderCredentialDecryptionError(RuntimeError):
    """A retained ciphertext cannot be decrypted with the configured key."""


def _validated_secret_fields(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value or len(value) > 32:
        raise ValueError("Provider credential must contain 1-32 secret fields")
    result: dict[str, str] = {}
    for key, secret in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 100
            or not isinstance(secret, str)
            or not secret
            or len(secret) > 8192
        ):
            raise ValueError("Provider credential fields must be non-empty strings")
        result[key] = secret
    return result


class ProviderSecretCodec:
    """Fernet codec whose string representation never includes plaintext."""

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    @classmethod
    def from_env(cls) -> "ProviderSecretCodec":
        value = getattr(config, "CANVAS_PROVIDER_SECRET_KEY", "")
        if not isinstance(value, str) or not value:
            raise ProviderCredentialConfigurationError(
                "Canvas Provider secret key is not configured"
            )
        try:
            return cls(Fernet(value.encode("ascii")))
        except (UnicodeEncodeError, ValueError) as exc:
            raise ProviderCredentialConfigurationError(
                "Canvas Provider secret key is invalid"
            ) from exc

    def encrypt_json(self, secret_fields: Mapping[str, str]) -> str:
        normalized = _validated_secret_fields(secret_fields)
        payload = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return _CREDENTIAL_PREFIX + self._fernet.encrypt(payload).decode("ascii")

    def decrypt_json(self, value: str) -> dict[str, str]:
        if not isinstance(value, str) or not value.startswith(_CREDENTIAL_PREFIX):
            raise ProviderCredentialDecryptionError("Provider credential format is invalid")
        try:
            decoded = self._fernet.decrypt(value[len(_CREDENTIAL_PREFIX):].encode("ascii"))
            document = json.loads(decoded.decode("utf-8"))
            return _validated_secret_fields(document)
        except (InvalidToken, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderCredentialDecryptionError(
                "Provider credential cannot be decrypted"
            ) from exc

    def __repr__(self) -> str:
        return "ProviderSecretCodec(<redacted>)"


__all__ = [
    "ProviderCredentialConfigurationError",
    "ProviderCredentialDecryptionError",
    "ProviderSecretCodec",
]
