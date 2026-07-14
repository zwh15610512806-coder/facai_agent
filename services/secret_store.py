"""Protect application secrets with Windows DPAPI.

Ciphertext is bound to the Windows account running the service.  The database
therefore never contains a reusable provider API key in plaintext.
"""
from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

# Ciphertext format marker, not a password.
SECRET_PREFIX = "dpapi:v1:"  # nosec B105
_ENTROPY = b"facai-agent-local:ai-interface-key:v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecretStorageError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def is_protected_secret(value: str | None) -> bool:
    return (value or "").startswith(SECRET_PREFIX)


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _crypt(data: bytes, *, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise SecretStorageError("DPAPI secret storage is available only on Windows")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, input_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    output_blob = _DataBlob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = function(
            ctypes.byref(input_blob),
            "facai-agent-local",
            ctypes.byref(entropy_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
    else:
        description = ctypes.c_wchar_p()
        ok = function(
            ctypes.byref(input_blob),
            ctypes.byref(description),
            ctypes.byref(entropy_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
    # Keep the backing buffers alive until the native call has completed.
    _ = input_buffer, entropy_buffer
    if not ok:
        raise SecretStorageError(str(ctypes.WinError()))
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def protect_secret(value: str) -> str:
    value = (value or "").strip()
    if not value or is_protected_secret(value):
        return value
    encrypted = _crypt(value.encode("utf-8"), protect=True)
    return SECRET_PREFIX + base64.urlsafe_b64encode(encrypted).decode("ascii")


def reveal_secret(value: str | None) -> str:
    value = (value or "").strip()
    if not value or not is_protected_secret(value):
        # Legacy plaintext is accepted only so startup migration can encrypt it.
        return value
    try:
        encrypted = base64.urlsafe_b64decode(value[len(SECRET_PREFIX):].encode("ascii"))
        return _crypt(encrypted, protect=False).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise SecretStorageError("Invalid DPAPI secret payload") from exc
