import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from google.cloud.firestore_v1.async_client import AsyncClient
from pydantic import BaseModel, Field, field_validator

from app.core.auth_middleware import require_auth
from app.core.firestore import COLLECTIONS, get_firestore_client
from app.models.voice import Celebrity

logger = logging.getLogger("suas.api.celebrities")
router = APIRouter(prefix="/celebrities", dependencies=[Depends(require_auth)])


class CreateCelebrityRequest(BaseModel):
    name: str
    search_aliases: list[str]
    platforms: list[str]
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("search_aliases")
    @classmethod
    def aliases_must_have_one_entry(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("search_aliases must have at least 1 entry")
        return v


class PatchCelebrityRequest(BaseModel):
    name: Optional[str] = None
    search_aliases: Optional[list[str]] = None
    platforms: Optional[list[str]] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


@router.get("")
async def list_celebrities(
    db: AsyncClient = Depends(get_firestore_client),
) -> list[dict]:
    """Return all tracked celebrities ordered by name ascending."""
    try:
        query = (
            db.collection(COLLECTIONS["tracked_voices"])
            .order_by("name")
        )
        results: list[dict] = []
        async for doc in query.stream():
            results.append(doc.to_dict())
        return results
    except Exception as exc:
        logger.error("Failed to fetch celebrities: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch celebrities")


@router.post("", status_code=201)
async def create_celebrity(
    body: CreateCelebrityRequest,
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Add a new celebrity to tracked voices."""
    celebrity = Celebrity(
        id=str(uuid.uuid4()),
        name=body.name,
        search_aliases=body.search_aliases,
        platforms=body.platforms,
        active=True,
    )
    data = celebrity.to_firestore()
    # Persist any extra fields not on the model (e.g. notes from the request)
    if body.notes is not None:
        data["notes"] = body.notes

    await db.collection(COLLECTIONS["tracked_voices"]).document(celebrity.id).set(data)
    return data


@router.patch("/{celebrity_id}")
async def update_celebrity(
    celebrity_id: str,
    body: PatchCelebrityRequest,
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Partially update a celebrity document."""
    ref = db.collection(COLLECTIONS["tracked_voices"]).document(celebrity_id)
    doc = await ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Celebrity not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return doc.to_dict()

    await ref.update(updates)
    updated = await ref.get()
    return updated.to_dict()


@router.delete("/{celebrity_id}")
async def delete_celebrity(
    celebrity_id: str,
    db: AsyncClient = Depends(get_firestore_client),
) -> dict:
    """Remove a celebrity from tracked voices."""
    ref = db.collection(COLLECTIONS["tracked_voices"]).document(celebrity_id)
    doc = await ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Celebrity not found")

    await ref.delete()
    return {"deleted": True}
