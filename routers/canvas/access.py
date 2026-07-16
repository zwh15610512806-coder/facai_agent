"""HTTP endpoints for the Product Canvas paid-access session."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from services.canvas import access as access_service


class CanvasAccessStatusResponse(BaseModel):
    configured: bool
    locked: bool


class CanvasAccessUnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=4096)


@asynccontextmanager
async def _access_lifespan(app: FastAPI):
    access_service.initialize_canvas_access_session(app)
    try:
        yield
    finally:
        access_service.clear_canvas_access_session(app)


router = APIRouter(prefix="/access", lifespan=_access_lifespan)


def _response(status: access_service.CanvasAccessStatus) -> CanvasAccessStatusResponse:
    return CanvasAccessStatusResponse(
        configured=status.configured,
        locked=status.locked,
    )


@router.get("/status", response_model=CanvasAccessStatusResponse)
def get_canvas_access_status(request: Request) -> CanvasAccessStatusResponse:
    return _response(access_service.canvas_access_status(request))


@router.post("/unlock", response_model=CanvasAccessStatusResponse)
def unlock_canvas_access(
    payload: CanvasAccessUnlockRequest,
    request: Request,
    response: Response,
) -> CanvasAccessStatusResponse:
    access_service.unlock_canvas_access(request, response, payload.token)
    return CanvasAccessStatusResponse(configured=True, locked=False)


@router.post("/lock", response_model=CanvasAccessStatusResponse)
def lock_canvas_access(
    request: Request,
    response: Response,
) -> CanvasAccessStatusResponse:
    configured = access_service.canvas_access_status(request).configured
    access_service.lock_canvas_access(response)
    return CanvasAccessStatusResponse(
        configured=configured,
        locked=True,
    )
