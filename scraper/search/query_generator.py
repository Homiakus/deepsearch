"""Search Query Variant Generator (DS-SI07).

Generates bounded, goal-directed query formulations without exponential query explosion.
"""

from typing import List, Optional
from scraper.research.intent import ResearchIntent
from scraper.research.goals import ResearchGoalGraph, ResearchGoal
from scraper.search.query_models import SearchQueryVariant, QueryType


class QueryGenerator:
    """Generates typed query variants per goal with budget caps."""

    def __init__(self, max_queries_per_goal: int = 4, max_total_query_variants: int = 16):
        self.max_queries_per_goal = max_queries_per_goal
        self.max_total_query_variants = max_total_query_variants

    def generate_variants(
        self, intent: ResearchIntent, goal_graph: ResearchGoalGraph
    ) -> List[SearchQueryVariant]:
        variants: List[SearchQueryVariant] = []
        seen_queries = set()

        for goal in goal_graph.goals.values():
            goal_variants = self._generate_for_goal(goal, intent)
            for v in goal_variants:
                q_key = (v.query.lower().strip(), v.language)
                if q_key not in seen_queries:
                    seen_queries.add(q_key)
                    variants.append(v)
                    if len(variants) >= self.max_total_query_variants:
                        return variants

        return variants

    def _generate_for_goal(self, goal: ResearchGoal, intent: ResearchIntent) -> List[SearchQueryVariant]:
        results: List[SearchQueryVariant] = []
        clean_q = intent.normalized_query

        # 1. Canonical / Semantic Query
        results.append(
            SearchQueryVariant(
                query=clean_q,
                language="ru" if intent.normalized_query and any(ord(c) > 127 for c in intent.normalized_query[:10]) else "en",
                goal_id=goal.id,
                query_type=QueryType.SEMANTIC,
                priority=1.0,
            )
        )

        # 2. Entity Exact Query if entities present
        if intent.entities:
            exact_tokens = [e.canonical_form or e.name for e in intent.entities[:3]]
            results.append(
                SearchQueryVariant(
                    query=" ".join(exact_tokens),
                    language="en",
                    goal_id=goal.id,
                    query_type=QueryType.ENTITY,
                    priority=0.9,
                )
            )

        # 3. English translation / cross-lingual variant if query is in Russian
        if any(ord(c) > 1000 for c in clean_q):
            # Medical or engineering translation heuristics
            en_query = clean_q
            if "алопец" in clean_q.lower() or "облысени" in clean_q.lower():
                en_query = clean_q.lower().replace("алопеции", "alopecia").replace("алопеция", "alopecia")
            elif "режимы резания" in clean_q.lower():
                en_query = "cutting parameters machining titanium alloys milling feed speed"
            elif "3d" in clean_q.lower() or "lcd" in clean_q.lower() or "печать" in clean_q.lower() or "принтер" in clean_q.lower() or "фотополимер" in clean_q.lower():
                en_query = "LCD MSLA resin 3D printing parameters exposure peeling speed"
            if en_query != clean_q:
                results.append(
                    SearchQueryVariant(
                        query=en_query,
                        language="en",
                        goal_id=goal.id,
                        query_type=QueryType.DOMAIN_SPECIFIC,
                        priority=0.85,
                    )
                )

        # 4. Primary Source Query
        if "GUIDELINE" in goal.required_evidence_types or "PRIMARY_RESEARCH" in goal.required_evidence_types:
            results.append(
                SearchQueryVariant(
                    query=f"{clean_q} clinical trial guideline systematic review",
                    language="en",
                    goal_id=goal.id,
                    query_type=QueryType.PRIMARY_SOURCE,
                    provider_hint="pubmed",
                    priority=0.8,
                )
            )

        return results[: self.max_queries_per_goal]
