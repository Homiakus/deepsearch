"""Single Application Boundary for DeepSearch Research Workflows (§0, §1, DS-A02)."""

from __future__ import annotations
import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Protocol

from scraper.application.models import (
    ResearchRequest,
    ResearchHandle,
    ResearchStatus,
    ResearchResult,
    RunLifecycleState,
)
from scraper.config import settings

logger = logging.getLogger(__name__)


class ResearchApplicationService(Protocol):
    """Public protocol for research execution boundary."""

    async def start(self, request: ResearchRequest) -> ResearchHandle:
        """Start or load an idempotent research execution."""
        ...

    async def status(self, run_id: str) -> ResearchStatus:
        """Get the current progress, state and node status of a run."""
        ...

    async def result(self, run_id: str) -> Optional[ResearchResult]:
        """Fetch the final research outcome if completed."""
        ...

    async def cancel(self, run_id: str) -> None:
        """Request durable cancellation of a research execution."""
        ...


class DefaultResearchApplicationService:
    """Production implementation of ResearchApplicationService.
    
    Provides unified lifecycle handling, durable run tracking, and bridges
    execution to activities / Axiom ADGO orchestration.
    """

    def __init__(self):
        self._runs: Dict[str, ResearchStatus] = {}
        self._results: Dict[str, ResearchResult] = {}
        self._idempotency_map: Dict[str, str] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start(self, request: ResearchRequest) -> ResearchHandle:
        # Check idempotency
        if request.idempotency_key and request.idempotency_key in self._idempotency_map:
            existing_run_id = self._idempotency_map[request.idempotency_key]
            existing_status = self._runs.get(existing_run_id)
            if existing_status:
                logger.info("Reusing existing run %s for idempotency key %s", existing_run_id, request.idempotency_key)
                return ResearchHandle(
                    run_id=existing_run_id,
                    idempotency_key=request.idempotency_key,
                    status=existing_status.status,
                    created_at=existing_status.created_at,
                )

        run_id = f"ds_run_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        status = ResearchStatus(
            run_id=run_id,
            status=RunLifecycleState.RUNNING,
            progress=0.05,
            current_node="NormalizeQuery",
            created_at=now,
            updated_at=now,
        )
        self._runs[run_id] = status
        if request.idempotency_key:
            self._idempotency_map[request.idempotency_key] = run_id

        # Spawn execution task
        task = asyncio.create_task(self._execute_run(run_id, request))
        self._tasks[run_id] = task

        return ResearchHandle(
            run_id=run_id,
            idempotency_key=request.idempotency_key,
            status=RunLifecycleState.RUNNING,
            created_at=now,
        )

    async def _execute_run(self, run_id: str, request: ResearchRequest):
        status = self._runs[run_id]
        try:
            status.current_node = "PlanResearch"
            status.progress = 0.15
            status.updated_at = datetime.now(timezone.utc)

            from scraper.pipeline.search_pipeline import DeepSearchPipeline, DeepSearchPipelineOptions

            output_archive = request.output_archive_path
            if not output_archive and request.output_archive_path is None:
                output_archive = f"deepsearch_{run_id}.zip"

            opts = DeepSearchPipelineOptions(
                query=request.query,
                domain=request.domain,
                preferred_sources=request.preferred_sources,
                depth=request.depth,
                max_pages=request.max_pages,
                mode=request.mode,
                min_media_count=request.min_media_count,
                max_media_count=request.max_media_count,
                enable_media_archiving=request.enable_media_archiving,
                output_archive_path=output_archive,
                auto_discover_sources=request.auto_discover,
                category=request.category,
            )

            status.current_node = "DiscoverSources"
            status.progress = 0.30
            status.updated_at = datetime.now(timezone.utc)

            pipeline = DeepSearchPipeline()
            pipeline_res = await pipeline.execute(opts)

            status.status = RunLifecycleState.COMPLETED
            status.progress = 1.0
            status.current_node = "CompleteResearch"
            status.pages_processed = pipeline_res.total_pages_processed
            status.rag_chunks_created = pipeline_res.total_rag_chunks
            status.updated_at = datetime.now(timezone.utc)

            res = ResearchResult(
                run_id=run_id,
                query=pipeline_res.query,
                status=RunLifecycleState.COMPLETED,
                total_pages_processed=pipeline_res.total_pages_processed,
                total_rag_chunks=pipeline_res.total_rag_chunks,
                archive_path=pipeline_res.archive_path,
                dir_path=pipeline_res.dir_path,
                manifest=pipeline_res.manifest,
                completed_at=datetime.now(timezone.utc),
            )
            self._results[run_id] = res

        except asyncio.CancelledError:
            status.status = RunLifecycleState.CANCELLED
            status.error_message = "Research job was cancelled."
            status.updated_at = datetime.now(timezone.utc)
            logger.info("Run %s cancelled.", run_id)
        except Exception as exc:
            status.status = RunLifecycleState.FAILED
            status.error_message = str(exc)
            status.updated_at = datetime.now(timezone.utc)
            logger.exception("Run %s failed with error: %s", run_id, exc)

    async def status(self, run_id: str) -> ResearchStatus:
        if run_id not in self._runs:
            raise KeyError(f"Research run '{run_id}' not found")
        return self._runs[run_id]

    async def result(self, run_id: str) -> Optional[ResearchResult]:
        if run_id not in self._runs:
            raise KeyError(f"Research run '{run_id}' not found")
        return self._results.get(run_id)

    async def cancel(self, run_id: str) -> None:
        if run_id not in self._runs:
            raise KeyError(f"Research run '{run_id}' not found")
        status = self._runs[run_id]
        if status.status in (RunLifecycleState.PENDING, RunLifecycleState.RUNNING):
            status.status = RunLifecycleState.CANCELLED
            status.updated_at = datetime.now(timezone.utc)
            task = self._tasks.get(run_id)
            if task and not task.done():
                task.cancel()


# Global singleton instance for application layer
research_service = DefaultResearchApplicationService()
