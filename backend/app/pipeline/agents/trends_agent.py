"""
trends_agent.py
---------------
Fetches trending topics from two sources in parallel:
  1. Google Trends (Philippines) — broad keyword popularity
  2. Brave Search API — real-time Philippine news headlines

Run as one of three parallel data-gathering agents at the start of each
pipeline run.  Returns a score-sorted list of up to 30 TrendItems.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from pytrends.request import TrendReq

from app.config import get_settings

logger = logging.getLogger("suas.pipeline.trends_agent")

_GOOGLE_TOP_N = 20
_GOOGLE_SCORE_MAX = 1.0
_GOOGLE_SCORE_MIN = 0.05

_BRAVE_QUERY = "Philippines politics government"
_BRAVE_COUNT = 20
_BRAVE_API_URL = "https://api.search.brave.com/res/v1/news/search"

_COMBINED_LIMIT = 30


@dataclass
class TrendItem:
    keyword: str
    source: str    # "google_trends" | "brave_news"
    score: float   # relative popularity 0.0–1.0
    context: str   # headline or keyword


# ─── Google Trends ────────────────────────────────────────────────────────────


def _fetch_google_trends_sync() -> list[TrendItem]:
    """Synchronous — called via asyncio.to_thread()."""
    pytrends = TrendReq(hl="en-PH", tz=480)
    df = pytrends.trending_searches(pn="philippines")
    keywords: list[str] = df.iloc[:, 0].tolist()
    top = keywords[:_GOOGLE_TOP_N]

    items: list[TrendItem] = []
    total = len(top)
    for rank, keyword in enumerate(top, start=1):
        score = (
            _GOOGLE_SCORE_MAX
            if total == 1
            else _GOOGLE_SCORE_MAX - (rank - 1) * (
                (_GOOGLE_SCORE_MAX - _GOOGLE_SCORE_MIN) / (total - 1)
            )
        )
        items.append(TrendItem(
            keyword=keyword,
            source="google_trends",
            score=round(score, 4),
            context=keyword,
        ))
    return items


async def _fetch_google_trends() -> list[TrendItem]:
    try:
        return await asyncio.to_thread(_fetch_google_trends_sync)
    except Exception as exc:
        logger.warning("Google Trends fetch failed: %s", exc)
        return []


# ─── Brave Search ─────────────────────────────────────────────────────────────


async def _fetch_brave_news() -> list[TrendItem]:
    """
    Calls Brave News Search API for recent Philippine political headlines.
    Each result gets a score based on its position (top result = 1.0).
    """
    settings = get_settings()
    if not settings.brave_api_key:
        logger.info("BRAVE_API_KEY not set — skipping Brave news fetch")
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                _BRAVE_API_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": settings.brave_api_key,
                },
                params={
                    "q": _BRAVE_QUERY,
                    "count": _BRAVE_COUNT,
                    "country": "PH",
                    "search_lang": "en",
                    "freshness": "pd",   # past day
                },
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        items: list[TrendItem] = []
        total = len(results)

        for rank, article in enumerate(results, start=1):
            title = article.get("title", "")
            description = article.get("description", "") or title
            score = (
                1.0 if total == 1
                else 1.0 - (rank - 1) * (0.95 / (total - 1))
            )
            items.append(TrendItem(
                keyword=title[:80],
                source="brave_news",
                score=round(score, 4),
                context=description[:200],
            ))

        logger.info("Brave news: fetched %d headlines", len(items))
        return items

    except Exception as exc:
        logger.warning("Brave news fetch failed: %s", exc)
        return []


# ─── Public entry-point ───────────────────────────────────────────────────────


async def fetch_trends() -> list[TrendItem]:
    """
    Fetch trending topics from Google Trends PH and Brave News in parallel.
    Returns a score-sorted list of up to 30 TrendItems.
    Individual source failures are logged and silently skipped.
    """
    results = await asyncio.gather(
        _fetch_google_trends(),
        _fetch_brave_news(),
        return_exceptions=True,
    )

    combined: list[TrendItem] = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Trend source raised an unexpected exception: %s", result)
        else:
            combined.extend(result)

    combined.sort(key=lambda item: item.score, reverse=True)
    return combined[:_COMBINED_LIMIT]
