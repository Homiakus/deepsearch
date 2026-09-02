"""Research Intent Representation (DS-SI02)."""

from enum import Enum

from pydantic import BaseModel, Field


class FreshnessRequirement(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    REALTIME = "REALTIME"


class SourcePreference(str, Enum):
    OFFICIAL_DOCS = "OFFICIAL_DOCS"
    PRIMARY_RESEARCH = "PRIMARY_RESEARCH"
    PATENTS = "PATENTS"
    STANDARDS = "STANDARDS"
    SOURCE_CODE = "SOURCE_CODE"
    NEWS = "NEWS"
    FORUMS = "FORUMS"
    WIKI = "WIKI"
    ALL = "ALL"


class EvidenceRequirements(BaseModel):
    min_independent_sources: int = 1
    preferred_source_types: list[str] = Field(default_factory=list)
    require_peer_reviewed: bool = False
    require_official_specification: bool = False
    allow_discussion_sources: bool = True
    contradiction_resolution_required: bool = False


class Entity(BaseModel):
    name: str
    entity_type: str
    canonical_form: str | None = None
    confidence: float = 1.0
    aliases: list[str] = Field(default_factory=list)


class Constraint(BaseModel):
    constraint_type: str  # DATE_RANGE, FILE_TYPE, LANGUAGE, DOMAIN, LICENSE
    value: str
    strict: bool = False


class ResearchIntent(BaseModel):
    original_query: str
    normalized_query: str
    task_type: str = "general_research"  # factual, scientific, engineering, medical, comparative, code
    domain: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en", "ru"])
    freshness_requirement: FreshnessRequirement = FreshnessRequirement.NONE
    source_preferences: list[SourcePreference] = Field(
        default_factory=lambda: [SourcePreference.ALL]
    )
    evidence_requirements: EvidenceRequirements = Field(
        default_factory=EvidenceRequirements
    )
    ambiguity: float = 0.0
