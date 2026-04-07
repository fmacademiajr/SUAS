"""
Image Generator
---------------
Generates a branded 1080×1080 PNG for each Facebook post.

Primary path:  Gemini Imagen 3 API (google.generativeai).
Fallback path: Playwright HTML/CSS template renderer.

If both paths fail, raises ImageGenerationError so the pipeline runner
can mark the post as needing a manual image upload.
"""
from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime

import google.generativeai as genai
from google.cloud import storage
from zoneinfo import ZoneInfo

from app.config import get_settings

logger = logging.getLogger("suas.pipeline.image_generator")

# ─── Constants ────────────────────────────────────────────────────────────────

_MIN_IMAGE_BYTES = 10 * 1024   # 10 KB — anything smaller is an error placeholder
_PHT = ZoneInfo("Asia/Manila")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1080px; height: 1080px; overflow: hidden;
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1b2a 50%, #0a1628 100%);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    font-family: 'Arial Black', 'Arial Bold', Arial, sans-serif;
  }}
  .grid {{
    position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    background-image:
      linear-gradient(rgba(0,120,255,0.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,120,255,0.05) 1px, transparent 1px);
    background-size: 60px 60px;
  }}
  .content {{
    position: relative; z-index: 2;
    text-align: center; padding: 80px;
  }}
  .one-liner {{
    color: #ffffff;
    font-size: {font_size}px;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    line-height: 1.15;
    text-shadow: 0 0 40px rgba(0,120,255,0.4);
  }}
  .brand {{
    position: absolute; bottom: 48px; width: 100%;
    text-align: center;
    color: rgba(255,255,255,0.35);
    font-size: 22px;
    letter-spacing: 0.3em;
    font-weight: 700;
    z-index: 2;
  }}
</style>
</head>
<body>
  <div class="grid"></div>
  <div class="content">
    <div class="one-liner">{one_liner_escaped}</div>
  </div>
  <div class="brand">SHUT UP AND SERVE</div>
