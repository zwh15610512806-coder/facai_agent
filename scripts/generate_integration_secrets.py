"""Generate integration secrets locally without reading or writing configuration files."""

from __future__ import annotations

import base64
import getpass
import hashlib
import secrets


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _hash_admin_password(password: str, *, salt: bytes) -> str:
    encoded = password.encode("utf-8")
    if not encoded or len(encoded) > 512:
        raise ValueError("Password must contain between 1 and 512 UTF-8 bytes")
    digest = hashlib.scrypt(
        encoded,
        salt=salt,
        n=32768,
        r=8,
        p=1,
        dklen=64,
        maxmem=134_217_728,
    )
    return f"$scrypt$n=32768,r=8,p=1${_base64url(salt)}${_base64url(digest)}"


def main() -> None:
    password = getpass.getpass("Integration administrator password: ")
    master_key = secrets.token_bytes(32)
    session_secret = secrets.token_bytes(48)
    password_salt = secrets.token_bytes(16)
    password_hash = _hash_admin_password(password, salt=password_salt)

    print(f"FACAI_INTEGRATIONS_MASTER_KEY={_base64url(master_key)}")
    print(f"FACAI_INTEGRATIONS_SESSION_SECRET={_base64url(session_secret)}")
    print(f"FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH={password_hash}")


if __name__ == "__main__":
    main()
