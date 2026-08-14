"""FastAPI Route Handlers (§55 REST API, §57 Inspect Mode, §62 Streaming Output)."""

import uuid
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from scraper.config import settings, ExecutionMode
from scraper.control.scheduler import RequestFrontier, CrawlRequest
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.search.search_engine import SearchEngine, SearchResultItem
from scraper.monitoring.telemetry import telemetry

router = APIRouter(prefix="/api/v1")
search_engine = SearchEngine()
frontier = RequestFrontier()
acquisition_engine = AdaptiveAcquisitionEngine()


class CrawlJobRequest(BaseModel):
    url: str
    max_depth: int = Field(default=3, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=50000)
    mode: ExecutionMode = ExecutionMode.BALANCED


class CrawlJobResponse(BaseModel):
    job_id: str
    status: str
    url: str
    max_depth: int
    max_pages: int


class InspectRequest(BaseModel):
    url: str


class InspectResponse(BaseModel):
    url: str
    canonical_url: str
    http_status: int
    content_type: str
    static_score: float
    js_dependency_score: float
    detected_apis_count: int
    tables_count: int
    canvas_detected: bool
    visual_score: float
    recommended_strategy: str
    estimated_cost: float


class SearchQueryRequest(BaseModel):
    query: str
    limit: int = 10


@router.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@router.get("/metrics/summary")
async def get_metrics():
    return telemetry.get_summary()


@router.post("/inspect", response_model=InspectResponse)
async def inspect_url(req: InspectRequest):
    """Inspect Mode (§57) showing page intelligence metrics and recommended strategy."""
    c_url = canonicalize_url(req.url)
    artifact = await acquisition_engine.acquire_page(req.url, c_url, mode=ExecutionMode.BALANCED)
    pi = artifact.page_intelligence

    rec_strategy = "HTTP"
    if pi.js_dependency_score >= settings.adaptive.browser_threshold:
        rec_strategy = "PLAYWRIGHT BROWSER"
    if pi.api_score >= 0.7:
        rec_strategy = "DIRECT API"

    return InspectResponse(
        url=req.url,
        canonical_url=c_url,
        http_status=artifact.status_code,
        content_type=artifact.content_type,
        static_score=pi.static_score,
        js_dependency_score=pi.js_dependency_score,
        detected_apis_count=len(pi.detected_apis),
        tables_count=pi.tables_count,
        canvas_detected=pi.has_canvas,
        visual_score=pi.visual_score,
        recommended_strategy=rec_strategy,
        estimated_cost=1.0 if rec_strategy == "HTTP" else 10.0
    )


@router.post("/crawl", response_model=CrawlJobResponse)
async def start_crawl(req: CrawlJobRequest, bg_tasks: BackgroundTasks):
    """Start a crawl job (§55)."""
    job_id = str(uuid.uuid4())
    c_url = canonicalize_url(req.url)

    request_obj = CrawlRequest(
        url=req.url,
        canonical_url=c_url,
        domain=req.url,
        depth=0,
        mode=req.mode.value
    )
    await frontier.add_request(request_obj)

    return CrawlJobResponse(
        job_id=job_id,
        status="RUNNING",
        url=req.url,
        max_depth=req.max_depth,
        max_pages=req.max_pages
    )


@router.get("/crawl/{job_id}")
async def get_crawl_status(job_id: str):
    stats = await frontier.stats()
    return {"job_id": job_id, "stats": stats}


@router.post("/search/text", response_model=List[SearchResultItem])
async def search_text(req: SearchQueryRequest):
    return search_engine.search_text(req.query, limit=req.limit)


@router.post("/search/visual", response_model=List[SearchResultItem])
async def search_visual(req: SearchQueryRequest):
    return search_engine.search_visual(req.query, limit=req.limit)


@router.post("/search/hybrid", response_model=List[SearchResultItem])
async def search_hybrid(req: SearchQueryRequest):
    return search_engine.search_hybrid(req.query, limit=req.limit)


class ResearchPipelineRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    preferred_sources: List[str] = Field(default_factory=list)
    depth: int = Field(default=3, ge=0, le=10)
    max_pages: int = Field(default=50, ge=1, le=5000)
    mode: ExecutionMode = ExecutionMode.BALANCED
    export_archive: bool = True


class ResearchPipelineResponse(BaseModel):
    query: str
    total_pages_processed: int
    total_rag_chunks: int
    archive_path: Optional[str] = None
    manifest: dict = Field(default_factory=dict)


@router.post("/research", response_model=ResearchPipelineResponse)
async def run_research_pipeline(req: ResearchPipelineRequest):
    """Executes full DeepSearch research pipeline and exports files/ (with links) + rag/ (LLM dataset) archive."""
    from scraper.pipeline.search_pipeline import DeepSearchPipeline, DeepSearchPipelineOptions

    output_zip = f"deepsearch_{uuid.uuid4().hex[:8]}.zip" if req.export_archive else None
    opts = DeepSearchPipelineOptions(
        query=req.query,
        domain=req.domain,
        preferred_sources=req.preferred_sources,
        depth=req.depth,
        max_pages=req.max_pages,
        mode=req.mode,
        output_archive_path=output_zip
    )
    pipeline = DeepSearchPipeline()
    res = await pipeline.execute(opts)

    return ResearchPipelineResponse(
        query=res.query,
        total_pages_processed=res.total_pages_processed,
        total_rag_chunks=res.total_rag_chunks,
        archive_path=res.archive_path,
        manifest=res.manifest
    )

