"""Discovery Provider Protocol and Base Descriptors (DS-13)."""

from enum import Enum
from typing import List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field
from scraper.search.candidates import SourceCandidate


class ProviderStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProviderExecutionReport(BaseModel):
    provider_name: str
    status: ProviderStatus
    candidate_count: int = 0
    latency_sec: float = 0.0
    error: Optional[str] = None


class ProviderDescriptor(BaseModel):
    name: str
    supported_domains: List[str] = Field(default_factory=list)
    supported_source_types: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=lambda: ["en", "ru"])
    freshness_capability: str = "MEDIUM"  # REALTIME, HIGH, MEDIUM, ARCHIVAL
    cost_class: str = "FREE"  # FREE, LOW, MEDIUM, HIGH
    rate_limit_class: str = "DEFAULT"
    opt_in_only: bool = False


class ProviderSearchRequest(BaseModel):
    query: str
    goal_id: Optional[str] = None
    max_results: int = 5
    language: str = "en"
    timeout_sec: float = 10.0


@runtime_checkable
class DiscoveryProvider(Protocol):
    descriptor: ProviderDescriptor

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]: ...
