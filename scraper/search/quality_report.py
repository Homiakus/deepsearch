"""Source quality policy and run-level quality report."""

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from pydantic import BaseModel

from scraper.acquisition.engine import CapturedArtifact
from scraper.extraction.engine import ExtractionResult
from scraper.search.source_policy import SourceClass, classify_source_class


class SourceQualityRequirements(BaseModel):
    min_independent_domains: int = 2
    min_direct_evidence: int = 3
    min_review_or_benchmark: int = 1
    max_source_chunk_concentration: float = 0.50


class SourceQualityEvaluator:
    """Evaluates corpus quality without treating ZIP creation as success."""

    def evaluate(
        self,
        results: Sequence[Tuple[CapturedArtifact, ExtractionResult]],
        rejections: Optional[Sequence[Dict[str, Any]]] = None,
        requirements: Optional[SourceQualityRequirements] = None,
    ) -> Dict[str, Any]:
        req = requirements or SourceQualityRequirements()
        sources: List[Dict[str, Any]] = []
        chunk_counts: Counter[str] = Counter()

        for artifact, extraction in results:
            domain = urlparse(artifact.url).netloc.lower()
            source_class = classify_source_class(
                artifact.url,
                extraction.source_type,
                extraction.source_title,
            )
            text_for_chunks = extraction.full_text_markdown or extraction.fit_markdown or extraction.clean_markdown
            chunk_count = max(1, math.ceil(len(text_for_chunks.split()) / 250)) if text_for_chunks else 0
            source_id = extraction.source_id or artifact.canonical_url or artifact.url
            chunk_counts[source_id] += chunk_count
            title_lower = extraction.source_title.lower()
            is_review_or_benchmark = any(
                term in title_lower for term in ("survey", "review", "benchmark", "evaluation", "ragas")
            )
            direct_evidence = source_class in {
                SourceClass.PEER_REVIEWED,
                SourceClass.PREPRINT,
                SourceClass.OFFICIAL,
            } and (extraction.relevance_score or 0.0) >= 0.35
            sources.append({
                "source_id": source_id,
                "url": artifact.url,
                "canonical_url": artifact.canonical_url,
                "domain": domain,
                "title": extraction.source_title,
                "provider": extraction.provider,
                "source_type": extraction.source_type,
                "source_class": source_class.value,
                "authority_score": extraction.authority_score,
                "topical_relevance": extraction.relevance_score,
                "extraction_completeness": extraction.extraction_completeness,
                "full_text": bool(extraction.full_text_markdown),
                "published_at": extraction.published_at,
                "chunk_count": chunk_count,
                "direct_evidence": direct_evidence,
                "review_or_benchmark": is_review_or_benchmark,
                "decision": "ACCEPTED",
            })

        total_chunks = sum(chunk_counts.values())
        max_concentration = max(chunk_counts.values(), default=0) / max(total_chunks, 1)
        independent_domains = len({s["domain"] for s in sources if s["domain"]})
        direct_evidence_count = sum(s["direct_evidence"] for s in sources)
        review_count = sum(s["review_or_benchmark"] for s in sources)
        accepted_count = len(sources)
        rejected_count = len(rejections or [])
        source_class_counts = dict(Counter(s["source_class"] for s in sources))
        missing_requirements: List[str] = []
        if independent_domains < req.min_independent_domains:
            missing_requirements.append("MIN_INDEPENDENT_DOMAINS")
        if direct_evidence_count < req.min_direct_evidence:
            missing_requirements.append("MIN_DIRECT_EVIDENCE")
        if review_count < req.min_review_or_benchmark:
            missing_requirements.append("MIN_REVIEW_OR_BENCHMARK")
        if max_concentration > req.max_source_chunk_concentration:
            missing_requirements.append("MAX_SOURCE_CHUNK_CONCENTRATION")

        passed = accepted_count > 0 and not missing_requirements
        return {
            "status": "SUFFICIENT_EVIDENCE" if passed else "INSUFFICIENT_EVIDENCE",
            "passed": passed,
            "requirements": req.model_dump(),
            "summary": {
                "accepted_source_count": accepted_count,
                "rejected_candidate_count": rejected_count,
                "independent_domain_count": independent_domains,
                "direct_evidence_count": direct_evidence_count,
                "direct_evidence_rate": round(direct_evidence_count / max(accepted_count, 1), 3),
                "review_or_benchmark_count": review_count,
                "total_rag_chunks_estimate": total_chunks,
                "max_source_chunk_concentration": round(max_concentration, 3),
                "source_class_counts": source_class_counts,
            },
            "missing_requirements": missing_requirements,
            "sources": sources,
            "rejections": list(rejections or []),
        }


source_quality_evaluator = SourceQualityEvaluator()
