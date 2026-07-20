"""Fail closed when the service is not running from the verified project venv."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV = (ROOT / ".venv").resolve()
LOCKS = (ROOT / "requirements.lock",)
LOCK_MARKER = VENV / ".facai-requirements.sha256"


def verified_lock_digest() -> str:
    """Hash every reviewed runtime lock in a stable, unambiguous order."""

    digest = hashlib.sha256()
    for lock in LOCKS:
        if not lock.exists():
            raise RuntimeError(f"Required dependency lock is missing: {lock.name}")
        digest.update(lock.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(lock.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def assert_verified_runtime() -> None:
    prefix = Path(sys.prefix).resolve()
    if prefix != VENV:
        raise RuntimeError(
            f"Refusing unisolated interpreter {sys.executable}; run "
            "scripts\\bootstrap-venv.ps1 and start with .venv\\Scripts\\python.exe."
        )
    if not all(lock.exists() for lock in LOCKS) or not LOCK_MARKER.exists():
        raise RuntimeError("The project venv has not been verified against requirements.lock")
    expected = verified_lock_digest()
    installed = LOCK_MARKER.read_text(encoding="ascii").strip()
    if installed != expected:
        raise RuntimeError(
            "requirements.lock changed after the venv was installed; rerun "
            "scripts\\bootstrap-venv.ps1."
        )


if __name__ == "__main__":
    assert_verified_runtime()
    print(f"verified isolated runtime: {sys.executable}")
