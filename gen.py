import os
base = r"C:\Users\Probably\facai-agent"
os.makedirs(base + r"\routers", exist_ok=True)

main_content = """# facai agent main - fixed AI search
import sys, os
NAS = r"\\\\192.168.0.118\\法采共享盘2026\\VibeCoding文件\\2026-05-07-task-2"
sys.path.insert(0, NAS)
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from database import init_db
from config import APP_TITLE, APP_VERSION, APP_DESCRIPTION
BASE_DIR = NAS
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
LOCAL = os.path.dirname(os.path.abspath(__file__))
if LOCAL not in sys.path: sys.path.insert(0, LOCAL)
from routers.search_local import router as search_router
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
"""

with open(base + r"\main.py", "w", encoding="utf-8") as f:
    f.write(main_content)
print("main.py written:", os.path.getsize(base + r"\main.py"), "bytes")
