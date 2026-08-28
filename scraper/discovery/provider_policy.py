"""Discovery Provider Selection Policy (DS-SI10).

Selects and configures optimal discovery providers based on intent, goals,
evidence preferences, and domain requirements without rigid hardcoded routing.
"""

from typing import List, Tuple, Optional, Dict, Any
from scraper.discovery.providers.base import DiscoveryProvider, ProviderSearchRequest
from scraper.discovery.providers.registry import ProviderRegistry, provider_registry
from scraper.research.intent import ResearchIntent
from scraper.research.goals import ResearchGoal
from scraper.search.query_models import SearchQueryVariant


class ProviderYieldTracker:
    """Tracks historical success, latency, and candidate yield of discovery providers (DS-SI10)."""

    def __init__(self):
        self._stats: Dict[str, Dict[str, Any]] = {}

    def record_call(
        self, provider_name: str, candidate_count: int, error: bool = False
    ):
        if provider_name not in self._stats:
            self._stats[provider_name] = {
                "calls": 0,
                "errors": 0,
                "total_candidates": 0,
            }
        s = self._stats[provider_name]
        s["calls"] += 1
        if error:
            s["errors"] += 1
        s["total_candidates"] += candidate_count

    def get_health_factor(self, provider_name: str) -> float:
        s = self._stats.get(provider_name)
        if not s or s["calls"] == 0:
            return 1.0
        error_rate = s["errors"] / s["calls"]
        if error_rate >= 0.8 and s["calls"] >= 3:
            return 0.2
        if error_rate >= 0.5:
            return 0.6
        return 1.0


provider_yield_tracker = ProviderYieldTracker()


class ProviderPolicy:
    """Evaluates suitability of providers for a set of goal query variants."""

    def __init__(
        self,
        registry: ProviderRegistry = provider_registry,
        yield_tracker: ProviderYieldTracker = provider_yield_tracker,
    ):
        self.registry = registry
        self.yield_tracker = yield_tracker

    def plan_provider_requests(
        self,
        intent: ResearchIntent,
        goal: ResearchGoal,
        query_variants: List[SearchQueryVariant],
        max_requests_per_goal: int = 8,
        target_pool_size: int = 25,
        max_results_per_provider: Optional[int] = None,
    ) -> List[Tuple[DiscoveryProvider, ProviderSearchRequest]]:
        requests: List[Tuple[DiscoveryProvider, ProviderSearchRequest]] = []

        q_lower = (intent.normalized_query or intent.original_query or "").lower()
        medical_keywords = {
            "cancer",
            "tumor",
            "dna",
            "rna",
            "crispr",
            "clinical",
            "disease",
            "drug",
            "trial",
            "therapy",
            "biopsy",
            "cell",
            "protein",
            "gene",
            "mutation",
            "oncology",
            "patient",
            "syndrome",
            "inhibitor",
            "alopecia",
            "antibody",
        }
        has_medical_kw = any(kw in q_lower for kw in medical_keywords)

        is_medical = (
            "GUIDELINE" in goal.required_evidence_types
            or intent.task_type in ("medical", "bio", "healthcare")
            or has_medical_kw
        )
        is_academic = (
            "PRIMARY_RESEARCH" in goal.required_evidence_types
            or intent.task_type
            in ("scientific", "medical", "general_research", "engineering")
            or True
        )
        is_code = "SOURCE_CODE" in goal.required_evidence_types or intent.task_type in (
            "technical",
            "code",
        )

        batch_size = max_results_per_provider or min(max(5, target_pool_size // 2), 50)

        for qv in query_variants:
            if qv.goal_id != goal.id:
                continue

            # 1. Targeted Provider Hint
            if qv.provider_hint:
                p = self.registry.get(qv.provider_hint)
                if p:
                    requests.append(
                        (
                            p,
                            ProviderSearchRequest(
                                query=qv.query,
                                goal_id=goal.id,
                                max_results=batch_size,
                                language=qv.language,
                            ),
                        )
                    )

            # 2. Domain & Evidence Matching
            if is_medical:
                for prov_name in (
                    "pubmed",
                    "europe_pmc",
                    "semantic_scholar",
                    "openalex",
                ):
                    p = self.registry.get(prov_name)
                    if p and not any(r[0] == p for r in requests):
                        requests.append(
                            (
                                p,
                                ProviderSearchRequest(
                                    query=qv.query,
                                    goal_id=goal.id,
                                    max_results=batch_size,
                                    language="en",
                                ),
                            )
                        )

            if is_academic:
                for prov_name in (
                    "semantic_scholar",
                    "openalex",
                    "crossref",
                    "arxiv",
                    "regional_academic",
                ):
                    p = self.registry.get(prov_name)
                    if p and not any(r[0] == p for r in requests):
                        requests.append(
                            (
                                p,
                                ProviderSearchRequest(
                                    query=qv.query,
                                    goal_id=goal.id,
                                    max_results=batch_size,
                                    language=qv.language,
                                ),
                            )
                        )

            if is_code:
                p_gh = self.registry.get("github")
                if p_gh and not any(r[0] == p_gh for r in requests):
                    requests.append(
                        (
                            p_gh,
                            ProviderSearchRequest(
                                query=qv.query,
                                goal_id=goal.id,
                                max_results=min(batch_size, 10),
                                language="en",
                            ),
                        )
                    )

            # 3. Grounding & Open Web Fallback (WebSearch, Anna's Archive & Wikipedia)
            for prov_name, limit in [
                ("web_search", 15),
                ("annas_archive", 10),
                ("wikipedia", 5),
            ]:
                p = self.registry.get(prov_name)
                if p and not any(r[0] == p for r in requests):
                    requests.append(
                        (
                            p,
                            ProviderSearchRequest(
                                query=qv.query,
                                goal_id=goal.id,
                                max_results=min(batch_size, limit),
                                language=qv.language,
                            ),
                        )
                    )

            if len(requests) >= max_requests_per_goal:
                break

        return requests[:max_requests_per_goal]


provider_policy = ProviderPolicy()
