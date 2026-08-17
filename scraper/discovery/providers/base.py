"""Discovery Provider Protocol and Base Descriptors (DS-SI08)."""

from typing import List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field
from scraper.search.candidates import SourceCandidate


class ProviderDescriptor(BaseModel):
    name: str
    supported_domains: List[str] = Field(default_factory=list)
    supported_source_types: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=lambda: ["en", "ru"])
    freshness_capability: str = "MEDIUM"  # REALTIME, HIGH, MEDIUM, ARCHIVAL
    cost_class: str = "FREE"  # FREE, LOW, MEDIUM, HIGH
    rate_limit_class: str = "DEFAULT"


class ProviderSearchRequest(BaseModel):
    query: str
    goal_id: Optional[str] = None
    max_results: int = 5
    language: str = "en"
    timeout_sec: float = 10.0


@runtime_checkable
class DiscoveryProvider(Protocol):
    descriptor: ProviderDescriptor

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        ...
