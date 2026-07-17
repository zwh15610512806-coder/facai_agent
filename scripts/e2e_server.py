"""Start an isolated E2E service that cannot read or mutate business data."""

from __future__ import annotations

import base64
import io
import ipaddress
import os
import sys
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Any


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

PROVIDER_KEY_ENV_ALIASES = (
    "DEEPSEEK_API_KEY",
    "ARK_API_KEY",
    "DOUBAO_API_KEY",
    "MINIMAX_API_KEY",
    "GLM_API_KEY",
    "ZAI_API_KEY",
    "QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
    "EMBEDDING_API_KEY",
)
_OUTBOUND_AUDIT_LOCK = Lock()
_LIFETIME_OUTBOUND_ATTEMPTS: list[dict[str, str]] = []
_SCENARIO_OUTBOUND_ATTEMPTS: list[dict[str, str]] = []


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
    if parsed.is_loopback:
        return True
    return bool(parsed.version == 6 and parsed.ipv4_mapped and parsed.ipv4_mapped.is_loopback)


def _socket_target_text(address: object) -> str:
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return str(address)


def _record_blocked_outbound(method: str, address: object) -> None:
    attempt = {
        "method": method,
        "target": _socket_target_text(address),
    }
    with _OUTBOUND_AUDIT_LOCK:
        _LIFETIME_OUTBOUND_ATTEMPTS.append(dict(attempt))
        _SCENARIO_OUTBOUND_ATTEMPTS.append(dict(attempt))


def _install_outbound_guard() -> None:
    def audit_socket_connect(event: str, arguments: tuple[object, ...]) -> None:
        if event != "socket.connect" or len(arguments) < 2:
            return
        address = arguments[1]
        if _loopback_socket_target(address):
            return
        _record_blocked_outbound("socket.connect", address)
        raise OSError(f"isolated E2E blocked outbound connect to {address!r}")

    sys.addaudithook(audit_socket_connect)

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
    "CANVAS_DATA_DIR": str(ROOT / "canvas-data"),
    "CANVAS_REMBG_MODEL_DIR": str(ROOT / "rembg-models"),
    # Keep filesystem handoffs deterministic on Windows; provider protocol
    # coverage remains sync/async, while the isolated server never needs
    # production parallel throughput.
    "CANVAS_GENERATION_CONCURRENCY": "1",
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
})

_install_outbound_guard()

# ChromaDB eagerly imports ONNX even when embedding is unconfigured. The Canvas
# browser suite does not exercise vector search, so install a narrow E2E-only
# compatibility surface before the application imports any router.
from tests.fakes import vector_store as isolated_vector_store

isolated_vector_store.__path__ = [str(PROJECT_ROOT / "vector_store")]
sys.modules["vector_store"] = isolated_vector_store

# Canvas browser coverage has its own leased workers.  The ordinary vector-sync
# scheduler is unrelated to these scenarios and competes for the same isolated
# SQLite writer, so leave it inert in this disposable E2E process only.
from services import vector_sync as isolated_vector_sync


def _e2e_noop_vector_sync(*_: object, **__: object) -> None:
    return None


isolated_vector_sync.start_vector_sync_worker = _e2e_noop_vector_sync
isolated_vector_sync.stop_vector_sync_worker = _e2e_noop_vector_sync

# The application and every module that reads config are intentionally imported only
# after the complete isolated environment above is installed.
import main as application

import config as effective_config
from fastapi import HTTPException, Request
from PIL import Image
from sqlalchemy import delete, func, select

from canvas_models import CanvasEvent, CanvasProject
from database import SessionLocal
from routers.canvas.assets import asset_json
from services.canvas import assets as canvas_assets
from services.canvas import previews as canvas_previews
from services.canvas import projects as canvas_projects
from services.canvas import storage as canvas_storage
from services.canvas.compose_operations import run_compose_operation
from services.canvas.runtime import configure_canvas_test_runtime
from tests.fakes.canvas_provider import (
    FakeCanvasProvider,
    build_e2e_provider_registry,
    seed_e2e_model_profiles,
)
from tests.fakes.canvas_processors import FakeMasker


