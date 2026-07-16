"""Replayable Product Canvas project event streams."""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from canvas_models import CanvasEvent, CanvasGeneration
from database import SessionLocal
from services.canvas import events as event_service
from services.canvas import projects as project_service
from routers.canvas.projects import project_snapshot_json


router = APIRouter()

EVENT_BATCH_SIZE = 200
POLL_INTERVAL_SECONDS = 0.25
HEARTBEAT_INTERVAL_SECONDS = 15.0
MAX_LAST_EVENT_ID = 2**63 - 1

_LAST_EVENT_ID = re.compile(r"^[0-9]+$")


def get_canvas_session_factory() -> Callable[[], Session]:
    """Dependency seam that keeps request sessions out of long-lived streams."""
    return SessionLocal


def parse_last_event_id(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    if not _LAST_EVENT_ID.fullmatch(raw_value):
        raise ValueError("Last-Event-ID must be a non-negative integer")
    value = int(raw_value)
    if value > MAX_LAST_EVENT_ID:
        raise ValueError("Last-Event-ID is outside the SQLite integer range")
    return value


def _event_record(row: Any) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "event_type": str(row.event_type),
        "payload_json": str(row.payload_json),
    }


def _load_events(
    session_factory: Callable[[], Session],
    *,
    project_id: str,
    after_id: int,
    generation_id: str | None = None,
) -> list[dict[str, Any]]:
    with session_factory() as db:
        conditions = [
            CanvasEvent.project_id == project_id,
            CanvasEvent.id > after_id,
        ]
        if generation_id is not None:
            conditions.append(CanvasEvent.generation_id == generation_id)
        rows = db.execute(
            select(CanvasEvent.id, CanvasEvent.event_type, CanvasEvent.payload_json)
            .where(*conditions)
            .order_by(CanvasEvent.id.asc())
            .limit(EVENT_BATCH_SIZE)
        ).all()
        return [_event_record(row) for row in rows]


def _initial_replay(
    session_factory: Callable[[], Session],
    *,
    project_id: str,
    last_event_id: int | None,
    generation_id: str | None = None,
) -> tuple[dict[str, Any] | None, int, list[dict[str, Any]]]:
    """Capture a coherent fresh/gap snapshot or one replay page."""
    with session_factory() as db:
        replay = event_service.prepare_event_replay(
            db,
            project_id=project_id,
            last_event_id=last_event_id,
            generation_id=generation_id,
        )
        if replay.snapshot is None:
            return None, replay.cursor, replay.events
        # The browser's project stream has always carried a full project wire
        # snapshot. Generation activity enriches that contract; it does not
        # replace it, otherwise a fresh EventSource cannot hydrate the canvas.
        snapshot = project_snapshot_json(
            project_service.get_project_snapshot(db, project_id=project_id)
        )
        snapshot["operations"] = replay.snapshot.get("operations", [])
        snapshot["generations"] = replay.snapshot.get("generations", [])
        snapshot["highWaterEventId"] = replay.snapshot.get("highWaterEventId", replay.cursor)
        return snapshot, replay.cursor, replay.events


def _format_sse_event(
    *,
    event_id: int | None,
    event_type: str,
    data_json: str,
) -> str:
    safe_event_type = event_type.replace("\r", "").replace("\n", "") or "message"
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {safe_event_type}")
    for line in data_json.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _snapshot_event(snapshot: dict[str, Any], event_id: int) -> str:
    return _format_sse_event(
        event_id=event_id,
        event_type="snapshot",
        data_json=json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    )


def _persisted_event(event: dict[str, Any]) -> str:
    return _format_sse_event(
        event_id=event["id"],
        event_type=event["event_type"],
        data_json=event["payload_json"],
    )


async def project_event_stream(
    request: Request,
    *,
    project_id: str,
    session_factory: Callable[[], Session],
    last_event_id: int | None,
    generation_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield committed events without retaining a Session across yields or sleeps."""
    if await request.is_disconnected():
        return

    snapshot, cursor, initial_events = _initial_replay(
        session_factory,
        project_id=project_id,
        last_event_id=last_event_id,
        generation_id=generation_id,
    )
    last_heartbeat = time.monotonic()

    if snapshot is not None:
        if await request.is_disconnected():
            return
        yield _snapshot_event(snapshot, cursor)

    for event in initial_events:
        if await request.is_disconnected():
            return
        cursor = event["id"]
        yield _persisted_event(event)
        last_heartbeat = time.monotonic()

    while True:
        if await request.is_disconnected():
            return

        events = _load_events(
            session_factory,
            project_id=project_id,
            after_id=cursor,
            generation_id=generation_id,
        )
        if events:
            for event in events:
                if await request.is_disconnected():
                    return
                cursor = event["id"]
                yield _persisted_event(event)
                last_heartbeat = time.monotonic()
            continue

        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
            if await request.is_disconnected():
                return
            yield ": heartbeat\n\n"
            last_heartbeat = now

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def _not_found_response() -> JSONResponse:
    return JSONResponse(
        {
            "detail": "Canvas resource not found",
            "code": "canvas_resource_not_found",
        },
        status_code=status.HTTP_404_NOT_FOUND,
    )


@router.get("/projects/{project_id}/events")
def project_events(
    request: Request,
    project_id: str,
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    session_factory: Callable[[], Session] = Depends(get_canvas_session_factory),
) -> Response:
    try:
        last_event_id = parse_last_event_id(last_event_id_header)
    except ValueError:
        return JSONResponse(
            {
                "detail": "Invalid Last-Event-ID",
                "code": "invalid_last_event_id",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    with session_factory() as db:
        try:
            project_service.get_project_snapshot(db, project_id=project_id)
        except project_service.CanvasProjectNotFound:
            return _not_found_response()

    return StreamingResponse(
        project_event_stream(
            request,
            project_id=project_id,
            session_factory=session_factory,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/generations/{generation_id}/events")
def generation_events(
    request: Request,
    generation_id: str,
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    session_factory: Callable[[], Session] = Depends(get_canvas_session_factory),
) -> Response:
    try:
        last_event_id = parse_last_event_id(last_event_id_header)
    except ValueError:
        return JSONResponse(
            {"detail": "Invalid Last-Event-ID", "code": "invalid_last_event_id"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    with session_factory() as db:
        generation = db.get(CanvasGeneration, generation_id)
        if generation is None:
            return _not_found_response()
        project_id = generation.project_id
    return StreamingResponse(
        project_event_stream(
            request,
            project_id=project_id,
            generation_id=generation_id,
            session_factory=session_factory,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
