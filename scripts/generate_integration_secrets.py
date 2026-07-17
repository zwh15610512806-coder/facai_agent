"""Generate the integration credential-encryption key without touching files."""
from __future__ import annotations

import base64
import secrets


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def main() -> None:
    print(f"FACAI_INTEGRATIONS_MASTER_KEY={_base64url(secrets.token_bytes(32))}")


if __name__ == "__main__":
    main()
