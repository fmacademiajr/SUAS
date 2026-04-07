"""
Pipeline Scorer
---------------
Scores a list of raw news articles or trend items for alignment with the
SUAS accountability theme and urgency.

Uses Claude Sonnet in batches of 15 articles per call.
Returns ScoredItem instances sorted by alignment_score descending.

Phase 5: If a trained GradientBoostingRegressor is available (R²≥0.30),
it is used for ML re-ranking after Sonnet scoring. Sonnet remains the fallback.
The ML model produces a predicted `engagement_score` used for secondary sorting;
primary sort key remains alignment_score (editorial integrity).
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime

import anthropic

from app.config import get_settings

logger = logging.getLogger("suas.pipeline.scorer")

# ─── Constants ────────────────────────────────────────────────────────────────

_SONNET_BATCH_SIZE = 15
_DEFAULT_ALIGNMENT = 0.3
_DEFAULT_URGENCY = 0.3
_DEFAULT_TIER = "cool"

_HOT_THRESHOLD = 0.8
_WARM_THRESHOLD = 0.4

# ─── ML Model Cache ───────────────────────────────────────────────────────────

_ml_model = None   # GradientBoostingRegressor or None
_ml_scaler = None  # StandardScaler or None

FEATURE_NAMES = [
    "alignment_score_hint",   # alignment_score from Sonnet (Pass 1)
    "urgency_score_hint",     # urgency_score from Sonnet (Pass 1)
    "has_voice_statement",    # 0 — not known at scoring time
    "hour_of_day",            # current hour in PHT
    "day_of_week",            # current weekday, Monday=0
    "urgency_tier_hot",       # 1 if urgency_tier == "hot", else 0
    "urgency_tier_warm",      # 1 if urgency_tier == "warm", else 0
    "post_type_amplify",      # 0 — not known at scoring time
]


# ─── Model ────────────────────────────────────────────────────────────────────


@dataclass
class ScoredItem:
    title: str
    url: str
    summary: str
    source: str
    published_at: datetime
    alignment_score: float      # 0.0–1.0: how well does this serve SUAS's confrontational voice?
    urgency_score: float        # 0.0–1.0: how time-sensitive is this?
    urgency_tier: str           # "hot" | "warm" | "cool"
    reasoning: str              # 1 sentence from Claude explaining the scores
    predicted_engagement: float = field(default=0.0)  # ML-predicted engagement (0.0 if ML unavailable)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _urgency_tier(urgency_score: float) -> str:
    """Derive the urgency tier from a numeric score."""
    if urgency_score >= _HOT_THRESHOLD:
        return "hot"
    if urgency_score >= _WARM_THRESHOLD:
        return "warm"
    return "cool"


def _extract_article_fields(article: object) -> tuple[str, str, str, str, datetime]:
    """
    Normalise a RawArticle or TrendItem to (title, url, summary, source, published_at).
    Falls back to safe defaults for missing attributes.
    """
    title = getattr(article, "title", "") or ""
    url = getattr(article, "url", "") or getattr(article, "link", "") or ""
    summary = (
        getattr(article, "summary", "")
        or getattr(article, "description", "")
        or getattr(article, "snippet", "")
        or ""
    )
    source = getattr(article, "source", "") or getattr(article, "outlet", "") or ""
    published_at = getattr(article, "published_at", None) or getattr(
        article, "pub_date", None
    )
    if not isinstance(published_at, datetime):
        published_at = datetime.utcnow()
    return title, url, summary, source, published_at


def _build_prompt(
    batch: list[object],
    voice_guide_summary: str,
) -> str:
    """Construct the scoring prompt for a batch of articles."""
    articles_block_lines: list[str] = []
    for i, article in enumerate(batch):
        title, url, summary, source, published_at = _extract_article_fields(article)
        articles_block_lines.append(
            f"[{i}]\n"
            f"Title: {title}\n"
            f"Source: {source}\n"
            f"Published: {published_at.isoformat()}\n"
            f"Summary: {summary or '(none)'}\n"
            f"URL: {url}"
        )
    articles_block = "\n\n".join(articles_block_lines)

    return f"""You are the editorial scoring engine for SUAS, a Filipino political accountability page.

SUAS VOICE GUIDE SUMMARY:
{voice_guide_summary}

Score each of the {len(batch)} articles below on two dimensions:

1. alignment_score (0.0–1.0): How well does this story serve SUAS's confrontational accountability voice?
   - 1.0 = clear government failure, confirmed corruption, broken promise, direct protest coverage
   - 0.5 = relevant political story but not a clear accountability moment
   - 0.0 = unrelated to governance, politics, or public accountability

