"""DeepSearch Model Context Protocol (MCP) Server (§100, DS-A02, DS-A03, §DS-04).

Exposes DeepSearch research, inspection, extraction, and hybrid retrieval tools
to LLM clients (Claude, Cursor, Antigravity, VS Code, etc.) over standard MCP interfaces.
Hardened for enterprise production reliability, memory safety, cancellation propagation,
strict schema validation, and path confinement.
"""

import asyncio
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from scraper.application.models import ResearchRequest, RunLifecycleState
from scraper.application.service import get_deepsearch_service
from scraper.config import ExecutionMode
from scraper.discovery.seed_finder import discover_diverse_seeds

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="deepsearch",
    instructions="DeepSearch Adaptive Scraping, Extraction, and Research Platform MCP Server",
)

ALLOWED_MODES = {"fast", "balanced", "complete", "research"}
MAX_DEPTH = 10
MAX_PAGES = 500
MAX_SEARCH_LIMIT = 100


def sanitize_archive_path(
    archive_path: str | None, default_prefix: str = "deepsearch_mcp"
) -> str:
    """Ensures archive path is safe, normalized, and confined to the current working directory or subfolders.

    Never constructs filenames from arbitrary user queries (§DS-20).
    """
    if not archive_path:
        default_filename = f"{default_prefix}_{uuid.uuid4().hex[:12]}.zip"
        return str((Path.cwd() / default_filename).resolve())

    # Strip dangerous leading drive letters or traversal components
    clean_p = Path(archive_path)

    # Restrict filename to prevent directory traversal
    filename = clean_p.name
    if not filename or filename in (".", ".."):
        filename = f"{default_prefix}_{uuid.uuid4().hex[:12]}.zip"

    safe_name = re.sub(r"[^\w\-.]", "_", filename)
    if not safe_name.endswith(".zip"):
        safe_name = f"{safe_name}.zip"

    # Confine to local directory
    target_path = Path.cwd() / safe_name
    return str(target_path.resolve())


@mcp.tool()
async def deepsearch_research(
    query: str,
    domain: str | None = None,
    preferred_sources: list[str] | None = None,
    depth: int = 3,
    max_pages: int = 50,
    mode: Literal["fast", "balanced", "complete", "research"] = "balanced",
    output_archive: str | None = None,
    category: str | None = None,
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
    safe_archive = sanitize_archive_path(output_archive)

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

    service = get_deepsearch_service()
    handle = await service.start_research(req)
    timeout_sec = 600.0  # 10 minute absolute safety boundary
    start_time = asyncio.get_event_loop().time()

    try:
        # Wait for completion in MCP async loop with durable cancellation
        while True:
            await asyncio.sleep(0.5)
            st = await service.research_status(handle.run_id)
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
                await service.cancel_research(handle.run_id)
                return json.dumps(
                    {
                        "status": "failed",
                        "run_id": handle.run_id,
                        "error": f"Research run exceeded maximum timeout of {timeout_sec}s.",
                    },
                    indent=2,
                    ensure_ascii=False,
                )

        res = await service.research_result(handle.run_id)
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
            st = await service.research_status(handle.run_id)
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
        await service.cancel_research(handle.run_id)
        raise
    except Exception as exc:
        logger.exception("Unexpected error in deepsearch_research handler: %s", exc)
        await service.cancel_research(handle.run_id)
        return json.dumps(
            {"status": "failed", "run_id": handle.run_id, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool()
async def deepsearch_discover(
    query: str,
    domain: str | None = None,
    preferred_sources: list[str] | None = None,
    category: str | None = None,
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
async def deepsearch_crawl(
    url: str,
    depth: int = 2,
    max_pages: int = 20,
    mode: Literal["fast", "balanced", "complete", "research", "archive"] = "balanced",
) -> str:
    """Executes a bounded crawl job via JobService (§DS-11, DS-20)."""
    if not url or not url.strip():
        return json.dumps(
            {"status": "failed", "error": "URL parameter cannot be empty."},
            indent=2,
            ensure_ascii=False,
        )

    if mode not in {"fast", "balanced", "complete", "research", "archive"}:
        return json.dumps(
            {
                "status": "failed",
                "error": f"Invalid mode '{mode}'. Allowed modes: ['fast', 'balanced', 'complete', 'research', 'archive']",
            },
            indent=2,
            ensure_ascii=False,
        )

    bounded_depth = max(0, min(depth, MAX_DEPTH))
    bounded_max_pages = max(1, min(max_pages, MAX_PAGES))

    from scraper.application.job_service import JobLifecycleState, JobRequest

    job_req = JobRequest(
        url=url.strip(),
        max_depth=bounded_depth,
        max_pages=bounded_max_pages,
        mode=ExecutionMode(mode),
    )

    service = get_deepsearch_service()
    handle = await service.submit_crawl_job(job_req)

    while True:
        await asyncio.sleep(0.5)
        st = await service.get_crawl_status(handle.job_id)
        if st.status in (
            JobLifecycleState.SUCCEEDED,
            JobLifecycleState.FAILED,
            JobLifecycleState.CANCELLED,
            JobLifecycleState.PARTIAL,
        ):
            break

    res = await service.get_crawl_result(handle.job_id)
    if res:
        return json.dumps(
            {
                "status": "success",
                "job_id": res.job_id,
                "lifecycle_state": res.status.value,
                "pages_processed": res.pages_processed,
                "artifacts_count": res.artifacts_count,
                "errors": res.errors,
            },
            indent=2,
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "status": "failed",
            "job_id": handle.job_id,
            "lifecycle_state": st.status.value,
            "errors": st.errors,
        },
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

    service = get_deepsearch_service()
    try:
        res = await service.inspect(url.strip(), mode=ExecutionMode.BALANCED)
        return json.dumps(
            {
                "status": "success",
                "url": res.url,
                "canonical_url": res.canonical_url,
                "http_status": res.http_status,
                "content_type": res.content_type,
                "static_score": res.static_score,
                "js_dependency_score": res.js_dependency_score,
                "detected_apis_count": res.detected_apis_count,
                "tables_count": res.tables_count,
                "canvas_detected": res.canvas_detected,
                "visual_score": res.visual_score,
                "recommended_strategy": res.recommended_strategy,
                "estimated_cost": res.estimated_cost,
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

    service = get_deepsearch_service()
    try:
        result = await service.extract(url.strip(), mode=ExecutionMode.BALANCED)

        return json.dumps(
            {
                "status": "success",
                "url": result.url,
                "clean_markdown": result.clean_markdown,
                "fit_markdown": result.fit_markdown,
                "tables_count": len(result.tables),
                "word_count": result.word_count,
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
    service = get_deepsearch_service()

    try:
        from scraper.contracts.capabilities import (
            CapabilityUnavailableError,
            require_capability,
        )

        try:
            require_capability("hybrid_search")
        except CapabilityUnavailableError as exc:
            return json.dumps(
                {
                    "status": "unavailable",
                    "capability": "hybrid_search",
                    "error": exc.message,
                    "results": [],
                    "count": 0,
                },
                indent=2,
                ensure_ascii=False,
            )

        state = service.search_engine.get_feature_state()
        # Offload synchronous vector/BM25 retrieval to a worker thread to prevent blocking event loop
        results = await asyncio.to_thread(
            service.search, query.strip(), limit=bounded_limit
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
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.INFO)

    logger.info("Initializing DeepSearch FastMCP server over stdio transport...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
