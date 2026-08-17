"""Discovery Provider Selection Policy (DS-SI10).

Selects and configures optimal discovery providers based on intent, goals,
evidence preferences, and domain requirements without rigid hardcoded routing.
"""

from typing import List, Tuple
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
        max_requests_per_goal: int = 6,
    ) -> List[Tuple[DiscoveryProvider, ProviderSearchRequest]]:
        requests: List[Tuple[DiscoveryProvider, ProviderSearchRequest]] = []

        is_medical = "GUIDELINE" in goal.required_evidence_types or intent.task_type == "medical"
        is_academic = "PRIMARY_RESEARCH" in goal.required_evidence_types or intent.task_type in ("scientific", "medical")
        is_code = "SOURCE_CODE" in goal.required_evidence_types or intent.task_type in ("technical", "code")

        for qv in query_variants:
            if qv.goal_id != goal.id:
                continue

            # 1. Targeted Provider Hint
            if qv.provider_hint:
                p = self.registry.get(qv.provider_hint)
                if p:
                    requests.append((p, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=5, language=qv.language)))

            # 2. Domain & Evidence Matching
            if is_medical:
                p_pmc = self.registry.get("europe_pmc")
                p_pub = self.registry.get("pubmed")
                if p_pmc and not any(r[0] == p_pmc for r in requests):
                    requests.append((p_pmc, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=4, language="en")))
                if p_pub and not any(r[0] == p_pub for r in requests):
                    requests.append((p_pub, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=4, language="en")))

            if is_academic:
                p_arxiv = self.registry.get("arxiv")
                if p_arxiv and not any(r[0] == p_arxiv for r in requests):
                    requests.append((p_arxiv, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=4, language="en")))

            if is_code:
                p_gh = self.registry.get("github")
                if p_gh and not any(r[0] == p_gh for r in requests):
                    requests.append((p_gh, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=4, language="en")))

            # 3. Grounding & Open Web Fallback (WebSearch, Wikipedia & Anna's Archive)
            p_web = self.registry.get("web_search")
            if p_web and not any(r[0] == p_web for r in requests):
                requests.append((p_web, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=5, language=qv.language)))

            p_wiki = self.registry.get("wikipedia")
            if p_wiki and not any(r[0] == p_wiki for r in requests):
                requests.append((p_wiki, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=3, language=qv.language)))

            p_annas = self.registry.get("annas_archive")
            if p_annas and not any(r[0] == p_annas for r in requests):
                requests.append((p_annas, ProviderSearchRequest(query=qv.query, goal_id=goal.id, max_results=3, language=qv.language)))

            if len(requests) >= max_requests_per_goal:
                break

        return requests[:max_requests_per_goal]


provider_policy = ProviderPolicy()
