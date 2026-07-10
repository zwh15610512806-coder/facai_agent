"""短视频脚本生成 Agent - FastAPI (本地修复版)"""
import sys, os
import logging
import ipaddress
sys.stdout.reconfigure(encoding='utf-8')
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from services.request_hardening import RequestBodyLimitMiddleware
from database import engine, init_db
from sqlalchemy import text
from config import APP_TITLE, APP_VERSION, APP_DESCRIPTION, ALLOWED_HOSTS, ALLOWED_ORIGINS
LOCAL = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = LOCAL

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from services.job_runs import recover_interrupted_jobs
    recover_interrupted_jobs()
    from vector_store import init_vector_store
    init_vector_store()
    from services.vector_sync import start_vector_sync_worker, stop_vector_sync_worker
    start_vector_sync_worker()
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except:
        lan_ip = ""
    print(f"OK {APP_TITLE} v{APP_VERSION}")
    print(f"   http://localhost:8001/app")
    print(f"   http://{lan_ip}:8001/app")
    logging.getLogger("facai.security").warning(
        "当前部署保持免登录：任何能够访问 8001 端口的用户都可修改、删除数据并调用 AI；请使用防火墙、VPN 或网络 ACL 限制访问。"
    )
    try:
        yield
    finally:
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

from routers import auth, products, templates as tpl_routes, scripts, import_data, reference_scripts, inspiration, ai_config, search_local

app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(tpl_routes.router, prefix="/api/templates", tags=["templates"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(import_data.router, prefix="/api/import", tags=["import"])
app.include_router(reference_scripts.router, prefix="/api/reference", tags=["reference"])
app.include_router(inspiration.router, prefix="/api/inspiration", tags=["inspiration"])
app.include_router(ai_config.router, prefix="/api/ai-config", tags=["ai-config"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(search_local.router, prefix="/api/search-proxy", tags=["search"])

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
    return _apply_security_headers(await call_next(request))


@app.get("/")
def home(): return RedirectResponse(url="/app")
@app.get("/healthz")
def healthz():
    """Lightweight local liveness check; deliberately avoids AI and embedding calls."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "database": "error", "detail": str(exc)[:500]},
            status_code=503,
        )
    return {"status": "ok", "database": "ok"}
@app.get("/app/login")
def login_page(): return RedirectResponse(url="/app", status_code=303)
@app.get("/app")
def app_page(request: Request): return templates.TemplateResponse(request, "inspiration.html", {"request": request})
@app.get("/app/generate")
def generate_page(request: Request): return templates.TemplateResponse(request, "index.html", {"request": request})
@app.get("/app/products")
def products_page(request: Request): return templates.TemplateResponse(request, "products.html", {"request": request})
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
    bind_host = "0.0.0.0"
    uvicorn.run(app, host=bind_host, port=8001)
