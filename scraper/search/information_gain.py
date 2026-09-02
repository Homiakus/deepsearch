"""Information Gain and Redundancy Scoring Engine (DS-SI57, DS-SI58)."""

from scraper.research.goals import ResearchGoalGraph
from scraper.search.candidates import SourceCandidate


class InformationGainScorer:
    """Estimates expected marginal information gain for a candidate against current goal coverage."""

    @staticmethod
    def compute_expected_gain(
        candidate: SourceCandidate,
        goal_graph: ResearchGoalGraph,
        covered_domains: set[str],
    ) -> float:
        gain = 0.5

        # 1. Uncovered Goal Bonus
        for gid in candidate.goal_ids:
            if gid in goal_graph.goals:
                goal = goal_graph.goals[gid]
                deficit = 1.0 - goal.coverage
                gain += 0.40 * deficit

        # 2. Source Lineage / Domain Novelty Bonus
        if candidate.domain not in covered_domains:
            gain += 0.20
        else:
            # Redundancy Penalty (DS-SI58)
            gain -= 0.15

        # 3. High Authority Prior Bonus
        if candidate.authority_prior >= 0.90:
            gain += 0.10

        return max(0.05, min(1.0, round(gain, 3)))


information_gain_scorer = InformationGainScorer()
