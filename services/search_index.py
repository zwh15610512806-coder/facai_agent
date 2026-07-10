"""Disk-backed FTS5 trigram index for shared-drive file search."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


FILE_COLUMNS = (
    "id",
    "file_name",
    "file_path",
    "file_type",
    "file_extension",
    "file_size",
    "file_modified",
    "parent_folder",
    "parent_path",
    "search_text",
)


def _normalise_folder(path: str) -> str:
    return os.path.normcase(os.path.normpath(path or ""))


class SQLiteSearchIndex:
    """Open-per-operation SQLite index; no process-wide file list is retained."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self, path: Path | None = None) -> sqlite3.Connection:
        target = path or self.path
        connection = sqlite3.connect(target, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE index_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_extension TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                file_modified TEXT NOT NULL DEFAULT '',
                parent_folder TEXT NOT NULL DEFAULT '',
                parent_path TEXT NOT NULL DEFAULT '',
                search_text TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX idx_files_type ON files(file_type);
            CREATE INDEX idx_files_extension ON files(file_extension);
            CREATE INDEX idx_files_modified ON files(file_modified);
            CREATE INDEX idx_files_parent ON files(parent_path);
            CREATE VIRTUAL TABLE files_fts USING fts5(
                search_text,
                content='files',
                content_rowid='id',
                tokenize='trigram'
            );
            CREATE TRIGGER files_ai AFTER INSERT ON files BEGIN
                INSERT INTO files_fts(rowid, search_text) VALUES (new.id, new.search_text);
            END;
            CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, search_text)
                VALUES ('delete', old.id, old.search_text);
            END;
            CREATE TRIGGER files_au AFTER UPDATE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, search_text)
                VALUES ('delete', old.id, old.search_text);
                INSERT INTO files_fts(rowid, search_text) VALUES (new.id, new.search_text);
            END;
            """
        )

    @staticmethod
    def _row_values(item: dict[str, Any], *, item_id: int | None = None) -> tuple:
        path = str(item.get("file_path") or "")
        parent_path = str(item.get("_parent_path") or os.path.dirname(path))
        search_text = str(
            item.get("_search_text")
            or f"{item.get('file_name', '')} {path}"
        ).lower()
        return (
            int(item_id if item_id is not None else item.get("id") or 0),
            str(item.get("file_name") or ""),
            path,
            str(item.get("file_type") or "other"),
            str(item.get("file_extension") or "").lower().lstrip("."),
            int(item.get("file_size") or 0),
            str(item.get("file_modified") or ""),
            str(item.get("parent_folder") or ""),
            _normalise_folder(parent_path),
            search_text,
        )

    def replace_from_entries(
        self,
        entries: Iterable[dict[str, Any]],
        last_indexed: str,
        *,
        sort_and_reassign: bool = False,
        progress: Callable[[int], None] | None = None,
    ) -> int:
        """Build a temporary DB and atomically replace the live index."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            temp_path.unlink(missing_ok=True)
            connection = self._connect(temp_path)
            try:
                self._create_schema(connection)
                if sort_and_reassign:
                    connection.execute(
                        """
                        CREATE TABLE scan_entries (
                            file_name TEXT, file_path TEXT, file_type TEXT,
                            file_extension TEXT, file_size INTEGER, file_modified TEXT,
                            parent_folder TEXT, parent_path TEXT, search_text TEXT
                        )
                        """
                    )
                count = 0
                batch: list[tuple] = []
                for item in entries:
                    count += 1
                    values = self._row_values(item, item_id=count if sort_and_reassign else None)
                    batch.append(values[1:] if sort_and_reassign else values)
                    if len(batch) >= 1000:
                        self._insert_batch(connection, batch, sort_and_reassign)
                        batch.clear()
                        if progress:
                            progress(count)
                if batch:
                    self._insert_batch(connection, batch, sort_and_reassign)
                if sort_and_reassign:
                    connection.execute(
                        """
                        INSERT INTO files(
                            file_name,file_path,file_type,file_extension,file_size,
                            file_modified,parent_folder,parent_path,search_text
                        )
                        SELECT file_name,file_path,file_type,file_extension,file_size,
                               file_modified,parent_folder,parent_path,search_text
                        FROM scan_entries
                        ORDER BY CASE WHEN file_type='folder' THEN 0 ELSE 1 END,
                                 lower(file_name) ASC
                        """
                    )
                    connection.execute("DROP TABLE scan_entries")
                connection.executemany(
                    "INSERT INTO index_meta(key,value) VALUES (?,?)",
                    [
                        ("schema_version", "1"),
                        ("last_indexed", last_indexed or ""),
                        ("total_files", str(count)),
                    ],
                )
                connection.commit()
            finally:
                connection.close()
            os.replace(temp_path, self.path)
            return count
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _insert_batch(connection: sqlite3.Connection, batch: list[tuple], staged: bool) -> None:
        if staged:
            connection.executemany(
                """
                INSERT INTO scan_entries(
                    file_name,file_path,file_type,file_extension,file_size,
                    file_modified,parent_folder,parent_path,search_text
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                batch,
            )
        else:
            connection.executemany(
                """
                INSERT INTO files(
                    id,file_name,file_path,file_type,file_extension,file_size,
                    file_modified,parent_folder,parent_path,search_text
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                batch,
            )

    def import_json(self, json_path: str | Path, *, allowed_path: Callable[[str], bool]) -> int:
        source = Path(json_path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        entries = (
            item
            for item in (payload.get("files") or [])
            if allowed_path(str(item.get("file_path") or ""))
        )
        return self.replace_from_entries(entries, str(payload.get("last_indexed") or ""))

    def export_json(self, json_path: str | Path) -> None:
        """Stream a compatibility JSON snapshot without materializing every row."""

        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        status = self.status()
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id,file_name,file_path,file_type,file_extension,file_size,
                       file_modified,parent_folder
                FROM files ORDER BY id
                """
            )
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write('{"last_indexed":')
                handle.write(json.dumps(status.get("last_indexed"), ensure_ascii=False))
                handle.write(',"files":[')
                first = True
                for row in rows:
                    if not first:
                        handle.write(",")
                    first = False
                    handle.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
                handle.write("]}")
            os.replace(temp_path, target)
        finally:
            connection.close()
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _select_columns() -> str:
        return (
            "f.id,f.file_name,f.file_path,f.file_type,f.file_extension,"
            "f.file_size,f.file_modified,f.parent_folder,"
            "f.parent_path AS _parent_path,f.search_text AS _search_text"
        )

    def _where(
        self,
        *,
        q: str,
        file_type: str,
        ext: str,
        date_from: str,
        date_to: str,
        folder: str,
    ) -> tuple[str, list[Any], str]:
        conditions: list[str] = []
        params: list[Any] = []
        join = ""
        query = (q or "").strip().lower()
        if query:
            if len(query) >= 3:
                join = " JOIN files_fts ON files_fts.rowid=f.id "
                conditions.append("files_fts MATCH ?")
                params.append('"' + query.replace('"', '""') + '"')
            else:
                conditions.append("f.search_text LIKE ?")
                params.append(f"%{query}%")
        if file_type:
            conditions.append("f.file_type=?")
            params.append(file_type)
        normal_ext = (ext or "").strip().lower().lstrip(".")
        if normal_ext:
            conditions.append("f.file_extension=?")
            params.append(normal_ext)
        if date_from:
            conditions.append("substr(f.file_modified,1,10)>=?")
            params.append(date_from)
        if date_to:
            conditions.append("substr(f.file_modified,1,10)<=?")
            params.append(date_to)
        if folder:
            conditions.append("f.parent_path=?")
            params.append(_normalise_folder(folder))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return join, params, where

    @staticmethod
    def _rows_to_items(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def search(
        self,
        *,
        q: str = "",
        file_type: str = "",
        ext: str = "",
        date_from: str = "",
        date_to: str = "",
        folder: str = "",
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        join, params, where = self._where(
            q=q,
            file_type=file_type,
            ext=ext,
            date_from=date_from,
            date_to=date_to,
            folder=folder,
        )
        sql = (
            f"SELECT {self._select_columns()} FROM files f{join}{where} "
            "ORDER BY CASE WHEN f.file_type='folder' THEN 0 ELSE 1 END DESC, "
            "f.file_modified DESC, lower(f.file_name) DESC"
        )
        connection = self._connect()
        try:
            return self._rows_to_items(connection.execute(sql, params))
        finally:
            connection.close()

    def search_page(self, *, page: int = 1, per_page: int = 20, **filters) -> dict[str, Any]:
        page = max(int(page or 1), 1)
        per_page = min(max(int(per_page or 20), 1), 100)
        if not self.path.exists():
            return {"files": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 1}
        join, params, where = self._where(**{
            "q": filters.get("q", ""),
            "file_type": filters.get("file_type", ""),
            "ext": filters.get("ext", ""),
            "date_from": filters.get("date_from", ""),
            "date_to": filters.get("date_to", ""),
            "folder": filters.get("folder", ""),
        })
        connection = self._connect()
        try:
            total = int(connection.execute(f"SELECT count(*) FROM files f{join}{where}", params).fetchone()[0])
            rows = connection.execute(
                f"SELECT {self._select_columns()} FROM files f{join}{where} "
                "ORDER BY CASE WHEN f.file_type='folder' THEN 0 ELSE 1 END DESC, "
                "f.file_modified DESC, lower(f.file_name) DESC LIMIT ? OFFSET ?",
                [*params, per_page, (page - 1) * per_page],
            )
            files = self._rows_to_items(rows)
        finally:
            connection.close()
        return {
            "files": files,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(math.ceil(total / per_page), 1),
        }

    def get(self, file_id: int) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {self._select_columns()} FROM files f WHERE f.id=?",
                (int(file_id),),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"last_indexed": None, "total_files": 0}
        connection = self._connect()
        try:
            rows = connection.execute("SELECT key,value FROM index_meta").fetchall()
        finally:
            connection.close()
        meta = {row["key"]: row["value"] for row in rows}
        return {
            "last_indexed": meta.get("last_indexed") or None,
            "total_files": int(meta.get("total_files") or 0),
        }
