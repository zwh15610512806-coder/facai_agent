import math
import mimetypes
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from routers.jobs import owner_key_for_request
from services.background_jobs import create_background_job, job_to_dict, register_background_handler


router = APIRouter(tags=["search"])

DEFAULT_SEARCH_ROOTS = [r"\\192.168.0.118\法采共享盘2026"]
SEARCH_ROOTS = [
    root.strip()
    for root in os.getenv("SEARCH_ROOTS", ";".join(DEFAULT_SEARCH_ROOTS)).split(";")
    if root.strip()
]

INDEX_PATH = Path(os.getenv("SEARCH_INDEX_PATH", "./data/search_index.json"))
INDEX_DB_PATH = Path(os.getenv("SEARCH_INDEX_DB_PATH", "./data/search_index.db"))
SEARCH_INDEX_BACKEND = os.getenv("SEARCH_INDEX_BACKEND", "sqlite").strip().lower() or "sqlite"
_DEFAULT_INDEX_PATH = INDEX_PATH
_DEFAULT_INDEX_DB_PATH = INDEX_DB_PATH
_BACKEND_WAS_EXPLICIT = "SEARCH_INDEX_BACKEND" in os.environ

FILE_TYPE_MAP = {
    "document": [".doc", ".docx", ".pdf", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md", ".json", ".xml"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
    "video": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"],
    "audio": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"],
    "archive": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
}
EXT_TYPE_MAP = {ext: file_type for file_type, exts in FILE_TYPE_MAP.items() for ext in exts}
PREVIEW_RANGE_CHUNK_SIZE = 1024 * 1024
PUBLIC_FILE_FIELDS = (
    "id",
    "file_name",
    "file_type",
    "file_extension",
    "file_size",
    "file_modified",
    "parent_folder",
)

_lock = threading.RLock()
_loaded = False
_files: list[dict[str, Any]] = []
_files_by_id: dict[int, dict[str, Any]] = {}
_state: dict[str, Any] = {
    "is_indexing": False,
    "last_indexed": None,
    "total_files": 0,
    "message": "",
    "migration_status": "not_started",
    "last_error": "",
}


def _active_backend() -> str:
    if SEARCH_INDEX_BACKEND == "json":
        return "json"
    if _BACKEND_WAS_EXPLICIT or INDEX_DB_PATH != _DEFAULT_INDEX_DB_PATH or INDEX_PATH == _DEFAULT_INDEX_PATH:
        return "sqlite"
    # Existing tests and one-release callers that override only SEARCH_INDEX_PATH
    # retain the legacy JSON backend.
    return "json"


def _sqlite_index():
    from services.search_index import SQLiteSearchIndex

    return SQLiteSearchIndex(INDEX_DB_PATH)


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
        if _active_backend() == "sqlite":
            try:
                index = _sqlite_index()
                if not INDEX_DB_PATH.exists() and INDEX_PATH.exists():
                    _state["migration_status"] = "importing_json"
                    index.import_json(INDEX_PATH, allowed_path=_is_allowed_file_path)
                    _state["migration_status"] = "imported_json"
                elif INDEX_DB_PATH.exists():
                    _state["migration_status"] = "ready"
                else:
                    _state["migration_status"] = "waiting_for_index"
                status = index.status()
                _files = []
                _files_by_id = {}
                _state["last_indexed"] = status["last_indexed"]
                _state["total_files"] = status["total_files"]
                _state["last_error"] = ""
            except Exception as exc:
                _state["migration_status"] = "failed"
                _state["last_error"] = str(exc)[:1000]
                _state["message"] = f"读取 SQLite 索引失败：{exc}"
            return
        if not INDEX_PATH.exists():
            _state["migration_status"] = "json_missing"
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
            _state["migration_status"] = "json_ready"
        except Exception as exc:
            _state["message"] = f"读取索引缓存失败：{exc}"
            _state["last_error"] = str(exc)[:1000]


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


def _iter_scan_entries(errors: list[str]):
    next_id = 1
    for root in SEARCH_ROOTS:
        if not os.path.exists(root):
            errors.append(f"路径不可访问：{root}")
            continue
        for current_root, dir_names, file_names in os.walk(root):
            dir_names.sort()
            file_names.sort()
            for name, is_dir in [*( (name, True) for name in dir_names), *( (name, False) for name in file_names)]:
                path = os.path.join(current_root, name)
                entry = _entry(next_id, path, root, is_dir=is_dir)
                if entry:
                    yield entry
                    next_id += 1


def _publish_partial_index(files: list[dict[str, Any]], force: bool = False) -> None:
    if not force and len(files) % 200 != 0:
        return
    with _lock:
        _files[:] = files
        _files_by_id.clear()
        _files_by_id.update({item["id"]: item for item in files})
        _state["total_files"] = len(files)
        _state["message"] = f"索引中，已发现 {len(files)} 个文件"


def _run_index(job_id: int | None = None) -> None:
    global _files, _files_by_id
    with _lock:
        _state["is_indexing"] = True
        _state["message"] = "索引中"

    try:
        if _active_backend() == "sqlite":
            errors: list[str] = []
            last_indexed = _now_iso()

            def publish_progress(count: int) -> None:
                with _lock:
                    _state["total_files"] = count
                    _state["message"] = f"索引中，已发现 {count} 个文件"
                if job_id:
                    from services.job_runs import update_job
                    update_job(job_id, current=count, message=f"已发现 {count} 个文件")

            count = _sqlite_index().replace_from_entries(
                _iter_scan_entries(errors),
                last_indexed,
                sort_and_reassign=True,
                progress=publish_progress,
            )
            # Keep a one-release JSON fallback without rebuilding a 61 MB list in memory.
            _sqlite_index().export_json(INDEX_PATH)
            with _lock:
                _files = []
                _files_by_id = {}
                _state["last_indexed"] = last_indexed
                _state["total_files"] = count
                _state["message"] = "；".join(errors) if errors else "索引完成"
                _state["migration_status"] = "ready"
                _state["last_error"] = ""
            if job_id:
                from services.job_runs import finish_job
                finish_job(
                    job_id,
                    status="succeeded",
                    message="检索索引重建完成",
                    details={"total_files": count, "errors": errors},
                )
            return
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
            _state["last_error"] = str(exc)[:1000]
        if job_id:
            from services.job_runs import finish_job
            finish_job(
                job_id,
                status="failed",
                message="检索索引重建失败",
                error_summary=str(exc),
            )
    finally:
        with _lock:
            _state["is_indexing"] = False


def _run_index_task(payload: dict) -> None:
    _run_index(payload.get("job_id"))


from services.task_queue import register_task_handler
register_task_handler("search_rebuild", _run_index_task)


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
    if _active_backend() == "sqlite":
        return _sqlite_index().search(
            q=q,
            file_type=file_type,
            ext=ext,
            date_from=date_from,
            date_to=date_to,
            folder=folder,
        )
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
    """Expose metadata by opaque index ID without leaking server paths."""

    return {key: item.get(key) for key in PUBLIC_FILE_FIELDS}


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


def _search_page(
    *,
    q: str = "",
    file_type: str = "",
    ext: str = "",
    date_from: str = "",
    date_to: str = "",
    folder: str = "",
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    _load_index()
    if _active_backend() == "sqlite":
        payload = _sqlite_index().search_page(
            q=q,
            file_type=file_type,
            ext=ext,
            date_from=date_from,
            date_to=date_to,
            folder=folder,
            page=page,
            per_page=per_page,
        )
        payload["files"] = [_public_item(item) for item in payload["files"]]
        return {"success": True, **payload}
    return _page(
        _search_items(
            q=q,
            file_type=file_type,
            ext=ext,
            date_from=date_from,
            date_to=date_to,
            folder=folder,
        ),
        page,
        per_page,
    )


@router.get("/index/status")
async def index_status():
    _load_index()
    with _lock:
        payload = {
            "success": True,
            "is_indexing": _state["is_indexing"],
            "last_indexed": _state["last_indexed"],
            "total_files": _state["total_files"],
            "message": _state["message"],
            "root_count": len(SEARCH_ROOTS),
            "backend": _active_backend(),
            "migration_status": _state.get("migration_status", "not_started"),
            "last_error": _state.get("last_error", ""),
        }
    if _active_backend() == "sqlite":
        from services.job_runs import latest_job
        job = latest_job("search_rebuild")
        payload["job_run"] = (
            {
                key: job.get(key)
                for key in (
                    "id",
                    "status",
                    "progress",
                    "progress_current",
                    "progress_total",
                    "message",
                    "created_at",
                    "updated_at",
                )
            }
            if job else None
        )
    return _json(payload)


@router.post("/index/start")
async def start_index(request: Request = None):
    _load_index()
    with _lock:
        if _state["is_indexing"]:
            return _json({"success": True, "message": "索引正在运行"})
        _state["is_indexing"] = True
        _state["message"] = "索引启动中"

    job_id = None
    if _active_backend() == "sqlite":
        from services.job_runs import start_job
        client_id = request.headers.get("X-Facai-Client-Id") if request is not None else None
        from routers.jobs import owner_key_for_request
        job_id = start_job(
            "search_rebuild",
            message="检索索引启动中",
            details={"root_count": len(SEARCH_ROOTS)},
            owner_key=owner_key_for_request(request, client_id) if client_id else None,
            origin_path="/app/search",
        )
    from services.task_queue import enqueue_task, task_worker_status
    if task_worker_status()["alive"]:
        enqueue_task("search_rebuild", {"job_id": job_id}, max_attempts=3, job_run_id=job_id)
    else:
        # Router-only test/dev apps do not run the main lifespan worker.
        threading.Thread(
            target=_run_index,
            args=(job_id,),
            name="facai-search-index-fallback",
            daemon=True,
        ).start()
    return _json({"success": True, "message": "索引已在后台启动"})


@router.get("/search")
async def search_files(
    q: str = Query(""),
    type: str = Query(""),
    ext: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    folder_id: int | None = Query(None, ge=1),
    page: int = Query(1),
    per_page: int = Query(20),
):
    folder = ""
    if folder_id is not None:
        folder_item = _get_indexed_file(folder_id)
        if not folder_item or folder_item.get("file_type") != "folder":
            return _json({"success": False, "message": "文件夹不存在或索引已过期"}, status_code=404)
        folder = str(folder_item.get("file_path") or "")
    return _json(_search_page(
        q=q,
        file_type=type,
        ext=ext,
        date_from=date_from,
        date_to=date_to,
        folder=folder,
        page=page,
        per_page=per_page,
    ))


def _ai_search_payload(body: dict[str, Any]) -> dict[str, Any]:
    query = str(body.get("query") or "").strip()
    page = int(body.get("page") or 1)
    per_page = int(body.get("per_page") or 20)
    if not query:
        return {"success": False, "message": "请输入搜索内容", "files": [], "total": 0, "total_pages": 1}

    parsed = _parse_ai_query(query)
    payload = _search_page(
        q=parsed["q"],
        file_type=parsed["file_type"],
        ext=parsed["extension"],
        date_from=parsed["date_from"],
        date_to=parsed["date_to"],
        page=page,
        per_page=per_page,
    )
    if not payload["files"] and parsed["q"] != query:
        payload = _search_page(
            q=query,
            file_type=parsed["file_type"],
            ext=parsed["extension"],
            date_from=parsed["date_from"],
            date_to=parsed["date_to"],
            page=page,
            per_page=per_page,
        )
    payload["ai_understanding"] = {
        "summary": f"按“{parsed['q']}”搜索" if parsed["q"] else f"搜索：{query}",
        "keywords": [parsed["q"]] if parsed["q"] else [],
        "file_type": parsed["file_type"],
        "extension": parsed["extension"],
        "date_from": parsed["date_from"],
        "date_to": parsed["date_to"],
    }
    return payload


@router.post("/ai-search")
async def ai_search(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _json(_ai_search_payload(body))


def _search_summary_payload(body: dict[str, Any]) -> dict[str, Any]:
    payload = _search_page(
        q=str(body.get("query") or ""),
        file_type=str(body.get("file_type") or ""),
        ext=str(body.get("extension") or ""),
        date_from=str(body.get("date_from") or ""),
        date_to=str(body.get("date_to") or ""),
        page=1,
        per_page=10,
    )
    top = payload["files"]
    total = payload["total"]
    lines = [
        "## 搜索结果汇总",
        f"- 共找到 {total} 个匹配项。",
    ]
    if top:
        lines.append("- 前 10 个结果：")
        lines.extend(f"  - {item['file_name']}（{item['file_type']}）" for item in top)
    else:
        lines.append("- 当前条件下没有匹配文件。")
    return {"success": True, "summary": "\n".join(lines)}


@router.post("/search-summary")
async def search_summary(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _json(_search_summary_payload(body))


def _enqueue_search_job(
    *,
    job_type: str,
    payload: dict[str, Any],
    request: Request,
    client_id: str | None,
    source_ref: str | None,
    idempotency_key: str | None,
    db: Session,
):
    job, created = create_background_job(
        db,
        owner_key=owner_key_for_request(request, client_id),
        job_type=job_type,
        request_payload=payload,
        origin_path=request.headers.get("X-Facai-Origin-Path") or "/app/search",
        source_ref=source_ref or "search",
        queue_group="ai",
        idempotency_key=idempotency_key or "",
        max_attempts=2,
        message="AI 搜索任务等待执行" if job_type.endswith("ai_search") else "搜索汇总等待执行",
    )
    return {"job": job_to_dict(job), "created": created}


@router.post("/ai-search/jobs", status_code=202)
async def enqueue_ai_search(
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    x_facai_source_ref: str | None = Header(None, alias="X-Facai-Source-Ref"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _enqueue_search_job(job_type="ai.search.ai_search", payload=payload, request=request, client_id=x_facai_client_id, source_ref=x_facai_source_ref, idempotency_key=idempotency_key, db=db)


@router.post("/search-summary/jobs", status_code=202)
async def enqueue_search_summary(
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    x_facai_source_ref: str | None = Header(None, alias="X-Facai-Source-Ref"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _enqueue_search_job(job_type="ai.search.summary", payload=payload, request=request, client_id=x_facai_client_id, source_ref=x_facai_source_ref, idempotency_key=idempotency_key, db=db)


register_background_handler("ai.search.ai_search", lambda payload, _job_id: _ai_search_payload(payload), queue_group="ai")
register_background_handler("ai.search.summary", lambda payload, _job_id: _search_summary_payload(payload), queue_group="ai")


def _get_indexed_file(file_id: int) -> dict[str, Any] | None:
    _load_index()
    if _active_backend() == "sqlite":
        item = _sqlite_index().get(file_id)
        if not item or not _is_allowed_file_path(item.get("file_path", "")):
            return None
        return item
    with _lock:
        item = _files_by_id.get(file_id)
    if not item or not _is_allowed_file_path(item.get("file_path", "")):
        return None
    return item


def _parse_byte_range(
    range_header: str,
    file_size: int,
    *,
    max_open_ended_length: int | None = None,
) -> tuple[int, int] | None:
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not match or file_size <= 0:
        return None

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None

    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
        if not end_text and max_open_ended_length:
            end = min(end, start + max_open_ended_length - 1)
    else:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            return None
        start = max(file_size - suffix_length, 0)
        end = file_size - 1

    if start >= file_size or start > end:
        return None
    return start, min(end, file_size - 1)


def _iter_file_range(path: str, start: int, end: int):
    with open(path, "rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _range_response(path: str, media_type: str, range_header: str) -> StreamingResponse | None:
    file_size = os.path.getsize(path)
    parsed = _parse_byte_range(
        range_header,
        file_size,
        max_open_ended_length=PREVIEW_RANGE_CHUNK_SIZE,
    )
    if not parsed:
        return None

    start, end = parsed
    return StreamingResponse(
        _iter_file_range(path, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
        },
    )


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
async def preview_file(file_id: int, request: Request):
    item = _get_indexed_file(file_id)
    if not item or item.get("file_type") == "folder" or not os.path.exists(item["file_path"]):
        return _json({"success": False, "message": "文件不存在或不能预览"}, status_code=404)
    media_type = mimetypes.guess_type(item["file_path"])[0] or "application/octet-stream"
    range_header = request.headers.get("range")
    if range_header:
        partial = _range_response(item["file_path"], media_type, range_header)
        if partial:
            return partial
    return FileResponse(item["file_path"], media_type=media_type, headers={"Accept-Ranges": "bytes"})
