"""Fail closed when the service is not running from the verified project venv."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV = (ROOT / ".venv").resolve()
LOCK = ROOT / "requirements.lock"
LOCK_MARKER = VENV / ".facai-requirements.sha256"


def assert_verified_runtime() -> None:
    prefix = Path(sys.prefix).resolve()
    if prefix != VENV:
        raise RuntimeError(
            f"Refusing unisolated interpreter {sys.executable}; run "
            "scripts\\bootstrap-venv.ps1 and start with .venv\\Scripts\\python.exe."
        )
    if not LOCK.exists() or not LOCK_MARKER.exists():
        raise RuntimeError("The project venv has not been verified against requirements.lock")
    expected = hashlib.sha256(LOCK.read_bytes()).hexdigest()
    installed = LOCK_MARKER.read_text(encoding="ascii").strip()
    if installed != expected:
        raise RuntimeError(
            "requirements.lock changed after the venv was installed; rerun "
            "scripts\\bootstrap-venv.ps1."
        )


if __name__ == "__main__":
    assert_verified_runtime()
    print(f"verified isolated runtime: {sys.executable}")
