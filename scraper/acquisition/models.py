"""Acquisition Domain Models and DTOs (§2, §4, DS-RB02)."""

import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from scraper.acquisition.capabilities import BrowserCapabilities


class ArtifactReference(BaseModel):
    """Content-Addressable Storage (CAS) reference to an acquisition artifact (DS-RB26)."""

    content_hash: str
    uri: str
    media_type: str = "text/html"
    size_bytes: int = 0
    metadata_hash: Optional[str] = None


class QualityReport(BaseModel):
    """Quality signals evaluated from page acquisition (DS-RB05)."""

    score: float = 1.0
    completeness: float = 1.0
    blocked: bool = False
    likely_unrendered: bool = False
    reasons: List[str] = Field(default_factory=list)
    suggested_escalation: Optional[str] = None


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
    retry_after_seconds: Optional[float] = None
    timestamp: float = Field(default_factory=time.time)


class AcquisitionRequest(BaseModel):
    """Normalized request for page acquisition across any backend."""

    url: str
    canonical_url: Optional[str] = None
    required_capabilities: BrowserCapabilities = Field(
        default_factory=BrowserCapabilities.create_minimal
    )
    optional_capabilities: Optional[BrowserCapabilities] = None
    mode: str = "balanced"  # fast, balanced, research, complete
    budget_max_ms: float = 30000.0
    security_context: Dict[str, Any] = Field(default_factory=dict)
    session_ref: Optional[str] = None
    wait_condition: Optional[str] = None
    artifact_policy: Dict[str, Any] = Field(default_factory=dict)
    trace_context: Dict[str, str] = Field(default_factory=dict)


class AcquisitionResult(BaseModel):
    """Uniform result returned from any acquisition backend."""

    requested_url: str
    final_url: str
    backend: str
    backend_version: str = "1.0.0"
    status_code: int = 200
    headers: Dict[str, str] = Field(default_factory=dict)
    content_type: str = "text/html"
    raw_content: Optional[bytes] = None
    text_preview: str = ""
    artifact_refs: List[ArtifactReference] = Field(default_factory=list)
    screenshot_bytes: Optional[bytes] = None
    network_summary: Dict[str, Any] = Field(default_factory=dict)
    quality: QualityReport = Field(default_factory=QualityReport)
    cost: CostReport = Field(default_factory=CostReport)
    failure: Optional[FailureRecord] = None
    elapsed_sec: float = 0.0
    capabilities_used: List[str] = Field(default_factory=list)
