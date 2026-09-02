"""Typed Pydantic v2 Models for SNC/SIH Epistemic Memory (DS-37).

Strictly mirrors SncSinCore schemas: sih.epistemic-artifact/1.0 and 2.0.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EpistemicNodeKind(str, Enum):
    DOCUMENT = "document"
    SPAN = "span"
    MENTION = "mention"
    ENTITY = "entity"
    CONCEPT = "concept"
    PROPOSITION = "proposition"
    ASSERTION = "assertion"
    RELATION_INSTANCE = "relation_instance"
    EVENT = "event"
    STATE = "state"
    QUANTITY = "quantity"
    EVIDENCE = "evidence"
    EPISTEMIC_ASSESSMENT = "epistemic_assessment"
    CONFLICT = "conflict"
    SUMMARY = "summary"


class EpistemicRelation(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    EVIDENCE_FOR = "evidence_for"
    CAUSES = "causes"
    ENABLES = "enables"
    PREVENTS = "prevents"
    PRECEDES = "precedes"
    INSTANCE_OF = "instance_of"
    SAME_ENTITY = "same_entity"
    SAME_TOPIC = "same_topic"
    DERIVED_FROM = "derived_from"
    ASSERTED_BY = "asserted_by"
    LOCATED_IN = "located_in"
    RESOLVES_TO = "resolves_to"
    SUPERSEDES = "supersedes"
    INCOMPATIBLE_CONTEXT = "incompatible_context"
    CORRELATES_WITH = "correlates_with"
    MEDIATES = "mediates"
    INHIBITS = "inhibits"


class EpistemicIntent(str, Enum):
    FACTUAL = "factual"
    ENTITY_CENTRIC = "entity_centric"
    MULTI_HOP = "multi_hop"
    CAUSAL = "causal"
    TEMPORAL = "temporal"
    COMPARISON = "comparison"
    CONTESTED = "contested"
    GLOBAL = "global"
    NUMERIC = "numeric"
    DEFINITION = "definition"
    PROCEDURAL = "procedural"
    SOURCE_AUDIT = "source_audit"


class EpistemicRequirementKind(str, Enum):
    FACT = "fact"
    RELATION = "relation"
    COMPARISON = "comparison"
    CAUSAL = "causal"
    TEMPORAL = "temporal"
    DEFINITION = "definition"
    PROCEDURAL = "procedural"
    ALTERNATIVES = "alternatives"
    CONFLICT = "conflict"
    GLOBAL_SUMMARY = "global_summary"
    NUMERIC = "numeric"
    POLICY = "policy"
    SOURCE_AUDIT = "source_audit"


class EpistemicNodeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: EpistemicNodeKind = EpistemicNodeKind.PROPOSITION
    text: str = ""
    belief: float | None = None
    evidence_quality: float | None = None
    uncertainty: float | None = None
    context: str = "general"
    scope: str = "public"
    provenance_cluster: str = ""
    conflict_family: str = ""


class EpistemicEdgeInput(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    relation: EpistemicRelation = EpistemicRelation.EVIDENCE_FOR
    weight: float | None = 1.0
    flags: list[str] = Field(default_factory=list)


class EpistemicRequirementInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = ""
    kind: EpistemicRequirementKind = EpistemicRequirementKind.FACT
    text: str
    criticality: float = 1.0
    minimum_coverage: float = 0.75
    targets: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    min_independent: int = 1


class EpistemicQueryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = "run_default"
    text: str
    intent: EpistemicIntent = EpistemicIntent.FACTUAL
    targets: list[str] = Field(default_factory=list)
    context: str = ""
    allowed_scopes: list[str] = Field(default_factory=lambda: ["public"])
    strict_context: bool = False
    requirements: list[EpistemicRequirementInput] = Field(default_factory=list)
    max_latency_ms: int = 2000
    max_tokens: int = 2048


class EpistemicPathScore(BaseModel):
    relevance: float = 0.0
    path_coherence: float = 0.0
    evidence_strength: float = 0.0
    temporal_fit: float = 1.0
    context_fit: float = 1.0
    independence: float = 1.0
    information_gain: float = 0.0
    uncertainty: float = 0.0


class EpistemicPath(BaseModel):
    id: str
    requirement_id: str = ""
    nodes: list[str] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    polarity: int = 1  # 1: support, -1: refute
    state: str = "accepted"
    score: EpistemicPathScore = Field(default_factory=EpistemicPathScore)
    provenance_clusters: list[str] = Field(default_factory=list)
    conflict_families: list[str] = Field(default_factory=list)


class EpistemicLLMContext(BaseModel):
    format: str = "sih-artifact-context/1.0"
    token_estimate: int = 0
    text: str = ""


class EpistemicRequirementResult(BaseModel):
    id: str
    type: str = "fact"
    text: str = ""
    criticality: float = 1.0
    minimum_coverage: float = 0.75
    coverage: float = 0.0
    critical: bool = True
    targets: list[str] = Field(default_factory=list)


class EpistemicQueryDiagnostics(BaseModel):
    candidate_count: int = 0
    activated_count: int = 0
    path_count_before_filter: int = 0


class EpistemicArtifact(BaseModel):
    schema_version: str = Field(default="sih.epistemic-artifact/1.0", alias="schema")
    id: str
    digest_sha256: str
    status: str = "complete"  # complete | partial | incomplete
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_paths: list[EpistemicPath] = Field(default_factory=list)
    llm: EpistemicLLMContext = Field(default_factory=EpistemicLLMContext)
    diagnostics: EpistemicQueryDiagnostics = Field(
        default_factory=EpistemicQueryDiagnostics
    )


class EpistemicQueryResponse(BaseModel):
    run_id: str
    artifact: EpistemicArtifact
    status: str
    digest_sha256: str
    coverage: float
    context_pack_text: str = ""
    elapsed_sec: float = 0.0
