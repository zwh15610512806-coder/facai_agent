"""Managed Uvicorn entry point with rotating application logs."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime_environment import load_project_environment  # noqa: E402

load_project_environment(ROOT)

from scripts.verify_runtime import assert_verified_runtime  # noqa: E402
from services.runtime_logging import configure_runtime_logging  # noqa: E402
from services.security import assert_startup_security  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    assert_verified_runtime()
    configure_runtime_logging(ROOT / "logs" / "facai-agent-server.log")
    logging.getLogger("facai.runtime").info(
        "Verified isolated runtime: executable=%s prefix=%s",
        sys.executable,
        sys.prefix,
    )
    assert_startup_security("0.0.0.0")
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
