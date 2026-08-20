"""Follow-Up Query Generator (DS-SI60).

Generates targeted follow-up search queries directly addressing identified research gaps.
"""

from typing import List
from scraper.research.gaps import ResearchGap
from scraper.search.query_models import SearchQueryVariant, QueryType


class FollowupQueryGenerator:
    """Produces targeted follow-up queries for uncovered gaps and contradictions."""

    @staticmethod
    def generate_followup_queries(gaps: List[ResearchGap]) -> List[SearchQueryVariant]:
        followups: List[SearchQueryVariant] = []

        for gap in gaps:
            if gap.gap_type == "UNRESOLVED_CONTRADICTION":
                # Contradiction resolution query
                q_text = f"{gap.target_topic} meta-analysis systematic review clinical evidence"
                followups.append(
                    SearchQueryVariant(
                        query=q_text,
                        goal_id=gap.goal_id,
                        query_type=QueryType.CONTRADICTION,
                        priority=0.95,
                    )
                )
            elif gap.gap_type == "UNCOVERED_GOAL":
                clean_q = gap.target_topic.replace(
                    "Answer primary research question: ", ""
                ).replace("Investigate characteristics and properties of ", "")
                followups.append(
                    SearchQueryVariant(
                        query=clean_q,
                        goal_id=gap.goal_id,
                        query_type=QueryType.FOLLOW_UP,
                        priority=0.85,
                    )
                )

        return followups


followup_query_generator = FollowupQueryGenerator()
