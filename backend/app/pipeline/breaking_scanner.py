"""
breaking_scanner.py — Lightweight breaking-news detector for SUAS.

Runs 6 times per day (8 AM, 10 AM, 12 PM, 2 PM, 4 PM, 6 PM PHT) and
performs a two-pass triage before the next scheduled full pipeline run:

  Pass 1 — Haiku keyword triage:
      Fetches the latest 30 headlines (last 2 hours), sends a compact list
      to Haiku, and asks it to flag any that meet HOT criteria.
      If nothing is flagged the scan exits immediately with no further API cost.

  Pass 2 — Sonnet confirmation:
      Takes the first flagged headline, optionally fetches the full article
      body, and asks Sonnet to confirm whether the story is truly HOT and
      to draft a SUAS-style post if so.

  If Sonnet confirms HOT:
      - Saves a draft Post to Firestore (status: pending_review).
      - Writes a notification flag to settings/pending_notifications.
      - Returns ScanResult(hot_story_found=True, ...).

The scanner never raises — any unhandled exception is caught, logged at
ERROR level, and surfaces as ScanResult(hot_story_found=False) so the
scheduler can continue without crashing.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import anthropic
import httpx

from app.config import get_settings
from app.core.firestore import get_firestore_client, COLLECTIONS
from app.core.model_router import ModelRouter, TaskCategory
from app.models.post import (
    PostCreate,
    PostContent,
    PostImage,
    PostType,
    UrgencyTier,
)
from app.pipeline.agents.news_agent import fetch_news

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("suas.pipeline.breaking_scanner")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Only articles published within this window are considered "breaking"
_BREAKING_WINDOW_HOURS = 2

# How many headlines are passed to Haiku
_HEADLINE_LIMIT = 30

# Maximum bytes of article body sent to Sonnet as a content preview
_CONTENT_PREVIEW_CHARS = 800

# HTTP timeout for fetching a full article (seconds)
_ARTICLE_FETCH_TIMEOUT = 8.0

_USER_AGENT = (
    "Mozilla/5.0 (compatible; SUAS-BreakingScanner/1.0; "
    "+https://github.com/fmacademiajr/SUAS; Philippine political tracker)"
)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """Returned by run_breaking_scan() regardless of outcome."""

    hot_story_found: bool
    story_title: str = ""
    story_url: str = ""
    story_summary: str = ""
    draft_post_id: str = ""     # Firestore post ID if a draft was saved
    confidence: float = 0.0     # 0.0–1.0, from Sonnet


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_headlines_text(articles: list) -> str:
    """
    Render a numbered list of headlines for the Haiku prompt.

    Each line: "{n}. {title} ({source}, {minutes_ago}m ago)"
    """
    now = datetime.now(tz=timezone.utc)
    lines: list[str] = []
    for i, article in enumerate(articles, start=1):
        minutes_ago = int((now - article.published_at).total_seconds() / 60)
        lines.append(
            f"{i}. {article.title} ({article.source}, {minutes_ago}m ago)"
        )
    return "\n".join(lines)


def _extract_json_from_response(raw: str) -> object:
    """
    Extract the first valid JSON value from a raw model response.

    Tries direct parse first, then strips markdown code fences, then
    searches for the first bracketed or braced block.
    Raises ValueError if no valid JSON is found.
    """
    text = raw.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Attempt 3: find the first [ ... ] or { ... } block
    for open_ch, close_ch in [("[", "]"), ("{", "}")]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not extract valid JSON from response: {text[:300]}")


async def _fetch_article_content(url: str) -> str:
    """
    Perform a simple HTTP GET on *url* and extract plain text from <p> tags.

    Returns an empty string on any error so callers can fall back to the
    RSS summary without disrupting the scan.
    """
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(_ARTICLE_FETCH_TIMEOUT),
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

        # Extract text content from <p> tags with a basic regex
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
        # Strip inner HTML tags and normalise whitespace
        texts: list[str] = []
        for p in paragraphs:
            cleaned = re.sub(r"<[^>]+>", "", p).strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if cleaned:
                texts.append(cleaned)

        return " ".join(texts)

    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not fetch article content from %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# Pass 1 — Haiku keyword triage
# ---------------------------------------------------------------------------


async def _pass1_haiku_triage(
    articles: list,
    client: anthropic.AsyncAnthropic,
    router: ModelRouter,
) -> list[dict]:
    """
    Send a compact headlines list to Haiku and return its list of flagged items.

    Returns an empty list when nothing is hot or when the response cannot
    be parsed as the expected JSON array.
    """
    headlines_text = _build_headlines_text(articles)

    prompt = f"""You are scanning Philippine political news headlines for breaking stories that require immediate accountability coverage.

