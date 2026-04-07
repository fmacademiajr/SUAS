"""
Voice Amplifier Agent
---------------------
Scans 10 tracked Filipino celebrities for accountability-related statements.
Runs as one of 3 parallel agents at the start of each pipeline run.

Search strategy:
  - 3 queries per celebrity → 30 total concurrent lookups
  - Google Custom Search API if available; falls back to Google News RSS
  - Results filtered to last 48 hours
  - Claude Haiku scores each headline 1–5 for accountability relevance
  - Only VoiceStatements with alignment_score >= 3.0 are returned
"""
from __future__ import annotations

import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote_plus

import anthropic
import httpx

from app.config import get_settings
from app.models.voice import Celebrity, VoiceStatement

logger = logging.getLogger("suas.pipeline.voice_agent")

# ─── Constants ───────────────────────────────────────────────────────────────

_NEWS_RSS_BASE = (
    "https://news.google.com/rss/search?q={query}&hl=en-PH&gl=PH&ceid=PH:en"
)
_HAIKU_BATCH_SIZE = 10
_CONCURRENCY_LIMIT = 10
_HOURS_WINDOW = 48
_MIN_SCORE = 3.0


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _is_within_window(pub_date_str: Optional[str]) -> bool:
    """Return True if the RFC-822 date string is within the last 48 hours."""
    if not pub_date_str:
        return False
    try:
        # pubDate format: "Mon, 06 Apr 2026 10:00:00 GMT"
        from email.utils import parsedate_to_datetime

        pub_dt = parsedate_to_datetime(pub_date_str)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_HOURS_WINDOW)
        return pub_dt >= cutoff
    except Exception:
        return False


def _parse_rss(xml_text: str) -> list[dict]:
    """Parse Google News RSS XML into a list of {title, url, pub_date} dicts."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text if title_el is not None else ""
            url = link_el.text if link_el is not None else ""
            pub_date = pub_date_el.text if pub_date_el is not None else None
            source = (
                source_el.text
                if source_el is not None
                else "Google News"
            )

            if title and url and _is_within_window(pub_date):
                items.append(
                    {"title": title, "url": url, "pub_date": pub_date, "source": source}
                )
    except ET.ParseError as exc:
        logger.warning("RSS parse error: %s", exc)
    return items


# ─── Single-query fetch ───────────────────────────────────────────────────────


async def _fetch_query(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    celebrity: Celebrity,
    query: str,
) -> list[dict]:
    """
    Fetch news results for a single query string.
    Returns a list of raw result dicts augmented with the celebrity reference.
    """
    settings = get_settings()
    results: list[dict] = []

    async with semaphore:
        try:
            # ── Google Custom Search API ──────────────────────────────────────
            gcs_api_key = getattr(settings, "google_cse_api_key", None)
            gcs_cx = getattr(settings, "google_cse_cx", None)

            if gcs_api_key and gcs_cx:
                params = {
                    "key": gcs_api_key,
                    "cx": gcs_cx,
                    "q": query,
                    "dateRestrict": "d2",  # last 2 days
                    "num": 10,
                }
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("items", []):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "source": item.get("displayLink", "Google CSE"),
                            "celebrity": celebrity,
                        }
                    )

            # ── Google News RSS fallback ──────────────────────────────────────
            else:
                rss_url = _NEWS_RSS_BASE.format(query=quote_plus(query))
                resp = await client.get(rss_url, timeout=10.0)
                resp.raise_for_status()
                parsed = _parse_rss(resp.text)
                for item in parsed:
                    item["celebrity"] = celebrity
                    results.append(item)

        except httpx.HTTPError as exc:
            logger.warning(
                "HTTP error fetching query '%s' for %s: %s",
                query,
                celebrity.name,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error fetching query '%s' for %s: %s",
                query,
                celebrity.name,
                exc,
            )

    return results


# ─── Haiku scoring ────────────────────────────────────────────────────────────


_HAIKU_SYSTEM = (
    "You are an editorial assistant for SUAS, a Filipino political accountability "
    "social media page. Your task is to score news headlines for accountability "
    "relevance on a scale of 1–5."
)

_HAIKU_SCORE_GUIDE = """
Scoring guide:
5 = Direct call from the celebrity for public servant accountability (e.g., naming corrupt officials, demanding resignations)
4 = Strong implied criticism of government, officials, or systemic failures
3 = General political observation or commentary with accountability undertones
2 = Tangentially related to politics or governance but no clear accountability angle
1 = Not relevant to accountability at all

