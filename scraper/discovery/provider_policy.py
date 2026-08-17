"""Discovery Provider Selection Policy (DS-SI10).

Selects and configures optimal discovery providers based on intent, goals,
evidence preferences, and domain requirements without rigid hardcoded routing.
"""

from typing import List, Tuple, Optional
from scraper.discovery.providers.base import DiscoveryProvider, ProviderSearchRequest
from scraper.discovery.providers.registry import ProviderRegistry, provider_registry
from scraper.research.intent import ResearchIntent, FreshnessRequirement
from scraper.research.goals import ResearchGoal
from scraper.search.query_models import SearchQueryVariant


class ProviderPolicy:
    """Evaluates suitability of providers for a set of goal query variants."""

    def __init__(self, registry: ProviderRegistry = provider_registry):
        self.registry = registry

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
            "cancer", "tumor", "dna", "rna", "crispr", "clinical", "disease", "drug",
            "trial", "therapy", "biopsy", "cell", "protein", "gene", "mutation",
            "oncology", "patient", "syndrome", "inhibitor", "alopecia", "antibody"
        }
        has_medical_kw = any(kw in q_lower for kw in medical_keywords)

        is_medical = (
            "GUIDELINE" in goal.required_evidence_types
            or intent.task_type in ("medical", "bio", "healthcare")
            or has_medical_kw
        )
        is_academic = (
            "PRIMARY_RESEARCH" in goal.required_evidence_types
            or intent.task_type in ("scientific", "medical", "general_research", "engineering")
            or True
        )
        is_code = (
            "SOURCE_CODE" in goal.required_evidence_types
            or intent.task_type in ("technical", "code")
        )

        batch_size = max_results_per_provider or min(max(5, target_pool_size // 2), 50)

        for qv in query_variants:
            if qv.goal_id != goal.id:
                continue

            # 1. Targeted Provider Hint
            if qv.provider_hint:
                p = self.registry.get(qv.provider_hint)
                if p:
                    requests.append((p, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=batch_size, language=qv.language)))

            # 2. Domain & Evidence Matching
            if is_medical:
                p_pmc = self.registry.get("europe_pmc")
                p_pub = self.registry.get("pubmed")
                if p_pmc and not any(r[0] == p_pmc for r in requests):
                    requests.append((p_pmc, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=batch_size, language="en")))
                if p_pub and not any(r[0] == p_pub for r in requests):
                    requests.append((p_pub, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=batch_size, language="en")))

            if is_academic:
                p_arxiv = self.registry.get("arxiv")
                if p_arxiv and not any(r[0] == p_arxiv for r in requests):
                    requests.append((p_arxiv, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=batch_size, language="en")))

            if is_code:
                p_gh = self.registry.get("github")
                if p_gh and not any(r[0] == p_gh for r in requests):
                    requests.append((p_gh, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=min(batch_size, 10), language="en")))

            # 3. Grounding & Open Web Fallback (WebSearch, Wikipedia & Anna's Archive)
            p_web = self.registry.get("web_search")
            if p_web and not any(r[0] == p_web for r in requests):
                requests.append((p_web, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=min(batch_size, 15), language=qv.language)))

            p_annas = self.registry.get("annas_archive")
            if p_annas and not any(r[0] == p_annas for r in requests):
                requests.append((p_annas, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=min(batch_size, 10), language=qv.language)))

            p_wiki = self.registry.get("wikipedia")
            if p_wiki and not any(r[0] == p_wiki for r in requests):
                requests.append((p_wiki, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=min(batch_size, 5), language=qv.language)))

            if len(requests) >= max_requests_per_goal:
                break

        return requests[:max_requests_per_goal]


provider_policy = ProviderPolicy()
