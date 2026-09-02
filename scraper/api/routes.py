"""FastAPI Route Handlers (§55 REST API, §57 Inspect Mode, DS-A02, DS-A03, DS-A07, §DS-04, §DS-08)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from scraper.api.security import resolve_safe_workspace_dir, verify_api_key
from scraper.api.sse import sse_broker
from scraper.application.job_service import (
    JobHandle,
    JobRequest,
    JobResult,
    JobStatus,
)
from scraper.application.models import (
    FeatureAvailabilityState,
    ResearchHandle,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)
from scraper.application.service import (
    DeepSearchService,
    InspectResponse,
    get_deepsearch_service,
)
from scraper.config import settings
from scraper.contracts.capabilities import (
    CapabilityUnavailableError,
    get_capability_matrix,
    require_capability,
)
from scraper.monitoring.telemetry import telemetry
from scraper.retrieval.epistemic_client import epistemic_client
from scraper.retrieval.epistemic_models import (
    EpistemicEdgeInput,
    EpistemicNodeInput,
    EpistemicQueryRequest,
    EpistemicQueryResponse,
)
from scraper.search.search_engine import SearchResponse, SearchResultItem
from scraper.storage.exporters.obsidian import ObsidianVaultExporter
from scraper.storage.exporters.zotero import ZoteroLibraryExporter

router = APIRouter(prefix="/api/v1")


class EpistemicIngestApiRequest(BaseModel):
    run_id: str
    doc_id: str
    url: str
    nodes: list[EpistemicNodeInput]
    edges: list[EpistemicEdgeInput] = []


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
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Inspect Mode (§57) showing page intelligence metrics and recommended strategy."""
    return await service.inspect(req.url)


@router.post("/crawl", response_model=JobHandle, status_code=status.HTTP_202_ACCEPTED)
async def start_crawl(
    req: JobRequest,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Submit a bounded in-process crawl job (§55, §DS-11)."""
    return await service.submit_crawl_job(req)


@router.get("/crawl/{job_id}", response_model=JobStatus)
async def get_crawl_status(
    job_id: str,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Get the status of a crawl job (§DS-11)."""
    try:
        return await service.get_crawl_status(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Crawl job '{job_id}' not found")


@router.get("/crawl/{job_id}/result", response_model=JobResult)
async def get_crawl_result(
    job_id: str,
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Get the outcome of a completed crawl job (§DS-11)."""
    try:
        res = await service.get_crawl_result(job_id)
        if res is None:
            status_obj = await service.get_crawl_status(job_id)
            raise HTTPException(
                status_code=425,
                detail=f"Crawl job '{job_id}' is still in progress (status={status_obj.status.value})",
            )
        return res
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Crawl job '{job_id}' not found")


@router.post("/crawl/{job_id}/cancel")
async def cancel_crawl(
    job_id: str,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Request cooperative cancellation of a crawl job (§DS-11)."""
    try:
        cancelled = await service.cancel_crawl_job(job_id)
        return {"job_id": job_id, "cancelled": cancelled}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Crawl job '{job_id}' not found")


@router.post("/search/text", response_model=list[SearchResultItem])
async def search_text(
    req: SearchQueryRequest,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Search text without fake synthetic results (DS-A03, DS-16)."""
    try:
        require_capability("hybrid_search")
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
    return service.search_engine.search_text(req.query, limit=req.limit)


@router.post("/search/visual", response_model=list[SearchResultItem])
async def search_visual(
    req: SearchQueryRequest,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Visual multivector search (DS-A03, DS-01, DS-16)."""
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


@router.post("/search/hybrid", response_model=list[SearchResultItem])
async def search_hybrid(
    req: SearchQueryRequest,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Hybrid text and visual retrieval (DS-A03, DS-16)."""
    try:
        require_capability("hybrid_search")
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
    return service.search_engine.search_hybrid(req.query, limit=req.limit)


@router.post("/search/query", response_model=SearchResponse)
async def search_query_detailed(
    req: SearchQueryRequest,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Detailed query endpoint returning typed feature state and results (DS-16)."""
    try:
        require_capability("hybrid_search")
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


@router.post("/epistemic/query", response_model=EpistemicQueryResponse)
async def query_epistemic_memory(
    req: EpistemicQueryRequest,
    _auth: str = Depends(verify_api_key),
):
    """Execute mathematical evidence-subgraph query over SNC/SIH Epistemic Memory (DS-40)."""
    return await epistemic_client.query(req)


@router.post("/epistemic/ingest")
async def ingest_epistemic_memory(
    req: EpistemicIngestApiRequest,
    _auth: str = Depends(verify_api_key),
):
    """Ingest extracted nodes and relations into SIH knowledge graph (DS-40)."""
    return await epistemic_client.ingest(
        run_id=req.run_id,
        doc_id=req.doc_id,
        url=req.url,
        nodes=req.nodes,
        edges=req.edges,
    )


# --- DS-A02 & DS-A07: Unified Research Application Service Endpoints ---


@router.post(
    "/research", response_model=ResearchHandle, status_code=status.HTTP_202_ACCEPTED
)
async def start_research(
    req: ResearchRequest,
    _auth: str = Depends(verify_api_key),
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
    _auth: str = Depends(verify_api_key),
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
    output_dir: str | None = None,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Export research execution artifacts to an Obsidian markdown vault strictly inside workspace (§DS-08)."""
    try:
        res = await service.research_result(run_id)
        if res is None:
            raise HTTPException(status_code=425, detail="Research is still running")

        base_export_dir = Path(settings.storage_path) / "exports"
        safe_vault_path = resolve_safe_workspace_dir(
            base_export_dir, output_dir, f"obsidian_{run_id}"
        )
        safe_vault_dir = str(safe_vault_path)

        exporter = ObsidianVaultExporter(safe_vault_dir)
        index_path = exporter.export_vault(
            query=res.query,
            extractions=[],
            evidence_claims=res.evidence_summary.get("claims", [])
            if res.evidence_summary
            else [],
            metadata={"run_id": run_id},
        )
        return {
            "status": "ok",
            "run_id": run_id,
            "vault_index": index_path,
            "vault_dir": safe_vault_dir,
        }
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )


@router.post("/research/{run_id}/export/zotero")
async def export_research_zotero(
    run_id: str,
    output_dir: str | None = None,
    _auth: str = Depends(verify_api_key),
    service: DeepSearchService = Depends(get_deepsearch_service),
):
    """Export research execution citations to Zotero CSL-JSON and RIS files strictly inside workspace (§DS-08)."""
    try:
        res = await service.research_result(run_id)
        if res is None:
            raise HTTPException(status_code=425, detail="Research is still running")

        base_export_dir = Path(settings.storage_path) / "exports"
        safe_zotero_path = resolve_safe_workspace_dir(
            base_export_dir, output_dir, f"zotero_{run_id}"
        )
        safe_zotero_dir = str(safe_zotero_path)

        exporter = ZoteroLibraryExporter(safe_zotero_dir)
        files = exporter.export_all([], query=res.query)
        return {
            "status": "ok",
            "run_id": run_id,
            "files": files,
            "output_dir": safe_zotero_dir,
        }
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Research run '{run_id}' not found"
        )
