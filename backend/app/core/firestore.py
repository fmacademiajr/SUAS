import os
from functools import lru_cache

from google.cloud.firestore_v1.async_client import AsyncClient


# Collection name constants — use these everywhere instead of bare strings.
# Changing a collection name is a 1-line edit here.
COLLECTIONS = {
    "posts": "posts",
    "tracked_voices": "tracked_voices",
    "editorial_digests": "editorial_digests",
    "editorial_reports": "editorial_reports",
    "learning_log": "learning_log",
    "model_training": "model_training",
    "settings": "settings",
    "content_bank": "content_bank",
}


@lru_cache
def get_firestore_client() -> AsyncClient:
    """
    Return a cached async Firestore client.

    Always async — never use the sync Client. The sync client blocks the event
    loop, which is fatal when asyncio.gather() fires 30 concurrent voice lookups.

    Emulator detection: if FIRESTORE_EMULATOR_HOST is set in Settings (local dev),
    we set the env var before initializing so the client points to the emulator.
    In production (Cloud Run), the env var is empty and the real Firestore is used.

    Call get_firestore_client.cache_clear() in tests to inject a mock client.
    """
    from app.config import get_settings

    settings = get_settings()
    if settings.firestore_emulator_host:
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host

    return AsyncClient(project=settings.gcp_project_id)
