from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class ThemeEntry(BaseModel):
    name: str
    intensity: int          # 1–5
    direction: str          # "escalating" | "steady" | "fading" | "new"


class SentimentSnapshot(BaseModel):
    dominant: str           # "anger" | "sarcasm" | "frustration" | "hope" | "outrage"
    secondary: Optional[str] = None
    shift_from_yesterday: Optional[str] = None   # e.g., "frustration -> anger"


class StoryCovered(BaseModel):
    topic: str
    angle: str              # "ride_the_wave" | "fill_the_gap" | "connect_the_dots"
    post_id: Optional[str] = None


class VoiceHeard(BaseModel):
    name: str
    platform: str
    alignment_score: float


class EngagementSummary(BaseModel):
    avg_likes: float = 0.0
    avg_shares: float = 0.0
    avg_comments: float = 0.0
    best_performing_post_type: Optional[str] = None


class EditorialDigest(BaseModel):
    """Daily summary generated at end of each pipeline day. Last 60 kept in Firestore."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str                           # "2026-04-05" — ISO date string, used as document ID
    themes: list[ThemeEntry] = Field(default_factory=list)
    public_sentiment: Optional[SentimentSnapshot] = None
    stories_covered: list[StoryCovered] = Field(default_factory=list)
    voices_heard: list[VoiceHeard] = Field(default_factory=list)
    narrative_connections: list[str] = Field(default_factory=list)
    editorial_strategy_used: dict[str, int] = Field(
        default_factory=lambda: {"ride_the_wave": 0, "fill_the_gap": 0, "connect_the_dots": 0}
    )
    posts_generated: int = 0
    engagement_from_previous_day: EngagementSummary = Field(default_factory=EngagementSummary)
    trending_topics_ph: list[str] = Field(default_factory=list)
    reddit_hot_topics: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Compressed summary (used when digest is >14 days old to save context window tokens)
    compressed_summary: Optional[str] = None
    is_compressed: bool = False

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore(cls, data: dict) -> "EditorialDigest":
        return cls(**data)


class WeeklyReport(BaseModel):
    """Generated every Monday 6 AM PHT. Stored in editorial_reports collection."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "weekly"
    period_start: str       # ISO date string
    period_end: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    report_text: str        # Full narrative from Claude (Sonnet)
    top_themes: list[ThemeEntry] = Field(default_factory=list)
    sentiment_trajectory: list[dict] = Field(default_factory=list)
    content_performance: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    blind_spots: list[str] = Field(default_factory=list)
    posts_published: int = 0
    avg_engagement_rate: float = 0.0

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")


class MonthlyReport(BaseModel):
    """Generated on 1st of month 6 AM PHT. Stored in editorial_reports collection."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "monthly"
    period_start: str
    period_end: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    report_text: str        # Full narrative from Claude (Opus)
    macro_narrative_shifts: list[str] = Field(default_factory=list)
    emerging_voices: list[str] = Field(default_factory=list)
    accountability_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    posts_published: int = 0

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")
