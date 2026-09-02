"""Evidence and Claim Extractor (DS-SI52).

Extracts factual claim candidates and citation quotes with exact provenance.
"""

import re
import urllib.parse

from scraper.evidence.models import Claim, EvidenceItem, EvidenceRelation
from scraper.search.retrieval.hybrid import FusedResult


class EvidenceExtractor:
    """Extracts factual claims and quotation spans from retrieved passages."""

    @staticmethod
    def extract_from_passages(
        passages: list[FusedResult], goal_id: str = None
    ) -> tuple[list[Claim], list[EvidenceItem]]:
        claims: list[Claim] = []
        evidence_items: list[EvidenceItem] = []

        for p in passages:
            hit = p.hit
            text = hit.text
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", text)
                if len(s.strip()) > 30
            ]

            for s in sentences[:3]:  # Top informative sentences per passage
                clm = Claim(
                    statement=s,
                    goal_id=goal_id or (hit.goal_ids[0] if hit.goal_ids else None),
                    confidence=0.75,
                )
                claims.append(clm)

                parsed = urllib.parse.urlparse(hit.url)
                domain = parsed.netloc.lower()

                evi = EvidenceItem(
                    claim_id=clm.id,
                    goal_id=clm.goal_id,
                    source_url=hit.url,
                    canonical_url=hit.url,
                    domain=domain,
                    chunk_id=hit.chunk_id,
                    quote=s,
                    relation=EvidenceRelation.SUPPORTS,
                    authority_score=hit.authority_score,
                    source_type=hit.source_type,
                    provenance=hit.metadata,
                )
                evidence_items.append(evi)

        return claims, evidence_items


evidence_extractor = EvidenceExtractor()
