"""Excel viral-script workbook import core, extracted from the API router."""

from pathlib import Path

from sqlalchemy.orm import Session


def import_workbook_scripts(workbook_path: Path, filename: str, workbook_sha256: str, db: Session) -> None:
    from routers import templates as routes

    ViralScript = routes.ViralScript
    _append_workbook_import_error = routes._append_workbook_import_error
    _existing_cake_images = routes._existing_cake_images
    _extract_workbook_rows = routes._extract_workbook_rows
    _find_existing_workbook_script = routes._find_existing_workbook_script
    _save_workbook_cake_images = routes._save_workbook_cake_images
    _sync_workbook_viral_index = routes._sync_workbook_viral_index
    _update_workbook_import_state = routes._update_workbook_import_state
    _workbook_import_lock = routes._workbook_import_lock
    _workbook_import_state = routes._workbook_import_state
    _workbook_performance_data = routes._workbook_performance_data
    _workbook_tags = routes._workbook_tags
    rows = _extract_workbook_rows(workbook_path, workbook_sha256, filename)
    _update_workbook_import_state(total=len(rows), message=f"发现 {len(rows)} 条 Excel 脚本")

    for row_info in rows:
        try:
            existing = _find_existing_workbook_script(db, row_info)
            if existing:
                existing_images = _existing_cake_images(existing)
                new_images = [] if existing_images else _save_workbook_cake_images(existing.id, row_info)
                existing_data = existing.performance_data if isinstance(existing.performance_data, dict) else {}
                should_update_metadata = bool(new_images) or not existing_data.get("workbook_sha256")
                new_data = _workbook_performance_data(row_info, existing_data, new_images) if should_update_metadata else existing_data
                if should_update_metadata and new_data != existing_data:
                    existing.performance_data = new_data
                    from services.vector_sync import enqueue_vector_sync
                    enqueue_vector_sync(db, "viral_script", existing.id, "upsert")
                    db.commit()
                    db.refresh(existing)
                    _sync_workbook_viral_index(existing, db)
                    with _workbook_import_lock:
                        _workbook_import_state["updated"] += 1
                        _workbook_import_state["image_count"] += len(new_images)
                        _workbook_import_state["message"] = f"已补充：{row_info['title']}"
                else:
                    with _workbook_import_lock:
                        _workbook_import_state["skipped"] += 1
                        _workbook_import_state["message"] = f"已跳过重复脚本：{row_info['title']}"
                with _workbook_import_lock:
                    _workbook_import_state["processed"] += 1
                continue

            viral = ViralScript(
                category=row_info["category"],
                video_type=row_info["video_type"],
                title=row_info["title"],
                script_content=row_info["script_content"],
                tags=_workbook_tags(row_info["sheet_name"], row_info["raw_type"], bool(row_info["images"])),
                is_high_conversion=row_info["is_high_conversion"],
                performance_data=_workbook_performance_data(row_info, {}, []),
            )
            db.add(viral)
            db.flush()
            from services.vector_sync import enqueue_vector_sync
            enqueue_vector_sync(db, "viral_script", viral.id, "upsert")
            db.commit()
            db.refresh(viral)
            cake_images = _save_workbook_cake_images(viral.id, row_info)
            if cake_images:
                viral.performance_data = _workbook_performance_data(row_info, viral.performance_data, cake_images)
                enqueue_vector_sync(db, "viral_script", viral.id, "upsert")
                db.commit()
                db.refresh(viral)
            _sync_workbook_viral_index(viral, db)
            with _workbook_import_lock:
                _workbook_import_state["created"] += 1
                _workbook_import_state["processed"] += 1
                _workbook_import_state["image_count"] += len(cake_images)
                _workbook_import_state["ids"].append(viral.id)
                _workbook_import_state["message"] = f"已导入：{row_info['title']}"
        except Exception as exc:
            db.rollback()
            with _workbook_import_lock:
                _workbook_import_state["skipped"] += 1
                _workbook_import_state["processed"] += 1
                _workbook_import_state["message"] = f"跳过：{row_info.get('title') or row_info.get('sheet_name')}"
            _append_workbook_import_error(f"{row_info.get('title') or row_info.get('sheet_name')}: {exc}")
