import logging
from datetime import datetime, timezone, timedelta
from google.cloud.firestore_v1.async_client import AsyncClient
import httpx

from app.core.firestore import COLLECTIONS, get_firestore_client
from app.config import get_settings
from app.models.post import PostStatus

logger = logging.getLogger("suas.tasks.sync_metrics")


async def sync_published_post_metrics(db: AsyncClient | None = None) -> None:
    """
    Fetches Facebook engagement metrics for all published posts.
    Runs every 6 hours via APScheduler.

    Queries Firestore for posts with status "published" or "metrics_synced",
    skips posts older than 7 days, and fetches likes, comments, shares, reach
    from Facebook Graph API v20. Updates post documents with metrics and sets
    status to "metrics_synced".

    Args:
        db: Firestore AsyncClient. If None, gets client via get_firestore_client().
    """
    if db is None:
        db = get_firestore_client()

    try:
        settings = get_settings()
        access_token = settings.facebook_page_access_token

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        now = datetime.now(timezone.utc)

        docs = db.collection(COLLECTIONS["posts"]) \
            .where("status", "in", [PostStatus.PUBLISHED.value, PostStatus.METRICS_SYNCED.value]) \
            .stream()

        synced = 0
        async for doc in docs:
            post = doc.to_dict()
            published_at_str = post.get("publishing", {}).get("published_at")

            if not published_at_str:
                continue

            try:
                published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                if published_at < cutoff:
                    continue  # skip posts older than 7 days

                facebook_post_id = post.get("publishing", {}).get("facebook_post_id")
                if not facebook_post_id:
                    continue

                logger.debug("Fetching metrics for post %s (fb_id: %s)", post["id"], facebook_post_id)
                metrics = await _fetch_metrics(facebook_post_id, access_token)

                if metrics is None:
                    logger.warning("Failed to fetch metrics for post %s", post["id"])
                    continue

                # Update Firestore post document
                update_data = {
                    "metrics.likes": metrics["likes"],
                    "metrics.comments": metrics["comments"],
                    "metrics.shares": metrics["shares"],
                    "metrics.reach": metrics["reach"],
                    "metrics.last_synced": now.isoformat(),
                    "status": PostStatus.METRICS_SYNCED.value,
                }

                db.collection(COLLECTIONS["posts"]).document(post["id"]).update(update_data)
                logger.debug("Updated metrics for post %s", post["id"])
                synced += 1

            except ValueError as e:
                logger.warning("Invalid published_at format for post %s: %s", post.get("id"), e)
                continue

        logger.info("Metrics sync completed: %d posts synced", synced)

    except Exception:
        logger.exception("Metrics sync failed")


async def _fetch_metrics(post_id: str, access_token: str) -> dict | None:
    """
    Fetches engagement metrics from Facebook Graph API v20 for a single post.

    Args:
        post_id: Facebook post ID (e.g., "123456789_987654321")
        access_token: Facebook page access token

    Returns:
        Dict with keys: likes, comments, shares, reach.
        Returns None on HTTP error or JSON parse error.
    """
    url = f"https://graph.facebook.com/v20.0/{post_id}"
    params = {
        "fields": "likes.summary(true),comments.summary(true),shares",
        "access_token": access_token,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            likes_count = data.get("likes", {}).get("summary", {}).get("total_count", 0)
            comments_count = data.get("comments", {}).get("summary", {}).get("total_count", 0)
            shares_count = data.get("shares", {}).get("count", 0)
            reach_count = 0  # requires Page Insights permission

            logger.debug(
                "Fetched metrics for post %s: likes=%d, comments=%d, shares=%d",
                post_id,
                likes_count,
                comments_count,
                shares_count,
            )

            return {
                "likes": likes_count,
                "comments": comments_count,
                "shares": shares_count,
                "reach": reach_count,
            }

    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching metrics for post %s: %s", post_id, e)
        return None
    except (ValueError, KeyError) as e:
        logger.warning("Error parsing metrics response for post %s: %s", post_id, e)
        return None
