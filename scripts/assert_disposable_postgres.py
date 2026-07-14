"""Validate a disposable PostgreSQL target without exposing its credentials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.engine import make_url

from integrations.db_safety import assert_disposable_postgres


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assert that a PostgreSQL URL targets an acknowledged test database."
    )
    parser.add_argument("--env", required=True, help="Environment variable containing the URL")
    parser.add_argument(
        "--ack-env",
        required=True,
        help="Environment variable containing the exact database acknowledgement",
    )
    arguments = parser.parse_args(argv)

    raw_url = assert_disposable_postgres(
        url_env=arguments.env,
        acknowledgement_env=arguments.ack_env,
    )
    url = make_url(raw_url)
    database = unquote(url.database or "")
    print(f"host={url.host} database={database} safe=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
