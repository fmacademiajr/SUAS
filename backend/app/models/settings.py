from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class HashtagPool(BaseModel):
    broad: list[str] = Field(default_factory=lambda: [
        "#ShutUpAndServe", "#PublicServant", "#Accountability",
        "#SerbisyoPubliko", "#GovernmentAccountability"
    ])
    philippines: list[str] = Field(default_factory=lambda: [
        "#Philippines", "#Pilipinas", "#PinoyPolitics",
        "#PHPolitics", "#BagongPilipinas"
    ])
    engagement: list[str] = Field(default_factory=lambda: [
        "#SerbisyoOWala", "#VoterPower", "#TaxpayerMoney"
    ])


class PublishSchedule(BaseModel):
    morning: str = "07:30"      # PHT, HH:MM
    midday: str = "12:30"
    evening: str = "20:00"


class VoiceGuide(BaseModel):
    """The SUAS editorial voice — stored in Firestore, editable from dashboard."""
    persona_description: str = (
        "SUAS is not a pundit. It is not a commentator. It is a receipt. "
        "It speaks directly, without filler, without false balance. "
        "It treats the audience as adults who can handle the truth."
    )
    tone_rules: list[str] = Field(default_factory=lambda: [
        "Attack the action, the failure, the system. Never the person.",
        "No personal attacks on appearance, family, identity, or character.",
        "No unverified allegations. Only reference what is in mainstream news.",
        "Never name a politician in the one-liner or catchline.",
        "Maximum 10 words for the one-liner.",
        "One-liner must work as a standalone statement.",
    ])
    one_liner_patterns: list[str] = Field(default_factory=lambda: [
        "Direct command: e.g., 'Stop sitting like it is.'",
        "Sharp contrast: e.g., 'Not a public saint.'",
        "Confrontational question: e.g., 'You wanted power?'",
        "Cold declaration: e.g., 'The only VIP is the voter.'",
        "Witty reframe: e.g., 'Your salary is our receipt.'",
    ])
    forbidden_phrases: list[str] = Field(default_factory=lambda: [
        "allegedly", "sources say", "rumor has it", "some people think"
    ])
    example_posts: list[str] = Field(default_factory=list)
    updated_at: Optional[str] = None    # ISO datetime string


class AppSettings(BaseModel):
    """Main settings document stored in Firestore settings/app_settings."""
    voice_guide: VoiceGuide = Field(default_factory=VoiceGuide)
    hashtag_pool: HashtagPool = Field(default_factory=HashtagPool)
    publish_schedule: PublishSchedule = Field(default_factory=PublishSchedule)
    breaking_scan_times: list[str] = Field(
        default_factory=lambda: ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"]
    )
    notification_email: str = ""
    notification_push: bool = True
    facebook_page_id: str = ""

    def to_firestore(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore(cls, data: dict) -> "AppSettings":
        return cls(**data)
