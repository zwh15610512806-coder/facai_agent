"""HTTP routing for Qianchuan import, matching and performance bindings."""
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from routers import templates as handlers
from routers.jobs import owner_key_for_request
from services.background_jobs import (
    create_background_job,
    job_to_dict,
    register_background_handler,
)


router = APIRouter()


def _run_qianchuan_match(request_payload: dict, job_id: int) -> dict:
    with SessionLocal() as db:
        response = handlers._execute_qianchuan_auto_match(
            request_payload,
            db,
            background_job_id=job_id,
        )
        return dict(response.data or {})


register_background_handler(
    "maintenance.qianchuan.auto_match",
    _run_qianchuan_match,
    queue_group="maintenance",
)


@router.post("/qianchuan/bindings/auto-match/jobs", status_code=status.HTTP_202_ACCEPTED)
def enqueue_qianchuan_auto_match(
    request: Request,
    payload: dict | None = None,
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    x_idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    job, _created = create_background_job(
        db,
        owner_key=owner_key_for_request(request, x_facai_client_id),
        job_type="maintenance.qianchuan.auto_match",
        request_payload=payload or {},
        origin_path=request.headers.get("X-Facai-Origin-Path") or "/app/templates",
        queue_group="maintenance",
        idempotency_key=x_idempotency_key or "",
        max_attempts=2,
        message="千川匹配等待执行",
    )
    return JSONResponse(status_code=202, content=job_to_dict(job))
router.add_api_route(
    "/qianchuan/bindings/auto-match",
    handlers.auto_match_qianchuan_bindings,
    methods=["POST"],
)
router.add_api_route(
    "/qianchuan/bindings/auto-match/status",
    handlers.qianchuan_auto_match_status,
    methods=["GET"],
)
router.add_api_route(
    "/qianchuan/bindings/rematch-workbook",
    handlers.rematch_workbook_qianchuan_bindings,
    methods=["POST"],
)
router.add_api_route("/qianchuan/import", handlers.import_qianchuan_performance, methods=["POST"])
router.add_api_route(
    "/viral/{script_id}/performance",
    handlers.get_viral_script_performance,
    methods=["GET"],
)
router.add_api_route(
    "/viral/{script_id}/performance/bind",
    handlers.bind_viral_script_performance,
    methods=["POST"],
)
router.add_api_route(
    "/viral/{script_id}/performance/bind/{binding_id}",
    handlers.unbind_viral_script_performance,
    methods=["DELETE"],
)
