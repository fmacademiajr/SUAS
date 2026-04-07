from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── App ─────────────────────────────────────────────────────────────────
    app_env: str = "local"          # local | staging | production
    log_level: str = "INFO"
    # Fernando's Google account — the only user allowed to access the dashboard
    allowed_user_email: str

    # ─── GCP ─────────────────────────────────────────────────────────────────
    gcp_project_id: str
    gcs_bucket_name: str
    # Set to "localhost:8080" for local dev. Empty string in production.
    # Cloud Run never sets this — the real Firestore is used automatically.
    firestore_emulator_host: str = ""

    # ─── Anthropic ───────────────────────────────────────────────────────────
    anthropic_api_key: str

    # ─── Google AI (Gemini) ───────────────────────────────────────────────────
    gemini_api_key: str

    # ─── Facebook ────────────────────────────────────────────────────────────
    facebook_page_id: str
    facebook_page_access_token: str

    # ─── Brave Search ────────────────────────────────────────────────────────
    brave_api_key: str = ""   # optional — pipeline skips Brave news if not set

    # ─── Scheduler ───────────────────────────────────────────────────────────
    timezone: str = "Asia/Manila"

    # ─── Model IDs ───────────────────────────────────────────────────────────
    # Pinned versions — override via env var if you want to test a newer model.
    # Never use string literals elsewhere; always go through ModelRouter.
    model_haiku: str = "claude-haiku-4-5-20251001"
    model_sonnet: str = "claude-sonnet-4-6"
    model_opus: str = "claude-opus-4-6"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance. Call get_settings.cache_clear() in tests."""
    return Settings()
