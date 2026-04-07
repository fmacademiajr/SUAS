"""
export_training_data.py
-----------------------
Standalone CLI script. Exports published post data from Firestore to a CSV
file suitable for ML training of the SUAS engagement-scoring model.

Usage:
    python3 scripts/export_training_data.py

Requires:
    - backend/.env (or environment variables already set)
    - google-cloud-firestore installed in the active Python environment

The script writes:
    scripts/training_data_YYYY-MM-DD.csv
"""
from __future__ import annotations

import asyncio
import csv
import math
import os
import sys
from datetime import date, datetime

# Allow imports from backend/app (e.g. app.config)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Load .env from backend/.env before importing app.config so pydantic-settings
# picks up the values even when running from the repo root.
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
if os.path.exists(_ENV_PATH):
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(_ENV_PATH)

import pytz  # noqa: E402 — must come after sys.path is patched

from google.cloud.firestore_v1.async_client import AsyncClient  # noqa: E402

from app.config import get_settings  # noqa: E402

_MANILA_TZ = pytz.timezone("Asia/Manila")
_ELIGIBLE_STATUSES = {"published", "metrics_synced"}
_MIN_POSTS_FOR_ACCURACY = 200

FEATURE_COLUMNS = [
    "post_id",
    "alignment_score",
    "urgency_score",
    "has_voice_statement",
    "hour_of_day",
    "day_of_week",
    "urgency_tier_hot",
    "urgency_tier_warm",
    "post_type_amplify",
    "engagement_normalized",
    "likes",
    "comments",
    "shares",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _safe_float(value: object, default: float) -> float:
    """Return float(value) clamped to [0.0, 1.0], or default on failure."""
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _published_at_manila(post: dict) -> datetime | None:
    """Parse publishing.published_at and localise to Asia/Manila. Returns None on failure."""
    raw = (post.get("publishing") or {}).get("published_at")
    if raw is None:
        return None
    try:
        if isinstance(raw, datetime):
            dt = raw
        else:
            # ISO string — may or may not include timezone info
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        # Convert to Manila time
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(_MANILA_TZ)
    except (ValueError, TypeError, OverflowError):
        return None


def _build_row(post: dict) -> dict | None:
    """
    Build a CSV row dict from a Firestore post document.

    Returns None if the post should be excluded (missing required fields or
    zero engagement).
    """
    scoring = post.get("scoring") or {}
    metrics = post.get("metrics") or {}

    likes = int(metrics.get("likes") or 0)
    comments = int(metrics.get("comments") or 0)
    shares = int(metrics.get("shares") or 0)

    # Only include posts with non-zero engagement
    if likes + comments + shares == 0:
        return None

    alignment_score = _safe_float(scoring.get("alignment_score"), 0.5)
    urgency_score = _safe_float(scoring.get("urgency_score"), 0.3)

    post_type = post.get("post_type") or ""
    urgency = post.get("urgency") or ""

    has_voice_statement = 1 if post_type == "amplify" else 0
    urgency_tier_hot = 1 if urgency == "hot" else 0
    urgency_tier_warm = 1 if urgency == "warm" else 0
    post_type_amplify = 1 if post_type == "amplify" else 0

    # Time features
    manila_dt = _published_at_manila(post)
    if manila_dt is not None:
        hour_of_day = manila_dt.hour
        day_of_week = manila_dt.weekday()  # Monday=0
    else:
        hour_of_day = 12  # fallback: noon
        day_of_week = 0   # fallback: Monday

    # Target variable: log1p of weighted engagement
    engagement_normalized = math.log1p(likes + 2 * comments + 3 * shares)

    return {
        "post_id": post.get("id", ""),
        "alignment_score": alignment_score,
        "urgency_score": urgency_score,
        "has_voice_statement": has_voice_statement,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "urgency_tier_hot": urgency_tier_hot,
        "urgency_tier_warm": urgency_tier_warm,
        "post_type_amplify": post_type_amplify,
        "engagement_normalized": round(engagement_normalized, 6),
        "likes": likes,
        "comments": comments,
        "shares": shares,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    settings = get_settings()

    # Point the Firestore client at the emulator when running locally.
    if settings.firestore_emulator_host:
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host

    db = AsyncClient(project=settings.gcp_project_id)

    print("Fetching posts...")

    # Query for all statuses we care about.  Firestore's `in` operator accepts
    # a list; we split into individual queries if needed but one `in` covers it.
    rows: list[dict] = []
    query = db.collection("posts").where("status", "in", list(_ELIGIBLE_STATUSES))

    async for doc in query.stream():
        data = doc.to_dict() or {}
        if "id" not in data:
            data["id"] = doc.id
        row = _build_row(data)
        if row is not None:
            rows.append(row)

    await db.close()

    n = len(rows)
    print(f"Found {n} eligible posts")

    if n < _MIN_POSTS_FOR_ACCURACY:
        print(
            f"Warning: only {n} posts available. "
            f"Model may not be accurate until {_MIN_POSTS_FOR_ACCURACY}+ posts are collected."
        )

    # Determine output path relative to the scripts/ directory
    today_str = date.today().isoformat()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, f"training_data_{today_str}.csv")

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV written to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