FAKE_MASKER = FakeMasker()
FAKE_PROVIDER = FakeCanvasProvider()
FAKE_PROVIDER_REGISTRY = build_e2e_provider_registry(FAKE_PROVIDER)
_AUDIT_LOCK = Lock()
_COMPOSE_CALLS: list[dict[str, object]] = []
_EVENT_REQUESTS: list[dict[str, object]] = []
_EVENT_DISCONNECT_GENERATIONS: dict[str, int] = {}
_CAPACITY_LOCK = Lock()
_FORCE_CAPACITY_FAILURE = False
_FINALIZE_DELETING_PROJECT = canvas_projects.finalize_deleting_project
_ASSERT_CANVAS_CAPACITY = canvas_storage.assert_canvas_capacity


def _e2e_assert_canvas_capacity(*args: Any, **kwargs: Any) -> None:
    """E2E-only low-disk gate; production storage capacity logic stays unchanged."""

    with _CAPACITY_LOCK:
        blocked = _FORCE_CAPACITY_FAILURE
    if blocked:
        raise canvas_storage.CanvasStorageError(
            "canvas_storage_low_disk",
            "canvas storage minimum free space would be crossed",
        )
    _ASSERT_CANVAS_CAPACITY(*args, **kwargs)


canvas_storage.assert_canvas_capacity = _e2e_assert_canvas_capacity


def _retrying_finalize_deleting_project(*args: Any, **kwargs: Any) -> None:
    """Retry only the transient Windows file-sharing race seen during browser cleanup."""
    maximum_attempts = 20
    for attempt in range(maximum_attempts):
        try:
            _FINALIZE_DELETING_PROJECT(*args, **kwargs)
            return
        except canvas_storage.CanvasStorageError as exc:
            cause = exc.__cause__
            sharing_violation = (
                isinstance(cause, PermissionError)
                and getattr(cause, "winerror", None) == 32
            )
            if not sharing_violation or attempt + 1 == maximum_attempts:
                raise
            time.sleep(min(0.02 * (attempt + 1), 0.2))


canvas_projects.finalize_deleting_project = _retrying_finalize_deleting_project


def _masker_factory() -> FakeMasker:
    return FAKE_MASKER


def _compose_runner(operation_id: str, **kwargs: Any) -> Any:
    call: dict[str, object] = {
        "operationId": operation_id,
        "attemptCount": kwargs.get("attempt_count"),
        "workerId": kwargs.get("worker_id"),
    }
    with _AUDIT_LOCK:
        _COMPOSE_CALLS.append(call)
    try:
        return run_compose_operation(operation_id, **kwargs)
    except Exception as exc:
        with _AUDIT_LOCK:
            call["errorType"] = type(exc).__name__
            call["causeType"] = type(exc.__cause__).__name__ if exc.__cause__ else None
            call["causeMessage"] = str(exc.__cause__) if exc.__cause__ else None
        raise


configure_canvas_test_runtime(
    application.app,
    masker_factory=_masker_factory,
    compose_runner=_compose_runner,
    provider_registry_factory=lambda: FAKE_PROVIDER_REGISTRY,
    model_profile_seed_factory=seed_e2e_model_profiles,
)


def _require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client is not None else ""
    try:
        is_loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = client_host == "localhost"
    if not is_loopback:
        raise HTTPException(status_code=404, detail="Not found")


