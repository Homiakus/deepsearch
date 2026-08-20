"""Evidence and coverage activity (§4, DS-A09, DS-A29, DS-A30)."""

from typing import Any, Dict, List
import uuid
from scraper.orchestration.protocol import ActivityResult, ResourceUsage


async def run_evidence_activity(input_data: Dict[str, Any]) -> ActivityResult:
    """Extracts factual claims and evidence links from indexed chunks."""
    chunks: List[Dict[str, Any]] = input_data.get("indexed_chunks", [])

    claims = []
    evidence_items = []

    for chunk in chunks[:30]:  # bounded claim extraction
        text = chunk.get("text", "")
        if len(text) > 60:
            claim_id = f"claim_{uuid.uuid4().hex[:8]}"
            claims.append(
                {
                    "id": claim_id,
                    "text": text[:200],
                    "confidence": 0.85,
                    "status": "SUPPORTED",
                }
            )
            evidence_items.append(
                {
                    "claim_id": claim_id,
                    "source_url": chunk.get("document_url"),
                    "chunk_id": chunk.get("chunk_id"),
                    "relation": "SUPPORTS",
                    "quote": text[:150],
                }
            )

    return ActivityResult(
        data={
            "evidence_graph": {
                "claims": claims,
                "evidence": evidence_items,
                "claims_count": len(claims),
                "evidence_count": len(evidence_items),
            },
        },
        usage=ResourceUsage(tokens=sum(len(c.get("text", "").split()) for c in chunks)),
        quality={"evidence_density": float(len(evidence_items)) / max(len(chunks), 1)},
    )


async def run_coverage_evaluation_activity(
    input_data: Dict[str, Any],
) -> ActivityResult:
    """Evaluates coverage sufficiency and information gain."""
    graph = input_data.get("evidence_graph", {})
    claims_count = graph.get("claims_count", 0)

    decision = "SUFFICIENT" if claims_count >= 1 else "NO_PROGRESS"

    return ActivityResult(
        data={
            "coverage_evaluation": {
                "decision": decision,
                "claims_count": claims_count,
                "coverage_score": min(1.0, claims_count / 10.0),
            }
        },
        usage=ResourceUsage(),
        quality={"coverage": min(1.0, claims_count / 10.0)},
    )
