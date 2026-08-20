"""Epistemic Authority Evaluator (DS-SI48, DS-SI49)."""

from scraper.search.source_policy import calculate_authority_prior


class AuthorityEvaluator:
    """Calculates multidimensional epistemic authority without conflating authority with relevance."""

    @staticmethod
    def evaluate_authority(
        domain: str,
        source_type: str = "UNKNOWN",
        has_citations: bool = False,
        is_peer_reviewed: bool = False,
        is_official: bool = False,
    ) -> float:
        base_prior = calculate_authority_prior(domain, source_type)
        score = base_prior

        if is_official or is_peer_reviewed:
            score = max(score, 0.92)
        if has_citations:
            score = min(1.0, score + 0.05)

        return round(score, 3)


authority_evaluator = AuthorityEvaluator()
