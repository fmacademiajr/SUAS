from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class PostStatus(str, Enum):
    PENDING_REVIEW = "pending_review"   # generated, awaiting Fernando's review
    APPROVED = "approved"               # Fernando approved, scheduled for publish
    REJECTED = "rejected"               # Fernando rejected
    PUBLISHED = "published"             # live on Facebook
    METRICS_SYNCED = "metrics_synced"   # engagement data fetched and stored


class PostType(str, Enum):
    NEWS = "news"
    AMPLIFY = "amplify"
    SPRINGBOARD = "springboard"
    LINK_DROP = "link_drop"


class UrgencyTier(str, Enum):
    HOT = "hot"     # publish within 2 hours
    WARM = "warm"   # publish within 8 hours
    COOL = "cool"   # publish within 24-48 hours, may go to Content Bank


class EditorialStrategy(str, Enum):
    RIDE_THE_WAVE = "ride_the_wave"
    FILL_THE_GAP = "fill_the_gap"
    CONNECT_THE_DOTS = "connect_the_dots"


class NewsSource(BaseModel):
    title: str
    url: str
    outlet: str
    fetched_at: datetime


class VoiceAmplifierInfo(BaseModel):
    celebrity_name: Optional[str] = None
    original_url: Optional[str] = None
    alignment_score: Optional[float] = None   # 1.0–5.0
    format: Optional[str] = None              # "amplify" | "springboard"


class PostContent(BaseModel):
    one_liner: str
    body: str
    hashtags: list[str] = Field(default_factory=list)
    full_text: str      # one_liner + "\n\n" + body + "\n\n" + hashtags combined


class PostImage(BaseModel):
    prompt: str
    storage_url: Optional[str] = None
    gcs_path: Optional[str] = None
    generated_at: Optional[datetime] = None
    generation_model: str = "gemini"


class PostPublishing(BaseModel):
    approved_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None
    published_at: Optional[datetime] = None
    facebook_post_id: Optional[str] = None


class EngagementMetrics(BaseModel):
    likes: int = 0
    comments: int = 0
    shares: int = 0
    reach: int = 0
    impressions: int = 0
    engagement_rate: float = 0.0   # (likes + comments + shares) / reach if reach > 0
    last_synced: Optional[datetime] = None


class Post(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_run_id: Optional[str] = None
    status: PostStatus = PostStatus.PENDING_REVIEW
    post_type: PostType = PostType.NEWS
    urgency: UrgencyTier = UrgencyTier.WARM
    editorial_strategy: Optional[EditorialStrategy] = None

    news_source: Optional[NewsSource] = None
    voice_amplifier: Optional[VoiceAmplifierInfo] = None
    content: PostContent
    image: PostImage
    publishing: PostPublishing = Field(default_factory=PostPublishing)
    metrics: EngagementMetrics = Field(default_factory=EngagementMetrics)

    rejection_reason: Optional[str] = None
    legal_review_required: bool = False   # Claude flags this if a politician is named directly

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_firestore(self) -> dict:
        """Serialize for Firestore (converts datetimes, strips None values)."""
        return self.model_dump(mode="json", exclude_none=False)

    @classmethod
    def from_firestore(cls, data: dict) -> "Post":
        return cls(**data)


class PostCreate(BaseModel):
    """Used when the pipeline creates a new post."""
    post_type: PostType = PostType.NEWS
    urgency: UrgencyTier = UrgencyTier.WARM
    editorial_strategy: Optional[EditorialStrategy] = None
    news_source: Optional[NewsSource] = None
    voice_amplifier: Optional[VoiceAmplifierInfo] = None
    content: PostContent
    image: PostImage
    pipeline_run_id: Optional[str] = None
    publishing: PostPublishing = Field(default_factory=PostPublishing)


class PostUpdate(BaseModel):
    """Used when Fernando edits a post in the dashboard."""
    one_liner: Optional[str] = None
    body: Optional[str] = None
    hashtags: Optional[list[str]] = None
    image_prompt: Optional[str] = None


class PostReject(BaseModel):
    reason: str
