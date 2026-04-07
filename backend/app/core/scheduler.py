import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger("suas.core.scheduler")

def create_scheduler() -> AsyncIOScheduler:
    """
    Create and configure the APScheduler instance.
    The scheduler is started in FastAPI's lifespan context manager, not here.
    All times are in Asia/Manila (PHT, UTC+8).
    """
    manila = pytz.timezone("Asia/Manila")
    scheduler = AsyncIOScheduler(timezone=manila)

    # ── Daily pipeline runs ──────────────────────────────────────────────────
    # Morning run: 5:30 AM PHT → post scheduled for 7:30 AM
    scheduler.add_job(
        "app.tasks.run_pipeline:run_morning_pipeline",
        CronTrigger(hour=5, minute=30, timezone=manila),
        id="morning_pipeline",
        name="Morning Pipeline Run",
        replace_existing=True,
        misfire_grace_time=300,   # 5 min grace — if server was briefly down
    )
    # Midday run: 11:00 AM PHT → post scheduled for 12:30 PM
    scheduler.add_job(
        "app.tasks.run_pipeline:run_midday_pipeline",
        CronTrigger(hour=11, minute=0, timezone=manila),
        id="midday_pipeline",
        name="Midday Pipeline Run",
        replace_existing=True,
        misfire_grace_time=300,
    )
    # Evening run: 6:00 PM PHT → post scheduled for 8:00 PM
    scheduler.add_job(
        "app.tasks.run_pipeline:run_evening_pipeline",
        CronTrigger(hour=18, minute=0, timezone=manila),
        id="evening_pipeline",
        name="Evening Pipeline Run",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── Breaking news scanner: 6x/day ────────────────────────────────────────
    for scan_hour in [8, 10, 12, 14, 16, 18]:
        scheduler.add_job(
            "app.tasks.run_pipeline:run_breaking_scan_task",
            CronTrigger(hour=scan_hour, minute=0, timezone=manila),
            id=f"breaking_scan_{scan_hour:02d}00",
            name=f"Breaking News Scan {scan_hour:02d}:00",
            replace_existing=True,
            misfire_grace_time=120,
        )

    # ── Metrics sync: every 6 hours ──────────────────────────────────────────
    scheduler.add_job(
        "app.tasks.sync_metrics:sync_published_post_metrics",
        CronTrigger(hour="*/6", timezone=manila),
        id="metrics_sync",
        name="Facebook Metrics Sync",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # ── Scheduled publishing check: every 5 minutes ──────────────────────────
    scheduler.add_job(
        "app.tasks.run_pipeline:check_scheduled_publishes",
        CronTrigger(minute="*/5", timezone=manila),
        id="publish_check",
        name="Scheduled Publish Check",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── Weekly report: Monday 6:00 AM PHT ────────────────────────────────────
    scheduler.add_job(
        "app.tasks.generate_reports:generate_weekly_report",
        CronTrigger(day_of_week="mon", hour=6, minute=0, timezone=manila),
        id="weekly_report",
        name="Weekly Narrative Report",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Monthly report: 1st of month, 6:00 AM PHT ────────────────────────────
    scheduler.add_job(
        "app.tasks.generate_reports:generate_monthly_report",
        CronTrigger(day=1, hour=6, minute=0, timezone=manila),
        id="monthly_report",
        name="Monthly Pattern Report",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
    return scheduler
