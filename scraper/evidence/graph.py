"""Evidence Graph Representation (DS-SI51)."""

from typing import Dict
from pydantic import BaseModel, Field
from scraper.evidence.models import Claim, EvidenceItem, EvidenceRelation


class EvidenceGraph(BaseModel):
    claims: Dict[str, Claim] = Field(default_factory=dict)
    evidence: Dict[str, EvidenceItem] = Field(default_factory=dict)

    def add_claim(self, claim: Claim) -> Claim:
        self.claims[claim.id] = claim
        return claim

    def add_evidence(self, item: EvidenceItem) -> EvidenceItem:
        self.evidence[item.id] = item
        if item.claim_id and item.claim_id in self.claims:
            claim = self.claims[item.claim_id]
            if item.relation == EvidenceRelation.SUPPORTS:
                if item.id not in claim.supporting_evidence_ids:
                    claim.supporting_evidence_ids.append(item.id)
            elif item.relation == EvidenceRelation.CONTRADICTS:
                if item.id not in claim.contradicting_evidence_ids:
                    claim.contradicting_evidence_ids.append(item.id)
            elif item.relation == EvidenceRelation.QUALIFIES:
                if item.id not in claim.qualifying_evidence_ids:
                    claim.qualifying_evidence_ids.append(item.id)
            self._update_claim_status(claim)
        return item

    def _update_claim_status(self, claim: Claim):
        sup = len(claim.supporting_evidence_ids)
        con = len(claim.contradicting_evidence_ids)

        # Count unique domains supporting this claim
        domains = set()
        for eid in claim.supporting_evidence_ids:
            if eid in self.evidence:
                domains.add(self.evidence[eid].domain)
        claim.independent_sources_count = len(domains)

        if con > 0 and sup > 0:
            claim.status = "DISPUTED"
            claim.confidence = max(0.2, 0.5 + 0.1 * sup - 0.3 * con)
        elif con > 0 and sup == 0:
            claim.status = "REFUTED"
            claim.confidence = 0.1
        elif sup >= 2 and claim.independent_sources_count >= 2:
            claim.status = "VERIFIED"
            claim.confidence = min(1.0, 0.7 + 0.15 * sup)
        elif sup >= 1:
            claim.status = "SUPPORTED"
            claim.confidence = 0.6 + 0.1 * sup
        else:
            claim.status = "UNVERIFIED"
            claim.confidence = 0.5
