"""Evidence Layer Package."""

from scraper.evidence.extractor import EvidenceExtractor, evidence_extractor
from scraper.evidence.graph import EvidenceGraph
from scraper.evidence.matcher import EvidenceMatcher, evidence_matcher
from scraper.evidence.models import Claim, EvidenceItem, EvidenceRelation
from scraper.evidence.store import EvidenceStore, evidence_store

__all__ = [
    "Claim",
    "EvidenceExtractor",
    "EvidenceGraph",
    "EvidenceItem",
    "EvidenceMatcher",
    "EvidenceRelation",
    "EvidenceStore",
    "evidence_extractor",
    "evidence_matcher",
    "evidence_store",
]
