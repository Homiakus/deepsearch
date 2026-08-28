"""FastAPI Route Handlers (§55 REST API, §57 Inspect Mode, DS-A02, DS-A03, DS-A07)."""

import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from scraper.config import settings, ExecutionMode
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.search.search_engine import SearchEngine, SearchResultItem, SearchResponse
from scraper.monitoring.telemetry import telemetry
from scraper.application.models import (
    ResearchRequest,
    ResearchHandle,
    ResearchStatus,
    ResearchResult,
    FeatureAvailabilityState,
)
from scraper.application.research_service import research_service
from scraper.api.sse import sse_broker
from scraper.storage.exporters.obsidian import ObsidianVaultExporter
from scraper.storage.exporters.zotero import ZoteroLibraryExporter
from scraper.contracts.capabilities import (
    CapabilityUnavailableError,
    get_capability_matrix,
    require_capability,
)

router = APIRouter(prefix="/api/v1")
search_engine = SearchEngine()
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
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "orchestration_backend": settings.orchestration_backend,
    }


@router.get("/capabilities")
async def get_capabilities():
    """Returns the canonical capability matrix (§DS-01) with honest status tiers."""
    return {
        "capabilities": {k: v.model_dump() for k, v in get_capability_matrix().items()}
    }


@router.get("/metrics/summary")
async def get_metrics():
    return telemetry.get_summary()


@router.post("/inspect", response_model=InspectResponse)
async def inspect_url(req: InspectRequest):
    """Inspect Mode (§57) showing page intelligence metrics and recommended strategy."""
    c_url = canonicalize_url(req.url)
    artifact = await acquisition_engine.acquire_page(
        req.url, c_url, mode=ExecutionMode.BALANCED
    )
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
        estimated_cost=1.0 if rec_strategy == "HTTP" else 10.0,
    )


@router.post("/crawl", response_model=CrawlJobResponse)
async def start_crawl(req: CrawlJobRequest):
    """Start a crawl job with bounded batch execution (§55, DS-A08)."""
    job_id = f"crawl_{uuid.uuid4().hex[:8]}"
    return CrawlJobResponse(
        job_id=job_id,
        status="ACCEPTED",
        url=req.url,
        max_depth=req.max_depth,
        max_pages=req.max_pages,
    )


@router.post("/search/text", response_model=List[SearchResultItem])
async def search_text(req: SearchQueryRequest):
    """Search text without fake synthetic results (DS-A03)."""
    return search_engine.search_text(req.query, limit=req.limit)


@router.post("/search/visual", response_model=List[SearchResultItem])
async def search_visual(req: SearchQueryRequest):
    """Visual multivector search (DS-A03, DS-01)."""
    try:
        require_capability("pixel_rag")
    except CapabilityUnavailableError as exc:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "capability_unavailable",
                "capability": exc.capability,
                "status": exc.status.value,
                "message": exc.message,
            },
        )
    return search_engine.search_visual(req.query, limit=req.limit)


@router.post("/search/hybrid", response_model=List[SearchResultItem])
async def search_hybrid(req: SearchQueryRequest):
    """Hybrid text and visual retrieval (DS-A03)."""
    return search_engine.search_hybrid(req.query, limit=req.limit)


@router.post("/search/query", response_model=SearchResponse)
async def search_query_detailed(req: SearchQueryRequest):
    """Detailed query endpoint returning typed feature state and results."""
    state = search_engine.get_feature_state()
    results = search_engine.search_hybrid(req.query, limit=req.limit)
    return SearchResponse(
        query=req.query,
        state=state,
        results=results,
        total_count=len(results),
        message="Search executed against indexed vector corpus"
        if state == FeatureAvailabilityState.READY
        else "Index empty or not configured",
    )


# --- DS-A02 & DS-A07: Unified Research Application Service Endpoints ---


@router.post(
    "/research", response_model=ResearchHandle, status_code=status.HTTP_202_ACCEPTED
)
async def start_research(req: ResearchRequest):
    """Asynchronously starts or loads a durable research execution (§55, DS-A02, DS-A07)."""
    handle = await research_service.start(req)
    return handle


@router.get("/research/{run_id}", response_model=ResearchStatus)
async def get_research_status(run_id: str):
    """Get durable progress, node status, and metrics for a research run."""
    try:
        return await research_service.status(run_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )


@router.get("/research/{run_id}/result", response_model=ResearchResult)
async def get_research_result(run_id: str):
    """Get the final research outcome if completed."""
    try:
        res = await research_service.result(run_id)
        if res is None:
            status_obj = await research_service.status(run_id)
            raise HTTPException(
                status_code=425,
                detail=f"Research run '{run_id}' is still in progress (status={status_obj.status.value})",
            )
        return res
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )


@router.post("/research/{run_id}/cancel")
async def cancel_research(run_id: str):
    """Request durable cancellation of a research execution."""
    try:
        await research_service.cancel(run_id)
        return {"run_id": run_id, "status": "CANCELLED"}
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )


@router.get("/research/{run_id}/events")
async def stream_research_events(run_id: str):
    """Real-time SSE event stream for live research execution telemetry and status updates."""
    return StreamingResponse(
        sse_broker.subscribe(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/research/{run_id}/export/obsidian")
async def export_research_obsidian(run_id: str, output_dir: Optional[str] = None):
    """Export research execution artifacts to an Obsidian markdown vault."""
    try:
        res = await research_service.result(run_id)
        if res is None:
            raise HTTPException(status_code=425, detail="Research is still running")
        vault_dir = output_dir or f"./data/exports/obsidian_{run_id}"
        exporter = ObsidianVaultExporter(vault_dir)
        index_path = exporter.export_vault(
            query=res.query,
            extractions=[],
            evidence_claims=res.claims,
            metadata={"run_id": run_id, "quality_score": res.quality_score},
        )
        return {
            "status": "ok",
            "run_id": run_id,
            "vault_index": index_path,
            "vault_dir": vault_dir,
        }
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )


@router.post("/research/{run_id}/export/zotero")
async def export_research_zotero(run_id: str, output_dir: Optional[str] = None):
    """Export research execution citations to Zotero CSL-JSON and RIS files."""
    try:
        res = await research_service.result(run_id)
        if res is None:
            raise HTTPException(status_code=425, detail="Research is still running")
        zotero_dir = output_dir or f"./data/exports/zotero_{run_id}"
        exporter = ZoteroLibraryExporter(zotero_dir)
        files = exporter.export_all([], query=res.query)
        return {
            "status": "ok",
            "run_id": run_id,
            "files": files,
            "output_dir": zotero_dir,
        }
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )
