"""Explainable Candidate Ranker (DS-SI22).

Combines lexical, semantic, authority, freshness, and cost features into
a calibrated ranking score with clear explainability.
"""

from pydantic import BaseModel, Field

from scraper.research.intent import ResearchIntent
from scraper.search.candidates import SourceCandidate
from scraper.search.cost import estimate_acquisition_cost
from scraper.search.features import CandidateFeatureVector
from scraper.search.freshness import calculate_freshness_score
from scraper.search.prerank.lexical import lexical_preranker
from scraper.search.prerank.semantic import semantic_preranker
from scraper.search.source_policy import calculate_authority_prior
from scraper.search.trace import SearchTrace, TraceEventType


class RankedCandidate(BaseModel):
    candidate: SourceCandidate
    final_score: float
    features: CandidateFeatureVector
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class CandidateRanker:
    """Ranks candidates deterministically using feature weights and emits detailed score breakdown."""

    def __init__(
        self,
        w_lexical: float = 0.35,
        w_semantic: float = 0.25,
        w_authority: float = 0.25,
        w_freshness: float = 0.10,
        w_agreement: float = 0.05,
    ):
        self.w_lexical = w_lexical
        self.w_semantic = w_semantic
        self.w_authority = w_authority
        self.w_freshness = w_freshness
        self.w_agreement = w_agreement

    def score_candidate(
        self,
        candidate: SourceCandidate,
        intent: ResearchIntent,
        depth: int = 0,
        domain_counts: dict[str, int] = None,
    ) -> RankedCandidate:
        domain_counts = domain_counts or {}

        # 1. Feature extraction
        lex_score = lexical_preranker.score_candidate(candidate, intent)
        sem_score = semantic_preranker.score_candidate(candidate, intent)
        auth_score = calculate_authority_prior(
            candidate.domain, candidate.source_type, intent.task_type
        )
        fresh_score = calculate_freshness_score(
            candidate.published_at, intent.freshness_requirement
        )
        cost = estimate_acquisition_cost(
            candidate.url, candidate.domain, candidate.provider
        )

        # Provider agreement bonus
        num_providers = len(candidate.found_by_providers)
        agreement_score = (
            min(1.0, (num_providers - 1) * 0.5) if num_providers > 1 else 0.0
        )

        # Domain diversity penalty
        dom_seen = domain_counts.get(candidate.domain, 0)
        diversity_bonus = max(0.0, 0.10 - 0.03 * dom_seen)

        depth_penalty = depth * 0.05

        features = CandidateFeatureVector(
            lexical_relevance=lex_score,
            semantic_relevance=sem_score,
            identifier_match=1.0
            if any(e.name.lower() in candidate.url.lower() for e in intent.entities)
            else 0.0,
            provider_agreement_score=agreement_score,
            authority_prior=auth_score,
            freshness_score=fresh_score,
            expected_cost=cost,
            source_diversity_bonus=diversity_bonus,
            depth_penalty=depth_penalty,
        )

        # 2. Weighted score calculation
        breakdown = {
            "lexical": round(self.w_lexical * lex_score, 4),
            "semantic": round(self.w_semantic * sem_score, 4),
            "authority": round(self.w_authority * auth_score, 4),
            "freshness": round(self.w_freshness * fresh_score, 4),
            "agreement": round(self.w_agreement * agreement_score, 4),
            "diversity": round(diversity_bonus, 4),
            "depth_penalty": round(-depth_penalty, 4),
        }

        raw_sum = sum(breakdown.values())
        # Cost normalization divisor
        final_score = max(0.0, min(1.0, round(raw_sum / (0.8 + 0.2 * cost), 4)))

        return RankedCandidate(
            candidate=candidate,
            final_score=final_score,
            features=features,
            score_breakdown=breakdown,
        )

    def rank_pool(
        self,
        candidates: list[SourceCandidate],
        intent: ResearchIntent,
        trace: SearchTrace = None,
    ) -> list[RankedCandidate]:
        domain_counts: dict[str, int] = {}
        ranked: list[RankedCandidate] = []

        for c in candidates:
            rc = self.score_candidate(c, intent, depth=0, domain_counts=domain_counts)
            ranked.append(rc)
            domain_counts[c.domain] = domain_counts.get(c.domain, 0) + 1

            if trace:
                trace.record(
                    event_type=TraceEventType.CANDIDATE_SCORED,
                    entity_id=c.url,
                    stage="pre_ranking",
                    decision="SCORED",
                    metrics={"score": rc.final_score},
                    metadata=rc.score_breakdown,
                )

        ranked.sort(key=lambda item: item.final_score, reverse=True)
        return ranked


candidate_ranker = CandidateRanker()
