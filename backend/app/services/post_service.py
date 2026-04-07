import logging
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.firestore import COLLECTIONS
from app.models.post import PostStatus

logger = logging.getLogger("suas.services.post")


class PostNotFoundError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


# Valid state transitions
TRANSITIONS = {
    PostStatus.PENDING_REVIEW: [PostStatus.APPROVED, PostStatus.REJECTED],
    PostStatus.APPROVED: [PostStatus.PUBLISHED, PostStatus.REJECTED],
    PostStatus.PUBLISHED: [PostStatus.METRICS_SYNCED],
    PostStatus.REJECTED: [],
    PostStatus.METRICS_SYNCED: [],
}


async def get_post(db: AsyncClient, post_id: str) -> dict:
    doc = await db.collection(COLLECTIONS["posts"]).document(post_id).get()
    if not doc.exists:
        raise PostNotFoundError(f"Post {post_id} not found")
    return doc.to_dict()


async def list_posts(db: AsyncClient, status: str | None = None, limit: int = 50) -> list[dict]:
    query = db.collection(COLLECTIONS["posts"])
    if status:
        query = query.where("status", "==", status)
    query = query.order_by("created_at", direction="DESCENDING").limit(limit)
    docs = query.stream()
    results = []
    async for doc in docs:
        results.append(doc.to_dict())
    return results


async def approve_post(db: AsyncClient, post_id: str) -> dict:
    post = await get_post(db, post_id)
    current = PostStatus(post["status"])
    if PostStatus.APPROVED not in TRANSITIONS[current]:
        raise InvalidStateTransitionError(f"Cannot approve post in status {current}")
    now = datetime.now(timezone.utc).isoformat()
    await db.collection(COLLECTIONS["posts"]).document(post_id).update({
        "status": PostStatus.APPROVED.value,
        "publishing.approved_at": now,
        "updated_at": now,
    })
    return await get_post(db, post_id)


async def reject_post(db: AsyncClient, post_id: str, reason: str) -> dict:
    post = await get_post(db, post_id)
    current = PostStatus(post["status"])
    if PostStatus.REJECTED not in TRANSITIONS[current]:
        raise InvalidStateTransitionError(f"Cannot reject post in status {current}")
    now = datetime.now(timezone.utc).isoformat()
    await db.collection(COLLECTIONS["posts"]).document(post_id).update({
        "status": PostStatus.REJECTED.value,
        "rejection_reason": reason,
        "updated_at": now,
    })
    return await get_post(db, post_id)


async def update_post_content(db: AsyncClient, post_id: str, updates: dict) -> dict:
    """Fernando edits one_liner, body, hashtags, or image_prompt."""
    post = await get_post(db, post_id)
    if post["status"] not in [PostStatus.PENDING_REVIEW.value, PostStatus.APPROVED.value]:
        raise InvalidStateTransitionError("Can only edit pending_review or approved posts")
    now = datetime.now(timezone.utc).isoformat()
    firestore_updates = {"updated_at": now}
    if "one_liner" in updates:
        firestore_updates["content.one_liner"] = updates["one_liner"]
    if "body" in updates:
        firestore_updates["content.body"] = updates["body"]
    if "hashtags" in updates:
        firestore_updates["content.hashtags"] = updates["hashtags"]
    if "image_prompt" in updates:
        firestore_updates["image.prompt"] = updates["image_prompt"]
    # Rebuild full_text if text fields changed
    if any(k in updates for k in ["one_liner", "body", "hashtags"]):
        content = post["content"]
        one_liner = updates.get("one_liner", content["one_liner"])
        body = updates.get("body", content["body"])
        hashtags = updates.get("hashtags", content["hashtags"])
        firestore_updates["content.full_text"] = one_liner + "\n\n" + body + "\n\n" + " ".join(hashtags)
    await db.collection(COLLECTIONS["posts"]).document(post_id).update(firestore_updates)
    return await get_post(db, post_id)
