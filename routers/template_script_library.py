"""HTTP routing for script-template and viral-script library operations."""
from fastapi import APIRouter

from routers import templates as handlers
from schemas import ScriptTemplateOut, ViralScriptOut, ViralScriptPageOut


router = APIRouter()

router.add_api_route("/", handlers.list_templates, methods=["GET"], response_model=list[ScriptTemplateOut])
router.add_api_route("/types", handlers.list_video_types, methods=["GET"], response_model=list[str])
router.add_api_route("/", handlers.create_template, methods=["POST"], response_model=ScriptTemplateOut)
router.add_api_route("/viral/list", handlers.list_viral_scripts, methods=["GET"], response_model=ViralScriptPageOut)
router.add_api_route("/viral/search", handlers.semantic_search_scripts, methods=["GET"])
router.add_api_route("/reindex", handlers.reindex_scripts, methods=["POST"])
router.add_api_route("/viral/upload", handlers.upload_viral_script, methods=["POST"])
router.add_api_route("/viral/upload-txt-batch", handlers.upload_viral_txt_batch, methods=["POST"])
router.add_api_route(
    "/viral/{script_id}/cake-images/{image_name}",
    handlers.get_viral_script_cake_image,
    methods=["GET"],
)
router.add_api_route("/viral/{script_id}/toggle-high", handlers.toggle_high_viral, methods=["POST"])
router.add_api_route("/viral/{script_id}", handlers.get_viral_script, methods=["GET"], response_model=ViralScriptOut)
router.add_api_route("/viral/{script_id}", handlers.delete_viral_script, methods=["DELETE"])
router.add_api_route("/{template_id}", handlers.get_template, methods=["GET"], response_model=ScriptTemplateOut)
router.add_api_route("/{template_id}", handlers.delete_template, methods=["DELETE"])
