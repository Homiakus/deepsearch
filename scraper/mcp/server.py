"""DeepSearch Model Context Protocol (MCP) Server (§100, DS-A02, DS-A03).

Exposes DeepSearch research, inspection, extraction, and hybrid retrieval tools
to LLM clients (Claude, Cursor, Antigravity, VS Code, etc.) over standard MCP interfaces.
Hardened for enterprise production reliability, memory safety, cancellation propagation,
strict schema validation, and path confinement.
"""

import sys
import re
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List, Literal
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
    instructions="DeepSearch Adaptive Scraping, Extraction, and Research Platform MCP Server",
)

search_engine = SearchEngine()
acquisition_engine = AdaptiveAcquisitionEngine()

ALLOWED_MODES = {"fast", "balanced", "complete", "research"}
MAX_DEPTH = 10
MAX_PAGES = 500
MAX_SEARCH_LIMIT = 100


def sanitize_archive_path(archive_path: Optional[str], default_filename: str) -> str:
    """Ensures archive path is safe, normalized, and confined to the current working directory or subfolders.

    Prevents path traversal attacks (e.g., `../../etc/shadow` or absolute system overwrites).
    """
    if not archive_path:
        safe_name = re.sub(r"[^\w\-.]", "_", default_filename)
        return safe_name if safe_name.endswith(".zip") else f"{safe_name}.zip"

    # Strip dangerous leading drive letters or traversal components
    clean_p = Path(archive_path)

    # Restrict filename to prevent directory traversal
    filename = clean_p.name
    if not filename or filename in (".", ".."):
        filename = default_filename

    safe_name = re.sub(r"[^\w\-.]", "_", filename)
    if not safe_name.endswith(".zip"):
        safe_name = f"{safe_name}.zip"

    # Confine to local directory
    target_path = Path.cwd() / safe_name
    return str(target_path.resolve())


