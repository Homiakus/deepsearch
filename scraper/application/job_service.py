"""In-Process Bounded Crawl Job Service (§DS-11)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from scraper.acquisition.engine import AdaptiveAcquisitionEngine, CapturedArtifact
from scraper.config import ExecutionMode
from scraper.exceptions import BudgetExceededError
from scraper.normalization.canonicalizer import canonicalize_url

logger = logging.getLogger(__name__)


class JobLifecycleState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobRequest(BaseModel):
    url: str
    max_depth: int = Field(default=2, ge=0, le=10)
    max_pages: int = Field(default=20, ge=1, le=1000)
    mode: ExecutionMode = ExecutionMode.BALANCED


class JobHandle(BaseModel):
    job_id: str
    status: JobLifecycleState = JobLifecycleState.QUEUED
    url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobStatus(BaseModel):
    job_id: str
    url: str
    status: JobLifecycleState
    progress: float = 0.0
    pages_processed: int = 0
    max_pages: int = 20
    errors: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobResult(BaseModel):
    job_id: str
    url: str
    status: JobLifecycleState
    pages_processed: int
    artifacts_count: int
    errors: list[str] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobService:
    """Single-instance bounded in-process crawl job manager with lifecycle state tracking (§DS-11)."""

    def __init__(
        self,
        acquisition_engine: AdaptiveAcquisitionEngine | None = None,
        max_queue_capacity: int = 100,
        max_concurrent_jobs: int = 3,
    ):
        self.acquisition_engine = acquisition_engine or AdaptiveAcquisitionEngine()
        self.max_queue_capacity = max_queue_capacity
        self.max_concurrent_jobs = max_concurrent_jobs

        self._jobs: dict[str, JobStatus] = {}
        self._results: dict[str, JobResult] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancellation_events: dict[str, asyncio.Event] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._lock = asyncio.Lock()

    async def submit_job(self, req: JobRequest) -> JobHandle:
        """Enqueues a new crawl job subject to queue bounds (§DS-11)."""
        async with self._lock:
            active_or_queued = sum(
                1
                for j in self._jobs.values()
                if j.status in (JobLifecycleState.QUEUED, JobLifecycleState.RUNNING)
            )
            if active_or_queued >= self.max_queue_capacity:
                raise BudgetExceededError(
                    f"Crawl job queue capacity ({self.max_queue_capacity}) exceeded."
                )

            job_id = f"job_{uuid.uuid4().hex[:10]}"
            now = datetime.now(UTC)
            status_obj = JobStatus(
                job_id=job_id,
                url=req.url,
                status=JobLifecycleState.QUEUED,
                progress=0.0,
                pages_processed=0,
                max_pages=req.max_pages,
                created_at=now,
                updated_at=now,
            )
            self._jobs[job_id] = status_obj
            self._cancellation_events[job_id] = asyncio.Event()

            task = asyncio.create_task(self._run_job(job_id, req))
            self._tasks[job_id] = task

            return JobHandle(
                job_id=job_id,
                status=JobLifecycleState.QUEUED,
                url=req.url,
                created_at=now,
            )

    async def get_status(self, job_id: str) -> JobStatus:
        """Returns the current status of a job, raising KeyError if not found (§DS-11)."""
        async with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Job '{job_id}' not found")
            return self._jobs[job_id]

    async def get_result(self, job_id: str) -> JobResult | None:
        """Returns the final outcome of a completed job, None if still running (§DS-11)."""
        async with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Job '{job_id}' not found")
            return self._results.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cooperatively cancels a running or queued job (§DS-11)."""
        async with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Job '{job_id}' not found")

            status_obj = self._jobs[job_id]
            if status_obj.status in (
                JobLifecycleState.SUCCEEDED,
                JobLifecycleState.FAILED,
                JobLifecycleState.CANCELLED,
            ):
                return False

            if job_id in self._cancellation_events:
                self._cancellation_events[job_id].set()

            task = self._tasks.get(job_id)
            if task and not task.done():
                task.cancel()

            status_obj.status = JobLifecycleState.CANCELLED
            status_obj.updated_at = datetime.now(UTC)
            return True

    async def _run_job(self, job_id: str, req: JobRequest):
        cancel_event = self._cancellation_events[job_id]
        async with self._semaphore:
            if cancel_event.is_set():
                return

            status_obj = self._jobs[job_id]
            status_obj.status = JobLifecycleState.RUNNING
            status_obj.updated_at = datetime.now(UTC)

            artifacts: list[CapturedArtifact] = []
            errors: list[str] = []

            try:
                c_url = canonicalize_url(req.url)
                artifact = await self.acquisition_engine.acquire_page(
                    url=req.url,
                    canonical_url=c_url,
                    mode=req.mode,
                )
                artifacts.append(artifact)
                status_obj.pages_processed = len(artifacts)
                status_obj.progress = 1.0

                if artifact.status_code == 200:
                    status_obj.status = JobLifecycleState.SUCCEEDED
                else:
                    errors.append(f"HTTP status {artifact.status_code}")
                    status_obj.status = JobLifecycleState.PARTIAL

            except asyncio.CancelledError:
                status_obj.status = JobLifecycleState.CANCELLED
                errors.append("Job cancelled by user request")
            except Exception as exc:
                logger.warning("Job %s execution failure: %s", job_id, exc)
                errors.append(str(exc))
                status_obj.status = JobLifecycleState.FAILED
            finally:
                status_obj.errors = errors
                status_obj.updated_at = datetime.now(UTC)

                res = JobResult(
                    job_id=job_id,
                    url=req.url,
                    status=status_obj.status,
                    pages_processed=len(artifacts),
                    artifacts_count=len(artifacts),
                    errors=errors,
                    completed_at=datetime.now(UTC),
                )
                self._results[job_id] = res

    async def close(self):
        """Cancels and shuts down all active background jobs."""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)


job_service = JobService()
