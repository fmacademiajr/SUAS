"""
Context Builder
---------------
Assembles the editorial memory context window that Claude Opus receives on
every pipeline run.  The context window gives Claude up to 60 days of
political-discourse awareness: daily editorial digests, the SUAS voice guide,
today's scored headlines, and any celebrity accountability statements.

Without this context every run is blind to history; with it Claude can detect
narrative arcs, avoid repetition, and make connect-the-dots insights.

The assembled ContextWindow is passed directly to post_generator.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import anthropic
from google.cloud.firestore_v1 import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from app.config import get_settings
from app.core.firestore import COLLECTIONS
from app.models.digest import EditorialDigest
from app.models.settings import AppSettings, VoiceGuide
from app.models.voice import VoiceStatement
from app.pipeline.scorer import ScoredItem

logger = logging.getLogger("suas.pipeline.context_builder")

# ─── Constants ────────────────────────────────────────────────────────────────

_MAX_CONTEXT_TOKENS = 22_000
_DIGEST_LIMIT = 60
_COMPRESSION_SPLIT = 30          # oldest N digests to compress
_COMPRESSION_TARGET_WORDS = 500
_TOP_NEWS_COUNT = 15
_VOICE_MIN_ALIGNMENT = 4.0
_TOKENS_PER_WORD = 1.33          # rough heuristic — good enough without an API call


# ─── ContextWindow dataclass ─────────────────────────────────────────────────


@dataclass
class ContextWindow:
    """Complete context payload assembled for Claude Opus."""

    digest_block: str               # formatted text of the last 60 digests (compressed if needed)
    voice_guide_block: str          # voice guide rules, tone, one-liner patterns
    news_block: str                 # today's top scored headlines + summaries
    voice_statements_block: str     # celebrity statements found today (may be empty)
    total_tokens: int               # estimated token count of the full context
    digest_count: int               # how many digests are in the window
    compression_applied: bool       # True if old digests were compressed


# ─── Token estimation ────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Estimate the token count of *text* using a word-based heuristic."""
    if not text:
        return 0
    return int(len(text.split()) * _TOKENS_PER_WORD)


# ─── Digest formatting ───────────────────────────────────────────────────────


def _format_single_digest(digest: EditorialDigest) -> str:
    """Format one EditorialDigest into a compact text block for the context window."""

    # If the digest was previously compressed, use the stored summary directly.
    if digest.is_compressed and digest.compressed_summary:
        return f"[{digest.date}] (compressed)\n{digest.compressed_summary}"

    lines: list[str] = [f"[{digest.date}]"]

    # Themes
    if digest.themes:
        theme_parts = []
        for t in digest.themes:
            arrow = {"escalating": "\u2191", "fading": "\u2193", "steady": "\u2192", "new": "\u2726"}.get(
                t.direction, "\u2192"
            )
            theme_parts.append(f"{t.name} ({arrow} {t.direction}, intensity {t.intensity})")
        lines.append(f"Themes: {', '.join(theme_parts)}")

    # Mood / sentiment
    if digest.public_sentiment:
        mood = digest.public_sentiment.dominant
        shift = ""
        if digest.public_sentiment.shift_from_yesterday:
            shift = f" (was: {digest.public_sentiment.shift_from_yesterday.split('->')[0].strip()})"
        elif digest.public_sentiment.secondary:
            shift = f" / {digest.public_sentiment.secondary}"
        lines.append(f"Mood: {mood}{shift}")

    # Stories covered
    if digest.stories_covered:
        covered_parts = [f"{s.topic} ({s.angle})" for s in digest.stories_covered]
        lines.append(f"Covered: {', '.join(covered_parts)}")

    # Voices heard
    if digest.voices_heard:
        voice_parts = [f"{v.name} ({v.platform}, score {v.alignment_score:.0f})" for v in digest.voices_heard]
        lines.append(f"Voices: {', '.join(voice_parts)}")

    # Narrative connections
    if digest.narrative_connections:
        lines.append(f"Connection: {'; '.join(digest.narrative_connections)}")

    return "\n".join(lines)


def _format_digest_block(digests: list[EditorialDigest]) -> str:
    """Render all digests (oldest-first) into a single text block."""
    if not digests:
        return ""
    entries = [_format_single_digest(d) for d in digests]
    return "\n---\n".join(entries)


