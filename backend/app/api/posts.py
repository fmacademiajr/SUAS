import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.firestore import get_firestore_client
from app.core.auth_middleware import require_auth
from app.services.post_service import (
    get_post, list_posts, approve_post, reject_post, update_post_content,
    PostNotFoundError, InvalidStateTransitionError,
)

logger = logging.getLogger("suas.api.posts")
router = APIRouter()


class PostUpdateRequest(BaseModel):
    one_liner: Optional[str] = None
    body: Optional[str] = None
    hashtags: Optional[list[str]] = None
    image_prompt: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str


@router.get("")
async def list_posts_endpoint(
    status: Optional[str] = Query(None),
    limit: int = Query(default=50, le=100),
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
):
    return await list_posts(db, status=status, limit=limit)


@router.get("/{post_id}")
async def get_post_endpoint(
    post_id: str,
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
):
    try:
        return await get_post(db, post_id)
    except PostNotFoundError:
        raise HTTPException(status_code=404, detail="Post not found")


@router.patch("/{post_id}")
async def update_post_endpoint(
    post_id: str,
    body: PostUpdateRequest,
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
):
    try:
        return await update_post_content(db, post_id, body.model_dump(exclude_none=True))
    except PostNotFoundError:
        raise HTTPException(status_code=404, detail="Post not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{post_id}/approve")
async def approve_post_endpoint(
    post_id: str,
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
):
    try:
        return await approve_post(db, post_id)
    except PostNotFoundError:
        raise HTTPException(status_code=404, detail="Post not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{post_id}/reject")
async def reject_post_endpoint(
    post_id: str,
    body: RejectRequest,
    db: AsyncClient = Depends(get_firestore_client),
    _uid: str = Depends(require_auth),
):
    try:
        return await reject_post(db, post_id, body.reason)
    except PostNotFoundError:
        raise HTTPException(status_code=404, detail="Post not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
