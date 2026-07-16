"""Local TXT script scan core, extracted from the API router."""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session


async def scan_local_txt_scripts(
    *,
    source_dir: Path,
    category: str,
    video_type: str,
    tags: str,
    product_name: str,
    db: Session,
) -> None:
    from routers import templates as routes

    MAX_UPLOAD_SIZE = routes.MAX_UPLOAD_SIZE
    ViralScript = routes.ViralScript
    _analyze_local_txt_script = routes._analyze_local_txt_script
    _append_local_txt_scan_error = routes._append_local_txt_scan_error
    _combine_tags = routes._combine_tags
    _decode_txt = routes._decode_txt
    _discover_local_txt_files = routes._discover_local_txt_files
    _find_existing_local_txt_script = routes._find_existing_local_txt_script
    _local_txt_scan_lock = routes._local_txt_scan_lock
    _local_txt_scan_state = routes._local_txt_scan_state
    _relative_path_for_display = routes._relative_path_for_display
    _resolve_local_txt_category_from_path = routes._resolve_local_txt_category_from_path
    _resolve_local_txt_script_category = routes._resolve_local_txt_script_category
    _script_content_hash = routes._script_content_hash
    _sync_viral_index = routes._sync_viral_index
    _title_from_relative_path = routes._title_from_relative_path
    _update_local_txt_scan_state = routes._update_local_txt_scan_state
    format_script = routes.format_script
    files = _discover_local_txt_files(source_dir)
    _update_local_txt_scan_state(total=len(files), message=f"发现 {len(files)} 个 txt 文件")

    for path in files:
        safe_name = path.name
        relative_path = _relative_path_for_display(path, source_dir)
        try:
            stat = path.stat()
            if stat.st_size > MAX_UPLOAD_SIZE:
                raise ValueError(f"文件过大，请控制在 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB 以内。")

            script_text = format_script(_decode_txt(path.read_bytes()))
            if len(script_text) < 20:
                raise ValueError("脚本内容太短")

            content_sha256 = _script_content_hash(script_text)
            path_category = _resolve_local_txt_category_from_path(db, relative_path)
            auto_category = _resolve_local_txt_script_category(
                db,
                category=category,
                product_name=product_name,
                relative_path=relative_path,
                path_category=path_category,
            )
            existing_script = _find_existing_local_txt_script(db, str(path), content_sha256)
            if existing_script:
                category_updated = False
                if path_category and existing_script.category != path_category:
                    existing_script.category = path_category
                    from services.vector_sync import enqueue_vector_sync
                    enqueue_vector_sync(db, "viral_script", existing_script.id, "upsert")
                    db.commit()
                    db.refresh(existing_script)
                    _sync_viral_index(existing_script, db)
                    category_updated = True
                with _local_txt_scan_lock:
                    _local_txt_scan_state["skipped"] += 1
                    _local_txt_scan_state["processed"] += 1
                    if category_updated:
                        _local_txt_scan_state["message"] = f"已修正重复脚本品类：{relative_path}"
                    else:
                        _local_txt_scan_state["message"] = f"已跳过重复脚本：{relative_path}"
                continue

            ai_analysis = await _analyze_local_txt_script(script_text, video_type)
            viral = ViralScript(
                category=auto_category,
                video_type=ai_analysis.get("video_type") or video_type or "机制类",
                title=_title_from_relative_path(relative_path),
                script_content=script_text,
                tags=_combine_tags(
                    _combine_tags(tags or "本地txt", product_name),
                    ai_analysis.get("tags", ""),
                ),
                performance_data={
                    "source": "本地TXT扫描",
                    "product_name": product_name or "",
                    "local_path": str(path),
                    "relative_path": relative_path,
                    "filename": safe_name,
                    "content_sha256": content_sha256,
                    "file_size": stat.st_size,
                    "file_modified": datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat(),
                    "ai_structure": ai_analysis.get("structure", ""),
                    "ai_viral_points": ai_analysis.get("viral_points", ""),
                },
            )
            db.add(viral)
            db.flush()
            from services.vector_sync import enqueue_vector_sync
            enqueue_vector_sync(db, "viral_script", viral.id, "upsert")
            db.commit()
            db.refresh(viral)
            _sync_viral_index(viral, db)
            with _local_txt_scan_lock:
                _local_txt_scan_state["success"] += 1
                _local_txt_scan_state["processed"] += 1
                _local_txt_scan_state["ids"].append(viral.id)
                _local_txt_scan_state["message"] = f"已导入：{relative_path}"
        except Exception as exc:
            db.rollback()
            with _local_txt_scan_lock:
                _local_txt_scan_state["skipped"] += 1
                _local_txt_scan_state["processed"] += 1
                _local_txt_scan_state["message"] = f"跳过：{relative_path}"
            _append_local_txt_scan_error(f"{relative_path}: {exc}")
