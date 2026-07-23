"""Unified browser-owned background job API."""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from services.background_jobs import (
    ALL_STATUSES,
    browser_owner_key,
    cancel_owned_job,
    get_owned_job,
    job_to_dict,
    list_owned_jobs,
    retry_owned_job,
    sync_integration_export_jobs,
    sync_integration_sync_jobs,
)
from services.security import request_actor_digest


router = APIRouter()


def _client_id(value: str | None) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="缺少 X-Facai-Client-Id")
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="X-Facai-Client-Id 必须是 UUID") from exc


def owner_key_for_request(request: Request, client_id: str | None) -> str:
    return browser_owner_key(request_actor_digest(request), _client_id(client_id))


@router.get("")
def list_jobs(
    request: Request,
    status: str | None = Query(None),
    job_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    db: Session = Depends(get_db),
):
    statuses = None
    if status:
        statuses = {item.strip() for item in status.split(",") if item.strip()}
        invalid = statuses - ALL_STATUSES
        if invalid:
            raise HTTPException(status_code=422, detail=f"不支持的任务状态：{', '.join(sorted(invalid))}")
    owner_key = owner_key_for_request(request, x_facai_client_id)
    sync_integration_export_jobs(db, owner_key=owner_key, actor_digest=request_actor_digest(request))
    sync_integration_sync_jobs(db, owner_key=owner_key)
    jobs = list_owned_jobs(db, owner_key, statuses=statuses, job_type=job_type, limit=limit)
    return {"items": [job_to_dict(job, include_payload=False) for job in jobs], "count": len(jobs)}


@router.get("/{public_id}")
def get_job(
    public_id: str,
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    db: Session = Depends(get_db),
):
    owner_key = owner_key_for_request(request, x_facai_client_id)
    sync_integration_sync_jobs(db, owner_key=owner_key)
    job = get_owned_job(db, owner_key, public_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_to_dict(job)


@router.get("/{public_id}/events")
async def observe_job(
    public_id: str,
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
):
    owner_key = owner_key_for_request(request, x_facai_client_id)
    last_event_id = request.headers.get("last-event-id", "0")
    try:
        after_version = max(0, int(last_event_id or 0))
    except ValueError:
        after_version = 0
    with SessionLocal() as db:
        if get_owned_job(db, owner_key, public_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")

    async def events():
        version = after_version
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                return
            with SessionLocal() as db:
                job = get_owned_job(db, owner_key, public_id)
                if job is None:
                    return
                snapshot = job_to_dict(job)
            current_version = int(snapshot["version"])
            if current_version > version:
                version = current_version
                idle_ticks = 0
                payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {version}\nevent: job\ndata: {payload}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks >= 30:
                    idle_ticks = 0
                    yield ": keepalive\n\n"
            if snapshot["status"] in {"succeeded", "failed", "cancelled"} and current_version <= version:
                return
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/{public_id}/cancel")
def cancel_job(
    public_id: str,
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    db: Session = Depends(get_db),
):
    owner_key = owner_key_for_request(request, x_facai_client_id)
    job = get_owned_job(db, owner_key, public_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_to_dict(cancel_owned_job(db, job))


@router.post("/{public_id}/retry")
def retry_job(
    public_id: str,
    request: Request,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    db: Session = Depends(get_db),
):
    owner_key = owner_key_for_request(request, x_facai_client_id)
    job = get_owned_job(db, owner_key, public_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        retried = retry_owned_job(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job_to_dict(retried)
