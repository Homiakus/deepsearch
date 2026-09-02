"""Unit tests for Keenable search discovery and AI clean markdown fetcher integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.acquisition.keenable_fetcher import KeenableFetcher, KeenableFetchResult
from scraper.config import ExecutionMode
from scraper.discovery.provider_policy import provider_policy
from scraper.discovery.providers.base import ProviderSearchRequest
from scraper.discovery.providers.keenable import KeenableSearchProvider
from scraper.discovery.providers.registry import provider_registry
from scraper.research.goals import ResearchGoal
from scraper.research.intent import ResearchIntent
from scraper.search.query_models import SearchQueryVariant


@pytest.mark.asyncio
async def test_keenable_search_provider_descriptor():
    provider = KeenableSearchProvider()
    assert provider.descriptor.name == "keenable"
    assert provider.descriptor.cost_class == "FREE"
    assert provider.descriptor.freshness_capability == "REALTIME"
    assert "en" in provider.descriptor.languages


@pytest.mark.asyncio
async def test_keenable_search_provider_public_search():
    provider = KeenableSearchProvider(api_key=None)

    mock_response_data = {
        "results": [
            {
                "title": "Attention Is All You Need",
                "url": "https://arxiv.org/abs/1706.03762",
                "snippet": "The Transformer architecture based solely on attention mechanisms.",
                "published_at": "2017-06-12T00:00:00Z",
            },
            {
                "title": "Transformer Tutorial",
                "url": "https://example.org/transformer-guide",
                "snippet": "A deep dive into self-attention and multi-head attention.",
                "published_at": "2023-01-01T00:00:00Z",
            },
        ]
    }

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = mock_response_data

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res
    ) as mock_post:
        req = ProviderSearchRequest(query="Attention Is All You Need", max_results=5)
        candidates = await provider.search(req)

        assert len(candidates) == 2
        assert candidates[0].title == "Attention Is All You Need"
        assert candidates[0].url == "https://arxiv.org/abs/1706.03762"
        assert candidates[0].provider == "keenable"
        assert candidates[0].source_type == "PRIMARY_RESEARCH"

        # Check call arguments
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["X-Keenable-Title"] == "DeepSearch"
        assert "X-API-Key" not in call_kwargs["headers"]
        assert call_kwargs["json"]["query"] == "Attention Is All You Need"
        assert call_kwargs["json"]["mode"] == "pro"


@pytest.mark.asyncio
async def test_keenable_search_provider_authenticated_search():
    provider = KeenableSearchProvider(api_key="test-api-key-123")

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"results": []}

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res
    ) as mock_post:
        req = ProviderSearchRequest(query="PostgreSQL Locking", max_results=5)
        await provider.search(req)

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["X-API-Key"] == "test-api-key-123"


@pytest.mark.asyncio
async def test_keenable_fetcher_success():
    fetcher = KeenableFetcher()

    mock_data = {
        "url": "https://example.com/deepsearch",
        "title": "DeepSearch Documentation",
        "content": "# DeepSearch\n\nAdaptive web scraper platform.",
        "description": "Platform docs",
        "author": "DeepSearch Team",
    }

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_res):
        res = await fetcher.fetch("https://example.com/deepsearch")
        assert res.success is True
        assert res.title == "DeepSearch Documentation"
        assert "Adaptive web scraper" in res.clean_markdown


@pytest.mark.asyncio
async def test_keenable_registry_registration():
    p = provider_registry.get("keenable")
    assert p is not None
    assert p.descriptor.name == "keenable"


@pytest.mark.asyncio
async def test_keenable_provider_policy_planning():
    intent = ResearchIntent(
        original_query="Quantum Computing Surface Codes",
        normalized_query="quantum computing surface codes",
        task_type="scientific",
    )
    goal = ResearchGoal(
        id="goal_1",
        goal_query="Quantum Computing Surface Codes",
        question="What are quantum surface codes?",
        required_evidence_types=["PRIMARY_RESEARCH"],
    )
    variants = [
        SearchQueryVariant(goal_id="goal_1", query="Quantum Computing Surface Codes")
    ]

    reqs = provider_policy.plan_provider_requests(intent, goal, variants)
    prov_names = [p.descriptor.name for p, _ in reqs]
    assert "keenable" in prov_names


@pytest.mark.asyncio
async def test_adaptive_acquisition_engine_keenable_fallback():
    mock_http_fetcher = MagicMock()
    mock_http_fetcher.fetch = AsyncMock(
        side_effect=Exception("HTTP Network Unreachable")
    )

    mock_browser_pool = MagicMock()
    mock_browser_pool.is_available.return_value = True
    mock_browser_pool.fetch_page = AsyncMock(
        side_effect=Exception("ERR_HTTP2_PROTOCOL_ERROR")
    )

    engine = AdaptiveAcquisitionEngine(
        http_fetcher=mock_http_fetcher,
        browser_pool=mock_browser_pool,
    )

    mock_k_res = KeenableFetchResult(
        url="https://challenging-site.org/paper",
        title="Recovered Paper",
        clean_markdown="# Recovered Title\n\nContent via Keenable AI.",
        success=True,
    )

    with patch(
        "scraper.acquisition.keenable_fetcher.keenable_fetcher.fetch",
        new_callable=AsyncMock,
        return_value=mock_k_res,
    ):
        artifact = await engine.acquire_page(
            url="https://challenging-site.org/paper",
            canonical_url="https://challenging-site.org/paper",
            mode=ExecutionMode.BALANCED,
        )

        assert artifact.strategy_used == "L2_KEENABLE"
        assert artifact.status_code == 200
        assert "Recovered Title" in artifact.text_content
