"""Source Lineage and Provenance Relationships (DS-SI36)."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class LineageRelation(str, Enum):
    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    INDEPENDENT_CORROBORATION = "INDEPENDENT_CORROBORATION"
    SYNDICATED_COPY = "SYNDICATED_COPY"
    SUMMARY_OF_SOURCE = "SUMMARY_OF_SOURCE"
    DERIVED_MIRROR = "DERIVED_MIRROR"
    SAME_PUBLISHER = "SAME_PUBLISHER"
    UNKNOWN = "UNKNOWN"


class SourceNode(BaseModel):
    source_id: str
    url: str
    domain: str
    publisher: Optional[str] = None
    relation_to_root: LineageRelation = LineageRelation.UNKNOWN
    is_primary: bool = False
    content_hash: str = ""
    near_dup_cluster: int = 0


class SourceLineage(BaseModel):
    """Tracks publisher relationships and distinguishes copies from independent corroboration."""

    sources: Dict[str, SourceNode] = Field(default_factory=dict)
    primary_source_ids: List[str] = Field(default_factory=list)

    def register_source(
        self,
        source_id: str,
        url: str,
        domain: str,
        content_hash: str = "",
        near_dup_cluster: int = 0,
        is_primary: bool = False,
    ) -> SourceNode:
        # Check if another source shares the exact content hash or near dup cluster
        relation = LineageRelation.INDEPENDENT_CORROBORATION
        if is_primary or not self.sources:
            relation = LineageRelation.PRIMARY_SOURCE

        for existing in self.sources.values():
            if existing.domain == domain:
                relation = LineageRelation.SAME_PUBLISHER
                break
            if content_hash and existing.content_hash == content_hash:
                relation = LineageRelation.DERIVED_MIRROR
                break
            if near_dup_cluster > 0 and existing.near_dup_cluster == near_dup_cluster:
                relation = LineageRelation.SYNDICATED_COPY
                break

        node = SourceNode(
            source_id=source_id,
            url=url,
            domain=domain,
            relation_to_root=relation,
            is_primary=(relation == LineageRelation.PRIMARY_SOURCE),
            content_hash=content_hash,
            near_dup_cluster=near_dup_cluster,
        )

        self.sources[source_id] = node
        if node.is_primary:
            self.primary_source_ids.append(source_id)

        return node

    def count_independent_sources(self) -> int:
        """Counts only genuinely independent source domains."""
        indep_domains = set()
        for s in self.sources.values():
            if s.relation_to_root in (
                LineageRelation.PRIMARY_SOURCE,
                LineageRelation.INDEPENDENT_CORROBORATION,
            ):
                indep_domains.add(s.domain)
        return len(indep_domains)
