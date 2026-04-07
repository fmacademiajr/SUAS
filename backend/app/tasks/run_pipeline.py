import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.config import get_settings
from app.core.firestore import get_firestore_client
from app.pipeline.runner import run_pipeline
from app.pipeline.breaking_scanner import run_breaking_scan
from app.services.facebook_service import publish_approved_posts

logger = logging.getLogger("suas.tasks.run_pipeline")


async def run_morning_pipeline() -> None:
    await _run_pipeline_for_slot("morning")


async def run_midday_pipeline() -> None:
    await _run_pipeline_for_slot("midday")


async def run_evening_pipeline() -> None:
    await _run_pipeline_for_slot("evening")


async def _run_pipeline_for_slot(slot: str) -> None:
    run_id = f"{slot}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    logger.info("Starting %s pipeline run: %s", slot, run_id)
    settings = get_settings()
    db = get_firestore_client()
    try:
        result = await run_pipeline(run_id=run_id, run_slot=slot, settings=settings, db=db)
        logger.info("Pipeline %s completed: post_id=%s", run_id, result.post_id if result else "none")
    except Exception:
        logger.exception("Pipeline %s failed", run_id)


async def run_breaking_scan_task() -> None:
    logger.debug("Running breaking news scan")
    db = get_firestore_client()
    try:
        result = await run_breaking_scan(db=db)
        if result.hot_story_found:
            logger.info("Breaking scan: HOT story → draft post %s", result.draft_post_id)
    except Exception:
        logger.exception("Breaking news scan failed")


async def check_scheduled_publishes() -> None:
    """Check every 5 minutes for approved posts whose scheduled_for is within 5 minutes."""
    db = get_firestore_client()
    try:
        await publish_approved_posts(db=db)
    except Exception:
        logger.exception("Scheduled publish check failed")
