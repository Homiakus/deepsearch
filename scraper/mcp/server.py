"""DeepSearch Model Context Protocol (MCP) Server.

Exposes DeepSearch research, inspection, extraction, and hybrid retrieval tools
to LLM clients (Claude, Cursor, Antigravity, VS Code, etc.) over standard MCP interfaces.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP

from scraper.config import settings, ExecutionMode
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.extraction.engine import ExtractionEngine
from scraper.pipeline.search_pipeline import DeepSearchPipeline, DeepSearchPipelineOptions
from scraper.search.search_engine import SearchEngine
from scraper.discovery.seed_finder import discover_diverse_seeds

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
    """Executes end-to-end DeepSearch research pipeline with multi-source discovery.
    
    Inputs:
      query: Topic or search query string
      domain: Subject domain or target domain scope (None = multi-domain)
      preferred_sources: List of priority seed URLs or whitelist domains
      depth: Max crawl depth
      max_pages: Page limit
      mode: Execution mode (fast|balanced|complete|research)
      output_archive: Destination path for generated .zip archive
      category: Query category hint (science|news|engineering|None for auto-detect)
      auto_discover: If True, automatically discover seeds from ArXiv, Wikipedia, etc.

    Outputs:
      JSON string with pages count, RAG chunks count, output directory, manifest summary, and files/ (with links) & rag/ (for LLM) archive location.
    """
    sources = preferred_sources or []
    opts = DeepSearchPipelineOptions(
        query=query,
        domain=domain,
        preferred_sources=sources,
        depth=depth,
        max_pages=max_pages,
        mode=ExecutionMode(mode),
        output_archive_path=output_archive or f"deepsearch_mcp_{query.replace(' ', '_')[:20]}.zip",
        auto_discover_sources=auto_discover,
        category=category
    )
    pipeline = DeepSearchPipeline(acquisition_engine=acquisition_engine)
    res = await pipeline.execute(opts)

    return json.dumps({
        "status": "success",
        "query": res.query,
        "total_pages_processed": res.total_pages_processed,
        "total_rag_chunks": res.total_rag_chunks,
        "archive_path": res.archive_path,
        "output_directory": res.dir_path,
        "manifest": res.manifest
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def deepsearch_discover(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    category: Optional[str] = None
) -> str:
    """Discovers diverse seed URLs from multiple academic and knowledge sources.

    Queries ArXiv API, Wikipedia (EN/RU), Anna's Archive, and domain-specific providers
    to build a comprehensive seed URL list before crawling.

    Inputs:
      query: Search topic or question
      domain: Optional domain scope hint
      preferred_sources: Optional user-supplied seed URLs to include
      category: Optional hint (science|news|engineering) for targeted discovery

    Outputs:
      JSON list of discovered seed URLs from multiple providers.
    """
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
    """Searches indexed content using text, visual, and hybrid multivector retrieval."""
    results = search_engine.search_hybrid(query, limit=limit)
    return json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False)


def run_mcp_server():
    """Runs the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()

