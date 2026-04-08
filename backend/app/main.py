import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.firestore import get_firestore_client
from app.core.scheduler import create_scheduler
from app.api.router import router as api_router

logger = logging.getLogger("suas.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start APScheduler on startup, shut it down on shutdown."""
    settings = get_settings()
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started (%d jobs)", len(scheduler.get_jobs()))

    from app.pipeline.scorer import initialize_ml_scorer
    db = get_firestore_client()
    try:
        await initialize_ml_scorer(db)
    except Exception as exc:
        logger.warning("ML scorer init failed (will use Sonnet fallback): %s", exc)

    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SUAS — Shut Up and Serve",
        description="Daily Philippine political accountability post generator",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    # CORS — frontend origin only
    # In production this should be the Firebase Hosting URL
    allowed_origins = ["http://localhost:5173", "http://localhost:3000"]
    if settings.app_env == "production":
        allowed_origins = ["https://suas.web.app", "https://suas.phronetos.com"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "suas-backend"}

    # Serve frontend static files (built React app copied into /app/static/)
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            file_path = static_dir / path
            if file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()
