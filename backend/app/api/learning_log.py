import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud.firestore_v1.async_client import AsyncClient
from pydantic import BaseModel, Field

from app.core.auth_middleware import require_auth
from app.core.firestore import COLLECTIONS, get_firestore_client

logger = logging.getLogger("suas.api.learning_log")
router = APIRouter(prefix="/learning-log", dependencies=[Depends(require_auth)])


class RatingRequest(BaseModel):
    fernando_rating: int = Field(..., ge=1, le=5)


@router.get("")
async def list_learning_log(
    limit: int = Query(default=20, ge=1, le=52),
    db: AsyncClient = Depends(get_firestore_client),
) -> list[dict]:
    """Return the most recent learning log entries, newest first."""
    try:
        query = (
            db.collection(COLLECTIONS["learning_log"])
            .order_by("generated_at", direction="DESCENDING")
            .limit(limit)
        )
        results: list[dict] = []
        async for doc in query.stream():
            results.append(doc.to_dict())
        return results
    except Exception as exc:
        logger.error("Failed to fetch learning log: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch learning log")


@router.patch("/{entry_id}")
async def rate_learning_log_entry(
    entry_id: str,
    body: RatingRequest,
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Set Fernando's star rating (1–5) on a learning log entry."""
    ref = db.collection(COLLECTIONS["learning_log"]).document(entry_id)
    doc = await ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Learning log entry not found")

    await ref.update({"fernando_rating": body.fernando_rating})
    return {"updated": True}
