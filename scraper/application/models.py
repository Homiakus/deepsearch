"""Domain models and DTOs for the Research Application Service (§55, §56, §100)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from scraper.config import ExecutionMode


class RunLifecycleState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class FeatureAvailabilityState(str, Enum):
    READY = "READY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INDEX_EMPTY = "INDEX_EMPTY"


class ResearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, description="Primary research query or statement"
    )
    domain: Optional[str] = Field(
        None, description="Domain / topic filter (e.g. biomed, engineering)"
    )
    preferred_sources: List[str] = Field(
        default_factory=list, description="Target initial URLs or domains"
    )
    depth: int = Field(default=3, ge=0, le=10, description="Max search and crawl depth")
    max_pages: int = Field(default=50, ge=1, le=5000, description="Max pages budget")
    mode: ExecutionMode = Field(
        default=ExecutionMode.BALANCED, description="Execution mode"
    )
    min_media_count: int = Field(
        default=5, ge=0, description="Minimum relevant media assets to archive"
    )
    max_media_count: int = Field(
        default=25, ge=0, description="Maximum relevant media assets to archive"
    )
    enable_media_archiving: bool = Field(
        default=True, description="Download & archive relevant media files"
    )
    output_archive_path: Optional[str] = Field(
        default=None, description="Custom zip archive path"
    )
    idempotency_key: Optional[str] = Field(
        default=None, description="Client-provided idempotency key"
    )
    auto_discover: bool = Field(
        default=True, description="Enable automatic multi-provider seed discovery"
    )
    category: Optional[str] = Field(
        default=None,
        description="Domain category hint (science, news, engineering, medical)",
    )


class ResearchHandle(BaseModel):
    run_id: str
    idempotency_key: Optional[str] = None
    status: RunLifecycleState = RunLifecycleState.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchStatus(BaseModel):
    run_id: str
    status: RunLifecycleState
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_node: Optional[str] = None
    pages_processed: int = 0
    rag_chunks_created: int = 0
    evidence_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderStatus(BaseModel):
    """Execution status and metrics for an individual seed or discovery provider (§DS-05, DS-13)."""

    provider: str
    status: str = "ok"  # ok, degraded, timeout, failed, disabled
    items_count: int = 0
    error: Optional[str] = None
    duration_sec: float = 0.0


class RunResult(BaseModel):
    """Structured execution outcome with warnings, errors, and provider statuses (§DS-05)."""

    run_id: str
    query: str
    status: RunLifecycleState = RunLifecycleState.COMPLETED
    total_pages_processed: int = 0
    total_rag_chunks: int = 0
    archive_path: Optional[str] = None
    dir_path: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    provider_statuses: Dict[str, ProviderStatus] = Field(default_factory=dict)
    manifest: Dict[str, Any] = Field(default_factory=dict)
    evidence_summary: Optional[Dict[str, Any]] = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchResult(RunResult):
    """Compatibility alias and typed result model for research runs."""

    pass
