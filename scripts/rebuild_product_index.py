"""Build and atomically activate a complete product knowledge index."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import SessionLocal, init_db
from routers.products import reindex_products


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        response = reindex_products(db)
        print(json.dumps({
            "success": response.success,
            "message": response.message,
            "data": response.data,
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
