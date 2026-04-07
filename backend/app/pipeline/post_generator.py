"""
Post Generator
--------------
The editorial core of SUAS. Calls Claude Opus with the full 22K token
editorial memory (digests, voice guide, scored news, voice statements)
and generates a single Facebook post per pipeline run.

If Opus fails after retries, raises PostGenerationError so the pipeline
runner can fall back to the Content Bank.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

import anthropic
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.core.model_router import ModelRouter, TaskCategory
from app.pipeline.context_builder import ContextWindow

logger = logging.getLogger("suas.pipeline.post_generator")

# ─── Constants ────────────────────────────────────────────────────────────────

_MAX_RETRIES = 2
_MAX_ONE_LINER_WORDS = 10
_PHT = ZoneInfo("Asia/Manila")

_VALID_STRATEGIES = {"ride_the_wave", "fill_the_gap", "connect_the_dots"}
_VALID_URGENCY_TIERS = {"hot", "warm", "cool"}

_SLOT_STRATEGY_BIAS: dict[str, str] = {
    "morning": "ride_the_wave",
    "midday": "fill_the_gap",
    "evening": "connect_the_dots",
}

_SLOT_STRATEGY_HINT: dict[str, str] = {
    "morning": (
        "Strategy bias: Ride the wave. What broke overnight. "
        "What people will talk about on their commute."
    ),
    "midday": (
        "Strategy bias: Fill the gap. What everyone missed this morning. "
        "A fresh development."
    ),
    "evening": (
        "Strategy bias: Connect the dots. The deeper take. Link two stories. "
        "Give the audience something to think about over dinner."
    ),
}

_REQUIRED_FIELDS = {
    "one_liner",
    "body",
    "hashtags",
    "image_prompt",
    "editorial_strategy",
    "urgency_tier",
    "source_description",
}

_IMAGE_PROMPT_TEMPLATE = (
    "Dark blue tech-themed background with subtle data visualization elements "
    "(floating charts, connection nodes, grid lines). Center text overlay in "
    "bold white uppercase: '{one_liner}'. Style: clean, modern, slightly "
    "futuristic. Mood: serious, authoritative. Aspect ratio 1:1. No faces. "
    "No political symbols. No flags."
)


# ─── Exceptions ──────────────────────────────────────────────────────────────


class PostGenerationError(Exception):
    """Raised when Opus fails to generate a valid post after all retries."""


# ─── Output dataclass ────────────────────────────────────────────────────────


@dataclass
class GeneratedPost:
    one_liner: str              # <=10 words, the hero element
    body: str                   # the post body
    hashtags: list[str]         # 3-5 hashtags
    full_text: str              # one_liner + "\n\n" + body + "\n\n" + " ".join(hashtags)
    image_prompt: str           # prompt for Gemini image generation
    editorial_strategy: str     # "ride_the_wave" | "fill_the_gap" | "connect_the_dots"
    urgency_tier: str           # "hot" | "warm" | "cool"
    source_description: str     # which story was used (for Fernando's review card)
    legal_review_required: bool # True if a politician is named directly


# ─── Prompt builders ─────────────────────────────────────────────────────────


def _build_system_message(context: ContextWindow) -> str:
    """Build the system message for the Opus editorial call."""
    return f"""You are the editorial engine for SUAS (Shut Up and Serve), a Philippine political \
accountability page on Facebook.

{context.voice_guide_block}

Your task on every run:
1. Read the editorial history and today's news carefully.
2. Answer these 7 questions before selecting a story:
   - What is the dominant narrative right now?
   - Is it escalating, plateauing, or fading?
   - What has this page already covered in the last 7 days?
   - What angle has NOT been used recently?
   - Is there a connection between today's stories and a longer pattern?
   - What would surprise the audience in a good way?
   - What would a lazy page post today? (Do something different.)
3. Select ONE story. Write ONE post.
4. Assign the appropriate editorial strategy for this time slot.
5. Generate an image prompt that puts the one-liner on a dark branded background.

LEGAL RULE: Never name a specific politician in the one-liner or catchline. \
Body text may reference public officials only when citing verifiable news reports. \
Attack the action, the failure, the system — never the person.
If your post names a specific politician, set legal_review_required to true.

