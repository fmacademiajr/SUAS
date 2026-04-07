from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class Celebrity(BaseModel):
    """A public figure tracked by the Voice Amplifier."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str                           # "Vice Ganda"
    search_aliases: list[str]           # ["Vice Ganda", "Jose Marie Viceral"]
    platforms: list[str] = Field(default_factory=lambda: ["facebook", "instagram", "tiktok"])
    active: bool = True
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_match_at: Optional[datetime] = None
    total_posts_generated: int = 0

    def get_search_queries(self) -> list[str]:
        """Returns all search query combinations for this celebrity."""
        query_templates = [
            "{name} political statement",
            "{name} corruption commentary",
            "{name} speaks out government",
        ]
        queries = []
        for alias in self.search_aliases:
            for template in query_templates:
                queries.append(template.format(name=alias))
        return queries

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore(cls, data: dict) -> "Celebrity":
        return cls(**data)


class VoiceStatement(BaseModel):
    """A statement found from a tracked celebrity that may be used in a post."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    celebrity_name: str
    celebrity_id: str
    statement_summary: str              # paraphrased — never the full quote
    source_url: str
    source_outlet: str
    found_at: datetime = Field(default_factory=datetime.utcnow)
    alignment_score: float              # 1.0–5.0: how well it aligns with SUAS theme
    accountability_flag: bool           # True if score >= 4
    raw_headline: str                   # original headline from the search result

    # Which post used this statement (set after post generation)
    used_in_post_id: Optional[str] = None
