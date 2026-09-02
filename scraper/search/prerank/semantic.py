"""Semantic Candidate Pre-Ranker (DS-SI17).

Computes bi-encoder cosine similarity between research intent and candidate title/snippet.
"""

from scraper.research.intent import ResearchIntent
from scraper.retrieval.embeddings import embedding_engine
from scraper.search.candidates import SourceCandidate


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


class SemanticPreRanker:
    """Computes dense similarity between candidate snippet and query without running slow cross-encoders."""

    @staticmethod
    def score_candidate(candidate: SourceCandidate, intent: ResearchIntent) -> float:
        q_vec = embedding_engine.embed_text_dense(intent.normalized_query)
        doc_text = f"{candidate.title}. {candidate.snippet}".strip()
        if not doc_text:
            candidate.semantic_score = candidate.lexical_score
            return candidate.semantic_score

        doc_vec = embedding_engine.embed_text_dense(doc_text)
        sim = cosine_similarity(q_vec, doc_vec)
        candidate.semantic_score = round(sim, 4)
        return candidate.semantic_score

    @classmethod
    def rank_candidates(
        cls, candidates: list[SourceCandidate], intent: ResearchIntent
    ) -> list[SourceCandidate]:
        for c in candidates:
            cls.score_candidate(c, intent)
        return sorted(candidates, key=lambda c: c.semantic_score, reverse=True)


semantic_preranker = SemanticPreRanker()
