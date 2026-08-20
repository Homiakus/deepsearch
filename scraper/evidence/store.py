"""EvidenceStore and Claim-Evidence Graph Repository (DS-SI51, DS-SI52)."""

from typing import List, Optional
from scraper.evidence.models import Claim, EvidenceItem, EvidenceRelation
from scraper.evidence.graph import EvidenceGraph


class EvidenceStore:
    """In-memory or durable store for research claims, citations, and confidence scoring."""

    def __init__(self):
        self.graph = EvidenceGraph()

    def add_claim(
        self,
        claim_id: str,
        statement: str,
        goal_id: Optional[str] = None,
        initial_confidence: float = 0.5,
    ) -> Claim:
        claim = Claim(
            id=claim_id,
            statement=statement,
            goal_id=goal_id,
            confidence=initial_confidence,
        )
        return self.graph.add_claim(claim)

    def add_evidence(
        self,
        evidence_id: str,
        claim_id: str,
        source_url: str,
        chunk_id: str,
        quote: str,
        relation: EvidenceRelation = EvidenceRelation.SUPPORTS,
        authority_score: float = 0.8,
        domain: str = "",
        source_type: str = "UNKNOWN",
    ) -> EvidenceItem:
        if not domain and "//" in source_url:
            domain = source_url.split("/")[2].lower()

        item = EvidenceItem(
            id=evidence_id,
            claim_id=claim_id,
            source_url=source_url,
            chunk_id=chunk_id,
            quote=quote,
            relation=relation,
            authority_score=authority_score,
            domain=domain,
            source_type=source_type,
            contradiction_flag=(relation == EvidenceRelation.CONTRADICTS),
        )
        return self.graph.add_evidence(item)

    def get_claims_for_goal(self, goal_id: str) -> List[Claim]:
        return [c for c in self.graph.claims.values() if c.goal_id == goal_id]

    def get_contradictions(self) -> List[Claim]:
        return [
            c
            for c in self.graph.claims.values()
            if c.status == "DISPUTED" or len(c.contradicting_evidence_ids) > 0
        ]


evidence_store = EvidenceStore()
