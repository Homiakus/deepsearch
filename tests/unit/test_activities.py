"""Unit tests for application activities and execution context (DS-A09, DS-A10)."""

import pytest

from scraper.application.activities import (
    run_coverage_evaluation_activity,
    run_evidence_activity,
    run_indexing_activity,
    run_normalization_activity,
    run_normalize_query_activity,
    run_plan_research_activity,
)
from scraper.application.context import ResearchExecutionContext
from scraper.orchestration.registry import activity_registry


def test_activity_registration():
    activities = activity_registry.list_activities()
    assert "NormalizeQuery" in activities
    assert "PlanResearch" in activities
    assert "DiscoverSources" in activities
    assert "RankSeeds" in activities
    assert "AcquireBatch" in activities
    assert "ExtractBatch" in activities
    assert "NormalizeBatch" in activities
    assert "IndexBatch" in activities
    assert "BuildEvidence" in activities
    assert "EvaluateCoverage" in activities
    assert "BuildArchive" in activities
    assert "CompleteResearch" in activities


def test_research_execution_context():
    ctx = ResearchExecutionContext(execution_id="e1", run_id="r1")
    assert ctx.execution_id == "e1"
    assert ctx.run_id == "r1"
    assert not ctx.is_cancelled
    assert ctx.elapsed_seconds() >= 0


@pytest.mark.asyncio
async def test_normalize_and_plan_activity():
    norm_res = await run_normalize_query_activity(
        {"query": "  Deep Learning in Medicine  "}
    )
    assert norm_res.data["normalized_query"] == "Deep Learning in Medicine"

    plan_res = await run_plan_research_activity(norm_res.data)
    assert "research_plan" in plan_res.data


@pytest.mark.asyncio
async def test_normalization_and_indexing_activity():
    norm_res = await run_normalization_activity(
        {
            "extracted_docs": [
                {
                    "url": "https://example.com/1",
                    "clean_markdown": "Sample text for chunking and indexing test 1",
                },
                {
                    "url": "https://example.com/1",
                    "clean_markdown": "Sample text for chunking and indexing test 1",
                },
            ]
        }
    )
    assert norm_res.data["total_normalized"] == 1
    assert norm_res.data["duplicates_removed"] == 1

    idx_res = await run_indexing_activity(norm_res.data)
    assert "indexed_chunks" in idx_res.data
    assert idx_res.data["total_chunks"] >= 1

    ev_res = await run_evidence_activity(idx_res.data)
    assert "evidence_graph" in ev_res.data

    cov_res = await run_coverage_evaluation_activity(ev_res.data)
    assert "coverage_evaluation" in cov_res.data
