"""Unit tests for Pydantic models."""

import pytest
from datetime import datetime, timezone
from app.models.post import Post, PostStatus, PostContent, PostImage, PostPublishing, UrgencyTier
from app.models.voice import Celebrity, VoiceStatement
from app.models.settings import VoiceGuide, AppSettings


class TestPostModel:
    def _make_post(self, **kwargs) -> Post:
        defaults = dict(
            content=PostContent(
                one_liner="Stop sitting like it is.",
                body="Test body text.",
                hashtags=["#ShutUpAndServe"],
                full_text="Stop sitting like it is.\n\nTest body text.\n\n#ShutUpAndServe",
            ),
            image=PostImage(prompt="Dark blue background with white text."),
        )
        defaults.update(kwargs)
        return Post(**defaults)

    def test_default_status_is_pending_review(self):
        post = self._make_post()
        assert post.status == PostStatus.PENDING_REVIEW

    def test_post_id_auto_generated(self):
        post = self._make_post()
        assert post.id is not None
        assert len(post.id) == 36  # UUID format

    def test_to_firestore_returns_dict(self):
        post = self._make_post()
        data = post.to_firestore()
        assert isinstance(data, dict)
        assert data["status"] == "pending_review"
        assert "content" in data

    def test_legal_review_flag_default_false(self):
        post = self._make_post()
        assert post.legal_review_required is False

    def test_urgency_tier_default_warm(self):
        post = self._make_post()
        assert post.urgency == UrgencyTier.WARM


class TestCelebrityModel:
    def test_search_queries_generated(self):
        celebrity = Celebrity(
            name="Vice Ganda",
            search_aliases=["Vice Ganda", "Jose Marie Viceral"],
        )
        queries = celebrity.get_search_queries()
        assert len(queries) == 6  # 2 aliases × 3 templates
        assert any("Vice Ganda" in q for q in queries)
        assert any("Jose Marie Viceral" in q for q in queries)

    def test_active_by_default(self):
        celebrity = Celebrity(name="Test", search_aliases=["Test"])
        assert celebrity.active is True


class TestAppSettings:
    def test_default_publish_schedule(self):
        settings = AppSettings()
        assert settings.publish_schedule.morning == "07:30"
        assert settings.publish_schedule.midday == "12:30"
        assert settings.publish_schedule.evening == "20:00"

    def test_default_hashtag_pool_not_empty(self):
        settings = AppSettings()
        assert len(settings.hashtag_pool.broad) > 0
        assert len(settings.hashtag_pool.philippines) > 0

    def test_to_firestore_roundtrip(self):
        settings = AppSettings()
        data = settings.to_firestore()
        restored = AppSettings.from_firestore(data)
        assert restored.publish_schedule.morning == settings.publish_schedule.morning
