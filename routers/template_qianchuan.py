"""HTTP routing for Qianchuan import, matching and performance bindings."""
from fastapi import APIRouter

from routers import templates as handlers


router = APIRouter()
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
