"""Product Canvas API router composition."""
from fastapi import APIRouter

from routers.canvas import access, assets, events, exports, generations, operations, projects, providers


router = APIRouter()
router.include_router(access.router)
router.include_router(projects.router)
router.include_router(assets.router)
router.include_router(operations.router)
router.include_router(events.router)
router.include_router(exports.router)
router.include_router(providers.router)
router.include_router(generations.router)
