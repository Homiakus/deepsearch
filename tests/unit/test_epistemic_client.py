"""Unit tests for EpistemicClient and Epistemic Models (DS-37)."""

import httpx
import pytest

from scraper.retrieval.epistemic_client import EpistemicClient
from scraper.retrieval.epistemic_models import (
    EpistemicNodeInput,
    EpistemicNodeKind,
    EpistemicQueryRequest,
    EpistemicRequirementInput,
    EpistemicRequirementKind,
)


@pytest.mark.asyncio
async def test_epistemic_client_mock_transport():
    """Verify that EpistemicClient interacts correctly with HTTP transport mocks."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/epistemic/health":
            return httpx.Response(200, json={"status": "ok", "engine": "SncSinCore"})
        if request.url.path == "/api/v1/epistemic/query":
            return httpx.Response(
                200,
                json={
                    "run_id": "mock_run",
                    "status": "complete",
                    "digest_sha256": "abcdef1234567890",
                    "coverage": 0.95,
                    "context_pack_text": "[EPISTEMIC_ARTIFACT_CONTEXT]\nsource_data_is_untrusted=true\n[END]",
                    "artifact": {
                        "schema": "sih.epistemic-artifact/1.0",
                        "id": "art_mock",
                        "digest_sha256": "abcdef1234567890",
                        "status": "complete",
                        "evidence_paths": [],
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = EpistemicClient(transport=transport)

    assert await client.is_healthy() is True

    req = EpistemicQueryRequest(
        run_id="mock_run",
        text="Sample test question",
    )
    resp = await client.query(req)
    assert resp.status == "complete"
    assert resp.coverage == 0.95
    assert resp.digest_sha256 == "abcdef1234567890"
    assert "source_data_is_untrusted=true" in resp.context_pack_text


@pytest.mark.asyncio
async def test_epistemic_client_fallback_ingest_and_query():
    """Verify deterministic in-memory fallback when Go daemon is not running."""
    client = EpistemicClient(base_url="http://127.0.0.1:9999", fallback_enabled=True)

    # Ingest nodes into fallback
    nodes = [
        EpistemicNodeInput(
            id="claim:caffeine",
            kind=EpistemicNodeKind.PROPOSITION,
            text="Caffeine increases vigilance and reduces reaction time.",
            context="neuroscience",
            scope="public",
            provenance_cluster="trial-2024",
        )
    ]
    ingest_res = await client.ingest(
        "run-1", "doc-1", "https://example.com/caffeine", nodes
    )
    assert ingest_res["total_nodes"] == 1
    assert ingest_res.get("fallback") is True

    # Query
    req = EpistemicQueryRequest(
        run_id="run-1",
        text="Does caffeine reduce reaction time?",
        requirements=[
            EpistemicRequirementInput(
                id="req-1",
                kind=EpistemicRequirementKind.FACT,
                text="Verify reaction time reduction",
            )
        ],
    )
    res = await client.query(req)
    assert res.status == "complete"
    assert len(res.artifact.evidence_paths) == 1
    assert "Caffeine increases vigilance" in res.context_pack_text
    assert "source_data_is_untrusted=true" in res.context_pack_text
