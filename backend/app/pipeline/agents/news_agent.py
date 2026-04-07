"""
news_agent.py — Philippine political news aggregator.

Fetches headlines from 5 RSS sources concurrently, normalises them into
RawArticle instances, deduplicates by URL, and returns up to 50 articles
from the last 24 hours sorted most-recent-first.

Called as one of three parallel data-source agents at the start of each
SUAS pipeline run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("suas.pipeline.news_agent")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RSS_SOURCES: list[dict[str, str]] = [
    {"name": "Inquirer", "url": "https://newsinfo.inquirer.net/feed"},
    {"name": "Rappler", "url": "https://www.rappler.com/feed/"},
    {"name": "PhilStar", "url": "https://www.philstar.com/rss/headlines"},
    {"name": "Manila Bulletin", "url": "https://mb.com.ph/feed/"},
    {"name": "ABS-CBN", "url": "https://news.abs-cbn.com/rss/news"},
]

# Maximum articles returned by fetch_news()
_MAX_ARTICLES = 50

# Look-back window for article recency filtering
_LOOKBACK_HOURS = 24

# Per-source HTTP timeout (seconds)
_HTTP_TIMEOUT = 10.0

# User-agent sent with every request so outlets don't reject the bot outright
_USER_AGENT = (
    "Mozilla/5.0 (compatible; SUAS-NewsAgent/1.0; "
    "+https://github.com/fmacademiajr/SUAS; Philippine political tracker)"
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RawArticle:
    """Normalised representation of a single RSS entry."""

    title: str
    url: str
    summary: str         # from RSS <description> / <summary> field
    published_at: datetime
    source: str          # outlet name, e.g. "Inquirer"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_published(entry: feedparser.FeedParserDict) -> datetime | None:
    """
    Convert feedparser's ``published_parsed`` (a ``time.struct_time`` in UTC)
    to a timezone-aware :class:`datetime`.

    Returns ``None`` when the field is absent or unparseable so the caller can
    decide whether to skip the entry.
    """
    struct = getattr(entry, "published_parsed", None)
    if struct is None:
        # Some feeds use ``updated_parsed`` as a fallback
        struct = getattr(entry, "updated_parsed", None)
    if struct is None:
        return None
    try:
        return datetime(*struct[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _extract_summary(entry: feedparser.FeedParserDict) -> str:
    """Return the best available plain-text summary for an entry."""
    # Prefer the explicit summary field; fall back to content[0].value
    raw: str = getattr(entry, "summary", "") or ""
    if not raw:
        content = getattr(entry, "content", [])
        if content:
            raw = content[0].get("value", "") or ""
    # Strip leading/trailing whitespace; callers handle further sanitisation
    return raw.strip()


async def _fetch_source(
    client: httpx.AsyncClient,
    source: dict[str, str],
    cutoff: datetime,
) -> list[RawArticle]:
    """
    Fetch and parse a single RSS source.

    Parameters
    ----------
    client:
        Shared :class:`httpx.AsyncClient` instance.
    source:
        Dict with ``"name"`` and ``"url"`` keys from ``RSS_SOURCES``.
    cutoff:
        Only articles published at or after this UTC datetime are kept.

    Returns
    -------
    list[RawArticle]
        Articles from this source that fall within the look-back window.
        An empty list is returned (never raises) so that ``asyncio.gather``
        callers can treat every outcome uniformly.
    """
    name: str = source["name"]
    url: str = source["url"]

    logger.debug("Fetching RSS from %s (%s)", name, url)

    response = await client.get(url)
    response.raise_for_status()

    # feedparser.parse() is CPU-bound and synchronous — run in a thread so we
    # don't block the event loop while it processes the XML.
    raw_bytes = response.content
    feed: feedparser.FeedParserDict = await asyncio.to_thread(
        feedparser.parse, raw_bytes
    )

    articles: list[RawArticle] = []
    for entry in feed.entries:
        published_at = _parse_published(entry)

        # Skip entries with no parseable date — we can't determine recency
        if published_at is None:
            logger.debug("%s: skipping entry with no date — %s", name, getattr(entry, "title", "<no title>"))
            continue

        # Recency filter
        if published_at < cutoff:
            continue

        link: str = getattr(entry, "link", "") or ""
        if not link:
            logger.debug("%s: skipping entry with no URL — %s", name, getattr(entry, "title", "<no title>"))
            continue

        articles.append(
            RawArticle(
                title=(getattr(entry, "title", "") or "").strip(),
                url=link.strip(),
                summary=_extract_summary(entry),
                published_at=published_at,
                source=name,
            )
        )

    logger.info("%s: %d article(s) in window", name, len(articles))
    return articles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_news() -> list[RawArticle]:
    """
    Fetch headlines from all Philippine RSS sources concurrently.

    Behaviour
    ---------
    - All 5 sources are fetched in parallel; a failure in one never aborts
      the others.
    - Only articles published within the last 24 hours (UTC) are included.
    - Articles are deduplicated by exact URL.
    - Results are sorted most-recent-first.
    - At most 50 articles are returned.

    Returns
    -------
    list[RawArticle]
        Deduplicated, sorted list of recent articles.
    """
    cutoff: datetime = datetime.now(tz=timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)

    headers = {"User-Agent": _USER_AGENT}
    timeout = httpx.Timeout(_HTTP_TIMEOUT)

    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        tasks = [
            _fetch_source(client, source, cutoff)
            for source in RSS_SOURCES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results; log and skip any source that raised an exception
    articles: list[RawArticle] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(
                "Source %s failed: %s: %s",
                RSS_SOURCES[i]["name"],
                type(result).__name__,
                result,
            )
            continue
        articles.extend(result)

    # Deduplicate by URL (preserve first occurrence in traversal order)
    seen_urls: set[str] = set()
    unique_articles: list[RawArticle] = []
    for article in articles:
        if article.url not in seen_urls:
            seen_urls.add(article.url)
            unique_articles.append(article)

    logger.info(
        "fetch_news: %d unique article(s) across %d source(s) before cap",
        len(unique_articles),
        len(RSS_SOURCES),
    )

    # Sort most-recent-first, then apply the hard cap
    unique_articles.sort(key=lambda a: a.published_at, reverse=True)
    return unique_articles[:_MAX_ARTICLES]
