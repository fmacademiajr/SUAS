"""
Digest Service
--------------
Generates and stores the daily editorial digest after each evening pipeline run.

Called by the scheduler after the 6 PM slot completes. Idempotent — safe to
call multiple times; returns immediately if today's digest already exists.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic
import pytz
from google.cloud.firestore_v1.async_client import AsyncClient

from app.config import get_settings
from app.core.firestore import COLLECTIONS
from app.core.model_router import ModelRouter, TaskCategory
from app.models.digest import (
    EditorialDigest,
    EngagementSummary,
    SentimentSnapshot,
    StoryCovered,
    ThemeEntry,
)

logger = logging.getLogger("suas.services.digest")

_MANILA_TZ = pytz.timezone("Asia/Manila")
_MAX_DIGESTS = 60


# ─── Public API ───────────────────────────────────────────────────────────────


async def create_daily_digest(
    db: AsyncClient,
    run_date: str | None = None,
) -> EditorialDigest:
    """
    Generate and store today's editorial digest.

    run_date defaults to today in Asia/Manila timezone (ISO date string,
    e.g. "2026-04-06"). Pass an explicit date only in tests or backfills.
    Returns the created EditorialDigest (or the existing one if already done).
    """
    settings = get_settings()
    date_str = run_date or datetime.now(_MANILA_TZ).strftime("%Y-%m-%d")

    # ── 1. Idempotency check ─────────────────────────────────────────────────
    existing_ref = db.collection(COLLECTIONS["editorial_digests"]).document(date_str)
    existing_snap = await existing_ref.get()
    if existing_snap.exists:
        logger.info("Digest already exists for %s — skipping", date_str)
        return EditorialDigest.from_firestore(existing_snap.to_dict())

    # ── 2. Fetch today's posts ────────────────────────────────────────────────
    manila_today = _MANILA_TZ.localize(
        datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    )
    manila_tomorrow = manila_today + timedelta(days=1)

    query = (
        db.collection(COLLECTIONS["posts"])
        .where("created_at", ">=", manila_today.isoformat())
        .where("created_at", "<", manila_tomorrow.isoformat())
    )
    posts: list[dict] = []
    async for doc in query.stream():
        posts.append(doc.to_dict())

    logger.info("Digest for %s: found %d posts", date_str, len(posts))

    # ── 3. Empty-day path ────────────────────────────────────────────────────
    if not posts:
        digest = EditorialDigest(
            date=date_str,
            posts_generated=0,
            generated_at=datetime.now(timezone.utc),
        )
        await existing_ref.set(digest.to_firestore())
        logger.info("No posts today — minimal digest saved for %s", date_str)
        await _trim_old_digests(db)
        return digest

    # ── 4. Format post summaries for Sonnet ──────────────────────────────────
    post_summaries = _format_post_summaries(posts)

    # ── 5. Call Sonnet ────────────────────────────────────────────────────────
    model_id = ModelRouter(settings).get_model(TaskCategory.REASONING)
    llm_data = await _call_sonnet(
        model_id=model_id,
        api_key=settings.anthropic_api_key,
        date_str=date_str,
        post_count=len(posts),
        post_summaries=post_summaries,
    )

    # ── 6. Build EditorialDigest ──────────────────────────────────────────────
    digest = _build_digest(date_str=date_str, posts=posts, llm_data=llm_data)

    # ── 7. Save ───────────────────────────────────────────────────────────────
    await existing_ref.set(digest.to_firestore())
    logger.info(
        "Digest saved for %s — %d posts, %d themes",
        date_str, digest.posts_generated, len(digest.themes),
    )

    # ── 8. Trim old digests ───────────────────────────────────────────────────
    await _trim_old_digests(db)

    return digest


# ─── Private helpers ──────────────────────────────────────────────────────────


def _format_post_summaries(posts: list[dict]) -> str:
    lines: list[str] = []
    for i, post in enumerate(posts, start=1):
        content = post.get("content", {})
        body_preview = (content.get("body") or "")[:200]
        lines.append(
            f"{i}. [{post.get('post_type', 'unknown')}] "
            f"urgency={post.get('urgency', '?')} "
            f"strategy={post.get('editorial_strategy', '?')} "
            f"alignment={post.get('alignment_score', '?')}\n"
            f"   {body_preview}"
        )
    return "\n".join(lines)


async def _call_sonnet(
    *,
    model_id: str,
    api_key: str,
    date_str: str,
    post_count: int,
    post_summaries: str,
) -> dict:
    """Call Sonnet for editorial analysis. Returns parsed dict or empty dict on failure."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    system_prompt = (
        "You are the editorial analyst for SUAS, a Philippine political accountability "
        "social media page. "
        f"Today is {date_str}. Review today's generated posts and produce a structured "
        "daily digest in JSON."
    )

    user_prompt = (
        f"Today SUAS generated {post_count} posts. Here are summaries:\n"
        f"{post_summaries}\n\n"
        "Respond with JSON only:\n"
        "{\n"
        '  "themes": [{"name": "...", "intensity": 1-5, "direction": "escalating|steady|fading|new"}],\n'
        '  "public_sentiment": {"dominant": "anger|sarcasm|frustration|hope|outrage", '
        '"secondary": null|"...", "shift_from_yesterday": null|"..."},\n'
        '  "narrative_connections": ["connection 1", "connection 2"],\n'
        '  "editorial_strategy_used": {"ride_the_wave": N, "fill_the_gap": N, "connect_the_dots": N},\n'
        '  "blind_spots": ["..."]\n'
        "}\n"
        "Keep themes to max 5. Narrative connections are cross-story patterns only Fernando would notice."
    )

    try:
        response = await client.messages.create(
            model=model_id,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Sonnet returned invalid JSON for digest %s: %s", date_str, exc)
        return {}
    except Exception as exc:
        logger.error("Sonnet call failed for digest %s: %s", date_str, exc)
        return {}


def _build_digest(
    *,
    date_str: str,
    posts: list[dict],
    llm_data: dict,
) -> EditorialDigest:
    """Assemble an EditorialDigest from today's posts and LLM output."""

    # Themes (max 5)
    themes: list[ThemeEntry] = []
    for t in llm_data.get("themes", [])[:5]:
        try:
            themes.append(ThemeEntry(
                name=t["name"],
                intensity=int(t["intensity"]),
                direction=t["direction"],
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # Public sentiment
    public_sentiment: SentimentSnapshot | None = None
    raw_sentiment = llm_data.get("public_sentiment")
    if isinstance(raw_sentiment, dict) and raw_sentiment.get("dominant"):
        try:
            public_sentiment = SentimentSnapshot(
                dominant=raw_sentiment["dominant"],
                secondary=raw_sentiment.get("secondary"),
                shift_from_yesterday=raw_sentiment.get("shift_from_yesterday"),
            )
        except (KeyError, ValueError, TypeError):
            pass

    # Stories covered — one per post
    stories_covered: list[StoryCovered] = []
    for post in posts:
        content = post.get("content", {})
        topic = (content.get("one_liner") or "")[:60]
        angle = post.get("editorial_strategy") or "unknown"
        stories_covered.append(StoryCovered(
            topic=topic,
            angle=angle,
            post_id=post.get("id"),
        ))

    # Editorial strategy counts from LLM (fall back to counting from posts)
    llm_strategy = llm_data.get("editorial_strategy_used", {})
    strategy_counts: dict[str, int] = {
        "ride_the_wave": int(llm_strategy.get("ride_the_wave", 0)),
        "fill_the_gap": int(llm_strategy.get("fill_the_gap", 0)),
        "connect_the_dots": int(llm_strategy.get("connect_the_dots", 0)),
    }
    # If LLM gave us nothing, count from the posts themselves
    if sum(strategy_counts.values()) == 0:
        for post in posts:
            s = post.get("editorial_strategy")
            if s in strategy_counts:
                strategy_counts[s] += 1

    return EditorialDigest(
        date=date_str,
        themes=themes,
        public_sentiment=public_sentiment,
        stories_covered=stories_covered,
        narrative_connections=llm_data.get("narrative_connections", []),
        editorial_strategy_used=strategy_counts,
        posts_generated=len(posts),
        engagement_from_previous_day=EngagementSummary(),
        generated_at=datetime.now(timezone.utc),
    )


async def _trim_old_digests(db: AsyncClient) -> None:
    """Delete digests beyond the most recent _MAX_DIGESTS entries."""
    query = (
        db.collection(COLLECTIONS["editorial_digests"])
        .order_by("date", direction="DESCENDING")
        .offset(_MAX_DIGESTS)
        .limit(500)  # safety cap; there will rarely be >560 total
    )
    old_docs: list[str] = []
    async for doc in query.stream():
        old_docs.append(doc.id)

    if not old_docs:
        return

    batch = db.batch()
    for doc_id in old_docs:
        ref = db.collection(COLLECTIONS["editorial_digests"]).document(doc_id)
        batch.delete(ref)
    await batch.commit()
    logger.info("Trimmed %d old digest(s)", len(old_docs))
