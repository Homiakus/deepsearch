"""Structured Document Domain Model (§9, DS-A24)."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    heading: str = Field(default="")
    level: int = 1
    text: str
    ordinal: int = 0
    section_path: list[str] = Field(default_factory=list)


class DocumentTable(BaseModel):
    table_id: str
    caption: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    markdown: str | None = None


class DocumentFigure(BaseModel):
    figure_id: str
    caption: str | None = None
    image_url: str | None = None
    alt_text: str | None = None


class DocumentProvenance(BaseModel):
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fetch_strategy: str = "HTTP"
    content_hash: str
    status_code: int = 200
    robots_decision: str = "allowed"


class Document(BaseModel):
    """Authoritative structural domain document model representing parsed content."""

    id: str
    source_url: str
    canonical_url: str
    title: str = "Untitled"
    language: str = "en"
    clean_markdown: str
    sections: list[DocumentSection] = Field(default_factory=list)
    tables: list[DocumentTable] = Field(default_factory=list)
    figures: list[DocumentFigure] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: DocumentProvenance
