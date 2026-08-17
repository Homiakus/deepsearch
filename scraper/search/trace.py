"""Search Lifecycle & Decision Trace System (DS-SI01).

Records why every URL or chunk was discovered, ranked, accepted, or rejected.
"""

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TraceEventType(str, Enum):
    QUERY_ANALYZED = "QUERY_ANALYZED"
    GOAL_CREATED = "GOAL_CREATED"
    QUERY_VARIANT_CREATED = "QUERY_VARIANT_CREATED"
    PROVIDER_CALLED = "PROVIDER_CALLED"
    CANDIDATE_DISCOVERED = "CANDIDATE_DISCOVERED"
    CANDIDATE_DEDUPED = "CANDIDATE_DEDUPED"
    CANDIDATE_SCORED = "CANDIDATE_SCORED"
    CANDIDATE_QUEUED = "CANDIDATE_QUEUED"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"
    DOCUMENT_ACCEPTED = "DOCUMENT_ACCEPTED"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    PASSAGE_RETRIEVED = "PASSAGE_RETRIEVED"
    PASSAGE_RERANKED = "PASSAGE_RERANKED"
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"
    GOAL_COVERAGE_CHANGED = "GOAL_COVERAGE_CHANGED"
    STOP_DECISION = "STOP_DECISION"


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    timestamp: float = Field(default_factory=time.time)
    event_type: TraceEventType
    entity_id: Optional[str] = None  # URL, goal_id, candidate_id, chunk_id, etc.
    stage: str = "search"
    decision: Optional[str] = None  # ACCEPTED, REJECTED, DEMOTED, STOPPED, etc.
    reason: Optional[str] = None
    metrics: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchTrace:
    """Collects and aggregates decision traces for an entire research session."""

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"trace_{uuid.uuid4().hex[:12]}"
        self.events: List[TraceEvent] = []

    def record(
        self,
        event_type: TraceEventType,
        entity_id: Optional[str] = None,
        stage: str = "search",
        decision: Optional[str] = None,
        reason: Optional[str] = None,
        metrics: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        event = TraceEvent(
            event_type=event_type,
            entity_id=entity_id,
            stage=stage,
            decision=decision,
            reason=reason,
            metrics=metrics or {},
            metadata=metadata or {},
        )
        self.events.append(event)
        return event

    def filter_by_entity(self, entity_id: str) -> List[TraceEvent]:
        return [e for e in self.events if e.entity_id == entity_id]

    def filter_by_type(self, event_type: TraceEventType) -> List[TraceEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total_events": len(self.events),
            "events": [e.model_dump() for e in self.events],
        }
