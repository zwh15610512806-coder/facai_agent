"""Versioned credential encryption and buyer identifier pseudonymization."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from enum import Enum

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class CredentialPurpose(str, Enum):
    APP_SECRET = "app_secret"
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"


class CredentialDecryptionError(ValueError):
    """Raised without envelope details when authenticated decryption fails."""


_ENVELOPE_KEYS = {"v", "alg", "nonce", "ciphertext", "tag"}
_BUYER_HMAC_INFO = b"facai-integrations/buyer-id-hmac/v1"
_ARCHIVE_PAGE_INFO = b"facai-integrations/archive-page/v1"


def _require_master_key(master_key: bytes) -> bytes:
    if not isinstance(master_key, bytes) or len(master_key) != 32:
        raise ValueError("Integration master key must be exactly 32 bytes")
    return master_key


def _require_purpose(purpose: CredentialPurpose) -> CredentialPurpose:
    if not isinstance(purpose, CredentialPurpose):
        raise ValueError("Credential purpose must be a CredentialPurpose")
    return purpose


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(value: object, *, allow_empty: bool = False) -> bytes:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise ValueError
    if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in value):
        raise ValueError
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError from exc
    if _base64url_encode(decoded) != value:
        raise ValueError
    return decoded


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("Duplicate JSON key")
        payload[key] = value
    return payload


def encrypt_credential(
    plaintext: str,
    *,
    master_key: bytes,
    purpose: CredentialPurpose,
) -> str:
    """Encrypt a credential into the exact version-1 A256GCM envelope."""

    key = _require_master_key(master_key)
    credential_purpose = _require_purpose(purpose)
    if not isinstance(plaintext, str):
        raise TypeError("Credential plaintext must be a string")
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(
        nonce,
        plaintext.encode("utf-8"),
        credential_purpose.value.encode("ascii"),
    )
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    envelope = {
        "v": 1,
        "alg": "A256GCM",
        "nonce": _base64url_encode(nonce),
        "ciphertext": _base64url_encode(ciphertext),
        "tag": _base64url_encode(tag),
    }
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)


def decrypt_credential(
    envelope: str,
    *,
    master_key: bytes,
    purpose: CredentialPurpose,
) -> str:
    """Authenticate and decrypt a credential, exposing no failure details."""

    key = _require_master_key(master_key)
    credential_purpose = _require_purpose(purpose)
    try:
        payload = json.loads(envelope, object_pairs_hook=_reject_duplicate_json_keys)
        if not isinstance(payload, dict) or set(payload) != _ENVELOPE_KEYS:
            raise ValueError
        if type(payload["v"]) is not int or payload["v"] != 1:
            raise ValueError
        if payload["alg"] != "A256GCM":
            raise ValueError
        nonce = _base64url_decode(payload["nonce"])
        ciphertext = _base64url_decode(payload["ciphertext"], allow_empty=True)
        tag = _base64url_decode(payload["tag"])
        if len(nonce) != 12 or len(tag) != 16:
            raise ValueError
        plaintext = AESGCM(key).decrypt(
            nonce,
            ciphertext + tag,
            credential_purpose.value.encode("ascii"),
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise CredentialDecryptionError("Unable to decrypt credential") from None


def _buyer_hmac_key(master_key: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_BUYER_HMAC_INFO,
    ).derive(_require_master_key(master_key))


def derive_archive_page_key(master_key: bytes) -> bytes:
    """Derive the AES key dedicated to encrypted page archives."""

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_ARCHIVE_PAGE_INFO,
    ).derive(_require_master_key(master_key))


def buyer_id_digest(external_id: str, *, master_key: bytes) -> str:
    """Return a deterministic HMAC digest using an HKDF-separated subkey."""

    if not isinstance(external_id, str):
        raise TypeError("External buyer ID must be a string")
    derived_key = _buyer_hmac_key(master_key)
    return hmac.new(
        derived_key,
        external_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


__all__ = [
    "CredentialDecryptionError",
    "CredentialPurpose",
    "buyer_id_digest",
    "decrypt_credential",
    "derive_archive_page_key",
    "encrypt_credential",
]
