"""Acquisition Domain Models and DTOs (§2, §4, DS-RB02)."""

import time
from typing import Any

from pydantic import BaseModel, Field

from scraper.acquisition.capabilities import BrowserCapabilities


class ArtifactReference(BaseModel):
    """Content-Addressable Storage (CAS) reference to an acquisition artifact (DS-RB26)."""

    content_hash: str
    uri: str
    media_type: str = "text/html"
    size_bytes: int = 0
    metadata_hash: str | None = None


class QualityReport(BaseModel):
    """Quality signals evaluated from page acquisition (DS-RB05)."""

    score: float = 1.0
    completeness: float = 1.0
    blocked: bool = False
    likely_unrendered: bool = False
    reasons: list[str] = Field(default_factory=list)
    suggested_escalation: str | None = None


class CostReport(BaseModel):
    """Resource consumption accounting for acquisition run (DS-RB32)."""

    base_cost: float = 1.0
    execution_time_ms: float = 0.0
    memory_mb: float = 0.0
    network_bytes: int = 0
    cpu_time_ms: float = 0.0


class FailureRecord(BaseModel):
    """Failure diagnostics when acquisition cannot complete cleanly (DS-RB31)."""

    failure_class: str  # transient, rate_limit, permanent, security, quality
    message: str
    retryable: bool = False
    retry_after_seconds: float | None = None
    timestamp: float = Field(default_factory=time.time)


class AcquisitionRequest(BaseModel):
    """Normalized request for page acquisition across any backend."""

    url: str
    canonical_url: str | None = None
    required_capabilities: BrowserCapabilities = Field(
        default_factory=BrowserCapabilities.create_minimal
    )
    optional_capabilities: BrowserCapabilities | None = None
    mode: str = "balanced"  # fast, balanced, research, complete
    budget_max_ms: float = 30000.0
    security_context: dict[str, Any] = Field(default_factory=dict)
    session_ref: str | None = None
    wait_condition: str | None = None
    artifact_policy: dict[str, Any] = Field(default_factory=dict)
    trace_context: dict[str, str] = Field(default_factory=dict)


class AcquisitionResult(BaseModel):
    """Uniform result returned from any acquisition backend."""

    requested_url: str
    final_url: str
    backend: str
    backend_version: str = "1.0.0"
    status_code: int = 200
    headers: dict[str, str] = Field(default_factory=dict)
    content_type: str = "text/html"
    raw_content: bytes | None = None
    text_preview: str = ""
    artifact_refs: list[ArtifactReference] = Field(default_factory=list)
    screenshot_bytes: bytes | None = None
    network_summary: dict[str, Any] = Field(default_factory=dict)
    quality: QualityReport = Field(default_factory=QualityReport)
    cost: CostReport = Field(default_factory=CostReport)
    failure: FailureRecord | None = None
    elapsed_sec: float = 0.0
    capabilities_used: list[str] = Field(default_factory=list)
