"""Canonical DeepSearch Platform Capability Matrix (§DS-01).

Defines the single source of truth for platform capabilities, their readiness tier
(stable, experimental, disabled), and boundary enforcement guards.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CapabilityStatus(str, Enum):
    """Honest readiness classification for every DeepSearch subsystem."""

    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    DISABLED = "disabled"


class CapabilityInfo(BaseModel):
    """Metadata describing a platform capability and its verified operational boundary."""

    name: str
    status: CapabilityStatus
    description: str
    interface_bindings: List[str] = Field(default_factory=list)
    reason_disabled: Optional[str] = None


class CapabilityUnavailableError(RuntimeError):
    """Raised when an operation requires a disabled or unconfigured capability."""

    def __init__(self, capability: str, status: CapabilityStatus, message: str):
        super().__init__(
            f"Capability '{capability}' is unavailable (status={status.value}): {message}"
        )
        self.capability = capability
        self.status = status
        self.message = message


CAPABILITY_REGISTRY: Dict[str, CapabilityInfo] = {
    "research_pipeline": CapabilityInfo(
        name="research_pipeline",
        status=CapabilityStatus.STABLE,
        description="End-to-end multi-provider discovery, adaptive acquisition, and dual-format archive export.",
        interface_bindings=[
            "CLI: scraper research",
            "REST: POST /api/v1/research",
            "MCP: deepsearch_research",
        ],
    ),
    "url_inspection": CapabilityInfo(
        name="url_inspection",
        status=CapabilityStatus.STABLE,
        description="Static/JS scoring, API detection, table counting, and acquisition strategy selection.",
        interface_bindings=[
            "CLI: scraper inspect",
            "REST: POST /api/v1/inspect",
            "MCP: deepsearch_inspect",
        ],
    ),
    "content_extraction": CapabilityInfo(
        name="content_extraction",
        status=CapabilityStatus.STABLE,
        description="Clean & fit Markdown extraction, table conversion (CSV/JSON/MD), and metadata extraction.",
        interface_bindings=[
            "CLI: scraper extract",
            "REST: POST /api/v1/extract",
            "MCP: deepsearch_extract",
        ],
    ),
    "seed_discovery": CapabilityInfo(
        name="seed_discovery",
        status=CapabilityStatus.STABLE,
        description="Multi-source academic and knowledge provider seed query discovery.",
        interface_bindings=["REST: POST /api/v1/discover", "MCP: deepsearch_discover"],
    ),
    "archive_export": CapabilityInfo(
        name="archive_export",
        status=CapabilityStatus.STABLE,
        description="Structured ZIP, JSONL RAG chunks, and Obsidian/Zotero export generation.",
        interface_bindings=[
            "REST: POST /api/v1/research/{id}/export/*",
            "CLI: --output flag",
        ],
    ),
    "hybrid_search": CapabilityInfo(
        name="hybrid_search",
        status=CapabilityStatus.EXPERIMENTAL,
        description="Dense semantic and sparse lexical vector retrieval over indexed local corpus.",
        interface_bindings=[
            "CLI: scraper search",
            "REST: POST /api/v1/search/query",
            "MCP: deepsearch_search",
        ],
        reason_disabled="Requires populated local Qdrant/FastEmbed vector index; returns empty state when unpopulated.",
    ),
    "pixel_rag": CapabilityInfo(
        name="pixel_rag",
        status=CapabilityStatus.DISABLED,
        description="Multimodal visual patch embedding and multivector tile similarity retrieval.",
        interface_bindings=["REST: POST /api/v1/search/visual"],
        reason_disabled="Disabled until real ColPali/Qwen2-VL native model weights and inference runtime are integrated.",
    ),
    "ocr_engine": CapabilityInfo(
        name="ocr_engine",
        status=CapabilityStatus.DISABLED,
        description="PaddleOCR visual text extraction and bounding box polygon generation.",
        interface_bindings=["Internal visual pipeline"],
        reason_disabled="Disabled when native PaddleOCR / CUDA binaries are not loaded in runtime environment.",
    ),
    "distributed_queue_postgres_redis": CapabilityInfo(
        name="distributed_queue_postgres_redis",
        status=CapabilityStatus.DISABLED,
        description="PostgreSQL persistence and Redis Streams distributed task queue.",
        interface_bindings=["Internal frontier scheduler"],
        reason_disabled="In-memory SQLite/JSON queue is active by default; external backends disabled until DS-13.",
    ),
    "rust_worker_acquisition": CapabilityInfo(
        name="rust_worker_acquisition",
        status=CapabilityStatus.EXPERIMENTAL,
        description="High-performance Rust sidecar worker client for HTTP acquisition.",
        interface_bindings=["scraper/acquisition/rust_worker_client.py"],
    ),
}


def get_capability_matrix() -> Dict[str, CapabilityInfo]:
    """Return the canonical capability registry mapping."""
    return dict(CAPABILITY_REGISTRY)


def require_capability(name: str) -> CapabilityInfo:
    """Enforce that a required capability is not disabled, raising CapabilityUnavailableError if disabled."""
    info = CAPABILITY_REGISTRY.get(name)
    if not info:
        raise CapabilityUnavailableError(
            capability=name,
            status=CapabilityStatus.DISABLED,
            message=f"Unknown capability '{name}'",
        )
    if info.status == CapabilityStatus.DISABLED:
        raise CapabilityUnavailableError(
            capability=name,
            status=info.status,
            message=info.reason_disabled or "Capability is currently disabled",
        )
    return info
