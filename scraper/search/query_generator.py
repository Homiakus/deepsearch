"""Search Query Variant Generator (DS-SI07).

Generates bounded, goal-directed query formulations without exponential query explosion.
"""

from typing import List
from scraper.research.intent import ResearchIntent
from scraper.research.goals import ResearchGoalGraph, ResearchGoal
from scraper.search.query_models import SearchQueryVariant, QueryType


class QueryGenerator:
    """Generates typed query variants per goal with budget caps."""

    def __init__(
        self, max_queries_per_goal: int = 4, max_total_query_variants: int = 16
    ):
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

    def _generate_for_goal(
        self, goal: ResearchGoal, intent: ResearchIntent
    ) -> List[SearchQueryVariant]:
        results: List[SearchQueryVariant] = []
        clean_q = intent.normalized_query

        # 1. Canonical / Semantic Query
        results.append(
            SearchQueryVariant(
                query=clean_q,
                language="ru"
                if intent.normalized_query
                and any(ord(c) > 127 for c in intent.normalized_query[:10])
                else "en",
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

        # 3. Scientific Cross-Lingual Mapping (RU/ZH/ES/DE -> EN)
        if any(ord(c) > 127 for c in clean_q):
            en_query = clean_q.lower()
            translations = [
                ("жидкостная биопсия", "liquid biopsy ctDNA circulating tumor DNA"),
                ("колоректальный рак", "colorectal cancer"),
                ("онкологи", "oncology"),
                ("квантов", "quantum"),
                ("лазерн", "laser cutting assist gas nozzle parameters"),
                ("резани", "machining parameters cutting speed feed rate"),
                ("титан", "titanium alloy Ti6Al4V"),
                ("печать", "3D printing additive manufacturing"),
                (
                    "алопец",
                    "alopecia androgenetica tofacitinib baricitinib JAK inhibitors",
                ),
                ("облысени", "hair loss alopecia treatment clinical trial"),
                ("иммунотерапи", "immunotherapy checkpoint inhibitors PD-1 CTLA-4"),
                ("нейросеть", "neural networks deep learning RAG LLM"),
                (
                    "первичное исследование",
                    "randomized clinical trial systematic review meta-analysis",
                ),
                ("научная статья", "journal article DOI"),
            ]
            for ru_term, en_replacement in translations:
                if ru_term in en_query:
                    en_query = en_query.replace(ru_term, en_replacement)

            if en_query != clean_q.lower():
                results.append(
                    SearchQueryVariant(
                        query=en_query,
                        language="en",
                        goal_id=goal.id,
                        query_type=QueryType.DOMAIN_SPECIFIC,
                        priority=0.92,
                    )
                )

        # 4. Primary Scientific Source Formulation (PubMed / Semantic Scholar / OpenAlex)
        if (
            "GUIDELINE" in goal.required_evidence_types
            or "PRIMARY_RESEARCH" in goal.required_evidence_types
            or "SYSTEMATIC_REVIEW" in goal.required_evidence_types
        ):
            results.append(
                SearchQueryVariant(
                    query=f"{clean_q} (systematic review OR meta-analysis OR clinical trial OR randomized controlled)",
                    language="en",
                    goal_id=goal.id,
                    query_type=QueryType.PRIMARY_SOURCE,
                    provider_hint="semantic_scholar",
                    priority=0.88,
                )
            )

        # 5. Multi-Regional Academic Formulation (HAL / CyberLeninka / CrossRef)
        results.append(
            SearchQueryVariant(
                query=clean_q,
                language="ru" if any(ord(c) > 127 for c in clean_q) else "en",
                goal_id=goal.id,
                query_type=QueryType.DOMAIN_SPECIFIC,
                provider_hint="regional_academic",
                priority=0.80,
            )
        )

        return results[: self.max_queries_per_goal]
