"""Shared upload size enforcement."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, UploadFile


UPLOAD_CHUNK_SIZE = 1024 * 1024


def format_file_size(byte_count: int) -> str:
    if byte_count >= 1024 * 1024:
        return f"{byte_count / (1024 * 1024):.0f}MB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.0f}KB"
    return f"{byte_count}B"


def _too_large(max_bytes: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"文件过大，请控制在 {format_file_size(max_bytes)} 以内。",
    )


async def iter_upload_chunks(upload: UploadFile, *, max_bytes: int):
    total = 0
    while True:
        chunk = await upload.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _too_large(max_bytes)
        yield chunk


async def read_upload_bytes(upload: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    async for chunk in iter_upload_chunks(upload, max_bytes=max_bytes):
        chunks.append(chunk)
    return b"".join(chunks)


async def write_upload_file(upload: UploadFile, file_path: str | os.PathLike[str], *, max_bytes: int) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("wb") as out:
            async for chunk in iter_upload_chunks(upload, max_bytes=max_bytes):
                out.write(chunk)
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
