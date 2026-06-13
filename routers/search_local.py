import math
import mimetypes
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse


router = APIRouter(tags=["search"])

DEFAULT_SEARCH_ROOTS = [r"\\192.168.0.118\法采共享盘2026"]
SEARCH_ROOTS = [
    root.strip()
    for root in os.getenv("SEARCH_ROOTS", ";".join(DEFAULT_SEARCH_ROOTS)).split(";")
    if root.strip()
]

INDEX_PATH = Path(os.getenv("SEARCH_INDEX_PATH", "./data/search_index.json"))

FILE_TYPE_MAP = {
    "document": [".doc", ".docx", ".pdf", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md", ".json", ".xml"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
    "video": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"],
    "audio": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"],
    "archive": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
}
EXT_TYPE_MAP = {ext: file_type for file_type, exts in FILE_TYPE_MAP.items() for ext in exts}

_lock = threading.RLock()
_loaded = False
_files: list[dict[str, Any]] = []
_files_by_id: dict[int, dict[str, Any]] = {}
_state: dict[str, Any] = {
    "is_indexing": False,
    "last_indexed": None,
    "total_files": 0,
    "message": "",
}


def _json(data: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status_code)


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _file_type(path: str, is_dir: bool = False) -> str:
    if is_dir:
        return "folder"
    return EXT_TYPE_MAP.get(os.path.splitext(path)[1].lower(), "other")


def _safe_stat(path: str):
    try:
        return os.stat(path)
    except OSError:
        return None


def _normalise_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _is_allowed_file_path(path: str) -> bool:
    if not path:
        return False
    try:
        target = _normalise_path(path)
    except (OSError, ValueError):
        return False
    for root in SEARCH_ROOTS:
        try:
            root_path = _normalise_path(root)
            if target == root_path or target.startswith(root_path + os.sep):
                return True
        except (OSError, ValueError):
            continue
    return False


def _parent_label(path: str, root: str) -> str:
    parent = os.path.dirname(path)
    try:
        rel = os.path.relpath(parent, root)
    except ValueError:
        rel = os.path.basename(parent)
    if rel in (".", ""):
        return os.path.basename(os.path.normpath(root))
    return rel.replace("\\", ",").replace("/", ",")


def _entry(item_id: int, path: str, root: str, is_dir: bool) -> dict[str, Any] | None:
    stat = _safe_stat(path)
    if stat is None:
        return None
    ext = "" if is_dir else os.path.splitext(path)[1].lower().lstrip(".")
    return {
        "id": item_id,
        "file_name": os.path.basename(os.path.normpath(path)),
        "file_path": path,
        "file_type": _file_type(path, is_dir=is_dir),
        "file_extension": ext,
        "file_size": 0 if is_dir else stat.st_size,
        "file_modified": datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat(),
        "parent_folder": _parent_label(path, root),
        "_parent_path": os.path.dirname(path),
        "_search_text": f"{os.path.basename(path)} {path}".lower(),
    }


def _save_index(files: list[dict[str, Any]], last_indexed: str) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    public_files = [{k: v for k, v in item.items() if not k.startswith("_")} for item in files]
    INDEX_PATH.write_text(
        _to_json({"last_indexed": last_indexed, "files": public_files}),
        encoding="utf-8",
    )


def _to_json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


def _load_index() -> None:
    global _loaded, _files, _files_by_id
    with _lock:
        if _loaded:
            return
        _loaded = True
        if not INDEX_PATH.exists():
            return
        try:
            import json

            payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            files = [
                item for item in (payload.get("files") or [])
                if _is_allowed_file_path(item.get("file_path", ""))
            ]
            for item in files:
                path = item.get("file_path", "")
                item["_parent_path"] = os.path.dirname(path)
                item["_search_text"] = f"{item.get('file_name', '')} {path}".lower()
            _files = files
            _files_by_id = {int(item["id"]): item for item in files if "id" in item}
            _state["last_indexed"] = payload.get("last_indexed")
            _state["total_files"] = len(files)
        except Exception as exc:
            _state["message"] = f"读取索引缓存失败：{exc}"


def _scan_roots() -> tuple[list[dict[str, Any]], list[str]]:
    files: list[dict[str, Any]] = []
    errors: list[str] = []
    next_id = 1

    for root in SEARCH_ROOTS:
        if not os.path.exists(root):
            errors.append(f"路径不可访问：{root}")
            continue

        for current_root, dir_names, file_names in os.walk(root):
            dir_names.sort()
            file_names.sort()
            for name in dir_names:
                path = os.path.join(current_root, name)
                entry = _entry(next_id, path, root, is_dir=True)
                if entry:
                    files.append(entry)
                    next_id += 1
                    _publish_partial_index(files)
            for name in file_names:
                path = os.path.join(current_root, name)
                entry = _entry(next_id, path, root, is_dir=False)
                if entry:
                    files.append(entry)
                    next_id += 1
                    _publish_partial_index(files)

    files.sort(key=lambda item: (item["file_type"] != "folder", item["file_name"].lower()))
    for new_id, item in enumerate(files, start=1):
        item["id"] = new_id
    return files, errors


def _publish_partial_index(files: list[dict[str, Any]], force: bool = False) -> None:
    if not force and len(files) % 200 != 0:
        return
    with _lock:
        _files[:] = files
        _files_by_id.clear()
        _files_by_id.update({item["id"]: item for item in files})
        _state["total_files"] = len(files)
        _state["message"] = f"索引中，已发现 {len(files)} 个文件"


def _run_index() -> None:
    global _files, _files_by_id
    with _lock:
        _state["is_indexing"] = True
        _state["message"] = "索引中"

    try:
        files, errors = _scan_roots()
        _publish_partial_index(files, force=True)
        last_indexed = _now_iso()
        with _lock:
            _files = files
            _files_by_id = {item["id"]: item for item in files}
            _state["last_indexed"] = last_indexed
            _state["total_files"] = len(files)
            _state["message"] = "；".join(errors) if errors else "索引完成"
        _save_index(files, last_indexed)
    except Exception as exc:
        with _lock:
            _state["message"] = f"索引失败：{exc}"
    finally:
        with _lock:
            _state["is_indexing"] = False


def _normalise_ext(ext: str) -> str:
    return ext.strip().lower().lstrip(".")


def _date_range_from_query(query: str) -> tuple[str, str] | tuple[None, None]:
    today = datetime.now().date()
    q = query.lower()
    if "今天" in query:
        start = end = today
    elif "昨天" in query:
        start = end = today - timedelta(days=1)
    elif "前天" in query:
        start = end = today - timedelta(days=2)
    elif "上周" in query:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
    elif "本周" in query or "这周" in query:
        start = today - timedelta(days=today.weekday())
        end = today
    elif "上个月" in query or "上月" in query:
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
    elif "本月" in query or "这个月" in query:
        start = today.replace(day=1)
        end = today
    else:
        match = re.search(r"(20\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?", q)
        if not match:
            return None, None
        year, month, day = match.groups()
        start = datetime(int(year), int(month), int(day or 1)).date()
        if day:
            end = start
        else:
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = next_month - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _parse_ai_query(query: str) -> dict[str, Any]:
    lower = query.lower()
    file_type = ""
    for key, words in [
        ("folder", ["文件夹", "目录"]),
        ("video", ["视频", "素材", "mp4", "录像"]),
        ("image", ["图片", "照片", "海报", "图"]),
        ("audio", ["音频", "音乐", "录音"]),
        ("archive", ["压缩包", "zip", "rar"]),
        ("document", ["文档", "表格", "excel", "word", "pdf", "ppt"]),
    ]:
        if any(word in lower or word in query for word in words):
            file_type = key
            break

    ext = ""
    for candidate in sorted(EXT_TYPE_MAP, key=len, reverse=True):
        bare = candidate.lstrip(".")
        if re.search(rf"(?<![a-z0-9]){re.escape(bare)}(?![a-z0-9])", lower):
            ext = bare
            file_type = EXT_TYPE_MAP[candidate]
            break

    date_from, date_to = _date_range_from_query(query)
    cleaned = query
    for word in [
        "帮我", "查找", "搜索", "寻找", "找", "一下", "相关", "文件", "资料", "视频", "图片",
        "照片", "文档", "表格", "上周", "本周", "这周", "今天", "昨天", "前天", "上个月", "本月", "这个月",
    ]:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"\b(docx?|xlsx?|pptx?|pdf|mp4|mov|png|jpe?g|zip|rar)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 的，,。 ")

    return {
        "q": cleaned or query,
        "file_type": file_type,
        "extension": ext,
        "date_from": date_from or "",
        "date_to": date_to or "",
    }


