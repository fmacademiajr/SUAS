from fastapi import APIRouter
from app.api import posts, pipeline, dashboard, reports, learning_log, celebrities, model_admin

router = APIRouter()
router.include_router(posts.router, prefix="/posts", tags=["posts"])
router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
router.include_router(reports.router, prefix="/reports", tags=["reports"])
router.include_router(learning_log.router, tags=["learning-log"])
router.include_router(celebrities.router, tags=["celebrities"])
router.include_router(model_admin.router, tags=["model-admin"])
