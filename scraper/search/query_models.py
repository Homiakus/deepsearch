"""Search Query Variant Models (DS-SI07)."""

from enum import Enum

from pydantic import BaseModel


class QueryType(str, Enum):
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"
    ENTITY = "ENTITY"
    EXACT = "EXACT"
    DOMAIN_SPECIFIC = "DOMAIN_SPECIFIC"
    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    CONTRADICTION = "CONTRADICTION"
    FOLLOW_UP = "FOLLOW_UP"


class SearchQueryVariant(BaseModel):
    query: str
    language: str = "en"
    provider_hint: str | None = None  # arxiv, pubmed, wikipedia, etc.
    goal_id: str
    query_type: QueryType = QueryType.SEMANTIC
    freshness: str = "NONE"
    required_source_type: str | None = None
    priority: float = 1.0
