"""Extraction Engine (§31, §32, §33 Confidence, §34 Provenance)."""

import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from scraper.extraction.markdown import process_markdown_pipeline
from scraper.extraction.table_extractor import extract_tables_from_html, TableData
from scraper.extraction.self_healing import SelfHealingSelector


class FieldProvenance(BaseModel):
    value: Any
    confidence: float = 1.0  # (§33)
    source_url: str
    selector: Optional[str] = None
    extracted_at: float = Field(default_factory=time.time)


class ExtractionResult(BaseModel):
    url: str
    title: Optional[str] = None
    raw_markdown: str
    clean_markdown: str
    fit_markdown: str
    extracted_records: Dict[str, FieldProvenance] = Field(default_factory=dict)
    tables: List[TableData] = Field(default_factory=list)
    extraction_strategy: str = "E1_DETERMINISTIC"
    abstract_markdown: Optional[str] = None
    full_text_markdown: Optional[str] = None
    source_type: str = "UNKNOWN"
    authority_score: float = 0.5
    relevance_score: Optional[float] = None
    published_at: Optional[str] = None
    document_type: str = "DOCUMENT"
    source_id: Optional[str] = None
    source_title: str = ""
    provider: str = ""
    extraction_completeness: float = 1.0


class ExtractionEngine:
    """Orchestrates E0-E4 extraction strategies (§31)."""

    @classmethod
    def extract_from_html(
        cls, url: str, raw_html: str, selectors: Optional[Dict[str, str]] = None
    ) -> ExtractionResult:
        # 1. Process Markdown Pipeline (§35)
        raw_md, clean_md, fit_md = process_markdown_pipeline(raw_html)

        # 2. Extract Tables (§36)
        tables = extract_tables_from_html(raw_html)

        # 3. Deterministic E1 Selector Extraction (§31 E1)
        records: Dict[str, FieldProvenance] = {}
        if selectors and raw_html:
            for field_name, selector in selectors.items():
                node = SelfHealingSelector.match_element(raw_html, selector)
                if node:
                    val = node.text().strip()
                    records[field_name] = FieldProvenance(
                        value=val, confidence=0.95, source_url=url, selector=selector
                    )

        return ExtractionResult(
            url=url,
            raw_markdown=raw_md,
            clean_markdown=clean_md,
            fit_markdown=fit_md,
            extracted_records=records,
            tables=tables,
            extraction_strategy="E1_DETERMINISTIC",
        )
