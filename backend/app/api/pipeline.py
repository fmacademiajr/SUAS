import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from google.cloud.firestore_v1.async_client import AsyncClient

from app.config import get_settings, Settings
from app.core.firestore import get_firestore_client
from app.core.auth_middleware import require_auth

logger = logging.getLogger("suas.api.pipeline")
router = APIRouter()

# Track in-memory pipeline run state (simple; single-worker Cloud Run)
_pipeline_state: dict = {"running": False, "last_run_id": None, "last_run_at": None, "last_error": None}


class TriggerRequest(BaseModel):
    slot: str = "manual"       # "morning" | "midday" | "evening" | "manual"
    dry_run: bool = False


@router.post("/trigger")
async def trigger_pipeline(
    body: TriggerRequest,
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
    _uid: str = Depends(require_auth),
):
    """Manually trigger a pipeline run. Runs in background."""
    if _pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    import asyncio
    from app.pipeline.runner import run_pipeline

    run_id = f"manual_{uuid.uuid4().hex[:8]}"
    _pipeline_state["running"] = True
    _pipeline_state["last_run_id"] = run_id
    _pipeline_state["last_error"] = None

    async def _run():
        try:
            result = await run_pipeline(
                run_id=run_id,
                run_slot=body.slot,
                settings=settings,
                db=db,
                dry_run=body.dry_run,
            )
            _pipeline_state["last_error"] = result.error
        except Exception as e:
            _pipeline_state["last_error"] = str(e)
            logger.exception("Manual pipeline run failed")
        finally:
            _pipeline_state["running"] = False
            from datetime import datetime, timezone
            _pipeline_state["last_run_at"] = datetime.now(timezone.utc).isoformat()

    asyncio.create_task(_run())
    return {"run_id": run_id, "status": "started", "dry_run": body.dry_run}


@router.get("/status")
async def get_pipeline_status(_uid: str = Depends(require_auth)):
    """Returns current pipeline state and next scheduled run times."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    # We can't easily get the scheduler from here without DI, so return basic state
    return {
        "running": _pipeline_state["running"],
        "last_run_id": _pipeline_state["last_run_id"],
        "last_run_at": _pipeline_state["last_run_at"],
        "last_error": _pipeline_state["last_error"],
    }
