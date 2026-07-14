"""HTTP routing for viral-script workbook imports."""
from fastapi import APIRouter

from routers import templates as handlers


router = APIRouter()
router.add_api_route("/viral/import-workbook", handlers.import_viral_workbook, methods=["POST"])
router.add_api_route("/viral/import-workbook/status", handlers.workbook_import_status, methods=["GET"])
