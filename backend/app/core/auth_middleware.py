import logging
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from fastapi import Header, HTTPException, Depends
from app.config import get_settings, Settings

logger = logging.getLogger("suas.core.auth")

# Initialize Firebase Admin SDK (idempotent — only runs once per process)
def _init_firebase() -> None:
    if not firebase_admin._apps:
        # In production: uses Application Default Credentials (Cloud Run service account)
        # In local dev: uses ADC or GOOGLE_APPLICATION_CREDENTIALS env var
        try:
            firebase_admin.initialize_app()
            logger.info("Firebase Admin initialized with Application Default Credentials")
        except Exception as e:
            logger.warning("Firebase Admin init failed (auth will not work): %s", e)

_init_firebase()


async def require_auth(
    authorization: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    FastAPI dependency. Verifies Firebase ID token and checks allowed email.
    Returns the user's Firebase UID if valid.
    Raises HTTP 401 if token is missing/invalid, HTTP 403 if email not allowed.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    try:
        decoded = firebase_auth.verify_id_token(token)
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.warning("Token verification error: %s", e)
        raise HTTPException(status_code=401, detail="Token verification failed")

    email = decoded.get("email", "")
    if email.lower() != settings.allowed_user_email.lower():
        logger.warning("Unauthorized access attempt from: %s", email)
        raise HTTPException(status_code=403, detail="Access denied")

    return decoded["uid"]
