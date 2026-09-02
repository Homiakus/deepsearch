"""Evidence Layer Data Models (DS-SI51, DS-SI52)."""

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceRelation(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    QUALIFIES = "QUALIFIES"
    DUPLICATES = "DUPLICATES"
    DERIVED_FROM = "DERIVED_FROM"


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: f"evi_{uuid.uuid4().hex[:8]}")
    claim_id: str | None = None
    goal_id: str | None = None
    source_url: str
    canonical_url: str = ""
    domain: str = ""
    chunk_id: str
    quote: str
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS
    confidence: float = 1.0
    authority_score: float = 0.8
    contradiction_flag: bool = False
    source_type: str = "UNKNOWN"
    extracted_at: float = Field(default_factory=time.time)
    provenance: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: f"clm_{uuid.uuid4().hex[:8]}")
    statement: str
    goal_id: str | None = None
    confidence: float = 0.5
    status: str = "UNVERIFIED"  # VERIFIED, SUPPORTED, DISPUTED, REFUTED
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    qualifying_evidence_ids: list[str] = Field(default_factory=list)
    independent_sources_count: int = 0
