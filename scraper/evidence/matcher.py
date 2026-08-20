"""Claim and Evidence Matcher (DS-SI53, DS-SI54).

Determines whether a candidate citation supports, contradicts, or qualifies a research claim.
"""

import re
from typing import Tuple
from scraper.evidence.models import EvidenceRelation


class EvidenceMatcher:
    """Matches textual evidence against claims to determine semantic relation."""

    CONTRADICTION_MARKERS = [
        "not found",
        "failed to show",
        "no significant difference",
        "contradicts",
        "ineffective",
        "disputed",
        "no evidence",
        "refuted",
        "however, no",
        "adverse",
        "не обнаружено",
        "не подтвердилось",
        "опровергает",
        "противоречит",
        "неэффективно",
    ]

    QUALIFICATION_MARKERS = [
        "only in cases of",
        "depends on",
        "limited to",
        "under specific conditions",
        "preliminary",
        "small sample",
        "только при условии",
        "зависит от",
        "ограничен",
    ]

    @classmethod
    def match_relation(
        cls, claim_text: str, evidence_text: str
    ) -> Tuple[EvidenceRelation, float]:
        ev_lower = evidence_text.lower()
        cl_lower = claim_text.lower()

        # Check for contradiction markers
        for m in cls.CONTRADICTION_MARKERS:
            if m in ev_lower:
                return EvidenceRelation.CONTRADICTS, 0.85

        # Check for qualification markers
        for m in cls.QUALIFICATION_MARKERS:
            if m in ev_lower:
                return EvidenceRelation.QUALIFIES, 0.75

        # Token overlap check for support
        c_words = set(re.findall(r"\w+", cl_lower))
        e_words = set(re.findall(r"\w+", ev_lower))
        overlap = len(c_words.intersection(e_words)) / max(len(c_words), 1)

        if overlap >= 0.3:
            return EvidenceRelation.SUPPORTS, min(1.0, 0.6 + overlap * 0.4)

        return EvidenceRelation.SUPPORTS, 0.5


evidence_matcher = EvidenceMatcher()
