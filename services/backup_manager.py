"""Consistent SQLite backups, retention, offsite copy, and restore verification."""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path


def _resolved_child(directory: Path, path: Path) -> Path:
    root = directory.resolve()
    resolved = path.resolve()
    if resolved.parent != root:
        raise ValueError("Backup path escaped the configured backup directory")
    return resolved


def _remove_backup_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def verify_backup(backup_path: str | os.PathLike[str]) -> dict:
    path = Path(backup_path).resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        table_count = int(connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0])
    if integrity.lower() != "ok":
        raise RuntimeError(f"Backup integrity check failed: {integrity}")
    return {
        "path": str(path),
        "integrity_check": integrity.lower(),
        "table_count": table_count,
        "size_bytes": path.stat().st_size,
    }


def create_backup(
    source_path: str | os.PathLike[str],
    *,
    backup_dir: str | os.PathLike[str] | None = None,
    offsite_dir: str | os.PathLike[str] | None = None,
) -> Path:
    source = Path(source_path).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    destination_dir = Path(backup_dir).resolve() if backup_dir else source.parent / "backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = _resolved_child(
        destination_dir,
        destination_dir / f"{source.stem}_daily_{stamp}{source.suffix or '.db'}",
    )
    with closing(sqlite3.connect(source)) as source_db, closing(sqlite3.connect(destination)) as backup_db:
        source_db.backup(backup_db)
    try:
        verify_backup(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        _remove_backup_sidecars(destination)
        raise
    _remove_backup_sidecars(destination)

    if offsite_dir:
        offsite = Path(offsite_dir).resolve()
        offsite.mkdir(parents=True, exist_ok=True)
        offsite_path = _resolved_child(offsite, offsite / destination.name)
        shutil.copy2(destination, offsite_path)
        verify_backup(offsite_path)
        _remove_backup_sidecars(offsite_path)
    return destination


def restore_backup(
    backup_path: str | os.PathLike[str],
    destination_path: str | os.PathLike[str],
) -> Path:
    source = Path(backup_path).resolve()
    destination = Path(destination_path).resolve()
    verify_backup(source)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as backup_db, closing(sqlite3.connect(destination)) as restored_db:
        backup_db.backup(restored_db)
    verify_backup(destination)
    return destination


def verify_restore_drill(
    backup_path: str | os.PathLike[str],
    *,
    work_dir: str | os.PathLike[str] | None = None,
) -> dict:
    """Restore a backup into an isolated temporary directory and verify it."""

    source = Path(backup_path).resolve()
    parent = Path(work_dir).resolve() if work_dir else source.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="facai-restore-drill-", dir=parent) as temp_dir:
        restored = restore_backup(source, Path(temp_dir) / source.name)
        report = verify_backup(restored)
    return {
        "integrity_check": report["integrity_check"],
        "table_count": report["table_count"],
        "size_bytes": report["size_bytes"],
    }


def prune_backups(
    backup_dir: str | os.PathLike[str],
    *,
    retention_days: int,
    max_daily_backups: int,
    max_migration_backups: int,
) -> list[Path]:
    directory = Path(backup_dir).resolve()
    if not directory.exists():
        return []
    cutoff = datetime.now().timestamp() - max(0, retention_days) * 86400
    groups = (
        (sorted(directory.glob("*_daily_*.db"), key=lambda item: item.stat().st_mtime, reverse=True), max_daily_backups),
        (sorted(directory.glob("*_before_migration_*.db"), key=lambda item: item.stat().st_mtime, reverse=True), max_migration_backups),
    )
    removed: list[Path] = []
    for paths, maximum in groups:
        for index, path in enumerate(paths):
            resolved = _resolved_child(directory, path)
            if index < max(0, maximum) and resolved.stat().st_mtime >= cutoff:
                continue
            resolved.unlink(missing_ok=True)
            _remove_backup_sidecars(resolved)
            removed.append(resolved)
    return removed


def ensure_daily_backup(
    source_path: str | os.PathLike[str],
    *,
    backup_dir: str | os.PathLike[str] | None = None,
    offsite_dir: str | os.PathLike[str] | None = None,
) -> Path:
    source = Path(source_path).resolve()
    directory = Path(backup_dir).resolve() if backup_dir else source.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    existing = sorted(
        directory.glob(f"{source.stem}_daily_{today}_*{source.suffix or '.db'}"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if existing:
        backup = existing[0].resolve()
        verify_backup(backup)
    else:
        backup = create_backup(source, backup_dir=directory, offsite_dir=offsite_dir)
    prune_backups(
        directory,
        retention_days=int(os.getenv("FACAI_BACKUP_RETENTION_DAYS", "30")),
        max_daily_backups=int(os.getenv("FACAI_BACKUP_MAX_DAILY", "30")),
        max_migration_backups=int(os.getenv("FACAI_BACKUP_MAX_MIGRATION", "10")),
    )
    verify_restore_drill(backup)
    _remove_backup_sidecars(backup)
    return backup


def ensure_configured_daily_backup() -> Path | None:
    if os.getenv("FACAI_DAILY_BACKUP_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    from database import engine

    if engine.dialect.name != "sqlite" or not engine.url.database or engine.url.database == ":memory:":
        return None
    source = Path(engine.url.database)
    if not source.is_absolute():
        source = Path.cwd() / source
    if not source.exists():
        return None
    offsite = os.getenv("FACAI_BACKUP_OFFSITE_DIR", "").strip() or None
    return ensure_daily_backup(source, offsite_dir=offsite)
