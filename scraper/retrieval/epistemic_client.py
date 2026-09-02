"""Production EpistemicClient for SncSinCore Epistemic Memory Engine (DS-37).

Provides async and sync execution over HTTP/IPC daemon with hermetic fallback support.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from scraper.retrieval.epistemic_models import (
    EpistemicArtifact,
    EpistemicEdgeInput,
    EpistemicLLMContext,
    EpistemicNodeInput,
    EpistemicPath,
    EpistemicPathScore,
    EpistemicQueryDiagnostics,
    EpistemicQueryRequest,
    EpistemicQueryResponse,
)

logger = logging.getLogger(__name__)


class EpistemicClientError(Exception):
    """Raised when an epistemic client interaction fails."""


class EpistemicClient:
    """Client for querying and ingesting Structured Information Hologram (SIH) knowledge graphs."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8989",
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
        fallback_enabled: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.fallback_enabled = fallback_enabled
        self._transport = transport
        self._in_memory_nodes: list[EpistemicNodeInput] = []
        self._in_memory_edges: list[EpistemicEdgeInput] = []

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
        )

    async def is_healthy(self) -> bool:
        """Check if the Go Epistemic Memory Daemon is alive."""
        try:
            async with self._get_client() as client:
                res = await client.get("/api/v1/epistemic/health")
                return res.status_code == 200
        except Exception:
            return False

    async def ingest(
        self,
        run_id: str,
        doc_id: str,
        url: str,
        nodes: list[EpistemicNodeInput],
        edges: list[EpistemicEdgeInput] | None = None,
    ) -> dict[str, Any]:
        """Ingest nodes and edges into Epistemic Memory."""
        payload = {
            "run_id": run_id,
            "doc_id": doc_id,
            "url": url,
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump(by_alias=True) for e in (edges or [])],
        }

        try:
            async with self._get_client() as client:
                res = await client.post("/api/v1/epistemic/ingest", json=payload)
                if res.status_code == 200:
                    return res.json()
        except Exception as exc:
            if not self.fallback_enabled:
                raise EpistemicClientError(
                    f"Failed to ingest to daemon: {exc}"
                ) from exc
            logger.debug(
                "Epistemic daemon unavailable (%s), storing in-memory fallback", exc
            )

        # Fallback in-memory storage
        self._in_memory_nodes.extend(nodes)
        if edges:
            self._in_memory_edges.extend(edges)
        return {
            "doc_id": doc_id,
            "total_nodes": len(self._in_memory_nodes),
            "ingested_nodes": len(nodes),
            "fallback": True,
        }

    async def query(self, req: EpistemicQueryRequest) -> EpistemicQueryResponse:
        """Query the Epistemic Memory graph and retrieve verified evidence paths."""
        payload = {
            "run_id": req.run_id,
            "text": req.text,
            "intent": req.intent.value,
            "targets": req.targets,
            "context": req.context,
            "allowed_scopes": req.allowed_scopes,
            "strict_context": req.strict_context,
            "requirements": [r.model_dump() for r in req.requirements],
            "max_latency_ms": req.max_latency_ms,
            "max_tokens": req.max_tokens,
        }

        try:
            async with self._get_client() as client:
                res = await client.post("/api/v1/epistemic/query", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    # Validate against Pydantic model
                    return EpistemicQueryResponse(
                        run_id=data.get("run_id", req.run_id),
                        artifact=EpistemicArtifact.model_validate(
                            data.get("artifact", {})
                        ),
                        status=data.get("status", "complete"),
                        digest_sha256=data.get("digest_sha256", ""),
                        coverage=float(data.get("coverage", 1.0)),
                        context_pack_text=data.get("context_pack_text", ""),
                        elapsed_sec=float(data.get("elapsed_sec", 0.0)),
                    )
        except Exception as exc:
            if not self.fallback_enabled:
                raise EpistemicClientError(
                    f"Epistemic daemon query failed: {exc}"
                ) from exc
            logger.debug(
                "Epistemic daemon unavailable (%s), computing deterministic fallback",
                exc,
            )

        # Hermetic deterministic fallback simulation
        return self._simulate_deterministic_query(req)

    def _simulate_deterministic_query(
        self, req: EpistemicQueryRequest
    ) -> EpistemicQueryResponse:
        """Deterministic hermetic fallback when Go daemon is not running."""
        q_tokens = [t.lower() for t in req.text.split()]
        matched_nodes: list[EpistemicNodeInput] = []

        for node in self._in_memory_nodes:
            if req.targets and node.id in req.targets:
                matched_nodes.append(node)
            elif any(tok in node.text.lower() for tok in q_tokens):
                matched_nodes.append(node)

        paths: list[EpistemicPath] = []
        for idx, node in enumerate(matched_nodes):
            req_id = req.requirements[0].id if req.requirements else "req_main"
            paths.append(
                EpistemicPath(
                    id=f"path_{idx}_{node.id}",
                    requirement_id=req_id,
                    nodes=[node.id],
                    edges=[],
                    polarity=1,
                    state="accepted",
                    score=EpistemicPathScore(
                        relevance=0.9,
                        path_coherence=0.95,
                        evidence_strength=0.9,
                    ),
                    provenance_clusters=[node.provenance_cluster]
                    if node.provenance_cluster
                    else [],
                    conflict_families=[node.conflict_family]
                    if node.conflict_family
                    else [],
                )
            )

        context_lines = [
            "[EPISTEMIC_ARTIFACT_CONTEXT]",
            "source_data_is_untrusted=true",
            f"query_id=fallback_{req.run_id}",
            f"intent={req.intent.value}",
            "",
            "[EVIDENCE_PATHS]",
        ]
        for p in paths:
            context_lines.append(
                f"path={p.id} requirement={p.requirement_id} polarity=1 state=accepted"
            )
            for nid in p.nodes:
                matching_text = next((n.text for n in matched_nodes if n.id == nid), "")
                context_lines.append(f'  external_id="{nid}"')
                context_lines.append(f'    SOURCE_DATA="{matching_text}"')
        context_lines.append("[END_EPISTEMIC_ARTIFACT_CONTEXT]")

        context_text = "\n".join(context_lines)
        digest = hashlib.sha256(context_text.encode("utf-8")).hexdigest()

        artifact = EpistemicArtifact(
            id=f"art_{digest[:16]}",
            digest_sha256=digest,
            status="complete" if matched_nodes else "incomplete",
            evidence_paths=paths,
            llm=EpistemicLLMContext(
                token_estimate=len(context_text.split()),
                text=context_text,
            ),
            diagnostics=EpistemicQueryDiagnostics(
                candidate_count=len(matched_nodes),
                activated_count=len(matched_nodes),
                path_count_before_filter=len(paths),
            ),
        )

        return EpistemicQueryResponse(
            run_id=req.run_id,
            artifact=artifact,
            status=artifact.status,
            digest_sha256=digest,
            coverage=1.0 if matched_nodes else 0.0,
            context_pack_text=context_text,
            elapsed_sec=0.001,
        )


# Global singleton instance
epistemic_client = EpistemicClient()