def _bounded_integer(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = payload.get(field)
    if type(value) is not int or value < minimum or value > maximum:
        raise HTTPException(status_code=422, detail=f"Invalid {field}")
    return value


@application.app.middleware("http")
async def _audit_event_source_requests(request: Request, call_next):
    event_prefix = "/api/canvas/projects/"
    event_suffix = "/events"
    project_id: str | None = None
    if request.url.path.startswith(event_prefix) and request.url.path.endswith(event_suffix):
        candidate = request.url.path[len(event_prefix) : -len(event_suffix)]
        if candidate and "/" not in candidate:
            project_id = candidate

    disconnect_generation: int | None = None
    if project_id is not None:
        with _AUDIT_LOCK:
            disconnect_generation = _EVENT_DISCONNECT_GENERATIONS.get(project_id, 0)
            _EVENT_REQUESTS.append(
                {
                    "path": request.url.path,
                    "lastEventId": request.headers.get("last-event-id"),
                    "clientHost": request.client.host if request.client is not None else None,
                }
            )
    response = await call_next(request)
    if project_id is None or disconnect_generation is None:
        return response

    body_iterator = response.body_iterator

    async def disconnectable_body_iterator():
        async for chunk in body_iterator:
            with _AUDIT_LOCK:
                should_disconnect = (
                    _EVENT_DISCONNECT_GENERATIONS.get(project_id, 0)
                    != disconnect_generation
                )
            if should_disconnect:
                close_iterator = getattr(body_iterator, "aclose", None)
                if close_iterator is not None:
                    await close_iterator()
                return
            yield chunk

    response.body_iterator = disconnectable_body_iterator()
    return response


@application.app.get("/_e2e/runtime-audit")
def runtime_audit(request: Request) -> dict[str, object]:
    _require_loopback(request)
    model_dir = Path(os.environ["CANVAS_REMBG_MODEL_DIR"])
    model_files = sorted(
        path.relative_to(model_dir).as_posix()
        for path in model_dir.rglob("*")
        if path.is_file()
    ) if model_dir.exists() else []
    with _AUDIT_LOCK:
        compose_calls = [dict(call) for call in _COMPOSE_CALLS]
        event_requests = [dict(event_request) for event_request in _EVENT_REQUESTS]
    with _OUTBOUND_AUDIT_LOCK:
        lifetime_external_attempts = [
            dict(attempt) for attempt in _LIFETIME_OUTBOUND_ATTEMPTS
        ]
        scenario_external_attempts = [
            dict(attempt) for attempt in _SCENARIO_OUTBOUND_ATTEMPTS
        ]
    return {
        "root": str(ROOT.resolve()),
        "canvasDataDir": str((ROOT / "canvas-data").resolve()),
        "providerKeyAliases": {
            name: os.environ.get(name, "")
            for name in PROVIDER_KEY_ENV_ALIASES
        },
        "effectiveProviderKeys": {
            name: str(getattr(effective_config, name, "") or "")
            for name in (
                "DEEPSEEK_API_KEY",
                "ARK_API_KEY",
                "DOUBAO_API_KEY",
                "MINIMAX_API_KEY",
                "GLM_API_KEY",
                "QWEN_API_KEY",
                "EMBEDDING_API_KEY",
            )
        },
        "rembg": {
            "rembgImported": any(
                name == "rembg" or name.startswith("rembg.")
                for name in sys.modules
            ),
            "onnxruntimeImported": any(
                name == "onnxruntime" or name.startswith("onnxruntime.")
                for name in sys.modules
            ),
            "modelDir": str(model_dir.resolve()),
            "modelFileCount": len(model_files),
            "modelFiles": model_files,
        },
        "network": {
            "lifetimeExternalAttemptCount": len(lifetime_external_attempts),
            "lifetimeExternalAttemptTargets": [
                attempt["target"] for attempt in lifetime_external_attempts
            ],
            "scenarioExternalAttemptCount": len(scenario_external_attempts),
            "scenarioExternalAttemptTargets": [
                attempt["target"] for attempt in scenario_external_attempts
            ],
        },
        "masker": FAKE_MASKER.audit_snapshot(),
        "provider": FAKE_PROVIDER.audit_snapshot(),
        "capacity": {"forcedFailure": _FORCE_CAPACITY_FAILURE},
        "compose": {
            "totalCalls": len(compose_calls),
            "calls": compose_calls,
        },
        "eventRequests": event_requests,
    }


@application.app.post("/_e2e/runtime-audit/reset")
def reset_runtime_audit(request: Request) -> dict[str, str]:
    global _FORCE_CAPACITY_FAILURE
    _require_loopback(request)
    FAKE_MASKER.reset_audit()
    FAKE_PROVIDER.reset_audit()
    with _AUDIT_LOCK:
        _COMPOSE_CALLS.clear()
        _EVENT_REQUESTS.clear()
    with _OUTBOUND_AUDIT_LOCK:
        _SCENARIO_OUTBOUND_ATTEMPTS.clear()
    with _CAPACITY_LOCK:
        _FORCE_CAPACITY_FAILURE = False
    return {"status": "reset"}


@application.app.post("/_e2e/runtime/capacity")
def configure_capacity_failure(request: Request, payload: dict[str, Any]) -> dict[str, bool]:
    global _FORCE_CAPACITY_FAILURE
    _require_loopback(request)
    blocked = payload.get("blocked")
    if type(blocked) is not bool:
        raise HTTPException(status_code=422, detail="Invalid blocked")
    with _CAPACITY_LOCK:
        _FORCE_CAPACITY_FAILURE = blocked
    return {"forcedFailure": blocked}


@application.app.post("/_e2e/projects/{project_id}/events/disconnect")
def disconnect_event_stream(request: Request, project_id: str) -> dict[str, object]:
    _require_loopback(request)
    with SessionLocal() as db:
        if db.get(CanvasProject, project_id) is None:
            raise HTTPException(status_code=404, detail="Canvas project not found")
    with _AUDIT_LOCK:
        generation = _EVENT_DISCONNECT_GENERATIONS.get(project_id, 0) + 1
        _EVENT_DISCONNECT_GENERATIONS[project_id] = generation
    return {
        "projectId": project_id,
        "disconnectGeneration": generation,
    }


@application.app.post("/_e2e/projects/{project_id}/events/prune-through")
def prune_events_through(
    request: Request,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, object]:
    _require_loopback(request)
    event_id = _bounded_integer(payload, "eventId", minimum=0, maximum=2**63 - 1)
    with SessionLocal() as db:
        if db.get(CanvasProject, project_id) is None:
            raise HTTPException(status_code=404, detail="Canvas project not found")
        pruned_ids = list(
            db.scalars(
                select(CanvasEvent.id)
                .where(
                    CanvasEvent.project_id == project_id,
                    CanvasEvent.id <= event_id,
                )
                .order_by(CanvasEvent.id)
            ).all()
        )
        db.execute(
            delete(CanvasEvent).where(
                CanvasEvent.project_id == project_id,
                CanvasEvent.id <= event_id,
            )
        )
        db.commit()
        earliest = db.scalar(
            select(func.min(CanvasEvent.id)).where(CanvasEvent.project_id == project_id)
        )
        latest = db.scalar(
            select(func.max(CanvasEvent.id)).where(CanvasEvent.project_id == project_id)
        )
    return {
        "projectId": project_id,
        "prunedThrough": event_id,
        "deletedEventIds": pruned_ids,
        "earliestEventId": earliest,
        "latestEventId": latest,
    }


@application.app.post("/_e2e/projects/{project_id}/seed-background", status_code=201)
def seed_background(
    request: Request,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, object]:
    _require_loopback(request)
    width = _bounded_integer(payload, "width", minimum=1, maximum=2_048)
    height = _bounded_integer(payload, "height", minimum=1, maximum=2_048)
    color_value = payload.get("color")
    if (
        not isinstance(color_value, list)
        or len(color_value) not in {3, 4}
        or any(type(channel) is not int or channel < 0 or channel > 255 for channel in color_value)
    ):
        raise HTTPException(status_code=422, detail="Invalid color")
    color = tuple(color_value)
    mode = "RGBA" if len(color) == 4 else "RGB"
    image = Image.new(mode, (width, height), color)
    output = io.BytesIO()
    try:
        image.save(output, format="PNG", compress_level=9, optimize=False)
    finally:
        image.close()

    with SessionLocal() as db:
        if db.get(CanvasProject, project_id) is None:
            raise HTTPException(status_code=404, detail="Canvas project not found")
        background = canvas_assets.persist_derived_image(
            db,
            project_id=project_id,
            asset_type="generated_background",
            data=output.getvalue(),
            mime_type="image/png",
            source_asset_id=None,
            metadata={"seededBy": "isolated-e2e-control-plane"},
            processor_version="e2e-background-v1",
        )
        background.transparency_status = "transparent" if mode == "RGBA" and color[3] < 255 else "opaque"
        preview = canvas_previews.create_preview_proxy(
            db,
            project_id=project_id,
            source_asset=background,
        )
        db.commit()
        db.refresh(background)
        db.refresh(preview)
        return {
            "asset": asset_json(background),
            "preview": asset_json(preview),
        }


def main() -> None:
    import uvicorn

    uvicorn.run(application.app, host="127.0.0.1", port=8765, workers=1, log_level="warning")


if __name__ == "__main__":
    main()
