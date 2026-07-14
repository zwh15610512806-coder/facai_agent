"""HTTP routing for recursive local TXT discovery/import."""
from fastapi import APIRouter

from routers import templates as handlers


router = APIRouter()
router.add_api_route("/viral/scan-local-txt", handlers.start_local_txt_scan, methods=["POST"])
router.add_api_route("/viral/scan-local-txt/status", handlers.local_txt_scan_status, methods=["GET"])
