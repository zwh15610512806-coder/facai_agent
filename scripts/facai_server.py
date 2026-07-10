"""Managed Uvicorn entry point with rotating application logs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.runtime_logging import configure_runtime_logging


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    configure_runtime_logging(ROOT / "logs" / "facai-agent-server.log")
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
