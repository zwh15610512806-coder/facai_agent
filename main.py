"""短视频脚本生成 Agent - FastAPI (本地修复版)"""
import ipaddress
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import ALLOWED_HOSTS, ALLOWED_ORIGINS, APP_DESCRIPTION, APP_TITLE, APP_VERSION
from database import init_db
from routers import (
    ai_config,
    auth,
    creators,
    import_data,
    inspiration,
    products,
    reference_scripts,
    scripts,
    search_local,
)
from routers import templates as tpl_routes
from services.access_control import (
    record_request_audit,
    request_limit_violation,
    should_audit,
)
from services.request_context import request_actor
from services.request_hardening import RequestBodyLimitMiddleware
from services.security import (
    Principal,
    auth_configured,
    auth_enabled,
    is_public_path,
    principal_from_request,
    request_uses_cookie_auth,
    role_is_allowed,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LOCAL = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = LOCAL

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from database import SessionLocal
    from services.retention import apply_data_retention

    with SessionLocal() as session:
        apply_data_retention(session)
    from services.backup_manager import ensure_configured_daily_backup
    try:
        ensure_configured_daily_backup()
    except Exception:
        logging.getLogger("facai.backup").exception("Daily backup failed")
    from services.job_runs import recover_interrupted_jobs
    recover_interrupted_jobs()
    from vector_store import init_vector_store
    init_vector_store()
    from services.vector_sync import start_vector_sync_worker, stop_vector_sync_worker
    start_vector_sync_worker()
    from services.task_queue import start_task_worker, stop_task_worker
    start_task_worker()
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
    if auth_enabled():
        logging.getLogger("facai.security").info(
            "Application authentication is enabled (configured=%s)", auth_configured()
        )
    else:
        logging.getLogger("facai.security").warning(
            "Application authentication is disabled; use loopback access only"
        )
    try:
        yield
    finally:
        stop_task_worker()
        stop_vector_sync_worker()

app = FastAPI(title=APP_TITLE, version=APP_VERSION, description=APP_DESCRIPTION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(search_local.router, prefix="/api/search-proxy", tags=["search"])
app.include_router(creators.router, prefix="/api/creators", tags=["creators"])

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
    current = f"{request.url.scheme.lower()}://{request.headers.get('host', '').lower()}"
    configured = {value.rstrip("/").lower() for value in ALLOWED_ORIGINS}
    return normalized == current or normalized in configured


def _host_is_allowed(host_header: str) -> bool:
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

    if not is_public_path(path):
        if auth_enabled():
            principal = principal_from_request(request)
            if principal is None:
                return _apply_security_headers(_auth_failure(request))
            if not role_is_allowed(principal.role, request.method, path):
                allowed_roles = sorted(
                    role for role in {"admin", "operator", "viewer"}
                    if role_is_allowed(role, request.method, path)
                )
                return _apply_security_headers(
                    JSONResponse(
                        {"detail": "Insufficient permission", "required_roles": allowed_roles},
                        status_code=403,
                    )
                )
            if (
                request.method in {"POST", "PUT", "PATCH", "DELETE"}
                and request_uses_cookie_auth(request)
                and not _csrf_evidence_is_valid(request)
            ):
                return _apply_security_headers(
                    JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
                )
        else:
            principal = Principal(name="local-bypass", role="admin", auth_source="disabled")
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
    if principal.auth_source == "disabled" or not should_audit(request.method, request.url.path):
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


def _csrf_evidence_is_valid(request: Request) -> bool:
    if request.headers.get("x-facai-csrf", "").strip() == "1":
        return True
    origin = request.headers.get("origin", "").strip()
    return bool(origin and _origin_is_allowed(request, origin))


def _auth_failure(request: Request):
    path = request.scope.get("path", "")
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    next_url = path + (("?" + request.url.query) if request.url.query else "")
    return RedirectResponse(
        url="/app/login?next=" + quote(next_url, safe=""),
        status_code=303,
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
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request})
@app.get("/app")
def app_page(request: Request): return templates.TemplateResponse(request, "inspiration.html", {"request": request})
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
if __name__ == "__main__":
    import uvicorn

    from scripts.verify_runtime import assert_verified_runtime
    from services.security import assert_startup_security

    assert_verified_runtime()
    bind_host = "0.0.0.0"
    assert_startup_security(bind_host)
    uvicorn.run(app, host=bind_host, port=8001)
