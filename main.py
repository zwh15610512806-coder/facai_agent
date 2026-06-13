"""短视频脚本生成 Agent - FastAPI (本地修复版)"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from database import init_db
from config import APP_TITLE, APP_VERSION, APP_DESCRIPTION
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

from routers import products, templates as tpl_routes, scripts, import_data, reference_scripts

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
app.include_router(search_router, prefix="/api/search-proxy", tags=["search"])

@app.get("/")
def home(): return RedirectResponse(url="/app")
@app.get("/app")
def app_page(request: Request): return templates.TemplateResponse(request, "index.html", {"request": request})
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
@app.get("/app/search")
def search_page(request: Request): return templates.TemplateResponse(request, "search.html", {"request": request})
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
