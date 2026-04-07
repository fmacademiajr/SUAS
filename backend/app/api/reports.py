import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.auth_middleware import require_auth
from app.core.firestore import COLLECTIONS, get_firestore_client
from app.services.digest_service import create_daily_digest

logger = logging.getLogger("suas.api.reports")
router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/digests")
async def list_digests(
    limit: int = Query(default=30, ge=1, le=90),
    db: AsyncClient = Depends(get_firestore_client),
) -> list[dict]:
    """Return the most recent editorial digests, newest first."""
    try:
        query = (
            db.collection(COLLECTIONS["editorial_digests"])
            .order_by("date", direction="DESCENDING")
            .limit(limit)
        )
        results: list[dict] = []
        async for doc in query.stream():
            results.append(doc.to_dict())
        return results
    except Exception as exc:
        logger.error("Failed to fetch digests: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch digests")


@router.get("/weekly")
async def list_weekly_reports(
    limit: int = Query(default=8, ge=1, le=52),
    db: AsyncClient = Depends(get_firestore_client),
) -> list[dict]:
    """Return the most recent weekly reports, newest first."""
    try:
        query = (
            db.collection(COLLECTIONS["editorial_reports"])
            .where("type", "==", "weekly")
            .order_by("period_end", direction="DESCENDING")
            .limit(limit)
        )
        results: list[dict] = []
        async for doc in query.stream():
            results.append(doc.to_dict())
        return results
    except Exception as exc:
        logger.error("Failed to fetch weekly reports: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch weekly reports")


@router.get("/monthly")
async def list_monthly_reports(
    limit: int = Query(default=6, ge=1, le=24),
    db: AsyncClient = Depends(get_firestore_client),
) -> list[dict]:
    """Return the most recent monthly reports, newest first."""
    try:
        query = (
            db.collection(COLLECTIONS["editorial_reports"])
            .where("type", "==", "monthly")
            .order_by("period_end", direction="DESCENDING")
            .limit(limit)
        )
        results: list[dict] = []
        async for doc in query.stream():
            results.append(doc.to_dict())
        return results
    except Exception as exc:
        logger.error("Failed to fetch monthly reports: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch monthly reports")


@router.post("/digests/generate", status_code=202)
async def trigger_digest_generation(
    background_tasks: BackgroundTasks,
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Manually trigger today's digest generation (for testing or recovery)."""
    background_tasks.add_task(create_daily_digest, db)
    return {"status": "accepted", "message": "Digest generation queued"}
