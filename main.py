"""短视频脚本生成 Agent - FastAPI (本地修复版)"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from contextlib import asynccontextmanager
from urllib.parse import quote
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from database import init_db
from config import APP_TITLE, APP_VERSION, APP_DESCRIPTION, ALLOWED_ORIGINS
from services.security import auth_configured, auth_enabled, is_admin_request
LOCAL = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = LOCAL

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from vector_store import init_vector_store
    init_vector_store()
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
    yield

app = FastAPI(title=APP_TITLE, version=APP_VERSION, description=APP_DESCRIPTION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

from routers import auth, products, templates as tpl_routes, scripts, import_data, reference_scripts, inspiration, ai_config

import importlib.util
spec = importlib.util.spec_from_file_location("search_local", os.path.join(LOCAL, "routers", "search_local.py"))
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)
search_router = sl.router

app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(tpl_routes.router, prefix="/api/templates", tags=["templates"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(import_data.router, prefix="/api/import", tags=["import"])
app.include_router(reference_scripts.router, prefix="/api/reference", tags=["reference"])
app.include_router(inspiration.router, prefix="/api/inspiration", tags=["inspiration"])
app.include_router(ai_config.router, prefix="/api/ai-config", tags=["ai-config"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(search_router, prefix="/api/search-proxy", tags=["search"])

@app.middleware("http")
async def protect_api_and_app_requests(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site":
            return JSONResponse({"detail": "Cross-site API requests are not allowed"}, status_code=403)
    if auth_enabled() and _requires_admin(path):
        if not auth_configured():
            return _auth_failure(path, "FACAI_ADMIN_TOKEN is not configured", status_code=503)
        if not is_admin_request(request):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            next_url = path + (("?" + request.url.query) if request.url.query else "")
            return RedirectResponse(url="/app/login?next=" + quote(next_url, safe=""), status_code=303)
    return await call_next(request)


def _requires_admin(path: str) -> bool:
    if path.startswith("/static/") or path.startswith("/api/auth/") or path == "/app/login":
        return False
    return path.startswith("/api/") or path.startswith("/app")


def _auth_failure(path: str, detail: str, status_code: int):
    if path.startswith("/api/"):
        return JSONResponse({"detail": detail}, status_code=status_code)
    return RedirectResponse(url="/app/login", status_code=303)


@app.get("/")
def home(): return RedirectResponse(url="/app")
@app.get("/app/login")
def login_page(request: Request): return templates.TemplateResponse(request, "login.html", {"request": request})
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
def seedance_page(request: Request): return templates.TemplateResponse(request, "seedance.html", {"request": request})
@app.get("/app/search")
def search_page(request: Request): return templates.TemplateResponse(request, "search.html", {"request": request})
@app.get("/app/inspiration")
def inspiration_page(): return RedirectResponse(url="/app", status_code=303)
@app.get("/app/ai-config")
def ai_config_page(request: Request): return templates.TemplateResponse(request, "ai_config.html", {"request": request})
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
