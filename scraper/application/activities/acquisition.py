"""Acquisition activity implementation (§4, DS-A09, DS-A15, DS-A16)."""

from typing import Any, Dict, List
from scraper.config import ExecutionMode
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.orchestration.protocol import ActivityResult, ResourceUsage


async def run_acquisition_activity(input_data: Dict[str, Any]) -> ActivityResult:
    """Acquires a batch of URLs using adaptive acquisition strategies."""
    engine = AdaptiveAcquisitionEngine()
    seeds: List[str] = input_data.get("ranked_seeds", []) or input_data.get(
        "discovered_seeds", []
    )
    mode_str = input_data.get("mode", "balanced")
    mode = ExecutionMode(mode_str) if isinstance(mode_str, str) else mode_str

    acquired_artifacts = []
    browser_fetches = 0

    for url in seeds:
        c_url = canonicalize_url(url)
        try:
            artifact = await engine.acquire_page(url, c_url, mode=mode)
            if artifact.strategy_used in ("PLAYWRIGHT_BROWSER", "BROWSER"):
                browser_fetches += 1

            acquired_artifacts.append(
                {
                    "url": artifact.url,
                    "canonical_url": artifact.canonical_url,
                    "status_code": artifact.status_code,
                    "content_type": artifact.content_type,
                    "strategy_used": artifact.strategy_used,
                    "html_content": artifact.text_content,
                    "page_intelligence": artifact.page_intelligence.model_dump()
                    if artifact.page_intelligence
                    else {},
                }
            )
        except Exception as e:
            # Degraded acquisition per URL without terminating whole batch
            acquired_artifacts.append(
                {
                    "url": url,
                    "canonical_url": c_url,
                    "status_code": 500,
                    "error": str(e),
                }
            )

    usage = ResourceUsage(
        browserFetches=browser_fetches,
        cost=1.0 * len(acquired_artifacts) + 9.0 * browser_fetches,
    )

    return ActivityResult(
        data={
            "acquired_artifacts": acquired_artifacts,
            "total_acquired": len(acquired_artifacts),
        },
        usage=usage,
        quality={
            "success_rate": float(
                len([a for a in acquired_artifacts if a.get("status_code", 0) < 400])
            )
            / max(len(acquired_artifacts), 1)
        },
    )