HOT criteria (publish within 2 hours):
- Breaking scandal involving public funds or officials
- Viral callout of a politician going widely shared
- Live or ongoing political protest/demonstration
- Major government failure exposed in real time
- Politician resigning, arrested, or caught lying publicly

Headlines:
{headlines_text}

For each headline, respond with ONLY a JSON array:
[{{"index": 1, "is_hot": true, "keyword_match": "arrested"}}, ...]

Only flag headlines where you are confident they meet HOT criteria.
If nothing is hot, return an empty array: []"""

    response = await client.messages.create(
        model=router.get_model(TaskCategory.MECHANICAL),
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    logger.debug("Haiku raw response:\n%s", raw)

    try:
        parsed = _extract_json_from_response(raw)
    except ValueError as exc:
        logger.warning("Could not parse Haiku response as JSON: %s", exc)
        return []

    if not isinstance(parsed, list):
        logger.warning("Haiku returned non-list JSON: %r", parsed)
        return []

    # Keep only items marked is_hot=true
    hot_items = [
        item for item in parsed
        if isinstance(item, dict) and item.get("is_hot") is True
    ]
    return hot_items


# ---------------------------------------------------------------------------
# Pass 2 — Sonnet confirmation + draft
# ---------------------------------------------------------------------------


async def _pass2_sonnet_confirm(
    article,
    client: anthropic.AsyncAnthropic,
    router: ModelRouter,
) -> dict | None:
    """
    Ask Sonnet whether the flagged article is genuinely HOT and, if so,
    draft a SUAS-style post.

    Returns the parsed JSON dict from Sonnet, or None on failure.
    """
    # Attempt to fetch the full article body for a richer content preview
    content_text = await _fetch_article_content(article.url)
    content_preview = (content_text[:_CONTENT_PREVIEW_CHARS] if content_text else article.summary)

    published_str = article.published_at.strftime("%Y-%m-%d %H:%M UTC")

    prompt = f"""You are the editorial engine for SUAS, a Philippine political accountability page.

A headline has been flagged as potentially BREAKING:
Title: {article.title}
Source: {article.source}
Published: {published_str}
Content preview: {content_preview}

Evaluate:
1. Is this genuinely HOT (needs posting within 2 hours)? Or is it WARM (can wait for the next scheduled run)?
2. If HOT: Draft a SUAS-style post for immediate review.

Respond with ONLY this JSON:
{{
  "is_hot": true,
  "confidence": 0.85,
  "reasoning": "One sentence explaining why this is hot.",
  "draft": {{
    "one_liner": "≤10 words, confrontational",
    "body": "3-4 sentences, fact-based, SUAS voice",
    "hashtags": ["#ShutUpAndServe", "..."],
    "image_prompt": "Dark blue background... bold white uppercase: 'ONE LINER HERE'"
  }}
}}

