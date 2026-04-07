import logging
from datetime import datetime, timezone, timedelta

from app.config import get_settings
from app.core.firestore import get_firestore_client, COLLECTIONS
from app.core.model_router import ModelRouter, TaskCategory
import anthropic

logger = logging.getLogger("suas.tasks.generate_reports")


async def generate_weekly_report() -> None:
    """
    Generates the weekly narrative report every Monday 6 AM PHT.
    Fetches the last 7 daily digests and calls Sonnet to summarize.
    Stores result in editorial_reports collection.
    """
    logger.info("Generating weekly narrative report")
    settings = get_settings()
    db = get_firestore_client()
    router = ModelRouter(settings)

    try:
        # Fetch last 7 digests
        docs = db.collection(COLLECTIONS["editorial_digests"]) \
            .order_by("date", direction="DESCENDING") \
            .limit(7) \
            .stream()

        digests = []
        async for doc in docs:
            digests.append(doc.to_dict())

        if not digests:
            logger.warning("No digests found for weekly report — skipping")
            return

        digest_text = "\n\n".join(
            f"[{d.get('date', 'unknown')}]\n"
            f"Themes: {d.get('themes', [])}\n"
            f"Sentiment: {d.get('public_sentiment', {})}\n"
            f"Stories: {d.get('stories_covered', [])}\n"
            f"Engagement: {d.get('engagement_from_previous_day', {})}"
            for d in reversed(digests)
        )

        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = now.strftime("%Y-%m-%d")

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=router.get_model(TaskCategory.REASONING),
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": (
                    f"You are the editorial analyst for SUAS, a Philippine political accountability page.\n\n"
                    f"Review these 7 daily digests ({week_start} to {week_end}) and write a weekly narrative report.\n\n"
                    f"{digest_text}\n\n"
                    f"Include: top 3 themes, sentiment trajectory, best/worst performing content, "
                    f"editorial blind spots, and recommended focus for next week. "
                    f"Be concise, analytical, and actionable."
                )
            }]
        )

        report_text = response.content[0].text
        report_id = f"weekly_{week_start}_{week_end}"

        await db.collection(COLLECTIONS["editorial_reports"]).document(report_id).set({
            "id": report_id,
            "type": "weekly",
            "period_start": week_start,
            "period_end": week_end,
            "generated_at": now.isoformat(),
            "report_text": report_text,
            "posts_published": len(digests),
        })
        logger.info("Weekly report saved: %s", report_id)

    except Exception:
        logger.exception("Weekly report generation failed")


async def generate_monthly_report() -> None:
    """
    Generates the monthly pattern report on the 1st of each month at 6 AM PHT.
    Fetches the last 4 weekly reports and calls Opus for deep analysis.
    """
    logger.info("Generating monthly pattern report")
    settings = get_settings()
    db = get_firestore_client()
    router = ModelRouter(settings)

    try:
        docs = db.collection(COLLECTIONS["editorial_reports"]) \
            .where("type", "==", "weekly") \
            .order_by("period_end", direction="DESCENDING") \
            .limit(4) \
            .stream()

        reports = []
        async for doc in docs:
            reports.append(doc.to_dict())

        if not reports:
            logger.warning("No weekly reports found for monthly report — skipping")
            return

        reports_text = "\n\n---\n\n".join(
            f"Week: {r.get('period_start')} to {r.get('period_end')}\n{r.get('report_text', '')}"
            for r in reversed(reports)
        )

        now = datetime.now(timezone.utc)
        month_label = now.strftime("%Y-%m")

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=router.get_model(TaskCategory.EDITORIAL),
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": (
                    f"You are the strategic analyst for SUAS, a Philippine political accountability page.\n\n"
                    f"Review these 4 weekly reports for {month_label} and write a monthly pattern report.\n\n"
                    f"{reports_text}\n\n"
                    f"Include: macro narrative shifts, emerging voices, long-term accountability gaps, "
                    f"content calendar recommendation, and comparative analysis vs last month's themes."
                )
            }]
        )

        report_text = response.content[0].text
        report_id = f"monthly_{month_label}"

        await db.collection(COLLECTIONS["editorial_reports"]).document(report_id).set({
            "id": report_id,
            "type": "monthly",
            "period_start": now.replace(day=1).strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "generated_at": now.isoformat(),
            "report_text": report_text,
        })
        logger.info("Monthly report saved: %s", report_id)

    except Exception:
        logger.exception("Monthly report generation failed")
