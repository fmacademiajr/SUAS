"""
Pytest fixtures for SUAS backend tests.

Key fixtures:
- mock_settings: overrides all API keys with test values
- mock_anthropic: patches the anthropic.AsyncAnthropic client with respx
- mock_firestore: in-memory Firestore emulation using a plain dict
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Settings ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Override all settings with safe test values. Applied to every test automatically."""
    env_overrides = {
        "APP_ENV": "test",
        "ALLOWED_USER_EMAIL": "test@example.com",
        "GCP_PROJECT_ID": "suas-test",
        "GCS_BUCKET_NAME": "suas-test-bucket",
        "FIRESTORE_EMULATOR_HOST": "localhost:8080",
        "ANTHROPIC_API_KEY": "sk-test-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "FACEBOOK_PAGE_ID": "test-page-id",
        "FACEBOOK_PAGE_ACCESS_TOKEN": "test-fb-token",
        "REDDIT_CLIENT_ID": "test-reddit-id",
        "REDDIT_CLIENT_SECRET": "test-reddit-secret",
        "MODEL_HAIKU": "claude-haiku-4-5-20251001",
        "MODEL_SONNET": "claude-sonnet-4-6",
        "MODEL_OPUS": "claude-opus-4-6",
    }
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)

    # Clear Settings cache so each test gets fresh settings
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Anthropic mock ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_anthropic_response():
    """Returns a factory for creating mock Anthropic API responses."""
    def _make_response(text: str):
        content_block = MagicMock()
        content_block.text = text
        response = MagicMock()
        response.content = [content_block]
        return response
    return _make_response


@pytest.fixture
def mock_anthropic_client(mock_anthropic_response):
    """Patches anthropic.AsyncAnthropic to return controllable responses."""
    with patch("anthropic.AsyncAnthropic") as mock_cls:
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=mock_anthropic_response('{"result": "mocked"}')
        )
        mock_cls.return_value = client
        yield client


# ── Firestore mock ───────────────────────────────────────────────────────────

class MockFirestoreDoc:
    def __init__(self, data: dict, doc_id: str = "test-doc"):
        self._data = data
        self.id = doc_id

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data.copy() if self._data else {}


class MockFirestoreCollection:
    def __init__(self, data: dict):
        self._data = data  # {doc_id: dict}

    def document(self, doc_id: str):
        mock_doc_ref = AsyncMock()
        mock_doc_ref.get = AsyncMock(
            return_value=MockFirestoreDoc(self._data.get(doc_id), doc_id)
        )
        mock_doc_ref.set = AsyncMock()
        mock_doc_ref.update = AsyncMock()
        mock_doc_ref.delete = AsyncMock()
        return mock_doc_ref

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n: int):
        return self

    async def stream(self):
        for doc_id, data in list(self._data.items())[:50]:
            yield MockFirestoreDoc(data, doc_id)

    def __aiter__(self):
        return self.stream()


@pytest.fixture
def mock_firestore_db():
    """
    In-memory Firestore mock. Pre-seeded with minimal test data.
    Use mock_firestore_db._collections to inspect/modify data in tests.
    """
    initial_data = {
        "settings": {
            "app_settings": {
                "voice_guide": {
                    "persona_description": "Test voice guide",
                    "tone_rules": ["Test rule"],
                    "one_liner_patterns": ["Test pattern"],
                    "forbidden_phrases": [],
                    "example_posts": [],
                }
            }
        },
        "posts": {},
        "tracked_voices": {},
        "editorial_digests": {},
        "editorial_reports": {},
        "learning_log": {},
        "content_bank": {},
    }

    db = MagicMock()
    db._collections = initial_data

    def _collection(name: str):
        return MockFirestoreCollection(initial_data.get(name, {}))

    db.collection = MagicMock(side_effect=_collection)
    return db
