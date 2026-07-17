"""短视频脚本生成 Agent - FastAPI (本地修复版)"""
import ipaddress
import json
import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import ALLOWED_HOSTS, ALLOWED_ORIGINS, APP_DESCRIPTION, APP_TITLE, APP_VERSION
from database import SessionLocal, engine, get_db, init_db
from routers import (
    ai_config,
    creators,
    import_data,
    inspiration,
    products,
    reference_scripts,
    scripts,
    search_local,
    integrations as integration_routes,
)
from sqlalchemy import text
from routers import templates as tpl_routes
from routers.canvas import router as canvas_router
from sqlalchemy.orm import Session
from services.access_control import (
    record_request_audit,
    request_limit_violation,
    should_audit,
)
from services.request_context import request_actor
from services.request_hardening import RequestBodyLimitMiddleware
from services.security import (
    Principal,
    principal_for_request,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LOCAL = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = LOCAL

@asynccontextmanager
async def lifespan(app: FastAPI):
    canvas_runtime_started = False
    vector_sync_started = False
    task_worker_started = False
    try:
        init_db()
        from services.retention import apply_data_retention

        try:
            with SessionLocal() as session:
                apply_data_retention(session)
        except Exception:
            logging.getLogger("facai.retention").exception("Data retention failed")
        from services.canvas.providers.bootstrap import bootstrap_builtin_image_profiles
        from services.canvas.projects import recover_deleting_projects
        from services.canvas.events import prune_all_canvas_events
        from services.canvas.runtime import start_canvas_runtime

        bootstrap_builtin_image_profiles(SessionLocal)
        recover_deleting_projects(SessionLocal)
        try:
            prune_all_canvas_events(SessionLocal)
        except Exception:
            logging.getLogger("facai.canvas").exception("Canvas event pruning failed")
        start_canvas_runtime(app, db_factory=SessionLocal)
        canvas_runtime_started = True
        from services.backup_manager import ensure_configured_daily_backup
        try:
            ensure_configured_daily_backup()
        except Exception:
            logging.getLogger("facai.backup").exception("Daily backup failed")
        from services.job_runs import recover_interrupted_jobs
        recover_interrupted_jobs()
        from vector_store import init_vector_store
        init_vector_store()
        from services.vector_sync import start_vector_sync_worker
        start_vector_sync_worker()
        vector_sync_started = True
        from services.task_queue import start_task_worker
        start_task_worker()
        task_worker_started = True
        lan_ip = ""
        if os.environ.get("FACAI_SKIP_LAN_IP_PROBE") != "1":
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                lan_ip = s.getsockname()[0]
                s.close()
            except OSError:
                lan_ip = ""
        print(f"OK {APP_TITLE} v{APP_VERSION}")
        print("   http://localhost:8001/app")
        print(f"   http://{lan_ip}:8001/app")
        logging.getLogger("facai.security").warning(
            "Passwordless trusted-intranet access is active; every reachable client has full access"
        )
        yield
    finally:
        try:
            if task_worker_started:
                from services.task_queue import stop_task_worker

                stop_task_worker()
        finally:
            try:
                if vector_sync_started:
                    from services.vector_sync import stop_vector_sync_worker

                    stop_vector_sync_worker()
            finally:
                if canvas_runtime_started:
                    from services.canvas.runtime import stop_canvas_runtime

                    stop_canvas_runtime(app)

app = FastAPI(title=APP_TITLE, version=APP_VERSION, description=APP_DESCRIPTION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(RequestBodyLimitMiddleware)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(tpl_routes.router, prefix="/api/templates", tags=["templates"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(import_data.router, prefix="/api/import", tags=["import"])
app.include_router(reference_scripts.router, prefix="/api/reference", tags=["reference"])
app.include_router(inspiration.router, prefix="/api/inspiration", tags=["inspiration"])
app.include_router(ai_config.router, prefix="/api/ai-config", tags=["ai-config"])
app.include_router(search_local.router, prefix="/api/search-proxy", tags=["search"])
app.include_router(creators.router, prefix="/api/creators", tags=["creators"])
app.include_router(canvas_router, prefix="/api/canvas", tags=["canvas"])
app.include_router(integration_routes.admin_router)
app.include_router(integration_routes.operations_router)
app.include_router(integration_routes.public_router)


def _serialize_canvas_bootstrap(payload: dict[str, object]) -> str:
    """Serialize Canvas page state without allowing an inline script escape."""

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _canvas_page_response(request: Request, *, project_id: str | None):
    return templates.TemplateResponse(
        request,
        "canvas.html",
        {
            "request": request,
            "canvas_bootstrap_json": _serialize_canvas_bootstrap(
                {"apiBase": "/api/canvas", "projectId": project_id}
            ),
        },
    )

def _apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


def _origin_is_allowed(request: Request, origin: str) -> bool:
    if not origin or origin == "null":
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc or parsed.path not in {"", "/"}:
        return False
    normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    request_host = request.headers.get("host", "").lower()
    configured = {value.rstrip("/").lower() for value in ALLOWED_ORIGINS}
    if request.scope.get("path", "").startswith("/api/integrations/"):
        from integrations.request_context import (
            RequestContextConfigurationError,
            resolve_request_context,
        )
        from integrations.settings import (
            TRUSTED_PROXY_CIDRS_ENV,
            load_integration_settings,
        )

        settings = load_integration_settings()
        if TRUSTED_PROXY_CIDRS_ENV in settings.errors:
            return parsed.netloc.lower() == request_host or normalized in configured
        try:
            context = resolve_request_context(
                request,
                settings.trusted_proxy_networks,
            )
        except RequestContextConfigurationError:
            return parsed.netloc.lower() == request_host or normalized in configured
        current = f"{context.effective_scheme}://{request_host}"
    else:
        current = f"{request.url.scheme.lower()}://{request_host}"
    return normalized == current or normalized in configured


def _canonical_hostname(hostname: str) -> tuple[str, str]:
    normalized = hostname.lower().rstrip(".")
    try:
        return "ip", ipaddress.ip_address(normalized).compressed
    except ValueError:
        return "dns", normalized


def _origin_authority(
    origin: str,
) -> tuple[tuple[str, str], int, int, bool] | None:
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        explicit_port = parsed.port is not None
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        port = parsed.port or default_port
    except (TypeError, ValueError):
        return None
    if not hostname or parsed.scheme.lower() not in {"http", "https"}:
        return None
    return _canonical_hostname(hostname), port, default_port, explicit_port


def _host_matches_origin(host_header: str, origin: str) -> bool:
    expected = _origin_authority(origin)
    if expected is None:
        return False
    expected_host, expected_port, expected_default_port, expected_explicit_port = expected
    try:
        parsed = urlsplit(f"//{host_header}")
        hostname = parsed.hostname
        supplied_port = parsed.port
    except ValueError:
        return False
    if (
        not hostname
        or parsed.netloc.endswith(":")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return False
    if supplied_port is None:
        if expected_explicit_port and expected_port != expected_default_port:
            return False
        supplied_port = expected_default_port
    return _canonical_hostname(hostname) == expected_host and supplied_port == expected_port


def _configured_integration_origin(host_header: str) -> str | None:
    from integrations.settings import (
        INTERNAL_BASE_URL_ENV,
        PUBLIC_BASE_URL_ENV,
        load_integration_settings,
    )

    settings = load_integration_settings()
    for kind, origin in (
        (
            "public",
            settings.public_base_url
            if PUBLIC_BASE_URL_ENV not in settings.errors
            else None,
        ),
        (
            "internal",
            settings.internal_base_url
            if INTERNAL_BASE_URL_ENV not in settings.errors
            else None,
        ),
    ):
        if origin is not None and _host_matches_origin(host_header, origin):
            return kind
    return None


def _host_uses_configured_integration_hostname(host_header: str) -> bool:
    from integrations.settings import (
        INTERNAL_BASE_URL_ENV,
        PUBLIC_BASE_URL_ENV,
        load_integration_settings,
    )

    try:
        hostname = urlsplit(f"//{host_header}").hostname
    except ValueError:
        return False
    if not hostname:
        return False
    candidate = _canonical_hostname(hostname)
    settings = load_integration_settings()
    for origin, error_key in (
        (settings.public_base_url, PUBLIC_BASE_URL_ENV),
        (settings.internal_base_url, INTERNAL_BASE_URL_ENV),
    ):
        if error_key in settings.errors:
            continue
        if origin is None:
            continue
        expected = _origin_authority(origin)
        if expected is not None and candidate == expected[0]:
            return True
    return False


def _public_callback_path_is_allowed(request: Request) -> bool:
    path = request.scope.get("path", "")
    raw_path = request.scope.get("raw_path")
    if not isinstance(path, str):
        return False
    if not isinstance(raw_path, bytes):
        raw_path = path.encode("utf-8", errors="surrogatepass")
    if b"%" in raw_path or b"\\" in raw_path or b"//" in raw_path:
        return False
    providers = {"qianchuan", "doudian", "taobao", "pdd"}
    parts = path.split("/")
    if (
        request.method == "GET"
        and len(parts) == 5
        and parts[1:4] == ["integrations", "oauth", "callback"]
        and parts[4] in providers
    ):
        return True
    return (
        request.method in {"GET", "POST"}
        and len(parts) == 4
        and parts[1:3] == ["integrations", "events"]
        and parts[3] in providers
    )


def _host_is_allowed(host_header: str) -> bool:
    if _configured_integration_origin(host_header) is not None:
        return True
    if _host_uses_configured_integration_hostname(host_header):
        return False
    try:
        hostname = urlsplit(f"//{host_header}").hostname
    except ValueError:
        return False
    if not hostname:
        return False
    hostname = hostname.lower().rstrip(".")
    if hostname in {"localhost", "testserver"} or hostname in ALLOWED_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


@app.middleware("http")
async def protect_api_and_app_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    integration_origin = _configured_integration_origin(
        request.headers.get("host", "")
    )
    if integration_origin == "public" and not _public_callback_path_is_allowed(request):
        return _apply_security_headers(
            JSONResponse({"detail": "Not Found"}, status_code=404)
        )
    if not _host_is_allowed(request.headers.get("host", "")):
        return _apply_security_headers(
            JSONResponse({"detail": "Request host is not allowed"}, status_code=400)
        )
    path = request.scope.get("path", "")
    if path.startswith("/api/"):
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site":
            return _apply_security_headers(
                JSONResponse({"detail": "Cross-site API requests are not allowed"}, status_code=403)
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin", "").strip()
            if origin and not _origin_is_allowed(request, origin):
                return _apply_security_headers(
                    JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)
                )

    principal = None
    if not _request_is_public_utility(path):
        principal = principal_for_request(request)
        request.state.principal = principal
        try:
            violation = request_limit_violation(
                principal=principal,
                method=request.method,
                path=path,
            )
        except Exception as exc:
            logging.getLogger("facai.security").warning(
                "Request-control check failed open for %s: %s", path, exc
            )
            violation = None
        if violation is not None:
            detail, retry_after = violation
            response = JSONResponse(
                {"detail": detail},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            response.headers["X-Request-ID"] = request_id
            _record_audit_safely(request, principal, response.status_code, request_id)
            return _apply_security_headers(response)

    principal = getattr(request.state, "principal", None)
    actor_name = principal.name if principal else "anonymous"
    with request_actor(actor_name, request_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if principal is not None:
        _record_audit_safely(request, principal, response.status_code, request_id)
    return _apply_security_headers(response)


def _record_audit_safely(
    request: Request,
    principal: Principal,
    status_code: int,
    request_id: str,
) -> None:
    if not should_audit(request.method, request.url.path):
        return
    try:
        record_request_audit(
            principal=principal,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            client_ip=request.client.host if request.client else "",
            request_id=request_id,
        )
    except Exception as exc:
        logging.getLogger("facai.security").warning(
            "Audit write failed for request %s: %s", request_id, exc
        )


def _request_is_public_utility(path: str) -> bool:
    normalized = path.rstrip("/")
    return (
        path in {"/", "/healthz", "/readyz"}
        or path.startswith("/static/")
        or re.fullmatch(
            r"/integrations/(?:oauth/callback|events)/(?:qianchuan|doudian|taobao|pdd)",
            normalized,
        )
        is not None
    )


@app.get("/")
def home(): return RedirectResponse(url="/app")
@app.get("/healthz")
def healthz():
    """Process liveness only; dependency failures belong to /readyz."""
    return {"status": "ok"}
@app.get("/readyz")
def readyz():
    from services.readiness import build_readiness_report
    payload, status_code = build_readiness_report()
    return JSONResponse(payload, status_code=status_code)
@app.get("/app/login")
def login_page():
    return RedirectResponse(url="/app", status_code=303)
@app.get("/app")
def app_page(request: Request): return templates.TemplateResponse(request, "inspiration.html", {"request": request})
@app.get("/app/canvas")
def canvas_page(request: Request):
    return _canvas_page_response(request, project_id=None)
@app.get("/app/canvas/{project_id}")
def canvas_project_page(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
):
    from services.canvas import projects as canvas_project_service

    try:
        canvas_project_service.get_project_snapshot(db, project_id=project_id)
    except canvas_project_service.CanvasProjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Canvas project not found") from exc
    return _canvas_page_response(request, project_id=project_id)
@app.get("/app/generate")
def generate_page(request: Request): return templates.TemplateResponse(request, "index.html", {"request": request})
@app.get("/app/products")
def products_page(request: Request): return templates.TemplateResponse(request, "products.html", {"request": request})
@app.get("/app/creators")
def creators_page(request: Request): return templates.TemplateResponse(request, "creators.html", {"request": request})
@app.get("/app/import")
def import_page(request: Request): return templates.TemplateResponse(request, "import.html", {"request": request})
@app.get("/app/templates")
def templates_page(request: Request): return templates.TemplateResponse(request, "templates.html", {"request": request})
@app.get("/app/history")
def history_page(request: Request): return templates.TemplateResponse(request, "history.html", {"request": request})
@app.get("/app/rewrite")
def rewrite_page(request: Request): return templates.TemplateResponse(request, "rewrite.html", {"request": request})
@app.get("/app/seedance")
def seedance_page(): return RedirectResponse(url="/app", status_code=303)
@app.get("/app/search")
def search_page(request: Request): return templates.TemplateResponse(request, "search.html", {"request": request})
@app.get("/app/inspiration")
def inspiration_page(): return RedirectResponse(url="/app", status_code=303)
@app.get("/app/ai-config")
def ai_config_page(request: Request): return templates.TemplateResponse(request, "ai_config.html", {"request": request})


@app.get("/app/api-connections/login")
def api_connections_login_page():
    return RedirectResponse(url="/app/api-connections", status_code=303)


_OPERATIONS_TABS = frozenset(
    {"overview", "orders", "products", "refunds", "ads", "sync-runs"}
)


@app.get("/app/api-connections")
def api_connections_page(request: Request, tab: str | None = None):
    if tab in _OPERATIONS_TABS:
        return RedirectResponse(url=f"/app/operations?tab={tab}", status_code=303)
    from integrations.settings import load_integration_settings

    settings = load_integration_settings()
    return templates.TemplateResponse(
        request,
        "api_connections.html",
        {
            "request": request,
            "credential_ready": settings.credential_ready,
        },
    )


@app.get("/app/operations")
def operations_page(request: Request, tab: str | None = None):
    active_tab = tab if tab in _OPERATIONS_TABS else "overview"
    return templates.TemplateResponse(
        request,
        "operations.html",
        {"request": request, "active_tab": active_tab},
    )
if __name__ == "__main__":
    import uvicorn

    from scripts.verify_runtime import assert_verified_runtime
    assert_verified_runtime()
    bind_host = "0.0.0.0"
    uvicorn.run(
        app,
        host=bind_host,
        port=8001,
        proxy_headers=False,
        forwarded_allow_ips="",
    )