</body>
</html>
"""


# ─── Exceptions ───────────────────────────────────────────────────────────────


class ImageGenerationError(Exception):
    """Raised when both Gemini and Playwright fail to produce an image."""


# ─── Output dataclass ─────────────────────────────────────────────────────────


@dataclass
class ImageResult:
    gcs_path: str           # "images/2026/04/post_id.png"
    public_url: str         # GCS public URL or signed URL
    generation_method: str  # "gemini" | "playwright"
    generated_at: datetime


# ─── Font size helper ─────────────────────────────────────────────────────────


def _font_size_for(one_liner: str) -> int:
    """Return the appropriate font size in px based on word count."""
    word_count = len(one_liner.split())
    if word_count <= 4:
        return 120
    if word_count <= 6:
        return 96
    if word_count <= 8:
        return 80
    return 68  # 9–10 words


# ─── GCS upload helper ────────────────────────────────────────────────────────


async def _upload_to_gcs(png_bytes: bytes, post_id: str) -> tuple[str, str]:
    """
    Upload PNG bytes to GCS and make the blob publicly readable.

    Returns:
        (gcs_path, public_url) — e.g. ("images/2026/04/post_id.png", "https://...")
    """
    settings = get_settings()
    now = datetime.now(_PHT)
    gcs_path = f"images/{now.year}/{now.month:02d}/{post_id}.png"

    def _sync_upload() -> str:
        client = storage.Client(project=settings.gcp_project_id)
        bucket = client.bucket(settings.gcs_bucket_name)
        blob = bucket.blob(gcs_path)
        blob.content_type = "image/png"
        blob.cache_control = "public, max-age=31536000"
        blob.upload_from_string(png_bytes, content_type="image/png")
        blob.make_public()
        return blob.public_url

    public_url = await asyncio.to_thread(_sync_upload)
    return gcs_path, public_url


# ─── Gemini Imagen path ───────────────────────────────────────────────────────


async def _generate_via_gemini(image_prompt: str) -> bytes:
    """
    Call Gemini Imagen 3 and return raw PNG bytes.

    Raises:
        Exception: propagated as-is so the caller can trigger fallback.
    """
    settings = get_settings()

    def _sync_call() -> bytes:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.ImageGenerationModel("imagen-3.0-generate-002")
        response = model.generate_images(
            prompt=image_prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_only_high",
        )
        if not response.images:
            raise ValueError("Gemini returned an empty images list.")
        return response.images[0]._image_bytes  # noqa: SLF001

    return await asyncio.to_thread(_sync_call)


# ─── Playwright fallback path ─────────────────────────────────────────────────


async def _generate_via_playwright(one_liner: str) -> bytes:
    """
    Render a branded 1080×1080 HTML template and return raw PNG bytes.

    Raises:
        Exception: propagated as-is so the caller can raise ImageGenerationError.
    """
    from playwright.async_api import async_playwright  # local import — optional dep

    font_size = _font_size_for(one_liner)
    one_liner_escaped = html.escape(one_liner.upper())
    rendered_html = HTML_TEMPLATE.format(
        font_size=font_size,
        one_liner_escaped=one_liner_escaped,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1080})
        await page.set_content(rendered_html)
        png_bytes = await page.screenshot(type="png")
        await browser.close()

    return png_bytes


# ─── Main entry point ─────────────────────────────────────────────────────────


async def generate_image(
    image_prompt: str,
    post_id: str,
    one_liner: str,
) -> ImageResult:
    """
    Generate a branded 1080×1080 PNG and upload it to GCS.

    Tries Gemini Imagen first; falls back to Playwright if Gemini raises,
    returns an empty list, or returns suspiciously small bytes (<10 KB).

    Args:
        image_prompt: The detailed image prompt written by the post generator.
        post_id:      Unique identifier for the post (used as the GCS filename).
        one_liner:    The hero text overlaid on the image (used in the
                      Playwright fallback and for font-size selection).

    Returns:
        An ImageResult with GCS path, public URL, generation method, and
        the timestamp of generation.

    Raises:
        ImageGenerationError: If both Gemini and Playwright fail.
    """
    png_bytes: bytes | None = None
    method: str | None = None
    gemini_error: Exception | None = None

    # ── Step 1: Gemini Imagen ────────────────────────────────────────────────
    try:
        raw = await _generate_via_gemini(image_prompt)

        if len(raw) < _MIN_IMAGE_BYTES:
            raise ValueError(
                f"Gemini returned only {len(raw)} bytes — likely an error placeholder."
            )

        png_bytes = raw
        method = "gemini"
        logger.info(
            "Gemini image generated for post_id=%s (%.1f KB).",
            post_id,
            len(png_bytes) / 1024,
        )

    except Exception as exc:  # noqa: BLE001
        gemini_error = exc
        logger.warning(
            "Gemini image generation failed for post_id=%s: %s — falling back to Playwright.",
            post_id,
            exc,
        )

    # ── Step 2: Playwright fallback ──────────────────────────────────────────
    if png_bytes is None:
        try:
            png_bytes = await _generate_via_playwright(one_liner)
            method = "playwright"
            logger.info(
                "Playwright image generated for post_id=%s (%.1f KB).",
                post_id,
                len(png_bytes) / 1024,
            )

        except Exception as exc:  # noqa: BLE001
            raise ImageGenerationError(
                f"Both Gemini and Playwright failed for post_id={post_id!r}. "
                f"Gemini error: {gemini_error!r}. Playwright error: {exc!r}."
            ) from exc

    # ── Upload to GCS ────────────────────────────────────────────────────────
    gcs_path, public_url = await _upload_to_gcs(png_bytes, post_id)

    logger.info(
        "Image uploaded to GCS: method=%s, path=%s, size=%.1f KB.",
        method,
        gcs_path,
        len(png_bytes) / 1024,
    )

    return ImageResult(
        gcs_path=gcs_path,
        public_url=public_url,
        generation_method=method,  # type: ignore[arg-type]
        generated_at=datetime.now(_PHT),
    )
