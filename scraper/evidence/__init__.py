"""Evidence Layer Package."""

from scraper.evidence.models import Claim, EvidenceItem, EvidenceRelation
from scraper.evidence.graph import EvidenceGraph
from scraper.evidence.store import EvidenceStore, evidence_store
from scraper.evidence.extractor import EvidenceExtractor, evidence_extractor
from scraper.evidence.matcher import EvidenceMatcher, evidence_matcher

__all__ = [
    "Claim",
    "EvidenceItem",
    "EvidenceRelation",
    "EvidenceGraph",
    "EvidenceStore",
    "evidence_store",
    "EvidenceExtractor",
    "evidence_extractor",
    "EvidenceMatcher",
    "evidence_matcher",
]