If NOT hot, set "is_hot": false and omit the "draft" field."""

    response = await client.messages.create(
        model=router.get_model(TaskCategory.REASONING),
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    logger.debug("Sonnet raw response:\n%s", raw)

    try:
        parsed = _extract_json_from_response(raw)
    except ValueError as exc:
        logger.warning("Could not parse Sonnet response as JSON: %s", exc)
        return None

    if not isinstance(parsed, dict):
        logger.warning("Sonnet returned non-dict JSON: %r", parsed)
        return None

    return parsed


# ---------------------------------------------------------------------------
# Firestore persistence
# ---------------------------------------------------------------------------


async def _save_draft_post(
    db,
    article,
    draft: dict,
    confidence: float,
) -> str:
    """
    Persist the Sonnet draft as a pending_review Post in Firestore and write
    the pending_notifications flag.

    Returns the new post_id.
    """
    post_id = str(uuid.uuid4())

    post = PostCreate(
        post_type=PostType.NEWS,
        urgency=UrgencyTier.HOT,
        content=PostContent(
            one_liner=draft["one_liner"],
            body=draft["body"],
            hashtags=draft["hashtags"],
            full_text=(
                draft["one_liner"]
                + "\n\n"
                + draft["body"]
                + "\n\n"
                + " ".join(draft["hashtags"])
            ),
        ),
        image=PostImage(
            prompt=draft["image_prompt"],
            generation_model="pending",   # image generated async after Fernando approves
        ),
        pipeline_run_id=f"breaking_{post_id[:8]}",
    )

    # Serialise via Pydantic and inject the explicit document ID + metadata
    post_data = post.model_dump(mode="json", exclude_none=False)
    post_data["id"] = post_id
    post_data["status"] = "pending_review"
    post_data["created_at"] = datetime.now(timezone.utc).isoformat()
    post_data["updated_at"] = post_data["created_at"]
    post_data["breaking_scan"] = True
    post_data["source_url"] = article.url
    post_data["breaking_confidence"] = confidence

    await db.collection(COLLECTIONS["posts"]).document(post_id).set(post_data)

    # Notify Fernando
    await db.collection("settings").document("pending_notifications").set(
        {
            "has_pending": True,
            "post_id": post_id,
            "story_title": article.title,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )

    return post_id


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_breaking_scan(db) -> ScanResult:
    """
    Execute the two-pass breaking-news scan and return a ScanResult.

    Parameters
    ----------
    db:
        An async Firestore client (``google.cloud.firestore_v1.async_client.AsyncClient``).

    Returns
    -------
    ScanResult
        ``hot_story_found=True`` with populated fields when a hot story was
        found and persisted; ``hot_story_found=False`` otherwise (including
        on any error).
    """
    try:
        settings = get_settings()
        router = ModelRouter(settings)
        anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        # ── Fetch news ────────────────────────────────────────────────────────
        all_articles = await fetch_news()

        # Filter to articles published within the last 2 hours
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_BREAKING_WINDOW_HOURS)
        recent_articles = [a for a in all_articles if a.published_at >= cutoff]

        # Apply headline cap
        recent_articles = recent_articles[:_HEADLINE_LIMIT]

        if not recent_articles:
            logger.info("Scan complete — no hot stories found")
            return ScanResult(hot_story_found=False)

        # ── Pass 1: Haiku keyword triage ──────────────────────────────────────
        hot_items = await _pass1_haiku_triage(recent_articles, anthropic_client, router)

        if not hot_items:
            logger.debug("Haiku found no hot headlines — scan complete")
            logger.info("Scan complete — no hot stories found")
            return ScanResult(hot_story_found=False)

        # ── Pass 2: Sonnet confirmation for the first flagged item ────────────
        # Haiku returns 1-based indices
        first_hot = hot_items[0]
        article_index = int(first_hot.get("index", 1)) - 1

        # Guard against an out-of-range index from Haiku
        if article_index < 0 or article_index >= len(recent_articles):
            logger.warning(
                "Haiku returned index %d which is out of range for %d articles; "
                "using index 0.",
                article_index + 1,
                len(recent_articles),
            )
            article_index = 0

        flagged_article = recent_articles[article_index]

        sonnet_result = await _pass2_sonnet_confirm(flagged_article, anthropic_client, router)

        if sonnet_result is None or not sonnet_result.get("is_hot"):
            logger.info("Scan complete — no hot stories found")
            return ScanResult(hot_story_found=False)

        # ── Sonnet confirmed HOT ──────────────────────────────────────────────
        confidence: float = float(sonnet_result.get("confidence", 0.0))
        draft: dict = sonnet_result.get("draft", {})

        # Validate that the draft has all required keys before persisting
        required_draft_keys = {"one_liner", "body", "hashtags", "image_prompt"}
        missing_keys = required_draft_keys - set(draft.keys())
        if missing_keys:
            logger.error(
                "Sonnet draft is missing required keys %s — cannot save post.",
                missing_keys,
            )
            logger.info("Scan complete — no hot stories found")
            return ScanResult(hot_story_found=False)

        # Ensure hashtags is a list of strings
        if not isinstance(draft.get("hashtags"), list):
            draft["hashtags"] = [str(draft["hashtags"])]
        draft["hashtags"] = [str(h) for h in draft["hashtags"]]

        # ── Persist draft ─────────────────────────────────────────────────────
        post_id = await _save_draft_post(db, flagged_article, draft, confidence)

        logger.info(
            "HOT story detected: %s (confidence: %.0f%%)",
            flagged_article.title,
            confidence * 100,
        )

        return ScanResult(
            hot_story_found=True,
            story_title=flagged_article.title,
            story_url=flagged_article.url,
            story_summary=flagged_article.summary,
            draft_post_id=post_id,
            confidence=confidence,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Breaking scan failed with an unexpected error: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return ScanResult(hot_story_found=False)