OUTPUT FORMAT: Respond with ONLY valid JSON. No markdown. No explanation before or after."""


def _build_user_message(context: ContextWindow, run_slot: str) -> str:
    """Build the user message assembling the full context window."""
    slot_hint = _SLOT_STRATEGY_HINT.get(run_slot, _SLOT_STRATEGY_HINT["morning"])
    today_pht = datetime.now(_PHT).strftime("%A, %B %d, %Y")

    return f"""=== EDITORIAL MEMORY (last {context.digest_count} days) ===
{context.digest_block}

{context.voice_statements_block}

{context.news_block}

=== YOUR TASK ===
Time slot: {run_slot} ({slot_hint})
Today's date: {today_pht}

Generate ONE Facebook post. Respond with ONLY this JSON structure:

{{
  "one_liner": "...",           // <=10 words, use one of the 5 voice patterns
  "body": "...",                // 3-5 sentences, confrontational but fact-based
  "hashtags": ["...", "..."],   // 3-5 hashtags from the pool
  "image_prompt": "...",        // dark blue background, bold white uppercase one-liner
  "editorial_strategy": "...",  // ride_the_wave | fill_the_gap | connect_the_dots
  "urgency_tier": "...",        // hot | warm | cool
  "source_description": "...", // 1 sentence: which story you used and why
  "legal_review_required": false
}}"""


# ─── Response parsing ────────────────────────────────────────────────────────


def _extract_json(raw: str) -> dict:
    """
    Extract a JSON object from Claude's response.

    Tries direct parsing first, then strips markdown code fences if present.
    Raises ValueError if no valid JSON object can be found.
    """
    text = raw.strip()

    # Attempt 1: direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Attempt 3: find the first { ... } block (greedy from first { to last })
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            parsed = json.loads(text[first_brace : last_brace + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from response: {text[:200]}...")


def _validate_parsed(data: dict, run_slot: str) -> dict:
    """
    Validate and normalize parsed JSON fields.
    Returns a cleaned dict ready for GeneratedPost construction.
    Raises ValueError if required fields are missing entirely.
    """
    missing = _REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields in Opus response: {missing}")

    # Validate hashtags is a list
    hashtags = data.get("hashtags", [])
    if not isinstance(hashtags, list):
        hashtags = [str(hashtags)]
    hashtags = [str(h) for h in hashtags]

    # Validate editorial_strategy
    strategy = str(data.get("editorial_strategy", "")).strip().lower()
    if strategy not in _VALID_STRATEGIES:
        logger.warning(
            "Invalid editorial_strategy '%s' from Opus; defaulting to slot bias '%s'.",
            strategy,
            _SLOT_STRATEGY_BIAS.get(run_slot, "ride_the_wave"),
        )
        strategy = _SLOT_STRATEGY_BIAS.get(run_slot, "ride_the_wave")

    # Validate urgency_tier
    urgency = str(data.get("urgency_tier", "")).strip().lower()
    if urgency not in _VALID_URGENCY_TIERS:
        logger.warning(
            "Invalid urgency_tier '%s' from Opus; defaulting to 'warm'.",
            urgency,
        )
        urgency = "warm"

    # Legal review flag
    legal_review = bool(data.get("legal_review_required", False))

    return {
        "one_liner": str(data["one_liner"]).strip(),
        "body": str(data["body"]).strip(),
        "hashtags": hashtags,
        "image_prompt": str(data.get("image_prompt", "")).strip(),
        "editorial_strategy": strategy,
        "urgency_tier": urgency,
        "source_description": str(data.get("source_description", "")).strip(),
        "legal_review_required": legal_review,
    }


# ─── One-liner shortening via Haiku ─────────────────────────────────────────


async def _shorten_one_liner(one_liner: str) -> str:
    """
    If the one-liner exceeds 10 words, call Haiku to shorten it.
    Returns the original if it's already within limits or if the
    Haiku call fails.
    """
    word_count = len(one_liner.split())
    if word_count <= _MAX_ONE_LINER_WORDS:
        return one_liner

    logger.info(
        "One-liner has %d words (limit %d); calling Haiku to shorten.",
        word_count,
        _MAX_ONE_LINER_WORDS,
    )

    settings = get_settings()
    router = ModelRouter(settings)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        response = await client.messages.create(
            model=router.get_model(TaskCategory.MECHANICAL),
            max_tokens=64,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'Shorten this to ≤10 words while keeping the punch: "{one_liner}"\n'
                        "Respond with ONLY the shortened one-liner. No quotes. No explanation."
                    ),
                }
            ],
        )
        shortened = response.content[0].text.strip().strip('"').strip("'")

        # Verify Haiku actually shortened it
        if len(shortened.split()) <= _MAX_ONE_LINER_WORDS and shortened:
            logger.info("Haiku shortened one-liner to %d words.", len(shortened.split()))
            return shortened

        logger.warning(
            "Haiku returned %d words; keeping original one-liner.",
            len(shortened.split()),
        )
        return one_liner

    except anthropic.APIError as exc:
        logger.warning("Haiku shortening call failed: %s; keeping original.", exc)
        return one_liner


# ─── Main entry point ────────────────────────────────────────────────────────


async def generate_post(
    context: ContextWindow,
    run_slot: str,
) -> GeneratedPost:
    """
    Generate a single Facebook post using Claude Opus with the full editorial
    memory context.

    Args:
        context:  The assembled 22K token context window from the context builder.
        run_slot: One of "morning", "midday", "evening".

    Returns:
        A GeneratedPost dataclass ready for image generation and review.

    Raises:
        PostGenerationError: If Opus fails to produce a valid post after retries.
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    router = ModelRouter(settings)

    system_message = _build_system_message(context)
    user_message = _build_user_message(context, run_slot)

    logger.debug("Opus system prompt:\n%s", system_message)
    logger.debug("Opus user prompt:\n%s", user_message)

    last_error: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.info(
            "Opus generation attempt %d/%d for slot=%s.",
            attempt,
            _MAX_RETRIES,
            run_slot,
        )

        try:
            # ── Call Claude Opus ──────────────────────────────────────────────
            response = await client.messages.create(
                model=router.get_model(TaskCategory.EDITORIAL),
                max_tokens=1024,
                system=system_message,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text

            logger.debug("Opus raw response:\n%s", raw_text)

            # ── Parse JSON ────────────────────────────────────────────────────
            parsed = _extract_json(raw_text)
            validated = _validate_parsed(parsed, run_slot)

            # ── Shorten one-liner if needed ───────────────────────────────────
            validated["one_liner"] = await _shorten_one_liner(validated["one_liner"])

            # ── Rebuild image prompt with the final one-liner ─────────────────
            if not validated["image_prompt"]:
                validated["image_prompt"] = _IMAGE_PROMPT_TEMPLATE.format(
                    one_liner=validated["one_liner"]
                )

            # ── Assemble full_text ────────────────────────────────────────────
            hashtag_str = " ".join(validated["hashtags"])
            full_text = (
                validated["one_liner"]
                + "\n\n"
                + validated["body"]
                + "\n\n"
                + hashtag_str
            )

            post = GeneratedPost(
                one_liner=validated["one_liner"],
                body=validated["body"],
                hashtags=validated["hashtags"],
                full_text=full_text,
                image_prompt=validated["image_prompt"],
                editorial_strategy=validated["editorial_strategy"],
                urgency_tier=validated["urgency_tier"],
                source_description=validated["source_description"],
                legal_review_required=validated["legal_review_required"],
            )

            logger.info(
                "Post generated: slot=%s, strategy=%s, urgency=%s, legal_review=%s, "
                "one_liner_words=%d, hashtags=%d.",
                run_slot,
                post.editorial_strategy,
                post.urgency_tier,
                post.legal_review_required,
                len(post.one_liner.split()),
                len(post.hashtags),
            )

            return post

        except anthropic.APIError as exc:
            last_error = exc
            logger.warning(
                "Opus API error on attempt %d/%d: %s",
                attempt,
                _MAX_RETRIES,
                exc,
            )

        except (ValueError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            logger.warning(
                "Parsing/validation error on attempt %d/%d: %s",
                attempt,
                _MAX_RETRIES,
                exc,
            )

    # All retries exhausted
    error_msg = f"Post generation failed after {_MAX_RETRIES} attempts. Last error: {last_error}"
    logger.error(error_msg)
    raise PostGenerationError(error_msg)
