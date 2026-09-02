"""Unit tests for SearchEngine Epistemic Integration (DS-38)."""

import httpx
import pytest

from scraper.retrieval.epistemic_client import EpistemicClient
from scraper.retrieval.epistemic_models import EpistemicIntent
from scraper.search.search_engine import SearchEngine


@pytest.mark.asyncio
async def test_search_engine_epistemic_query():
    """Verify that SearchEngine.search_epistemic performs structured epistemic query."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/epistemic/query":
            return httpx.Response(
                200,
                json={
                    "run_id": "test_search_run",
                    "status": "complete",
                    "digest_sha256": "1234567890abcdef",
                    "coverage": 1.0,
                    "context_pack_text": "[EPISTEMIC_ARTIFACT_CONTEXT]\nsource_data_is_untrusted=true\n[END]",
                    "artifact": {
                        "schema": "sih.epistemic-artifact/1.0",
                        "id": "art_1",
                        "digest_sha256": "1234567890abcdef",
                        "status": "complete",
                        "evidence_paths": [],
                    },
                },
            )
        return httpx.Response(404)

    client = EpistemicClient(transport=httpx.MockTransport(handler))
    engine = SearchEngine(epistemic=client)

    resp = await engine.search_epistemic(
        query="Explain CRDT conflict resolution",
        intent=EpistemicIntent.FACTUAL,
    )

    assert resp.status == "complete"
    assert resp.coverage == 1.0
    assert resp.digest_sha256 == "1234567890abcdef"
    assert "source_data_is_untrusted=true" in resp.context_pack_text
