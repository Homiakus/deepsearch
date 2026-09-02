"""Post-Acquisition Document Quality Assessment (DS-SI28).

Separates technical acquisition health (DOM rendered, no block page)
from epistemic document quality (evidence density, spam likelihood, relevance).
"""

from pydantic import BaseModel


class DocumentQuality(BaseModel):
    topical_relevance: float = 0.5
    evidence_density: float = 0.5
    spam_likelihood: float = 0.0
    navigation_ratio: float = 0.0
    boilerplate_ratio: float = 0.0
    authority_score: float = 0.5
    freshness_score: float = 0.5
    extractability_score: float = 0.9
    is_accepted: bool = True
    reject_reason: str | None = None
    composite_quality_score: float = 0.75