2. urgency_score (0.0–1.0): How time-sensitive is this story for posting?
   - 1.0 = breaking scandal, viral story right now, live protest, politician caught red-handed today
   - 0.5 = relevant recent story (1–2 days old) still gaining traction
   - 0.0 = old story, evergreen content, or nothing time-sensitive

3. urgency_tier (derived from urgency_score):
   - "hot"  if urgency_score >= 0.8  → publish within 2 hours
   - "warm" if urgency_score >= 0.4  → publish within 8 hours
   - "cool" if urgency_score <  0.4  → can wait 24–48 hours (may go to Content Bank)

4. reasoning: One sentence explaining the scores for this article.

ARTICLES TO SCORE:

{articles_block}

Respond with ONLY a valid JSON array of exactly {len(batch)} objects, in the same order as the articles above:
[
  {{"alignment_score": 0.85, "urgency_score": 0.9, "urgency_tier": "hot", "reasoning": "..."}},
  ...
]
Do not include markdown code fences or any other text outside the JSON array."""


def _parse_sonnet_response(raw: str, batch_size: int) -> list[dict]:
    """
    Parse Sonnet's JSON response. Returns a list of score dicts.
    Falls back to defaults on any parse error.
    """
    try:
        # Strip accidental markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        scores = json.loads(text)
        if isinstance(scores, list) and len(scores) == batch_size:
            return scores
        logger.warning(
            "Sonnet returned %d score objects for a batch of %d; using defaults.",
            len(scores) if isinstance(scores, list) else -1,
            batch_size,
        )
    except (json.JSONDecodeError, IndexError) as exc:
        logger.warning("Malformed JSON from Sonnet scorer: %s", exc)
    return [
        {
            "alignment_score": _DEFAULT_ALIGNMENT,
            "urgency_score": _DEFAULT_URGENCY,
            "urgency_tier": _DEFAULT_TIER,
            "reasoning": "Scoring unavailable (parse error).",
        }
    ] * batch_size


def _safe_float(value: object, default: float) -> float:
    """Clamp a value to [0.0, 1.0], returning default on failure."""
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ─── ML Scorer Initialisation ─────────────────────────────────────────────────


async def initialize_ml_scorer(db) -> None:
    """
    Load the active ML scoring model from Firestore/GCS into module-level cache.
    Called once at app startup from main.py lifespan.
    If no model is available or loading fails, scorer falls back to Sonnet-only mode.
    """
    global _ml_model, _ml_scaler
    # Import here to avoid circular imports at module level
    from app.services.learning_service import get_active_model, load_model_from_gcs

    record = await get_active_model(db)
    if record is None:
        logger.info("No active ML scoring model found — using Sonnet only.")
        return
    result = await load_model_from_gcs(record.gcs_path)
    if result is None:
        logger.warning("Failed to load ML model from GCS — using Sonnet only.")
        return
    _ml_model, _ml_scaler = result
    logger.info(
        "ML scorer loaded: %s (R²=%.3f)",
        record.model_version,
        record.accuracy_metrics.r_squared,
    )


# ─── Override Logger ──────────────────────────────────────────────────────────


async def log_override(
    db,
    post_id: str,
    fernando_rating: int,
    predicted_engagement: float,
) -> None:
    """
    Log an override when Fernando's rating diverges from the ML prediction by >0.3.
    Written to model_training/overrides as an array of override records.
    Called from the learning log PATCH endpoint.
    """
    from google.cloud.firestore_v1 import ArrayUnion
    from app.core.firestore import COLLECTIONS

    normalized_rating = fernando_rating / 5.0
    # Normalize predicted_engagement from log1p space back to 0-1 range (approximate)
    normalized_pred = min(1.0, math.expm1(predicted_engagement) / 50.0)

    if abs(normalized_rating - normalized_pred) <= 0.3:
        return  # not a significant override

    override = {
        "post_id": post_id,
        "fernando_rating": fernando_rating,
        "predicted_engagement": predicted_engagement,
        "normalized_rating": normalized_rating,
        "normalized_pred": normalized_pred,
        "divergence": abs(normalized_rating - normalized_pred),
        "logged_at": datetime.utcnow().isoformat(),
    }
    ref = db.collection(COLLECTIONS["model_training"]).document("overrides")
    await ref.set({"records": ArrayUnion([override])}, merge=True)
    logger.info(
        "Override logged for post %s: rating=%.2f pred=%.2f",
        post_id,
        normalized_rating,
        normalized_pred,
    )


# ─── Main entry point ─────────────────────────────────────────────────────────


async def score_items(
    articles: list,
    voice_guide_summary: str,
) -> list[ScoredItem]:
    """
    Score a list of RawArticle or TrendItem objects for SUAS alignment and urgency.

    Pass 1: Claude Sonnet scores all articles for alignment and urgency.
    Pass 2 (optional): If a trained ML model is loaded, it re-ranks articles using
    the Sonnet scores as features plus time-of-day features, producing a
    predicted_engagement value. Final sort is: primary alignment_score (editorial),
    secondary predicted_engagement (ML engagement prediction).

    Args:
        articles:            Heterogeneous list; duck-typed via _extract_article_fields.
        voice_guide_summary: Short editorial brief describing SUAS's current voice/theme.

    Returns:
        List of ScoredItem instances sorted by alignment_score descending
        (with predicted_engagement as tiebreaker when ML model is active).
    """
    if not articles:
        logger.info("Scorer received empty article list; returning early.")
        return []

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    scored: list[ScoredItem] = []

    logger.info("Scorer: scoring %d articles in batches of %d.", len(articles), _SONNET_BATCH_SIZE)

    for batch_start in range(0, len(articles), _SONNET_BATCH_SIZE):
        batch = articles[batch_start : batch_start + _SONNET_BATCH_SIZE]
        prompt = _build_prompt(batch, voice_guide_summary)

        # ── Call Claude Sonnet ────────────────────────────────────────────────
        try:
            message = await client.messages.create(
                model=settings.model_sonnet,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_response = message.content[0].text
        except anthropic.APIError as exc:
            logger.warning(
                "Sonnet API error for batch starting at index %d: %s; assigning defaults.",
                batch_start,
                exc,
            )
            raw_response = "[]"  # triggers default fallback below

        score_dicts = _parse_sonnet_response(raw_response, len(batch))

        # ── Build ScoredItems ─────────────────────────────────────────────────
        for article, score_dict in zip(batch, score_dicts):
            title, url, summary, source, published_at = _extract_article_fields(article)

            alignment = _safe_float(score_dict.get("alignment_score"), _DEFAULT_ALIGNMENT)
            urgency = _safe_float(score_dict.get("urgency_score"), _DEFAULT_URGENCY)

            # Trust Claude's tier if valid; recalculate if not
            raw_tier = score_dict.get("urgency_tier", "")
            tier = raw_tier if raw_tier in ("hot", "warm", "cool") else _urgency_tier(urgency)

            reasoning = str(score_dict.get("reasoning", "")) or "No reasoning provided."

            scored.append(
                ScoredItem(
                    title=title,
                    url=url,
                    summary=summary,
                    source=source,
                    published_at=published_at,
                    alignment_score=alignment,
                    urgency_score=urgency,
                    urgency_tier=tier,
                    reasoning=reasoning,
                )
            )

    # ── Sort by alignment_score descending (Sonnet-only baseline) ─────────────
    scored.sort(key=lambda x: x.alignment_score, reverse=True)

    # ── Pass 2: ML re-ranking (if model is loaded) ────────────────────────────
    if _ml_model is not None and _ml_scaler is not None:
        import numpy as np
        import pytz

        manila = pytz.timezone("Asia/Manila")
        now = datetime.now(manila)
        hour = now.hour
        dow = now.weekday()

        features = []
        for item in scored:
            features.append([
                item.alignment_score,                        # alignment_score_hint
                item.urgency_score,                          # urgency_score_hint
                0,                                           # has_voice_statement (unknown)
                hour,                                        # hour_of_day
                dow,                                         # day_of_week
                1 if item.urgency_tier == "hot" else 0,     # urgency_tier_hot
                1 if item.urgency_tier == "warm" else 0,    # urgency_tier_warm
                0,                                           # post_type_amplify (unknown)
            ])

        X = np.array(features)
        X_scaled = _ml_scaler.transform(X)
        predictions = _ml_model.predict(X_scaled)

        for item, pred in zip(scored, predictions):
            item.predicted_engagement = float(pred)

        # Re-sort: primary by alignment_score (editorial integrity),
        # secondary by predicted_engagement (ML engagement signal).
        # Round alignment to nearest 0.5 to create broad buckets so ML can
        # meaningfully differentiate within each editorial tier.
        scored.sort(
            key=lambda x: (round(x.alignment_score * 2) / 2, x.predicted_engagement),
            reverse=True,
        )
        logger.info(
            "ML re-ranking applied. Top predicted_engagement=%.3f",
            scored[0].predicted_engagement if scored else 0,
        )

    logger.info(
        "Scorer: returning %d ScoredItems. Top alignment=%.2f, hot=%d, warm=%d, cool=%d.",
        len(scored),
        scored[0].alignment_score if scored else 0.0,
        sum(1 for s in scored if s.urgency_tier == "hot"),
        sum(1 for s in scored if s.urgency_tier == "warm"),
        sum(1 for s in scored if s.urgency_tier == "cool"),
    )
    return scored
