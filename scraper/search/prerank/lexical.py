"""Cheap Lexical Pre-Ranker (DS-SI16).

Scores candidate URLs, titles, and snippets against query tokens, entities,
and exact identifiers with high precision and zero latency.
"""

import re

from scraper.research.intent import ResearchIntent
from scraper.search.candidates import SourceCandidate


class LexicalPreRanker:
    """Calculates lexical relevance features prior to expensive acquisition or neural reranking."""

    @staticmethod
    def score_candidate(candidate: SourceCandidate, intent: ResearchIntent) -> float:
        q_text = intent.normalized_query.lower()
        title_lower = (candidate.title or "").lower()
        snippet_lower = (candidate.snippet or "").lower()
        url_lower = candidate.url.lower()

        score = 0.0

        # 1. Exact Identifier Match (High Priority)
        for entity in intent.entities:
            val = (entity.canonical_form or entity.name).lower()
            if entity.entity_type in (
                "DOI",
                "PMID",
                "STANDARD",
                "SOFTWARE_API",
                "CHEMICAL",
                "PRODUCT",
            ):
                if val in title_lower:
                    score += 0.40
                elif val in url_lower:
                    score += 0.35
                elif val in snippet_lower:
                    score += 0.25

        # 2. Quoted Phrase Match
        q_tokens = [t for t in re.findall(r"\w+", q_text) if len(t) > 2]
        if not q_tokens:
            return min(1.0, score + 0.1)

        # 3. Query Term Coverage in Title & Snippet
        title_matches = sum(1 for t in q_tokens if t in title_lower)
        snippet_matches = sum(1 for t in q_tokens if t in snippet_lower)
        url_matches = sum(1 for t in q_tokens if t in url_lower)

        title_coverage = title_matches / len(q_tokens)
        snippet_coverage = snippet_matches / len(q_tokens)
        url_coverage = url_matches / len(q_tokens)

        score += title_coverage * 0.35
        score += snippet_coverage * 0.20
        score += url_coverage * 0.15

        # 4. Provider rank bonus
        rank_bonus = max(0.0, (6 - min(candidate.provider_rank, 5)) * 0.02)
        score += rank_bonus

        # 5. Provider agreement bonus
        if len(candidate.found_by_providers) > 1:
            score += 0.10 * (len(candidate.found_by_providers) - 1)

        candidate.lexical_score = min(1.0, round(score, 4))
        return candidate.lexical_score

    @classmethod
    def rank_candidates(
        cls, candidates: list[SourceCandidate], intent: ResearchIntent
    ) -> list[SourceCandidate]:
        for c in candidates:
            cls.score_candidate(c, intent)
        return sorted(candidates, key=lambda c: c.lexical_score, reverse=True)


lexical_preranker = LexicalPreRanker()
