from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class OverrideRecord(BaseModel):
    post_id: str
    claude_predicted: str       # Claude's recommended angle/strategy
    model_predicted: float      # ML model's predicted engagement score
    actual_engagement: float    # normalized engagement after 48h
    claude_was_right: bool


class LearningLogEntry(BaseModel):
    """Weekly learning log. Last 12 entries (3 months) fed to Claude on every run."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    week: str                   # "2026-04-07 to 2026-04-13"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    posts_analyzed: int = 0
    top_insight: str = ""
    confirmed_patterns: list[str] = Field(default_factory=list)
    disproven_assumptions: list[str] = Field(default_factory=list)
    adjustments: list[str] = Field(default_factory=list)
    experiment_for_next_week: str = ""
    model_overrides_this_week: int = 0
    override_outcomes: list[OverrideRecord] = Field(default_factory=list)

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")


class ModelAccuracyMetrics(BaseModel):
    r_squared: float
    mae: float                  # mean absolute error
    training_set_size: int


class TopFeature(BaseModel):
    name: str
    importance: float


class TrainingRecord(BaseModel):
    """Metadata for each trained scikit-learn scoring model. Stored in model_training."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trained_at: datetime = Field(default_factory=datetime.utcnow)
    posts_in_training_set: int
    model_version: str          # "v1", "v2", etc.
    accuracy_metrics: ModelAccuracyMetrics
    top_features: list[TopFeature] = Field(default_factory=list)
    gcs_path: str               # "models/scorer_v1.pkl"
    is_active: bool = False     # only one model is active at a time

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")
