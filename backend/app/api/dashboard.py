import logging
from datetime import datetime, timedelta
from typing import List, Dict
from fastapi import APIRouter, Depends, Query
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.firestore import get_firestore_client, COLLECTIONS
from app.core.auth_middleware import require_auth

logger = logging.getLogger("suas.api.dashboard")
router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
):
    """Returns post counts by status for the dashboard overview."""
    counts = {
        "pending_review": 0,
        "approved": 0,
        "published": 0,
        "rejected": 0,
        "metrics_synced": 0,
    }
    try:
        for status in counts:
            # Firestore count query (v1 API)
            query = db.collection(COLLECTIONS["posts"]).where("status", "==", status)
            docs = query.stream()
            count = 0
            async for _ in docs:
                count += 1
            counts[status] = count
    except Exception as e:
        logger.warning("Error fetching dashboard stats: %s", e)

    return {"post_counts": counts}


@router.get("/engagement")
async def get_engagement_data(
    days: int = Query(30, ge=1, le=90),
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
) -> List[Dict[str, object]]:
    """Returns daily engagement totals (likes, comments, shares) for the last N days."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Initialize result dict with all dates filled (zero-filled)
    result_dict: Dict[str, Dict[str, object]] = {}
    current_date = cutoff_date.date()
    today = datetime.utcnow().date()
    while current_date <= today:
        date_str = current_date.isoformat()
        result_dict[date_str] = {
            "date": date_str,
            "likes": 0,
            "comments": 0,
            "shares": 0,
        }
        current_date = (datetime.combine(current_date, datetime.min.time()) + timedelta(days=1)).date()

    try:
        # Query published posts
        query = db.collection(COLLECTIONS["posts"]).where(
            "status", "in", ["published", "metrics_synced"]
        )
        docs = query.stream()

        async for doc in docs:
            post = doc.to_dict()

            # Get published_at timestamp
            published_at = post.get("publishing", {}).get("published_at")
            if not published_at:
                continue

            # Convert to datetime if needed and extract date
            if isinstance(published_at, str):
                try:
                    published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
            else:
                # Assume it's already a datetime object
                published_dt = published_at

            # Check if within date range
            if published_dt.astimezone().replace(tzinfo=None) < cutoff_date:
                continue

            date_str = published_dt.astimezone().date().isoformat()

            # Accumulate metrics
            metrics = post.get("metrics", {})
            likes = metrics.get("likes", 0) or 0
            comments = metrics.get("comments", 0) or 0
            shares = metrics.get("shares", 0) or 0

            result_dict[date_str]["likes"] = (result_dict[date_str].get("likes", 0) or 0) + likes
            result_dict[date_str]["comments"] = (result_dict[date_str].get("comments", 0) or 0) + comments
            result_dict[date_str]["shares"] = (result_dict[date_str].get("shares", 0) or 0) + shares

    except Exception as e:
        logger.warning("Error fetching engagement data: %s", e)

    # Convert to sorted list
    result = sorted(result_dict.values(), key=lambda x: x["date"])
    return result


@router.get("/score-distribution")
async def get_score_distribution(
    days: int = Query(30, ge=1, le=90),
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
) -> List[Dict[str, object]]:
    """Returns alignment score distribution (1-5 bins) from published posts."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Initialize all 5 score buckets
    score_counts: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    try:
        # Query published posts
        query = db.collection(COLLECTIONS["posts"]).where(
            "status", "in", ["published", "metrics_synced"]
        )
        docs = query.stream()

        async for doc in docs:
            post = doc.to_dict()

            # Get created_at timestamp
            created_at = post.get("created_at")
            if not created_at:
                continue

            # Convert to datetime if needed
            if isinstance(created_at, str):
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
            else:
                created_dt = created_at

            # Check if within date range
            if created_dt.astimezone().replace(tzinfo=None) < cutoff_date:
                continue

            # Get alignment score and round to nearest int (1-5)
            alignment_score = post.get("scoring", {}).get("alignment_score")
            if alignment_score is None:
                continue

            # Round to nearest int and clamp to 1-5
            score_int = max(1, min(5, round(float(alignment_score))))
            score_counts[score_int] += 1

    except Exception as e:
        logger.warning("Error fetching score distribution: %s", e)

    # Convert to list format, always returning all 5 scores
    result = [
        {"score": score, "count": count}
        for score in range(1, 6)
        for count in [score_counts[score]]
    ]

    return result
