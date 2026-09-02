"""Reranker Base Interface (DS-SI42)."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from scraper.search.retrieval.hybrid import FusedResult


class RerankedPassage(BaseModel):
    fused_result: FusedResult
    rerank_score: float
    calibrated_confidence: float
    explanation: str = ""


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: list[FusedResult], top_n: int = 10
    ) -> list[RerankedPassage]: ...
