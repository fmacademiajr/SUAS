import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    await initialize_ml_scorer(db)

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

    return app


app = create_app()
