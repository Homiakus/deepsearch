"""Discovery activity implementation (§4, DS-A09, DS-A22, DS-A23)."""

from typing import Any, Dict, List
from scraper.discovery.seed_finder import discover_diverse_seeds
from scraper.orchestration.protocol import ActivityResult, ResourceUsage


async def run_discovery_activity(input_data: Dict[str, Any]) -> ActivityResult:
    """Discovers seed URLs from multiple academic, knowledge and web sources."""
    query = input_data.get("query", "")
    domain = input_data.get("domain")
    preferred_sources = input_data.get("preferred_sources", [])
    category = input_data.get("category")

    seeds = await discover_diverse_seeds(
        query=query,
        domain=domain,
        preferred_sources=preferred_sources,
        category=category,
    )

    usage = ResourceUsage(
        searchQueries=len(seeds) if seeds else 1,
        activeDurationNanos=0,
    )

    return ActivityResult(
        data={
            "query": query,
            "discovered_seeds": seeds,
            "total_discovered": len(seeds),
        },
        usage=usage,
        quality={"seed_count": float(len(seeds))},
    )
