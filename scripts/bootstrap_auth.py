"""Enable or rotate role authentication in .env without printing secrets."""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ROLE_KEYS = ("FACAI_ADMIN_TOKEN", "FACAI_OPERATOR_TOKEN", "FACAI_VIEWER_TOKEN")


def _token() -> str:
    return secrets.token_urlsafe(36)


def bootstrap_auth(path: Path = ENV_PATH, *, rotate: bool = False) -> tuple[str, ...]:
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    replacements = {"FACAI_AUTH_ENABLED": "1"}
    existing: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        existing[key.strip()] = value.strip()
    created = []
    for key in ROLE_KEYS:
        value = existing.get(key, "")
        if rotate or not value or value.lower().startswith("change-me"):
            replacements[key] = _token()
            created.append(key)

    output = []
    seen = set()
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")

    temporary = path.with_suffix(".env.tmp")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)
    return tuple(created)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Replace all existing role tokens; active sessions become invalid.",
    )
    args = parser.parse_args()
    created = bootstrap_auth(rotate=args.rotate)
    print("authentication enabled; generated roles: " + (", ".join(created) or "none"))
    print("tokens were written only to the gitignored .env file")