def _matches_date(item: dict[str, Any], date_from: str, date_to: str) -> bool:
    if not date_from and not date_to:
        return True
    modified = (item.get("file_modified") or "")[:10]
    if date_from and modified < date_from:
        return False
    if date_to and modified > date_to:
        return False
    return True


def _matches_folder(item: dict[str, Any], folder: str) -> bool:
    if not folder:
        return True
    wanted = os.path.normcase(os.path.normpath(folder))
    parent = os.path.normcase(os.path.normpath(item.get("_parent_path") or ""))
    return parent == wanted


def _search_items(
    *,
    q: str = "",
    file_type: str = "",
    ext: str = "",
    date_from: str = "",
    date_to: str = "",
    folder: str = "",
) -> list[dict[str, Any]]:
    _load_index()
    q = q.strip().lower()
    ext = _normalise_ext(ext)

    with _lock:
        items = list(_files)

    results = []
    for item in items:
        if file_type and item.get("file_type") != file_type:
            continue
        if ext and item.get("file_extension", "").lower() != ext:
            continue
        if not _matches_date(item, date_from, date_to):
            continue
        if not _matches_folder(item, folder):
            continue
        if q and q not in item.get("_search_text", ""):
            continue
        results.append(item)

    results.sort(
        key=lambda item: (
            0 if item.get("file_type") == "folder" else 1,
            item.get("file_modified", ""),
            item.get("file_name", "").lower(),
        ),
        reverse=True,
    )
    return results


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _page(items: list[dict[str, Any]], page: int, per_page: int) -> dict[str, Any]:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    total = len(items)
    total_pages = max(math.ceil(total / per_page), 1)
    start = (page - 1) * per_page
    return {
        "success": True,
        "files": [_public_item(item) for item in items[start:start + per_page]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@router.get("/index/status")
async def index_status():
    _load_index()
    with _lock:
        return _json({
            "success": True,
            "is_indexing": _state["is_indexing"],
            "last_indexed": _state["last_indexed"],
            "total_files": _state["total_files"],
            "message": _state["message"],
            "roots": SEARCH_ROOTS,
        })


@router.post("/index/start")
async def start_index():
    _load_index()
    with _lock:
        if _state["is_indexing"]:
            return _json({"success": True, "message": "索引正在运行"})
        _state["is_indexing"] = True
        _state["message"] = "索引启动中"

    thread = threading.Thread(target=_run_index, name="facai-search-index", daemon=True)
    thread.start()
    return _json({"success": True, "message": "索引已在后台启动"})


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
    items = _search_items(q=q, file_type=type, ext=ext, date_from=date_from, date_to=date_to, folder=folder)
    return _json(_page(items, page, per_page))


@router.post("/ai-search")
async def ai_search(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    query = str(body.get("query") or "").strip()
    page = int(body.get("page") or 1)
    per_page = int(body.get("per_page") or 20)
    if not query:
        return _json({"success": False, "message": "请输入搜索内容", "files": [], "total": 0, "total_pages": 1})

    parsed = _parse_ai_query(query)
    items = _search_items(
        q=parsed["q"],
        file_type=parsed["file_type"],
        ext=parsed["extension"],
        date_from=parsed["date_from"],
        date_to=parsed["date_to"],
    )
    if not items and parsed["q"] != query:
        items = _search_items(
            q=query,
            file_type=parsed["file_type"],
            ext=parsed["extension"],
            date_from=parsed["date_from"],
            date_to=parsed["date_to"],
        )

    payload = _page(items, page, per_page)
    payload["ai_understanding"] = {
        "summary": f"按“{parsed['q']}”搜索" if parsed["q"] else f"搜索：{query}",
        "keywords": [parsed["q"]] if parsed["q"] else [],
        "file_type": parsed["file_type"],
        "extension": parsed["extension"],
        "date_from": parsed["date_from"],
        "date_to": parsed["date_to"],
    }
    return _json(payload)


@router.post("/search-summary")
async def search_summary(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    items = _search_items(
        q=str(body.get("query") or ""),
        file_type=str(body.get("file_type") or ""),
        ext=str(body.get("extension") or ""),
        date_from=str(body.get("date_from") or ""),
        date_to=str(body.get("date_to") or ""),
    )
    top = items[:10]
    lines = [
        "## 搜索结果汇总",
        f"- 共找到 {len(items)} 个匹配项。",
    ]
    if top:
        lines.append("- 前 10 个结果：")
        lines.extend(f"  - {item['file_name']}（{item['file_type']}）" for item in top)
    else:
        lines.append("- 当前条件下没有匹配文件。")
    return _json({"success": True, "summary": "\n".join(lines)})


def _get_indexed_file(file_id: int) -> dict[str, Any] | None:
    _load_index()
    with _lock:
        item = _files_by_id.get(file_id)
    if not item or not _is_allowed_file_path(item.get("file_path", "")):
        return None
    return item


@router.get("/files/{file_id}")
async def get_file(file_id: int):
    item = _get_indexed_file(file_id)
    if not item:
        return _json({"success": False, "message": "文件不存在或索引已过期"}, status_code=404)
    return _json({"success": True, "file": _public_item(item)})


@router.get("/files/{file_id}/download")
async def download_file(file_id: int):
    item = _get_indexed_file(file_id)
    if not item or item.get("file_type") == "folder" or not os.path.exists(item["file_path"]):
        return _json({"success": False, "message": "文件不存在或不能下载"}, status_code=404)
    media_type = mimetypes.guess_type(item["file_path"])[0] or "application/octet-stream"
    return FileResponse(item["file_path"], media_type=media_type, filename=item["file_name"])


@router.get("/files/{file_id}/preview")
async def preview_file(file_id: int):
    item = _get_indexed_file(file_id)
    if not item or item.get("file_type") == "folder" or not os.path.exists(item["file_path"]):
        return _json({"success": False, "message": "文件不存在或不能预览"}, status_code=404)
    media_type = mimetypes.guess_type(item["file_path"])[0] or "application/octet-stream"
    return FileResponse(item["file_path"], media_type=media_type)
