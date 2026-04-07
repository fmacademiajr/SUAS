import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import pytz

from app.config import Settings
from app.core.firestore import COLLECTIONS
from app.pipeline.agents.news_agent import fetch_news
from app.pipeline.agents.trends_agent import fetch_trends
from app.pipeline.agents.voice_agent import scan_voices
from app.pipeline.dedup import dedup_articles
from app.pipeline.scorer import score_items
from app.pipeline.context_builder import build_context_window
from app.pipeline.post_generator import generate_post, PostGenerationError
from app.pipeline.image_generator import generate_image, ImageGenerationError
from app.models.post import Post, PostCreate, PostContent, PostImage, PostPublishing, PostType, UrgencyTier, EditorialStrategy
from google.cloud.firestore_v1.async_client import AsyncClient

logger = logging.getLogger("suas.pipeline.runner")


@dataclass
class PipelineResult:
    run_id: str
    post_id: str | None
    success: bool
    error: str | None = None
    duration_seconds: float = 0.0


async def run_pipeline(
    run_id: str,
    run_slot: str,          # "morning" | "midday" | "evening"
    settings: Settings,
    db: AsyncClient,
    dry_run: bool = False,  # if True, generate post but don't save to Firestore
) -> PipelineResult:
    start = time.monotonic()
    logger.info("Pipeline run starting: id=%s slot=%s dry_run=%s", run_id, run_slot, dry_run)

    # ── Step 1: Parallel data fetch ──────────────────────────────────────────
    # All 3 sources run simultaneously. return_exceptions=True ensures one
    # failing source (e.g. Reddit down) never aborts the whole pipeline.
    try:
        celebrities_doc = await db.collection(COLLECTIONS["tracked_voices"]).stream()
        celebrities = []
        async for doc in celebrities_doc:
            from app.models.voice import Celebrity
            celebrities.append(Celebrity(**doc.to_dict()))
    except Exception as e:
        logger.warning("Could not fetch celebrities: %s", e)
        celebrities = []

    news_result, trends_result, voices_result = await asyncio.gather(
        fetch_news(),
        fetch_trends(),
        scan_voices(celebrities),
        return_exceptions=True,
    )

    raw_articles = news_result if not isinstance(news_result, Exception) else []
    trends = trends_result if not isinstance(trends_result, Exception) else []
    voice_statements = voices_result if not isinstance(voices_result, Exception) else []

    if isinstance(news_result, Exception):
        logger.warning("News fetch failed: %s", news_result)
    if isinstance(trends_result, Exception):
        logger.warning("Trends fetch failed: %s", trends_result)
    if isinstance(voices_result, Exception):
        logger.warning("Voice scan failed: %s", voices_result)

    # ── Step 2: Dedup + score ────────────────────────────────────────────────
    deduped = dedup_articles(raw_articles)

    # Build a simple voice guide summary for the scorer
    voice_guide_summary = "SUAS covers Philippine political accountability: corruption, public spending failures, broken promises."
    try:
        settings_doc = await db.collection(COLLECTIONS["settings"]).document("app_settings").get()
        if settings_doc.exists:
            from app.models.settings import AppSettings
            app_settings = AppSettings(**settings_doc.to_dict())
            voice_guide_summary = app_settings.voice_guide.persona_description
    except Exception:
        pass

    scored_items = await score_items(list(deduped) + list(trends), voice_guide_summary)

    # ── Step 3: Build editorial memory context ───────────────────────────────
    context = await build_context_window(
        db=db,
        scored_items=scored_items,
        voice_statements=list(voice_statements),
    )

    # ── Step 4: Generate post (Claude Opus) ──────────────────────────────────
    try:
        generated = await generate_post(context=context, run_slot=run_slot)
    except PostGenerationError as e:
        logger.error("Post generation failed: %s — pulling from Content Bank", e)
        # TODO Phase 2: pull from Content Bank
        return PipelineResult(
            run_id=run_id,
            post_id=None,
            success=False,
            error=str(e),
            duration_seconds=time.monotonic() - start,
        )

    # ── Step 5: Generate image (Gemini → Playwright fallback) ────────────────
    post_id = str(uuid.uuid4())
    image_result = None
    try:
        image_result = await generate_image(
            image_prompt=generated.image_prompt,
            post_id=post_id,
            one_liner=generated.one_liner,
        )
    except ImageGenerationError as e:
        logger.error("Image generation failed: %s — post will be saved without image", e)

    # ── Step 6: Persist to Firestore ─────────────────────────────────────────
    # Determine scheduled_for time based on slot
    manila = pytz.timezone("Asia/Manila")
    now_manila = datetime.now(manila)

    slot_publish_offsets = {
        "morning": {"hour": 7, "minute": 30},
        "midday":  {"hour": 12, "minute": 30},
        "evening": {"hour": 20, "minute": 0},
    }
    pub = slot_publish_offsets.get(run_slot, {"hour": 20, "minute": 0})
    scheduled_for = now_manila.replace(
        hour=pub["hour"], minute=pub["minute"], second=0, microsecond=0
    )
    # If the scheduled time has already passed today, schedule for tomorrow
    if scheduled_for <= now_manila:
        scheduled_for += timedelta(days=1)

    urgency = (
        UrgencyTier(generated.urgency_tier)
        if generated.urgency_tier in UrgencyTier._value2member_map_
        else UrgencyTier.WARM
    )
    strategy_map = {s.value: s for s in EditorialStrategy}
    strategy = strategy_map.get(generated.editorial_strategy)

    post_doc = {
        "id": post_id,
        "pipeline_run_id": run_id,
        "status": "pending_review",
        "post_type": "news",
        "urgency": urgency.value,
        "editorial_strategy": strategy.value if strategy else None,
        "content": {
            "one_liner": generated.one_liner,
            "body": generated.body,
            "hashtags": generated.hashtags,
            "full_text": generated.full_text,
        },
        "image": {
            "prompt": generated.image_prompt,
            "storage_url": image_result.public_url if image_result else None,
            "gcs_path": image_result.gcs_path if image_result else None,
            "generated_at": image_result.generated_at.isoformat() if image_result else None,
            "generation_model": image_result.generation_method if image_result else "pending",
        },
        "publishing": {
            "scheduled_for": scheduled_for.isoformat(),
        },
        "metrics": {"likes": 0, "comments": 0, "shares": 0, "reach": 0},
        "scoring": {
            "alignment_score": scored_items[0].alignment_score if scored_items else None,
            "urgency_score": scored_items[0].urgency_score if scored_items else None,
        },
        "source_description": generated.source_description,
        "legal_review_required": generated.legal_review_required,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not dry_run:
        await db.collection(COLLECTIONS["posts"]).document(post_id).set(post_doc)
        logger.info(
            "Post saved: id=%s strategy=%s urgency=%s legal_flag=%s",
            post_id, generated.editorial_strategy, urgency.value, generated.legal_review_required,
        )
    else:
        logger.info("DRY RUN — post not saved. one_liner: %s", generated.one_liner)

    duration = time.monotonic() - start
    logger.info("Pipeline run complete: id=%s duration=%.1fs", run_id, duration)
    return PipelineResult(run_id=run_id, post_id=post_id, success=True, duration_seconds=duration)
