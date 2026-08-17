"""Source Candidate Models (DS-SI11)."""

import urllib.parse
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SourceCandidate(BaseModel):
    url: str
    canonical_url: str
    title: str = ""
    snippet: str = ""
    provider: str
    provider_rank: int = 1
    source_type: str = "UNKNOWN"
    published_at: Optional[str] = None
    domain: str = ""
    goal_ids: List[str] = Field(default_factory=list)
    query_variants: List[str] = Field(default_factory=list)
    found_by_providers: List[str] = Field(default_factory=list)
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    authority_prior: float = 0.5
    freshness_score: float = 0.5
    novelty_prior: float = 1.0
    expected_cost: float = 1.0
    expected_extractability: float = 0.9
    risk_score: float = 0.0
    provider_metadata: Dict[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if not self.domain and self.url:
            parsed = urllib.parse.urlparse(self.url)
            self.domain = parsed.netloc.lower()
        if not self.canonical_url:
            self.canonical_url = self.url
        if self.provider and self.provider not in self.found_by_providers:
            self.found_by_providers.append(self.provider)
