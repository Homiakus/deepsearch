"""DeepSearch Model Context Protocol (MCP) Server (§100, DS-A02, DS-A03).

Exposes DeepSearch research, inspection, extraction, and hybrid retrieval tools
to LLM clients (Claude, Cursor, Antigravity, VS Code, etc.) over standard MCP interfaces.
"""

import asyncio
import json
import logging
from typing import Optional, List
from mcp.server.fastmcp import FastMCP

from scraper.config import settings, ExecutionMode
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.extraction.engine import ExtractionEngine
from scraper.search.search_engine import SearchEngine
from scraper.discovery.seed_finder import discover_diverse_seeds
from scraper.application.models import ResearchRequest, RunLifecycleState
from scraper.application.research_service import research_service

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="deepsearch",
    instructions="DeepSearch Adaptive Scraping, Extraction, and Research Platform MCP Server"
)

search_engine = SearchEngine()
acquisition_engine = AdaptiveAcquisitionEngine()


@mcp.tool()
async def deepsearch_research(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    depth: int = 3,
    max_pages: int = 50,
    mode: str = "balanced",
    output_archive: Optional[str] = None,
    category: Optional[str] = None,
    auto_discover: bool = True
) -> str:
    """Executes end-to-end DeepSearch research pipeline via ResearchApplicationService (DS-A02)."""
    sources = preferred_sources or []
    req = ResearchRequest(
        query=query,
        domain=domain,
        preferred_sources=sources,
        depth=depth,
        max_pages=max_pages,
        mode=ExecutionMode(mode),
        output_archive_path=output_archive or f"deepsearch_mcp_{query.replace(' ', '_')[:20]}.zip",
        auto_discover=auto_discover,
        category=category,
    )
    handle = await research_service.start(req)

    # Wait for completion in MCP sync wrapper
    while True:
        await asyncio.sleep(0.5)
        st = await research_service.status(handle.run_id)
        if st.status in (
            RunLifecycleState.COMPLETED,
            RunLifecycleState.INSUFFICIENT_EVIDENCE,
            RunLifecycleState.FAILED,
            RunLifecycleState.CANCELLED,
        ):
            break

    res = await research_service.result(handle.run_id)
    if res and res.status in (RunLifecycleState.COMPLETED, RunLifecycleState.INSUFFICIENT_EVIDENCE):
        return json.dumps({
            "status": "success",
            "quality_status": res.status.value,
            "run_id": res.run_id,
            "query": res.query,
            "total_pages_processed": res.total_pages_processed,
            "total_rag_chunks": res.total_rag_chunks,
            "archive_path": res.archive_path,
            "output_directory": res.dir_path,
            "manifest": res.manifest
        }, indent=2, ensure_ascii=False)
    else:
        st = await research_service.status(handle.run_id)
        return json.dumps({
            "status": "failed",
            "run_id": handle.run_id,
            "error": st.error_message or "Unknown failure"
        }, indent=2, ensure_ascii=False)


@mcp.tool()
async def deepsearch_discover(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    category: Optional[str] = None
) -> str:
    """Discovers diverse seed URLs from multiple academic and knowledge sources."""
    seeds = await discover_diverse_seeds(
        query=query,
        domain=domain,
        preferred_sources=preferred_sources,
        category=category
    )
    return json.dumps({
        "status": "success",
        "query": query,
        "total_seeds": len(seeds),
        "seeds": seeds
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def deepsearch_inspect(url: str) -> str:
    """Inspects a target URL and returns page intelligence metrics and recommended strategy."""
    c_url = canonicalize_url(url)
    artifact = await acquisition_engine.acquire_page(url, c_url, mode=ExecutionMode.BALANCED)
    pi = artifact.page_intelligence

    rec_strategy = "HTTP"
    if pi.js_dependency_score >= settings.adaptive.browser_threshold:
        rec_strategy = "PLAYWRIGHT BROWSER"
    if pi.api_score >= 0.7:
        rec_strategy = "DIRECT API"

    return json.dumps({
        "url": url,
        "canonical_url": c_url,
        "http_status": artifact.status_code,
        "content_type": artifact.content_type,
        "static_score": pi.static_score,
        "js_dependency_score": pi.js_dependency_score,
        "detected_apis_count": len(pi.detected_apis),
        "tables_count": pi.tables_count,
        "canvas_detected": pi.has_canvas,
        "visual_score": pi.visual_score,
        "recommended_strategy": rec_strategy,
        "estimated_cost": 1.0 if rec_strategy == "HTTP" else 10.0
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def deepsearch_extract(url: str) -> str:
    """Extracts raw/clean/fit Markdown, records, and tables from a target URL."""
    c_url = canonicalize_url(url)
    artifact = await acquisition_engine.acquire_page(url, c_url, mode=ExecutionMode.BALANCED)
    result = ExtractionEngine.extract_from_html(url, artifact.text_content)

    return json.dumps({
        "url": url,
        "clean_markdown": result.clean_markdown,
        "fit_markdown": result.fit_markdown,
        "tables_count": len(result.tables),
        "extracted_records_count": len(result.extracted_records)
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def deepsearch_search(query: str, limit: int = 10) -> str:
    """Searches indexed content using text, visual, and hybrid multivector retrieval without fake results."""
    state = search_engine.get_feature_state()
    results = search_engine.search_hybrid(query, limit=limit)
    return json.dumps({
        "query": query,
        "state": state.value,
        "results": [r.model_dump() for r in results],
        "count": len(results)
    }, indent=2, ensure_ascii=False)


def run_mcp_server():
    """Runs the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
