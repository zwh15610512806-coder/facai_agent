"""Recursive allow-safe payload redaction for normalized and archived data."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any


class PayloadSafetyError(ValueError):
    """Reports only the unsafe key path, never its associated value."""


_BANNED_NORMALIZED_KEYS = {
    "buyername",
    "receivername",
    "consigneename",
    "mobile",
    "mobilenumber",
    "mobilephone",
    "phone",
    "phonenumber",
    "telephone",
    "idcard",
    "identitycard",
    "detailaddress",
    "detailedaddress",
    "fulladdress",
    "shippingaddress",
    "accesstoken",
    "refreshtoken",
    "appsecret",
    "clientsecret",
    "authorizationcode",
    "authcode",
    "cookie",
    "cookies",
    "setcookie",
    "ciphertext",
}
_SENSITIVE_PARTY_PREFIXES = ("buyer", "receiver", "consignee")
_SENSITIVE_PARTY_FIELDS = {
    "name",
    "fullname",
    "address",
    "fulladdress",
    "detailaddress",
    "detailedaddress",
}


def normalize_payload_key(key: str) -> str:
    normalized = unicodedata.normalize("NFKC", key).casefold()
    return "".join(
        character
        for character in normalized
        if "a" <= character <= "z" or "0" <= character <= "9"
    )


def is_banned_payload_key(
    key: object,
    *,
    parent_key: object | None = None,
    sensitive_party_context: bool = False,
) -> bool:
    if not isinstance(key, str):
        return False
    normalized = normalize_payload_key(key)
    if normalized in _BANNED_NORMALIZED_KEYS:
        return True
    parent_normalized = (
        normalize_payload_key(parent_key) if isinstance(parent_key, str) else ""
    )
    if (
        sensitive_party_context
        or parent_normalized.startswith(_SENSITIVE_PARTY_PREFIXES)
    ) and normalized in _SENSITIVE_PARTY_FIELDS:
        return True
    if any(
        marker in normalized
        for marker in (
            "accesstoken",
            "refreshtoken",
            "appsecret",
            "clientsecret",
            "authorizationcode",
            "ciphertext",
            "cookie",
            "idcard",
            "identitycard",
            "detailaddress",
            "detailedaddress",
            "fulladdress",
            "phone",
            "mobile",
        )
    ):
        return True
    if normalized.startswith(("buyer", "receiver", "consignee")) and normalized.endswith("name"):
        return True
    return False


def _redact_payload(
    payload: Any,
    *,
    parent_key: object | None,
    sensitive_party_context: bool,
) -> Any:
    current_party_context = sensitive_party_context or (
        isinstance(parent_key, str)
        and normalize_payload_key(parent_key).startswith(_SENSITIVE_PARTY_PREFIXES)
    )
    if isinstance(payload, Mapping):
        return {
            key: _redact_payload(
                value,
                parent_key=key,
                sensitive_party_context=current_party_context,
            )
            for key, value in payload.items()
            if not is_banned_payload_key(
                key,
                parent_key=parent_key,
                sensitive_party_context=current_party_context,
            )
        }
    if isinstance(payload, list):
        return [
            _redact_payload(
                value,
                parent_key=parent_key,
                sensitive_party_context=current_party_context,
            )
            for value in payload
        ]
    if isinstance(payload, tuple):
        return tuple(
            _redact_payload(
                value,
                parent_key=parent_key,
                sensitive_party_context=current_party_context,
            )
            for value in payload
        )
    return payload


def redact_payload(payload: Any) -> Any:
    """Return a deep redacted copy while preserving safe normalized fields."""

    return _redact_payload(
        payload,
        parent_key=None,
        sensitive_party_context=False,
    )


def _key_path(parent: str, key: object) -> str:
    if isinstance(key, str) and key.isidentifier():
        return f"{parent}.{key}"
    escaped = str(key).replace("\\", "\\\\").replace("'", "\\'")
    return f"{parent}['{escaped}']"


def _find_unsafe_key(
    payload: Any,
    path: str,
    *,
    parent_key: object | None,
    sensitive_party_context: bool,
) -> str | None:
    current_party_context = sensitive_party_context or (
        isinstance(parent_key, str)
        and normalize_payload_key(parent_key).startswith(_SENSITIVE_PARTY_PREFIXES)
    )
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            child_path = _key_path(path, key)
            if is_banned_payload_key(
                key,
                parent_key=parent_key,
                sensitive_party_context=current_party_context,
            ):
                return child_path
            unsafe = _find_unsafe_key(
                value,
                child_path,
                parent_key=key,
                sensitive_party_context=current_party_context,
            )
            if unsafe is not None:
                return unsafe
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            unsafe = _find_unsafe_key(
                value,
                f"{path}[{index}]",
                parent_key=parent_key,
                sensitive_party_context=current_party_context,
            )
            if unsafe is not None:
                return unsafe
    return None


def assert_payload_safe(payload: Any) -> None:
    """Reject a payload containing banned key names without exposing values."""

    unsafe_path = _find_unsafe_key(
        payload,
        "$",
        parent_key=None,
        sensitive_party_context=False,
    )
    if unsafe_path is not None:
        raise PayloadSafetyError(f"Unsafe payload key: {unsafe_path}")


__all__ = [
    "PayloadSafetyError",
    "assert_payload_safe",
    "is_banned_payload_key",
    "normalize_payload_key",
    "redact_payload",
]
