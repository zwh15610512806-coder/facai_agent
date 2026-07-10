"""Start an isolated test service that cannot read or mutate business data."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEMP_DIR = tempfile.TemporaryDirectory(prefix="facai-e2e-")
ROOT = Path(TEMP_DIR.name)
SEARCH_ROOT = ROOT / "search-root"
SEARCH_ROOT.mkdir(parents=True, exist_ok=True)

os.environ.update({
    "DATABASE_URL": f"sqlite:///{(ROOT / 'test.db').as_posix()}",
    "CHROMA_PERSIST_DIR": str(ROOT / "chroma"),
    "SEARCH_INDEX_BACKEND": "sqlite",
    "SEARCH_INDEX_DB_PATH": str(ROOT / "search_index.db"),
    "SEARCH_INDEX_PATH": str(ROOT / "search_index.json"),
    "SEARCH_ROOTS": str(SEARCH_ROOT),
    "LOCAL_PRODUCT_SOURCE_DIR": str(ROOT / "products"),
    "LOCAL_TXT_SCRIPT_SOURCE_DIR": str(ROOT / "scripts"),
    "UPLOAD_DIR": str(ROOT / "uploads"),
    "ALLOWED_HOSTS": "127.0.0.1,localhost",
    "DEEPSEEK_API_KEY": "",
    "ARK_API_KEY": "",
    "DOUBAO_API_KEY": "",
    "MINIMAX_API_KEY": "",
    "GLM_API_KEY": "",
    "QWEN_API_KEY": "",
    "EMBEDDING_API_KEY": "",
})


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8765, workers=1, log_level="warning")


if __name__ == "__main__":
    main()
