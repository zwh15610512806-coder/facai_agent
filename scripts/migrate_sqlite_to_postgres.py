"""Operator CLI for verified SQLite-to-PostgreSQL migration."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.migration import (
    MigrationError,
    backup_sqlite_source,
    migrate_sqlite_to_postgres,
)


_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Back up or migrate a SQLite database with verified evidence."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target-env")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backup-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _emit(value: Any) -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True))


def _emit_error(message: str) -> int:
    _emit({"error": message, "ok": False})
    return 1


def _read_target_environment(name: str) -> str:
    return os.environ.get(name, "")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.backup_only:
            if args.target_env is not None:
                return _emit_error("--target-env is not accepted with --backup-only")
            report = backup_sqlite_source(args.source)
        else:
            if not args.target_env:
                return _emit_error(
                    "--target-env is required with --dry-run or --apply"
                )
            if _ENVIRONMENT_NAME.fullmatch(args.target_env) is None:
                return _emit_error(
                    "--target-env must be an environment-variable name"
                )
            target_url = _read_target_environment(args.target_env)
            if not target_url:
                return _emit_error("The named target environment variable is empty")
            report = migrate_sqlite_to_postgres(
                source=args.source,
                target_url=target_url,
                apply=bool(args.apply),
            )
    except MigrationError as exc:
        return _emit_error(str(exc))
    except Exception:
        return _emit_error("Migration command failed safely")

    _emit(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
