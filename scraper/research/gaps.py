"""Research Gap Analyzer (DS-SI59).

Identifies under-covered goals, weakly supported claims, and unresolved contradictions.
"""

from typing import List
from pydantic import BaseModel, Field
from scraper.research.goals import ResearchGoalGraph, GoalStatus
from scraper.evidence.store import EvidenceStore


class ResearchGap(BaseModel):
    gap_type: str  # UNCOVERED_GOAL, WEAKLY_SUPPORTED_CLAIM, UNRESOLVED_CONTRADICTION, MISSING_PRIMARY_SOURCE
    goal_id: str
    target_topic: str
    suggested_focus: str
    priority: float = 1.0


class GapAnalyzer:
    """Analyzes evidence graph and goal graph to generate actionable research gaps."""

    @staticmethod
    def identify_gaps(goal_graph: ResearchGoalGraph, store: EvidenceStore) -> List[ResearchGap]:
        gaps: List[ResearchGap] = []

        # 1. Uncovered Subgoals
        for goal in goal_graph.goals.values():
            if goal.coverage < 0.6:
                gaps.append(
                    ResearchGap(
                        gap_type="UNCOVERED_GOAL",
                        goal_id=goal.id,
                        target_topic=goal.question,
                        suggested_focus="General evidence acquisition for goal",
                        priority=1.0 - goal.coverage,
                    )
                )

        # 2. Unresolved Contradictions
        for claim in store.get_contradictions():
            gaps.append(
                ResearchGap(
                    gap_type="UNRESOLVED_CONTRADICTION",
                    goal_id=claim.goal_id or goal_graph.root_goal_id or "",
                    target_topic=claim.statement,
                    suggested_focus="Resolve dispute with peer-reviewed meta-analysis or authoritative regulator guideline",
                    priority=0.95,
                )
            )

        return gaps


gap_analyzer = GapAnalyzer()
