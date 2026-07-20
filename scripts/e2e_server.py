"""Start an isolated E2E service that cannot read or mutate business data."""

from __future__ import annotations

import base64
import ipaddress
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
INTEGRATION_ARCHIVE_ROOT = ROOT / "integration-archive"
INTEGRATION_ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _loopback_socket_target(address: object) -> bool:
    if isinstance(address, (str, bytes)):
        return True
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="ignore")
    if not isinstance(host, str):
        return False
    normalized = host.strip().strip("[]").rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        parsed = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return parsed.is_loopback or bool(
        parsed.version == 6 and parsed.ipv4_mapped and parsed.ipv4_mapped.is_loopback
    )


def _install_outbound_guard() -> None:
    def audit_socket_connect(event: str, arguments: tuple[object, ...]) -> None:
        if event != "socket.connect" or len(arguments) < 2:
            return
        if not _loopback_socket_target(arguments[1]):
            raise OSError("isolated E2E blocked an outbound connection")

    sys.addaudithook(audit_socket_connect)


os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(ROOT / 'test.db').as_posix()}",
        "CHROMA_PERSIST_DIR": str(ROOT / "chroma"),
        "SEARCH_INDEX_BACKEND": "sqlite",
        "SEARCH_INDEX_DB_PATH": str(ROOT / "search_index.db"),
        "SEARCH_INDEX_PATH": str(ROOT / "search_index.json"),
        "SEARCH_ROOTS": str(SEARCH_ROOT),
        "LOCAL_PRODUCT_SOURCE_DIR": str(ROOT / "products"),
        "LOCAL_TXT_SCRIPT_SOURCE_DIR": str(ROOT / "scripts"),
        "UPLOAD_DIR": str(ROOT / "uploads"),
        "FACAI_SKIP_LAN_IP_PROBE": "1",
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DEEPSEEK_API_KEY": "",
        "ARK_API_KEY": "",
        "DOUBAO_API_KEY": "",
        "MINIMAX_API_KEY": "",
        "GLM_API_KEY": "",
        "ZAI_API_KEY": "",
        "QWEN_API_KEY": "",
        "DASHSCOPE_API_KEY": "",
        "EMBEDDING_API_KEY": "",
        "FACAI_INTEGRATIONS_MASTER_KEY": _base64url(bytes(range(32, 64))),
        "FACAI_INTEGRATIONS_INTERNAL_BASE_URL": "http://127.0.0.1:8765",
        "FACAI_INTEGRATIONS_PUBLIC_BASE_URL": "https://callbacks.test.invalid",
        "FACAI_INTEGRATION_ARCHIVE_DIR": str(INTEGRATION_ARCHIVE_ROOT),
        "FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS": "",
        "FACAI_INTEGRATION_WORKER_ENABLED": "0",
    }
)

_install_outbound_guard()

# ChromaDB eagerly imports ONNX even when embeddings are unconfigured. The
# browser suite does not exercise vector search, so keep that isolated surface
# inert before importing the application.
from tests.fakes import vector_store as isolated_vector_store

isolated_vector_store.__path__ = [str(PROJECT_ROOT / "vector_store")]
sys.modules["vector_store"] = isolated_vector_store

from services import vector_sync as isolated_vector_sync


def _e2e_noop_vector_sync(*_: object, **__: object) -> None:
    return None


isolated_vector_sync.start_vector_sync_worker = _e2e_noop_vector_sync
isolated_vector_sync.stop_vector_sync_worker = _e2e_noop_vector_sync

import main as application


def main() -> None:
    import uvicorn

    uvicorn.run(application.app, host="127.0.0.1", port=8765, workers=1, log_level="warning")


if __name__ == "__main__":
    main()
