"""Discovery Provider Protocol and Base Descriptors (DS-13)."""

from enum import Enum
from typing import Protocol, runtime_checkable

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
    error: str | None = None


class ProviderDescriptor(BaseModel):
    name: str
    supported_domains: list[str] = Field(default_factory=list)
    supported_source_types: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en", "ru"])
    freshness_capability: str = "MEDIUM"  # REALTIME, HIGH, MEDIUM, ARCHIVAL
    cost_class: str = "FREE"  # FREE, LOW, MEDIUM, HIGH
    rate_limit_class: str = "DEFAULT"
    opt_in_only: bool = False


class ProviderSearchRequest(BaseModel):
    query: str
    goal_id: str | None = None
    max_results: int = 5
    language: str = "en"
    timeout_sec: float = 10.0


@runtime_checkable
class DiscoveryProvider(Protocol):
    descriptor: ProviderDescriptor

    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]: ...
