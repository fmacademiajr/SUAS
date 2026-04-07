import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.auth_middleware import require_auth
from app.core.firestore import COLLECTIONS, get_firestore_client
from app.services.learning_service import train_scoring_model

logger = logging.getLogger("suas.api.model_admin")

router = APIRouter(prefix="/model-admin", dependencies=[Depends(require_auth)])

TRAINING_THRESHOLD = 200


@router.get("/status")
async def get_model_status(
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Return the currently active ML model's status, or a flag indicating none exists."""
    try:
        query = (
            db.collection(COLLECTIONS["model_training"])
            .where("is_active", "==", True)
            .limit(1)
        )
        async for doc in query.stream():
            data = doc.to_dict()
            return {
                "has_active_model": True,
                "model_version": data.get("model_version"),
                "r_squared": data.get("r_squared"),
                "training_set_size": data.get("training_set_size"),
                "trained_at": data.get("trained_at"),
                "gcs_path": data.get("gcs_path"),
                "top_features": data.get("top_features", []),
            }
        return {"has_active_model": False}
    except Exception as exc:
        logger.error("Failed to fetch model status: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch model status")


@router.get("/overrides")
async def get_overrides(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncClient = Depends(get_firestore_client),
) -> list[dict]:
    """Return the last N override log entries, sorted by logged_at descending."""
    try:
        ref = db.collection(COLLECTIONS["model_training"]).document("overrides")
        doc = await ref.get()
        if not doc.exists:
            return []

        records: list[dict] = doc.to_dict().get("records", [])
        records.sort(key=lambda r: r.get("logged_at", ""), reverse=True)
        return records[:limit]
    except Exception as exc:
        logger.error("Failed to fetch overrides: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch overrides")


@router.post("/train", status_code=202)
async def trigger_training(
    background_tasks: BackgroundTasks,
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Manually trigger model training in the background."""
    background_tasks.add_task(train_scoring_model, db)
    return {"status": "accepted", "message": "Training queued"}


@router.get("/post-count")
async def get_post_count(
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Return how many posts are eligible for training."""
    try:
        eligible = 0
        query = db.collection(COLLECTIONS["posts"]).where(
            "status", "in", ["published", "metrics_synced"]
        )
        async for doc in query.stream():
            data = doc.to_dict()
            scoring = data.get("scoring") or {}
            if scoring.get("alignment_score") is not None:
                eligible += 1

        return {
            "eligible_posts": eligible,
            "threshold": TRAINING_THRESHOLD,
            "ready_to_train": eligible >= TRAINING_THRESHOLD,
        }
    except Exception as exc:
        logger.error("Failed to count eligible posts: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to count eligible posts")
