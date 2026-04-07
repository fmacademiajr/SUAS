"""
Facebook Graph API v20 service for SUAS.

Responsibilities:
- Upload images and create feed posts on the configured Facebook Page.
- Poll every 5 minutes for approved posts whose scheduled_for falls within the
  next 5-minute window, publish them, and write Firestore state back.
- Check the saved page-token expiry and fire a notification when renewal is due.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import pytz
from google.cloud.firestore_v1 import ArrayUnion
from google.cloud.firestore_v1.async_client import AsyncClient

from app.config import get_settings
from app.core.firestore import COLLECTIONS
from app.models.post import PostStatus

logger = logging.getLogger("suas.services.facebook")

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"
MANILA_TZ = pytz.timezone("Asia/Manila")

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class FacebookPublishError(Exception):
    """Raised when the Graph API returns a non-2xx response or a missing key."""

    def __init__(self, message: str, post_id: str) -> None:
        super().__init__(message)
        self.post_id = post_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _write_notification(db: AsyncClient, message: str) -> None:
    """Atomically append an alert string to settings/pending_notifications.alerts."""
    ref = db.collection(COLLECTIONS["settings"]).document("pending_notifications")
    await ref.set({"alerts": ArrayUnion([message])}, merge=True)
    logger.info("Notification written: %s", message)


# ---------------------------------------------------------------------------
# Core publish
# ---------------------------------------------------------------------------


async def publish_post(db: AsyncClient, post_doc, settings) -> str:
    """
    Publish a single post to Facebook via Graph API v20.

    1. Upload the image to /photos (published=false) to get a photo_id.
       If storage_url is absent, skip to text-only.
    2. Create the feed post at /feed, attaching the photo if we have one.
    3. Write back facebook_post_id, published_at, and status=published to
       Firestore.

    Returns the facebook_post_id string.
    Raises FacebookPublishError on any API-level failure.
    """
    post = post_doc.to_dict()
    post_id: str = post.get("id", post_doc.id)

    page_id: str = settings.facebook_page_id
    token: str = settings.facebook_page_access_token

    image_url: Optional[str] = post.get("image", {}).get("storage_url") or None
    full_text: str = post.get("content", {}).get("full_text", "")

    async with httpx.AsyncClient(timeout=30.0) as client:
        photo_id: Optional[str] = None

        # ── Step 1: upload image ──────────────────────────────────────────────
        if image_url:
            photos_url = f"{GRAPH_API_BASE}/{page_id}/photos"
            params = {
                "url": image_url,
                "published": "false",
                "access_token": token,
            }
            logger.debug("Uploading image for post_id=%s url=%s", post_id, photos_url)
            resp = await client.post(photos_url, params=params)
            body = resp.json()
            logger.debug(
                "Graph /photos response status=%d body_excerpt=%.200s",
                resp.status_code,
                str(body),
            )
            if not resp.is_success:
                raise FacebookPublishError(
                    f"Image upload failed (HTTP {resp.status_code}): {body}",
                    post_id,
                )
            photo_id = body.get("id")
            if not photo_id:
                raise FacebookPublishError(
                    f"Image upload response missing 'id': {body}",
                    post_id,
                )
            logger.debug("Uploaded photo_id=%s for post_id=%s", photo_id, post_id)

        # ── Step 2: create feed post ──────────────────────────────────────────
        feed_url = f"{GRAPH_API_BASE}/{page_id}/feed"
        payload: dict = {
            "message": full_text,
            "access_token": token,
        }
        if photo_id:
            payload["attached_media"] = [{"media_fbid": photo_id}]

        logger.debug("Creating feed post for post_id=%s url=%s", post_id, feed_url)
        resp = await client.post(feed_url, json=payload)
        body = resp.json()
        logger.debug(
            "Graph /feed response status=%d body_excerpt=%.200s",
            resp.status_code,
            str(body),
        )
        if not resp.is_success:
            raise FacebookPublishError(
                f"Feed post creation failed (HTTP {resp.status_code}): {body}",
                post_id,
            )
        fb_post_id: Optional[str] = body.get("id")
        if not fb_post_id:
            raise FacebookPublishError(
                f"Feed post response missing 'id': {body}",
                post_id,
            )

    # ── Step 3: write back to Firestore ──────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.collection(COLLECTIONS["posts"]).document(post_doc.id).update(
        {
            "publishing.facebook_post_id": fb_post_id,
            "publishing.published_at": now_iso,
            "status": PostStatus.PUBLISHED.value,
        }
    )

    logger.info(
        "Published post_id=%s facebook_post_id=%s", post_id, fb_post_id
    )
    return fb_post_id


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------


async def publish_approved_posts(db: AsyncClient) -> int:
    """
    Publish every approved post whose scheduled_for falls within the next 5
    minutes.  Called by the scheduler every 5 minutes.

    Retries up to 3 times (30 s delay between attempts) on FacebookPublishError.
    After 3 consecutive failures, writes a pending_notifications alert and moves
    on to the next post.

    Returns the count of successfully published posts.
    Never raises — all exceptions are caught and logged.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=5)
    published_count = 0

    try:
        docs_stream = db.collection(COLLECTIONS["posts"]) \
            .where("status", "==", PostStatus.APPROVED.value) \
            .stream()

        async for doc in docs_stream:
            post = doc.to_dict()
            post_id: str = post.get("id", doc.id)

            scheduled_for_str = post.get("publishing", {}).get("scheduled_for")
            if not scheduled_for_str:
                continue

            # Parse scheduled_for — handle both naive ISO (assume UTC) and
            # aware ISO strings returned by Firestore / the dashboard.
            try:
                scheduled_for = datetime.fromisoformat(
                    str(scheduled_for_str).replace("Z", "+00:00")
                )
                if scheduled_for.tzinfo is None:
                    scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                logger.warning(
                    "Could not parse scheduled_for='%s' for post_id=%s — skipping",
                    scheduled_for_str,
                    post_id,
                )
                continue

            if not (now <= scheduled_for <= window_end):
                continue

            logger.info(
                "Attempting to publish post_id=%s scheduled_for=%s",
                post_id,
                scheduled_for_str,
            )

            # ── Retry loop ────────────────────────────────────────────────────
            max_attempts = 3
            last_error: Optional[FacebookPublishError] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    await publish_post(db, doc, settings)
                    published_count += 1
                    last_error = None
                    break
                except FacebookPublishError as exc:
                    last_error = exc
                    logger.warning(
                        "Publish attempt %d/%d failed for post_id=%s: %s",
                        attempt,
                        max_attempts,
                        post_id,
                        exc,
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(30)
                except Exception:
                    logger.exception(
                        "Unexpected error publishing post_id=%s (attempt %d)",
                        post_id,
                        attempt,
                    )
                    break

            if last_error is not None:
                alert = (
                    f"Failed to publish post_id={post_id} after {max_attempts} "
                    f"attempts: {last_error}"
                )
                logger.error(alert)
                try:
                    await _write_notification(db, alert)
                except Exception:
                    logger.exception(
                        "Could not write failure notification for post_id=%s", post_id
                    )

    except Exception:
        logger.exception("Unexpected error in publish_approved_posts")

    logger.info("publish_approved_posts complete: published %d post(s)", published_count)
    return published_count


# ---------------------------------------------------------------------------
# Token expiry check
# ---------------------------------------------------------------------------


async def check_token_expiry(db: AsyncClient) -> None:
    """
    Read settings/facebook_token_expiry.  If the `expiry` field is within 7
    days of now, append an alert to settings/pending_notifications.  If the
    document does not exist, do nothing.
    """
    try:
        doc = await db.collection(COLLECTIONS["settings"]).document(
            "facebook_token_expiry"
        ).get()
        if not doc.exists:
            return

        data = doc.to_dict() or {}
        expiry_val = data.get("expiry")
        if not expiry_val:
            return

        expiry_dt = datetime.fromisoformat(str(expiry_val).replace("Z", "+00:00"))
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days_remaining = (expiry_dt - now).days

        if days_remaining <= 7:
            alert = (
                f"Facebook page access token expires on {expiry_dt.date().isoformat()} "
                f"({days_remaining} day(s) remaining). Please renew it."
            )
            logger.warning(alert)
            await _write_notification(db, alert)

    except Exception:
        logger.exception("Error checking Facebook token expiry")


# ---------------------------------------------------------------------------
# Existing helper — keep as-is
# ---------------------------------------------------------------------------


async def get_page_token_expiry(db: AsyncClient) -> Optional[datetime]:
    """Returns the Facebook page token expiry date, or None if not set."""
    try:
        doc = await db.collection(COLLECTIONS["settings"]).document(
            "facebook_token"
        ).get()
        if doc.exists:
            data = doc.to_dict()
            expiry_str = data.get("expiry")
            if expiry_str:
                return datetime.fromisoformat(expiry_str)
    except Exception:
        pass
    return None