Return ONLY a JSON array of numbers (one per headline, same order), e.g. [3, 5, 1, 2].
Do not include any other text.
"""


async def _score_batch_with_haiku(
    client: anthropic.AsyncAnthropic,
    batch: list[dict],
) -> list[float]:
    """
    Send up to _HAIKU_BATCH_SIZE headlines to Claude Haiku for scoring.
    Returns a list of float scores aligned 1-to-1 with the input batch.
    Falls back to 1.0 on any error.
    """
    settings = get_settings()
    headlines_block = "\n".join(
        f"{i + 1}. {item['title']}" for i, item in enumerate(batch)
    )
    prompt = (
        f"Score the following {len(batch)} headlines for accountability relevance "
        f"(1–5):\n\n{headlines_block}\n\n{_HAIKU_SCORE_GUIDE}"
    )

    try:
        message = await client.messages.create(
            model=settings.model_haiku,
            max_tokens=256,
            system=_HAIKU_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        scores = json.loads(raw)
        if isinstance(scores, list) and len(scores) == len(batch):
            return [float(s) for s in scores]
        logger.warning("Haiku returned unexpected score list length; using defaults.")
    except (json.JSONDecodeError, IndexError, anthropic.APIError) as exc:
        logger.warning("Haiku scoring error: %s", exc)

    return [1.0] * len(batch)


# ─── Main entry point ────────────────────────────────────────────────────────


async def scan_voices(celebrities: list[Celebrity]) -> list[VoiceStatement]:
    """
    Scan tracked celebrities for accountability-related statements.

    Steps:
      1. Build all (celebrity, query) pairs.
      2. Fetch all 30 queries concurrently (semaphore-limited to 10).
      3. Deduplicate raw results by URL.
      4. Score batches with Claude Haiku.
      5. Return VoiceStatements with alignment_score >= 3.0.
    """
    settings = get_settings()
    semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)

    # ── 1. Build fetch tasks ─────────────────────────────────────────────────
    async with httpx.AsyncClient(
        headers={"User-Agent": "SUAS/1.0 NewsScanner"},
        follow_redirects=True,
    ) as http_client:
        fetch_tasks = []
        for celebrity in celebrities:
            queries = celebrity.get_search_queries()
            # Use exactly the first 3 queries (one per alias template combo is
            # already handled by get_search_queries; we cap at 3 per celebrity).
            for query in queries[:3]:
                fetch_tasks.append(
                    _fetch_query(http_client, semaphore, celebrity, query)
                )

        # ── 2. Run all fetches concurrently ──────────────────────────────────
        nested_results = await asyncio.gather(*fetch_tasks, return_exceptions=False)

    # ── 3. Flatten and deduplicate by URL ────────────────────────────────────
    seen_urls: set[str] = set()
    raw_items: list[dict] = []
    for batch_result in nested_results:
        for item in batch_result:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                raw_items.append(item)

    if not raw_items:
        logger.info("Voice agent: no raw results found for any celebrity.")
        return []

    logger.info("Voice agent: %d unique headlines to score.", len(raw_items))

    # ── 4. Score with Haiku in batches of _HAIKU_BATCH_SIZE ──────────────────
    haiku_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    all_scores: list[float] = []

    for i in range(0, len(raw_items), _HAIKU_BATCH_SIZE):
        batch = raw_items[i : i + _HAIKU_BATCH_SIZE]
        scores = await _score_batch_with_haiku(haiku_client, batch)
        all_scores.extend(scores)

    # ── 5. Build VoiceStatements ──────────────────────────────────────────────
    statements: list[VoiceStatement] = []
    for item, score in zip(raw_items, all_scores):
        if score < _MIN_SCORE:
            continue
        celebrity: Celebrity = item["celebrity"]
        headline: str = item.get("title", "")
        url: str = item.get("url", "")
        source: str = item.get("source", "Unknown")

        statements.append(
            VoiceStatement(
                celebrity_name=celebrity.name,
                celebrity_id=celebrity.id,
                statement_summary=headline,
                source_url=url,
                source_outlet=source,
                alignment_score=score,
                accountability_flag=(score >= 4.0),
                raw_headline=headline,
            )
        )

    logger.info(
        "Voice agent: %d VoiceStatements passed threshold (>= %.1f).",
        len(statements),
        _MIN_SCORE,
    )
    return statements
