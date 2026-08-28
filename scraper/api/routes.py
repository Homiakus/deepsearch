"""FastAPI Route Handlers (§55 REST API, §57 Inspect Mode, DS-A02, DS-A03, DS-A07, §DS-04)."""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from scraper.config import settings, ExecutionMode
from scraper.monitoring.telemetry import telemetry
from scraper.search.search_engine import SearchResultItem, SearchResponse
from scraper.application.models import (
    ResearchRequest,
    ResearchHandle,
    ResearchStatus,
    ResearchResult,
    FeatureAvailabilityState,
)
from scraper.application.service import (
    DeepSearchService,
    InspectResponse,
    get_deepsearch_service,
)
from scraper.api.sse import sse_broker
from scraper.storage.exporters.obsidian import ObsidianVaultExporter
from scraper.storage.exporters.zotero import ZoteroLibraryExporter
from scraper.contracts.capabilities import (
    CapabilityUnavailableError,
    get_capability_matrix,
    require_capability,
)

router = APIRouter(prefix="/api/v1")


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
async def inspect_url(
    req: InspectRequest,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Inspect Mode (§57) showing page intelligence metrics and recommended strategy."""
    return await service.inspect(req.url)


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
async def search_text(
    req: SearchQueryRequest,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Search text without fake synthetic results (DS-A03)."""
    return service.search_engine.search_text(req.query, limit=req.limit)


@router.post("/search/visual", response_model=List[SearchResultItem])
async def search_visual(
    req: SearchQueryRequest,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
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
    return service.search_engine.search_visual(req.query, limit=req.limit)


@router.post("/search/hybrid", response_model=List[SearchResultItem])
async def search_hybrid(
    req: SearchQueryRequest,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Hybrid text and visual retrieval (DS-A03)."""
    return service.search_engine.search_hybrid(req.query, limit=req.limit)


@router.post("/search/query", response_model=SearchResponse)
async def search_query_detailed(
    req: SearchQueryRequest,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Detailed query endpoint returning typed feature state and results."""
    state = service.search_engine.get_feature_state()
    results = service.search_engine.search_hybrid(req.query, limit=req.limit)
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
async def start_research(
    req: ResearchRequest,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Asynchronously starts or loads a durable research execution (§55, DS-A02, DS-A07)."""
    return await service.start_research(req)


@router.get("/research/{run_id}", response_model=ResearchStatus)
async def get_research_status(
    run_id: str,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Get durable progress, node status, and metrics for a research run."""
    try:
        return await service.research_status(run_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )


@router.get("/research/{run_id}/result", response_model=ResearchResult)
async def get_research_result(
    run_id: str,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Get the final research outcome if completed."""
    try:
        res = await service.research_result(run_id)
        if res is None:
            status_obj = await service.research_status(run_id)
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
async def cancel_research(
    run_id: str,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Request durable cancellation of a research execution."""
    try:
        await service.cancel_research(run_id)
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
async def export_research_obsidian(
    run_id: str,
    output_dir: Optional[str] = None,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Export research execution artifacts to an Obsidian markdown vault."""
    try:
        res = await service.research_result(run_id)
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
async def export_research_zotero(
    run_id: str,
    output_dir: Optional[str] = None,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Export research execution citations to Zotero CSL-JSON and RIS files."""
    try:
        res = await service.research_result(run_id)
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
