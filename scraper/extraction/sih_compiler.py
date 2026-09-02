"""Deterministic SIH (Structured Information Hologram) Compiler (DS-39).

Deconstructs extracted text and markdown into typed epistemic propositions and evidence.
"""

from __future__ import annotations

import hashlib
import re

from scraper.normalization.text import sanitize_unicode_string
from scraper.retrieval.epistemic_models import (
    EpistemicEdgeInput,
    EpistemicNodeInput,
    EpistemicNodeKind,
    EpistemicRelation,
)


def compile_markdown_to_sih(
    doc_id: str,
    url: str,
    title: str,
    markdown_text: str,
    context: str = "general",
    scope: str = "public",
) -> tuple[list[EpistemicNodeInput], list[EpistemicEdgeInput]]:
    """Compile extracted markdown into structured epistemic nodes and evidence edges."""
    nodes: list[EpistemicNodeInput] = []
    edges: list[EpistemicEdgeInput] = []

    clean_text = sanitize_unicode_string(markdown_text or "")
    clean_title = sanitize_unicode_string(title or "")
    clean_url = sanitize_unicode_string(url or "")

    domain = clean_url.split("/")[2] if "//" in clean_url else "unknown"
    prov_cluster = f"prov_{domain.replace('.', '_')}"

    # 1. Document Root Proposition Node
    doc_node_id = f"doc:{doc_id}"
    nodes.append(
        EpistemicNodeInput(
            id=doc_node_id,
            kind=EpistemicNodeKind.DOCUMENT,
            text=clean_title or f"Document {clean_url}",
            belief=1.0,
            evidence_quality=0.9,
            context=context,
            scope=scope,
            provenance_cluster=prov_cluster,
        )
    )

    # 2. Split by Headings and Paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean_text) if p.strip()]

    for i, para in enumerate(paragraphs):
        # Ignore trivial paragraphs
        if len(para.split()) < 4:
            continue

        para_hash = hashlib.sha256(para.encode("utf-8")).hexdigest()[:12]
        is_heading = para.startswith("#")

        if is_heading:
            clean_heading = para.lstrip("#").strip()
            heading_node_id = f"claim:{doc_id}:h_{i}_{para_hash}"
            nodes.append(
                EpistemicNodeInput(
                    id=heading_node_id,
                    kind=EpistemicNodeKind.PROPOSITION,
                    text=clean_heading,
                    belief=0.95,
                    evidence_quality=0.9,
                    context=context,
                    scope=scope,
                    provenance_cluster=prov_cluster,
                )
            )
            edges.append(
                EpistemicEdgeInput(
                    from_node=doc_node_id,
                    to_node=heading_node_id,
                    relation=EpistemicRelation.DERIVED_FROM,
                )
            )
        else:
            evidence_node_id = f"evidence:{doc_id}:p_{i}_{para_hash}"
            nodes.append(
                EpistemicNodeInput(
                    id=evidence_node_id,
                    kind=EpistemicNodeKind.EVIDENCE,
                    text=para,
                    belief=0.90,
                    evidence_quality=0.85,
                    context=context,
                    scope=scope,
                    provenance_cluster=prov_cluster,
                )
            )
            edges.append(
                EpistemicEdgeInput(
                    from_node=doc_node_id,
                    to_node=evidence_node_id,
                    relation=EpistemicRelation.EVIDENCE_FOR,
                )
            )

    return nodes, edges
