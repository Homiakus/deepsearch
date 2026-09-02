"""Quality evaluation models and decision states (§52, DS-A19)."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityDecision(str, Enum):
    ACCEPT = "ACCEPT"
    RETRY = "RETRY"
    ESCALATE = "ESCALATE"
    DISCARD = "DISCARD"


class ContentQualityReport(BaseModel):
    decision: QualityDecision
    overall_score: float = Field(default=1.0, ge=0.0, le=1.0)
    text_density: float = Field(default=1.0, ge=0.0, le=1.0)
    boilerplate_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    language_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_challenge_or_shell: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
