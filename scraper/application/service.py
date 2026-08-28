"""Single Unified Application Service and Composition Root (§DS-04)."""

from __future__ import annotations

import logging
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from scraper.config import ExecutionMode, settings
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.extraction.engine import ExtractionEngine, ExtractionResult
from scraper.search.search_engine import SearchEngine, SearchResultItem
from scraper.application.models import (
    ResearchRequest,
    ResearchHandle,
    ResearchStatus,
    ResearchResult,
)
from scraper.application.job_service import (
    JobService,
    JobRequest,
    JobHandle,
    JobStatus,
    JobResult,
    job_service as default_job_service,
)
from scraper.application.research_service import (
    ResearchApplicationService,
    research_service as default_research_service,
)

logger = logging.getLogger(__name__)


class PageInspectionResult(BaseModel):
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


InspectResponse = PageInspectionResult


class ExtractedContentResult(BaseModel):
    url: str
    canonical_url: str
    clean_markdown: str
    fit_markdown: str
    tables: List[Any] = Field(default_factory=list)
    document_type: str = "general"
    word_count: int = 0


class DeepSearchService:
    """Unified application service orchestrating acquisition, extraction, search, and research (§DS-04)."""

    def __init__(
        self,
        acquisition_engine: Optional[AdaptiveAcquisitionEngine] = None,
        search_engine: Optional[SearchEngine] = None,
        research_service: Optional[ResearchApplicationService] = None,
        job_service: Optional[JobService] = None,
    ):
        self.acquisition_engine = acquisition_engine or AdaptiveAcquisitionEngine()
        self.search_engine = search_engine or SearchEngine()
        self.research_service = (
            research_service
            if research_service is not None
            else default_research_service
        )
        self.job_service = (
            job_service if job_service is not None else default_job_service
        )

    async def submit_crawl_job(self, request: JobRequest) -> JobHandle:
        """Submit a bounded crawl job (§DS-11)."""
        return await self.job_service.submit_job(request)

    async def get_crawl_status(self, job_id: str) -> JobStatus:
        """Get the status of a crawl job (§DS-11)."""
        return await self.job_service.get_status(job_id)

    async def get_crawl_result(self, job_id: str) -> Optional[JobResult]:
        """Get the final result of a crawl job (§DS-11)."""
        return await self.job_service.get_result(job_id)

    async def cancel_crawl_job(self, job_id: str) -> bool:
        """Cancel a crawl job (§DS-11)."""
        return await self.job_service.cancel_job(job_id)

    async def inspect(
        self, url: str, mode: ExecutionMode = ExecutionMode.BALANCED
    ) -> PageInspectionResult:
        """Inspect a target URL and analyze page intelligence without manually configuring scrapers."""
        c_url = canonicalize_url(url)
        artifact = await self.acquisition_engine.acquire_page(url, c_url, mode=mode)
        pi = artifact.page_intelligence

        rec_strategy = "HTTP"
        if pi.js_dependency_score >= settings.adaptive.browser_threshold:
            rec_strategy = "PLAYWRIGHT BROWSER"
        if pi.api_score >= 0.7:
            rec_strategy = "DIRECT API"

        cost = 1.0 if rec_strategy == "HTTP" else 10.0

        return PageInspectionResult(
            url=url,
            canonical_url=c_url,
            http_status=artifact.status_code,
            content_type=artifact.content_type,
            static_score=round(pi.static_score, 4),
            js_dependency_score=round(pi.js_dependency_score, 4),
            detected_apis_count=len(pi.detected_apis),
            tables_count=pi.tables_count,
            canvas_detected=pi.has_canvas,
            visual_score=round(pi.visual_score, 4),
            recommended_strategy=rec_strategy,
            estimated_cost=cost,
        )

    async def extract(
        self, url: str, mode: ExecutionMode = ExecutionMode.BALANCED
    ) -> ExtractedContentResult:
        """Extract sanitized Clean & Fit Markdown from target URL."""
        c_url = canonicalize_url(url)
        artifact = await self.acquisition_engine.acquire_page(url, c_url, mode=mode)
        extracted: ExtractionResult = ExtractionEngine.extract_from_html(
            url, artifact.text_content
        )
        return ExtractedContentResult(
            url=url,
            canonical_url=c_url,
            clean_markdown=extracted.clean_markdown,
            fit_markdown=extracted.fit_markdown,
            tables=list(extracted.tables),
            word_count=len(extracted.clean_markdown.split()),
        )

    def search(
        self, query: str, limit: int = 10, explain: bool = False
    ) -> List[SearchResultItem]:
        """Execute hybrid search query."""
        if explain:
            return self.search_engine.search_evidence(query, limit=limit)
        return self.search_engine.search_hybrid(query, limit=limit)

    async def start_research(self, request: ResearchRequest) -> ResearchHandle:
        """Start or load idempotent research workflow."""
        return await self.research_service.start(request)

    async def research_status(self, run_id: str) -> ResearchStatus:
        """Get status of running research workflow."""
        return await self.research_service.status(run_id)

    async def research_result(self, run_id: str) -> Optional[ResearchResult]:
        """Fetch final result of completed research workflow."""
        return await self.research_service.result(run_id)

    async def cancel_research(self, run_id: str) -> None:
        """Cancel research workflow."""
        await self.research_service.cancel(run_id)

    async def close(self) -> None:
        """Gracefully release HTTP connection pools, browser instances, and background tasks."""
        logger.info("Closing DeepSearchService resources...")
        try:
            if (
                hasattr(self.acquisition_engine, "browser_pool")
                and self.acquisition_engine.browser_pool
            ):
                await self.acquisition_engine.browser_pool.close()
        except Exception as exc:
            logger.warning("Error closing browser pool: %s", exc)

        try:
            if (
                hasattr(self.acquisition_engine, "http_fetcher")
                and self.acquisition_engine.http_fetcher
            ):
                await self.acquisition_engine.http_fetcher.close()
        except Exception as exc:
            logger.warning("Error closing http fetcher: %s", exc)

        try:
            if hasattr(self, "job_service") and self.job_service:
                await self.job_service.close()
        except Exception as exc:
            logger.warning("Error closing job service: %s", exc)


_default_service: Optional[DeepSearchService] = None


def get_deepsearch_service() -> DeepSearchService:
    """Composition root provider for DeepSearchService (§DS-04)."""
    global _default_service
    if _default_service is None:
        _default_service = DeepSearchService()
    return _default_service
