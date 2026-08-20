"""Candidate Feature Vector (DS-SI21)."""

from pydantic import BaseModel


class CandidateFeatureVector(BaseModel):
    lexical_relevance: float = 0.0
    semantic_relevance: float = 0.0
    identifier_match: float = 0.0
    provider_rank_score: float = 0.5
    provider_agreement_score: float = 0.0
    authority_prior: float = 0.5
    freshness_score: float = 0.5
    expected_novelty: float = 1.0
    expected_extractability: float = 0.9
    expected_cost: float = 1.0
    risk_score: float = 0.0
    source_diversity_bonus: float = 0.0
    depth_penalty: float = 0.0
