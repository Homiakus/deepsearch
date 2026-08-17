"""Unit tests for Discovery Providers and Provider Registry (DS-SI08 - DS-SI11)."""

import pytest
from unittest.mock import AsyncMock, patch
from scraper.discovery.providers.registry import ProviderRegistry, provider_registry
from scraper.discovery.providers.base import ProviderSearchRequest, ProviderDescriptor
from scraper.search.candidates import SourceCandidate
from scraper.discovery.provider_policy import ProviderPolicy
from scraper.research.intent import ResearchIntent
from scraper.research.goals import ResearchGoal
from scraper.search.query_models import SearchQueryVariant


class MockProvider:
    descriptor = ProviderDescriptor(
        name="mock_search",
        supported_domains=["mock.org"],
        supported_source_types=["PRIMARY_RESEARCH"],
    )

    async def search(self, request: ProviderSearchRequest):
        return [
            SourceCandidate(
                url=f"https://mock.org/article_{i}",
                canonical_url=f"https://mock.org/article_{i}",
                title=f"Mock Title {i}",
                snippet="Mock snippet text",
                provider=self.descriptor.name,
                provider_rank=i,
                goal_ids=[request.goal_id] if request.goal_id else [],
            )
            for i in range(1, request.max_results + 1)
        ]


@pytest.mark.asyncio
async def test_provider_registry_and_parallel_search():
    reg = ProviderRegistry()
    mock_p = MockProvider()
    reg.register(mock_p)

    assert reg.get("mock_search") is not None

    reqs = [
        (mock_p, ProviderSearchRequest(query="test query 1", goal_id="g1", max_results=3)),
        (mock_p, ProviderSearchRequest(query="test query 2", goal_id="g2", max_results=2)),
    ]

    results = await reg.search_parallel(reqs, max_concurrency=2)
    assert len(results) == 5
    assert all(isinstance(c, SourceCandidate) for c in results)


def test_provider_policy_planning():
    policy = ProviderPolicy(registry=provider_registry)
    intent = ResearchIntent(
        original_query="alopecia areata treatment",
        normalized_query="alopecia areata treatment",
        task_type="medical",
    )
    goal = ResearchGoal(
        id="goal_med_1",
        question="What are standard treatments?",
        required_evidence_types=["GUIDELINE", "PRIMARY_RESEARCH"],
    )
    qv = [SearchQueryVariant(query="alopecia areata treatment", goal_id=goal.id)]

    planned = policy.plan_provider_requests(intent, goal, qv)
    assert len(planned) > 0
    provider_names = [p.descriptor.name for p, r in planned]
    assert "europe_pmc" in provider_names or "pubmed" in provider_names or "wikipedia" in provider_names
