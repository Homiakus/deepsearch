"""Unit tests for DS-19: Removal of domain-specific root prototypes and unified research entrypoint."""

import json
from pathlib import Path
import pytest
from scraper.application.models import ResearchRequest
from scraper.application.service import DeepSearchService
from scraper.config import ExecutionMode


def test_root_prototypes_and_redundant_rules_are_absent():
    """Verify that domain-specific prototype scripts and legacy rules are deleted from repo root."""
    root_dir = Path(__file__).resolve().parent.parent.parent
    forbidden_files = [
        "deep_pdf_research_engine.py",
        "run_laser_research.py",
        "run_papanicolaou_lbc_research.py",
        "rule.md",
        "cycle-rule.md",
        "deepsearch_source_quality_analysis.md",
    ]
    for filename in forbidden_files:
        assert not (root_dir / filename).exists(), (
            f"File {filename} must not exist in repo root"
        )


def test_sample_research_queries_fixture_structure():
    """Verify sample research queries fixture contains valid data for research requests."""
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "sample_research_queries.json"
    )
    assert fixture_path.exists()

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 3

    for item in data:
        assert "id" in item
        assert "query" in item
        assert "topic" in item
        req = ResearchRequest(
            query=item["query"],
            domain=item.get("domain"),
            depth=1,
            max_pages=5,
            mode=ExecutionMode.BALANCED,
        )
        assert req.query == item["query"]


@pytest.mark.asyncio
async def test_single_research_entrypoint():
    """Verify single canonical research entrypoint DeepSearchService executes sample queries."""
    service = DeepSearchService()
    handle = await service.start_research(
        ResearchRequest(
            query="Photopolymer laser cutting parameters and heat affected zone",
            domain="engineering",
            depth=1,
            max_pages=2,
            mode=ExecutionMode.FAST,
        )
    )
    assert handle.run_id is not None
    assert handle.status is not None
