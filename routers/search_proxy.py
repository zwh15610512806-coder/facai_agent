"""检索代理路由 — 将请求转发到 Flask 后端（192.168.0.127:5000）"""
import httpx
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from config import SEARCH_BACKEND_URL

# httpx 传输层异常（来自 httpcore）
from httpx import ConnectError, TimeoutException, RemoteProtocolError, ReadError

router = APIRouter(tags=["检索"])

# 共享 httpx 客户端（连接池复用）
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            trust_env=False,  # 禁用系统代理，直连本地检索服务
        )
    return _client


def _safe_json(resp) -> dict:
    """安全解析 JSON，非 JSON 响应返回原始文本"""
    ct = resp.headers.get("content-type", "")
    if "application/json" in ct:
        try:
            return resp.json()
        except Exception:
            pass
    # 非 JSON 或解析失败，返回包装文本
    text = resp.text[:5000] if resp.text else "(empty response)"
    return {"_raw": text, "_status": resp.status_code, "_content_type": ct}


async def _proxy_get(path: str, params: dict | None = None, stream: bool = False):
    """代理 GET 请求到 Flask"""
    client = _get_client()
    url = f"{SEARCH_BACKEND_URL}{path}"
    try:
        resp = await client.get(url, params=params)
        if stream:
            return StreamingResponse(
                resp.aiter_bytes(),
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type", "application/octet-stream"),
            )
        return JSONResponse(content=_safe_json(resp), status_code=resp.status_code)
    except ConnectError:
        raise HTTPException(status_code=503, detail="检索服务未启动（192.168.0.127:5000）")
    except TimeoutException:
        raise HTTPException(status_code=504, detail="检索服务响应超时")
    except RemoteProtocolError:
        raise HTTPException(status_code=502, detail="检索服务连接异常断开")
    except ReadError:
        raise HTTPException(status_code=502, detail="检索服务读取错误")


async def _proxy_post(path: str, body: dict | None = None):
    """代理 POST 请求到 Flask"""
    client = _get_client()
    url = f"{SEARCH_BACKEND_URL}{path}"
    try:
        resp = await client.post(url, json=body)
        return JSONResponse(content=_safe_json(resp), status_code=resp.status_code)
    except ConnectError:
        raise HTTPException(status_code=503, detail="检索服务未启动（192.168.0.127:5000）")
    except TimeoutException:
        raise HTTPException(status_code=504, detail="检索服务响应超时")
    except RemoteProtocolError:
        raise HTTPException(status_code=502, detail="检索服务连接异常断开")
    except ReadError:
        raise HTTPException(status_code=502, detail="检索服务读取错误")


# ---- 文件搜索 ----

@router.get("/search")
async def search_files(
    q: str = Query(""),
    type: str = Query(""),
    ext: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    folder: str = Query(""),
    page: int = Query(1),
    per_page: int = Query(20),
):
    """关键词搜索文件"""
    params = {}
    if q: params["q"] = q
    if type: params["type"] = type
    if ext: params["ext"] = ext
    if date_from: params["date_from"] = date_from
    if date_to: params["date_to"] = date_to
    if folder: params["folder"] = folder
    params["page"] = page
    params["per_page"] = per_page
    return await _proxy_get("/api/search", params)


# ---- AI 智能搜索 ----

@router.post("/ai-search")
async def ai_search(request: Request):
    """AI 自然语言搜索"""
    try:
        body = await request.json()
    except Exception:
        # JSON 解析失败，尝试从表单或原始文本中提取
        raw = (await request.body()).decode("utf-8", errors="replace")
        body = {"query": raw}
    return await _proxy_post("/api/ai-search", body)


# ---- 统计 ----

@router.get("/stats")
async def get_stats():
    """获取索引统计"""
    return await _proxy_get("/api/stats")


# ---- AI 搜索汇总 ----

@router.post("/search-summary")
async def search_summary(request: Request):
    """AI 整理搜索结果汇总"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    return await _proxy_post("/api/search-summary", body)


# ---- 文件详情 ----

@router.get("/files/{file_id}")
async def get_file(file_id: int):
    """获取文件详情"""
    return await _proxy_get(f"/api/files/{file_id}")


# ---- 文件下载 ----

@router.get("/files/{file_id}/download")
async def download_file(file_id: int):
    """下载文件（二进制流）"""
    return await _proxy_get(f"/api/files/{file_id}/download", stream=True)


# ---- 文件预览 ----

@router.get("/files/{file_id}/preview")
async def preview_file(file_id: int):
    """预览文件（图片/视频等）"""
    return await _proxy_get(f"/api/files/{file_id}/preview", stream=True)


# ---- 索引管理 ----

@router.get("/index/status")
async def index_status():
    """获取索引状态"""
    return await _proxy_get("/api/index/status")


@router.post("/index/start")
async def start_index():
    """手动触发索引"""
    return await _proxy_post("/api/index/start")
