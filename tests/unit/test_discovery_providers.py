"""Unit tests for Discovery Providers and Provider Registry (DS-SI08 - DS-SI11)."""

import pytest
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
        tag = request.goal_id or request.query.replace(" ", "_")
        return [
            SourceCandidate(
                url=f"https://mock.org/{tag}_article_{i}",
                canonical_url=f"https://mock.org/{tag}_article_{i}",
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
        (
            mock_p,
            ProviderSearchRequest(query="test query 1", goal_id="g1", max_results=3),
        ),
        (
            mock_p,
            ProviderSearchRequest(query="test query 2", goal_id="g2", max_results=2),
        ),
    ]

    results = await reg.search_parallel(reqs, max_concurrency=2)
    assert len(results) == 5
    assert all(isinstance(c, SourceCandidate) for c in results)


def test_provider_policy_planning():
    policy = ProviderPolicy(registry=provider_registry)
    intent = ResearchIntent(
        original_query="melanoma immunotherapy treatment",
        normalized_query="melanoma immunotherapy treatment",
        task_type="medical",
    )
    goal = ResearchGoal(
        id="goal_med_1",
        question="What are standard treatments?",
        required_evidence_types=["GUIDELINE", "PRIMARY_RESEARCH"],
    )
    qv = [SearchQueryVariant(query="melanoma immunotherapy treatment", goal_id=goal.id)]

    planned = policy.plan_provider_requests(intent, goal, qv)
    assert len(planned) > 0
    provider_names = [p.descriptor.name for p, r in planned]
    assert any(
        name in provider_names
        for name in ("semantic_scholar", "openalex", "crossref", "europe_pmc", "pubmed")
    )
    # Anna's Archive must NOT be planned by default (opt-in only)
    assert "annas_archive" not in provider_names


@pytest.mark.asyncio
async def test_provider_concurrency_deterministic_merge_and_fault_isolation():
    import asyncio
    from scraper.discovery.providers.base import ProviderStatus

    class VariableLatencyProvider:
        def __init__(self, name: str, delay_sec: float, should_fail: bool = False):
            self.descriptor = ProviderDescriptor(name=name)
            self.delay_sec = delay_sec
            self.should_fail = should_fail

        async def search(self, request: ProviderSearchRequest):
            await asyncio.sleep(self.delay_sec)
            if self.should_fail:
                raise RuntimeError(f"Simulated fault in {self.descriptor.name}")
            return [
                SourceCandidate(
                    url=f"https://{self.descriptor.name}.org/p_{i}",
                    canonical_url=f"https://{self.descriptor.name}.org/p_{i}",
                    title=f"{self.descriptor.name} Title {i}",
                    provider=self.descriptor.name,
                    provider_rank=i,
                )
                for i in range(1, request.max_results + 1)
            ]

    p_slow = VariableLatencyProvider("p_slow", delay_sec=0.08)
    p_fast = VariableLatencyProvider("p_fast", delay_sec=0.01)
    p_err = VariableLatencyProvider("p_err", delay_sec=0.02, should_fail=True)

    reg = ProviderRegistry()
    reqs = [
        (p_slow, ProviderSearchRequest(query="q1", max_results=2)),
        (p_fast, ProviderSearchRequest(query="q2", max_results=2)),
        (p_err, ProviderSearchRequest(query="q3", max_results=2)),
    ]

    candidates, reports = await reg.search_parallel_with_reports(
        reqs, max_concurrency=3
    )

    # 1. Deterministic merge: p_slow was request 0, so its candidates come before p_fast (request 1)
    assert len(candidates) == 4
    assert candidates[0].provider == "p_slow"
    assert candidates[1].provider == "p_slow"
    assert candidates[2].provider == "p_fast"
    assert candidates[3].provider == "p_fast"

    # 2. Fault isolation: p_err error did not crash the batch and is reported accurately
    report_map = {r.provider_name: r for r in reports}
    assert report_map["p_slow"].status == ProviderStatus.SUCCESS
    assert report_map["p_fast"].status == ProviderStatus.SUCCESS
    assert report_map["p_err"].status == ProviderStatus.FAILED
    assert "Simulated fault" in (report_map["p_err"].error or "")


def test_domain_filter_parsed_hostname_isolation():
    from scraper.discovery.providers.registry import is_matching_domain

    target = "example.com"
    # Valid exact and subdomains
    assert is_matching_domain("https://example.com/page", target)
    assert is_matching_domain("https://sub.example.com/item", target)
    assert is_matching_domain("http://deep.nested.example.com", target)

    # Substring attacks or lookalikes must be rejected
    assert not is_matching_domain("https://fake-example.com/page", target)
    assert not is_matching_domain("https://example.com.attacker.org/phish", target)
    assert not is_matching_domain("https://malicious.org/example.com", target)
    assert not is_matching_domain("not_a_url", target)


@pytest.mark.asyncio
async def test_sota_academic_providers_registered():
    assert provider_registry.get("semantic_scholar") is not None
    assert provider_registry.get("openalex") is not None
    assert provider_registry.get("crossref") is not None
    assert provider_registry.get("regional_academic") is not None

    sem_scholar = provider_registry.get("semantic_scholar")
    assert "semanticscholar.org" in sem_scholar.descriptor.supported_domains

    openalex = provider_registry.get("openalex")
    assert "openalex.org" in openalex.descriptor.supported_domains

    crossref = provider_registry.get("crossref")
    assert "api.crossref.org" in crossref.descriptor.supported_domains

    regional = provider_registry.get("regional_academic")
    assert "cyberleninka.ru" in regional.descriptor.supported_domains
    assert "hal.science" in regional.descriptor.supported_domains