# ─── Compression via Haiku ───────────────────────────────────────────────────


async def _compress_old_digests(
    digests: list[EditorialDigest],
    db: AsyncClient,
) -> str:
    """
    Send the oldest *digests* to Claude Haiku for compression into a dense
    ~500-word historical summary.  On success the compressed text is stored
    back onto the most recent of those digests in Firestore so future runs
    can reuse it.

    Returns the compressed summary text, or a simple fallback on failure.
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    raw_block = _format_digest_block(digests)

    prompt = (
        "Summarize these {count} daily editorial digests into a {words}-word "
        "historical context block.\n"
        "Focus on: recurring themes, sentiment trajectory, which celebrities "
        "spoke out, any narrative arcs that are building over time. "
        "Be dense, not narrative.\n\n"
        "{block}"
    ).format(count=len(digests), words=_COMPRESSION_TARGET_WORDS, block=raw_block)

    try:
        message = await client.messages.create(
            model=settings.model_haiku,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        compressed_text = message.content[0].text
    except Exception as exc:
        logger.error("Haiku compression failed: %s — falling back to raw block.", exc)
        return raw_block

    # Persist to the most recent of the compressed digests for future reuse.
    try:
        newest = digests[-1]  # digests are oldest-first
        doc_ref = db.collection(COLLECTIONS["editorial_digests"]).document(newest.date)
        await doc_ref.update({
            "compressed_summary": compressed_text,
            "is_compressed": True,
        })
        logger.info("Stored compressed summary on digest %s.", newest.date)
    except Exception as exc:
        logger.warning("Failed to persist compressed summary to Firestore: %s", exc)

    return compressed_text


# ─── Voice guide formatting ──────────────────────────────────────────────────


def _format_voice_guide_block(vg: VoiceGuide) -> str:
    """Render the VoiceGuide into the text block Claude receives."""
    lines: list[str] = [
        "=== SUAS VOICE GUIDE ===",
        f"Persona: {vg.persona_description}",
        "",
        "Tone Rules:",
    ]
    for i, rule in enumerate(vg.tone_rules, 1):
        lines.append(f"  {i}. {rule}")

    lines.append("")
    lines.append("One-Liner Patterns (use a DIFFERENT pattern for each post today):")
    for i, pattern in enumerate(vg.one_liner_patterns, 1):
        lines.append(f"  {i}. {pattern}")

    lines.append("")
    lines.append(f"Forbidden phrases: {', '.join(vg.forbidden_phrases)}")
    lines.append("===")

    return "\n".join(lines)


# ─── News block formatting ───────────────────────────────────────────────────


def _format_news_block(scored_items: list[ScoredItem]) -> str:
    """Render the top scored news items into the context block."""
    if not scored_items:
        return "=== TODAY'S NEWS ===\n(no scored items available)\n==="

    # Take top N by alignment_score (they should already be sorted, but be safe).
    top = sorted(scored_items, key=lambda s: s.alignment_score, reverse=True)[:_TOP_NEWS_COUNT]

    lines: list[str] = ["=== TODAY'S NEWS (scored by alignment + urgency) ==="]
    for i, item in enumerate(top, 1):
        lines.append(
            f"{i}. [{item.urgency_tier.upper()}] {item.title} ({item.source})\n"
            f"   Alignment: {item.alignment_score:.2f} | Urgency: {item.urgency_score:.2f}\n"
            f"   {item.summary[:200]}\n"
            f"   Reasoning: {item.reasoning}\n"
            f"   URL: {item.url}"
        )
    lines.append("===")
    return "\n".join(lines)


# ─── Voice statements block ──────────────────────────────────────────────────


def _format_voice_statements_block(statements: list[VoiceStatement]) -> str:
    """
    Render qualifying celebrity voice statements.  Only include statements
    whose alignment_score >= 4.0 — these are the ones with a genuine
    accountability angle.
    """
    qualifying = [s for s in statements if s.alignment_score >= _VOICE_MIN_ALIGNMENT]
    if not qualifying:
        return ""

    lines: list[str] = [f"=== CELEBRITY VOICES (accountability angle >= {_VOICE_MIN_ALIGNMENT:.1f}) ==="]
    for stmt in qualifying:
        lines.append(
            f'{stmt.celebrity_name} (score {stmt.alignment_score:.1f}):\n'
            f'  "{stmt.statement_summary}"\n'
            f'  Source: {stmt.source_url}'
        )
    lines.append("===")
    return "\n".join(lines)


# ─── Main entry point ────────────────────────────────────────────────────────


async def build_context_window(
    db: AsyncClient,
    scored_items: list[ScoredItem],
    voice_statements: list[VoiceStatement],
) -> ContextWindow:
    """
    Assemble the full editorial memory context window for Claude Opus.

    This function is called once per pipeline run and never raises — if
    Firestore is unreachable it returns a ContextWindow with empty digest
    and voice guide blocks and logs the error.
    """
    digests: list[EditorialDigest] = []
    voice_guide = VoiceGuide()
    compression_applied = False

    # ── Step 1: Fetch digests ────────────────────────────────────────────────
    try:
        query = (
            db.collection(COLLECTIONS["editorial_digests"])
            .order_by("date", direction="DESCENDING")
            .limit(_DIGEST_LIMIT)
        )
        docs = []
        async for doc in query.stream():
            docs.append(doc)

        for doc in docs:
            try:
                digests.append(EditorialDigest.from_firestore(doc.to_dict()))
            except Exception as exc:
                logger.warning("Skipping malformed digest %s: %s", doc.id, exc)

        # Sort oldest-first — chronological order reads more naturally for Claude.
        digests.sort(key=lambda d: d.date)

        logger.info("Loaded %d editorial digests.", len(digests))
    except Exception as exc:
        logger.error("Failed to fetch editorial digests from Firestore: %s", exc)

    # ── Step 2: Fetch VoiceGuide ─────────────────────────────────────────────
    try:
        settings_doc = await (
            db.collection(COLLECTIONS["settings"])
            .document("app_settings")
            .get()
        )
        if settings_doc.exists:
            app_settings = AppSettings.from_firestore(settings_doc.to_dict())
            voice_guide = app_settings.voice_guide
        else:
            logger.info("No app_settings document found — using VoiceGuide defaults.")
    except Exception as exc:
        logger.error("Failed to fetch VoiceGuide from Firestore: %s — using defaults.", exc)

    # ── Step 3: Format digest block ──────────────────────────────────────────
    digest_block = _format_digest_block(digests)

    # ── Step 4: Estimate tokens & compress if needed ─────────────────────────
    digest_tokens = _estimate_tokens(digest_block)

    if digest_tokens > _MAX_CONTEXT_TOKENS and len(digests) > _COMPRESSION_SPLIT:
        logger.info(
            "Digest block ~%d tokens exceeds %d limit; compressing oldest %d digests.",
            digest_tokens,
            _MAX_CONTEXT_TOKENS,
            _COMPRESSION_SPLIT,
        )
        old_digests = digests[:_COMPRESSION_SPLIT]
        recent_digests = digests[_COMPRESSION_SPLIT:]

        compressed_summary = await _compress_old_digests(old_digests, db)

        # Rebuild digest block: compressed historical summary + recent entries.
        compressed_header = (
            f"=== HISTORICAL SUMMARY ({old_digests[0].date} to {old_digests[-1].date}) ===\n"
            f"{compressed_summary}\n"
            f"=== END HISTORICAL SUMMARY ==="
        )
        recent_block = _format_digest_block(recent_digests)
        digest_block = f"{compressed_header}\n---\n{recent_block}" if recent_block else compressed_header
        compression_applied = True

    # ── Step 5: Format remaining blocks ──────────────────────────────────────
    voice_guide_block = _format_voice_guide_block(voice_guide)
    news_block = _format_news_block(scored_items)
    voice_statements_block = _format_voice_statements_block(voice_statements)

    # ── Step 6: Final token estimate ─────────────────────────────────────────
    total_text = "\n\n".join(
        block for block in [digest_block, voice_guide_block, news_block, voice_statements_block] if block
    )
    total_tokens = _estimate_tokens(total_text)

    logger.info(
        "Context window ready: %d digests, ~%d tokens, compression=%s.",
        len(digests),
        total_tokens,
        compression_applied,
    )

    # ── Step 7: Return ───────────────────────────────────────────────────────
    return ContextWindow(
        digest_block=digest_block,
        voice_guide_block=voice_guide_block,
        news_block=news_block,
        voice_statements_block=voice_statements_block,
        total_tokens=total_tokens,
        digest_count=len(digests),
        compression_applied=compression_applied,
    )
