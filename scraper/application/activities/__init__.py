"""Application Activities Registry & Definitions (§4, DS-A09)."""

from typing import Any, Dict
from scraper.orchestration.protocol import ActivityResult, ResourceUsage
from scraper.orchestration.registry import activity_registry
from scraper.application.activities.discovery import run_discovery_activity
from scraper.application.activities.acquisition import run_acquisition_activity
from scraper.application.activities.extraction import run_extraction_activity
from scraper.application.activities.normalization import run_normalization_activity
from scraper.application.activities.indexing import run_indexing_activity
from scraper.application.activities.evidence import run_evidence_activity, run_coverage_evaluation_activity
from scraper.application.activities.export import run_export_activity


async def run_normalize_query_activity(input_data: Dict[str, Any]) -> ActivityResult:
    query = input_data.get("query", "").strip()
    return ActivityResult(
        data={"normalized_query": query},
        usage=ResourceUsage(),
        quality={"query_length": float(len(query))},
    )


async def run_plan_research_activity(input_data: Dict[str, Any]) -> ActivityResult:
    query = input_data.get("normalized_query", "")
    return ActivityResult(
        data={
            "research_plan": {
                "target_query": query,
                "strategy": "multi_source_academic",
            }
        },
        usage=ResourceUsage(),
        quality={"plan_valid": 1.0},
    )


async def run_rank_seeds_activity(input_data: Dict[str, Any]) -> ActivityResult:
    seeds = input_data.get("discovered_seeds", [])
    return ActivityResult(
        data={"ranked_seeds": seeds},
        usage=ResourceUsage(),
        quality={"ranked_count": float(len(seeds))},
    )


async def run_complete_research_activity(input_data: Dict[str, Any]) -> ActivityResult:
    return ActivityResult(
        data={"research_outcome": {"status": "SUCCESS", "message": "Research pipeline completed."}},
        usage=ResourceUsage(),
        quality={"final_quality": 1.0},
    )


# Register all activities in global registry
activity_registry.register("NormalizeQuery", run_normalize_query_activity)
activity_registry.register("PlanResearch", run_plan_research_activity)
activity_registry.register("DiscoverSources", run_discovery_activity)
activity_registry.register("RankSeeds", run_rank_seeds_activity)
activity_registry.register("AcquireBatch", run_acquisition_activity)
activity_registry.register("ExtractBatch", run_extraction_activity)
activity_registry.register("NormalizeBatch", run_normalization_activity)
activity_registry.register("IndexBatch", run_indexing_activity)
activity_registry.register("BuildEvidence", run_evidence_activity)
activity_registry.register("EvaluateCoverage", run_coverage_evaluation_activity)
activity_registry.register("BuildArchive", run_export_activity)
activity_registry.register("CompleteResearch", run_complete_research_activity)

__all__ = [
    "run_normalize_query_activity",
    "run_plan_research_activity",
    "run_discovery_activity",
    "run_rank_seeds_activity",
    "run_acquisition_activity",
    "run_extraction_activity",
    "run_normalization_activity",
    "run_indexing_activity",
    "run_evidence_activity",
    "run_coverage_evaluation_activity",
    "run_export_activity",
    "run_complete_research_activity",
]
