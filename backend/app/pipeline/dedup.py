"""
Deduplication module for news articles from multiple RSS sources.

This module removes duplicate articles based on:
1. Exact URL matches (after normalization)
2. Near-duplicate titles (simhash distance <= 5 bits)
"""

import logging
from simhash import Simhash
from app.pipeline.agents.news_agent import RawArticle

logger = logging.getLogger("suas.pipeline.dedup")


def normalize_url(url: str) -> str:
    """
    Normalize a URL for comparison.

    Args:
        url: The URL to normalize.

    Returns:
        Normalized URL with:
        - Query parameters removed (everything after '?')
        - Trailing slashes removed
        - Scheme and host lowercased
    """
    # Remove query parameters
    base_url = url.split("?")[0]

    # Remove trailing slashes
    base_url = base_url.rstrip("/")

    # Parse and lowercase the scheme and host
    # Find the scheme separator
    if "://" in base_url:
        scheme, rest = base_url.split("://", 1)
        scheme = scheme.lower()

        # Find where the host ends (at the next '/' or end of string)
        if "/" in rest:
            host, path = rest.split("/", 1)
            host = host.lower()
            normalized = f"{scheme}://{host}/{path}"
        else:
            host = rest.lower()
            normalized = f"{scheme}://{host}"
    else:
        # No scheme, just lowercase what we have
        normalized = base_url.lower()

    return normalized


def title_simhash(title: str) -> Simhash:
    """
    Compute simhash of a title using word trigrams.

    Args:
        title: The title to hash.

    Returns:
        Simhash object computed from word trigrams (3-word sliding windows).
    """
    # Tokenize into words
    words = title.lower().split()

    # Generate trigrams (3-word sliding windows)
    trigrams = []
    for i in range(len(words) - 2):
        trigram = " ".join(words[i : i + 3])
        trigrams.append(trigram)

    # If there are fewer than 3 words, just use the words themselves
    if not trigrams:
        trigrams = words if words else [title.lower()]

    # Create and return simhash from trigrams
    return Simhash(" ".join(trigrams))


def dedup_articles(articles: list[RawArticle]) -> list[RawArticle]:
    """
    Deduplicate articles by removing exact URL duplicates and near-duplicate titles.

    Deduplication happens in two passes:
    1. Exact URL duplicates: Keep first seen article with a given URL
    2. Near-duplicate titles: Keep first seen article with a given title simhash
       (distance threshold: 5 bits)

    Args:
        articles: List of articles to deduplicate.

    Returns:
        Deduplicated list of articles, preserving original order.
    """
    if not articles:
        return []

    # First pass: remove exact URL duplicates
    seen_urls = set()
    url_deduped = []
    url_duplicates_removed = 0

    for article in articles:
        normalized = normalize_url(article.url)
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            url_deduped.append(article)
        else:
            url_duplicates_removed += 1

    # Second pass: remove near-duplicate titles using simhash
    kept_hashes = []
    title_deduped = []
    title_duplicates_removed = 0

    for article in url_deduped:
        article_hash = title_simhash(article.title)

        # Check if this simhash is similar to any kept hash
        is_duplicate = False
        for kept_hash in kept_hashes:
            if article_hash.distance(kept_hash) <= 5:
                is_duplicate = True
                break

        if not is_duplicate:
            kept_hashes.append(article_hash)
            title_deduped.append(article)
        else:
            title_duplicates_removed += 1

    # Log deduplication results
    total_removed = url_duplicates_removed + title_duplicates_removed
    logger.debug(
        f"Deduplication complete: removed {url_duplicates_removed} URL duplicates, "
        f"{title_duplicates_removed} title duplicates (total: {total_removed} from {len(articles)} articles)"
    )

    return title_deduped