@mcp.tool()
async def deepsearch_research(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    depth: int = 3,
    max_pages: int = 50,
    mode: Literal["fast", "balanced", "complete", "research"] = "balanced",
    output_archive: Optional[str] = None,
    category: Optional[str] = None,
    auto_discover: bool = True,
) -> str:
    """Executes end-to-end DeepSearch research pipeline via ResearchApplicationService (DS-A02).

    Args:
        query: Research topic or search query.
        domain: Optional target domain to constrain crawling.
        preferred_sources: Optional seed URLs to prioritize.
        depth: Crawl exploration depth (1 to 10).
        max_pages: Maximum pages to acquire and process (1 to 500).
        mode: Execution mode strategy ('fast', 'balanced', 'complete', 'research').
        output_archive: Optional custom filename for destination .zip archive (path-sanitized).
        category: Query classification hint ('science', 'news', 'engineering', etc.).
        auto_discover: Enable automated multi-source seed discovery.
    """
    if not query or not query.strip():
        return json.dumps(
            {"status": "failed", "error": "Query parameter cannot be empty."},
            indent=2,
            ensure_ascii=False,
        )

    if mode not in ALLOWED_MODES:
        return json.dumps(
            {
                "status": "failed",
                "error": f"Invalid mode '{mode}'. Allowed modes: {sorted(ALLOWED_MODES)}",
            },
            indent=2,
            ensure_ascii=False,
        )

    bounded_depth = max(1, min(depth, MAX_DEPTH))
    bounded_max_pages = max(1, min(max_pages, MAX_PAGES))
    safe_archive = sanitize_archive_path(
        output_archive, f"deepsearch_mcp_{query.replace(' ', '_')[:20]}.zip"
    )

    sources = preferred_sources or []
    req = ResearchRequest(
        query=query.strip(),
        domain=domain.strip() if domain else None,
        preferred_sources=sources,
        depth=bounded_depth,
        max_pages=bounded_max_pages,
        mode=ExecutionMode(mode),
        output_archive_path=safe_archive,
        auto_discover=auto_discover,
        category=category.strip() if category else None,
    )

    handle = await research_service.start(req)
    timeout_sec = 600.0  # 10 minute absolute safety boundary
    start_time = asyncio.get_event_loop().time()

    try:
        # Wait for completion in MCP async loop with durable cancellation
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

            if asyncio.get_event_loop().time() - start_time > timeout_sec:
                logger.warning(
                    "Research run %s exceeded max execution timeout of %ss. Cancelling...",
                    handle.run_id,
                    timeout_sec,
                )
                await research_service.cancel(handle.run_id)
                return json.dumps(
                    {
                        "status": "failed",
                        "run_id": handle.run_id,
                        "error": f"Research run exceeded maximum timeout of {timeout_sec}s.",
                    },
                    indent=2,
                    ensure_ascii=False,
                )

        res = await research_service.result(handle.run_id)
        if res and res.status in (
            RunLifecycleState.COMPLETED,
            RunLifecycleState.INSUFFICIENT_EVIDENCE,
        ):
            return json.dumps(
                {
                    "status": "success",
                    "quality_status": res.status.value,
                    "run_id": res.run_id,
                    "query": res.query,
                    "total_pages_processed": res.total_pages_processed,
                    "total_rag_chunks": res.total_rag_chunks,
                    "archive_path": res.archive_path,
                    "output_directory": res.dir_path,
                    "manifest": res.manifest,
                },
                indent=2,
                ensure_ascii=False,
            )
        else:
            st = await research_service.status(handle.run_id)
            return json.dumps(
                {
                    "status": "failed",
                    "run_id": handle.run_id,
                    "error": st.error_message
                    or "Pipeline execution failed or produced insufficient evidence.",
                },
                indent=2,
                ensure_ascii=False,
            )

    except asyncio.CancelledError:
        logger.info(
            "MCP client cancelled research request %s. Propagating cancellation to backend...",
            handle.run_id,
        )
        await research_service.cancel(handle.run_id)
        raise
    except Exception as exc:
        logger.exception("Unexpected error in deepsearch_research handler: %s", exc)
        await research_service.cancel(handle.run_id)
        return json.dumps(
            {"status": "failed", "run_id": handle.run_id, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool()
async def deepsearch_discover(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    category: Optional[str] = None,
) -> str:
    """Discovers diverse seed URLs from multiple academic and knowledge sources."""
    if not query or not query.strip():
        return json.dumps(
            {"status": "failed", "error": "Query parameter cannot be empty."},
            indent=2,
            ensure_ascii=False,
        )

    try:
        seeds = await discover_diverse_seeds(
            query=query.strip(),
            domain=domain.strip() if domain else None,
            preferred_sources=preferred_sources,
            category=category.strip() if category else None,
        )
        return json.dumps(
            {
                "status": "success",
                "query": query,
                "total_seeds": len(seeds),
                "seeds": seeds,
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("Error discovering seeds for query '%s': %s", query, exc)
        return json.dumps(
            {"status": "failed", "query": query, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool()
async def deepsearch_inspect(url: str) -> str:
    """Inspects a target URL and returns page intelligence metrics and recommended strategy."""
    if not url or not url.strip():
        return json.dumps(
            {"status": "failed", "error": "URL parameter cannot be empty."},
            indent=2,
            ensure_ascii=False,
        )

    try:
        c_url = canonicalize_url(url.strip())
        artifact = await acquisition_engine.acquire_page(
            url.strip(), c_url, mode=ExecutionMode.BALANCED
        )
        pi = artifact.page_intelligence

        rec_strategy = "HTTP"
        if pi.js_dependency_score >= settings.adaptive.browser_threshold:
            rec_strategy = "PLAYWRIGHT BROWSER"
        if pi.api_score >= 0.7:
            rec_strategy = "DIRECT API"

        return json.dumps(
            {
                "status": "success",
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
                "estimated_cost": 1.0 if rec_strategy == "HTTP" else 10.0,
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("Failed to inspect URL '%s': %s", url, exc)
        return json.dumps(
            {"status": "failed", "url": url, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool()
async def deepsearch_extract(url: str) -> str:
    """Extracts raw/clean/fit Markdown, records, and tables from a target URL."""
    if not url or not url.strip():
        return json.dumps(
            {"status": "failed", "error": "URL parameter cannot be empty."},
            indent=2,
            ensure_ascii=False,
        )

    try:
        c_url = canonicalize_url(url.strip())
        artifact = await acquisition_engine.acquire_page(
            url.strip(), c_url, mode=ExecutionMode.BALANCED
        )
        result = ExtractionEngine.extract_from_html(url.strip(), artifact.text_content)

        return json.dumps(
            {
                "status": "success",
                "url": url,
                "clean_markdown": result.clean_markdown,
                "fit_markdown": result.fit_markdown,
                "tables_count": len(result.tables),
                "extracted_records_count": len(result.extracted_records),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("Failed to extract content from URL '%s': %s", url, exc)
        return json.dumps(
            {"status": "failed", "url": url, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool()
async def deepsearch_search(query: str, limit: int = 10) -> str:
    """Searches indexed content using text, visual, and hybrid multivector retrieval without fake results."""
    if not query or not query.strip():
        return json.dumps(
            {"status": "failed", "error": "Query parameter cannot be empty."},
            indent=2,
            ensure_ascii=False,
        )

    bounded_limit = max(1, min(limit, MAX_SEARCH_LIMIT))

    try:
        state = search_engine.get_feature_state()
        # Offload synchronous vector/BM25 retrieval to a worker thread to prevent blocking event loop
        results = await asyncio.to_thread(
            search_engine.search_hybrid, query.strip(), limit=bounded_limit
        )
        return json.dumps(
            {
                "status": "success",
                "query": query,
                "state": state.value,
                "results": [r.model_dump() for r in results],
                "count": len(results),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("Search execution error for query '%s': %s", query, exc)
        return json.dumps(
            {"status": "failed", "query": query, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool()
async def deepsearch_capabilities() -> str:
    """Returns the canonical capability matrix (§DS-01) with honest status tiers (stable, experimental, disabled)."""
    from scraper.contracts.capabilities import get_capability_matrix

    matrix = get_capability_matrix()
    return json.dumps(
        {
            "status": "success",
            "capabilities": {k: v.model_dump() for k, v in matrix.items()},
        },
        indent=2,
        ensure_ascii=False,
    )


def run_mcp_server():
    """Runs the MCP server over stdio transport, ensuring stderr logging and stdout isolation."""
    # Guarantee logs are routed strictly to stderr so stdio JSON-RPC framing remains uncorrupted
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    logger.info("Initializing DeepSearch Production MCP Server on stdio transport...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
