"""Structured Document Domain Model (§9, DS-A24)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    heading: str = Field(default="")
    level: int = 1
    text: str
    ordinal: int = 0
    section_path: List[str] = Field(default_factory=list)


class DocumentTable(BaseModel):
    table_id: str
    caption: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown: Optional[str] = None


class DocumentFigure(BaseModel):
    figure_id: str
    caption: Optional[str] = None
    image_url: Optional[str] = None
    alt_text: Optional[str] = None


class DocumentProvenance(BaseModel):
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    sections: List[DocumentSection] = Field(default_factory=list)
    tables: List[DocumentTable] = Field(default_factory=list)
    figures: List[DocumentFigure] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: DocumentProvenance
