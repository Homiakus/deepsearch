"""Extraction activity implementation (§4, DS-A09, DS-A24)."""

from typing import Any, Dict, List
from scraper.extraction.engine import ExtractionEngine
from scraper.orchestration.protocol import ActivityResult, ResourceUsage


async def run_extraction_activity(input_data: Dict[str, Any]) -> ActivityResult:
    """Extracts clean Markdown, fit summary, and structured tables from acquired artifacts."""
    artifacts: List[Dict[str, Any]] = input_data.get("acquired_artifacts", [])
    extracted_docs = []

    for art in artifacts:
        html = art.get("html_content")
        url = art.get("url", "")
        if not html:
            continue

        try:
            res = ExtractionEngine.extract_from_html(url, html)
            extracted_docs.append(
                {
                    "url": url,
                    "canonical_url": art.get("canonical_url", url),
                    "clean_markdown": res.clean_markdown,
                    "fit_markdown": res.fit_markdown,
                    "tables": [t.model_dump() for t in res.tables]
                    if res.tables
                    else [],
                    "extracted_records": res.extracted_records,
                    "word_count": len(res.clean_markdown.split()),
                }
            )
        except Exception as e:
            extracted_docs.append(
                {
                    "url": url,
                    "error": str(e),
                }
            )

    return ActivityResult(
        data={
            "extracted_docs": extracted_docs,
            "total_extracted": len(extracted_docs),
        },
        usage=ResourceUsage(tokens=sum(d.get("word_count", 0) for d in extracted_docs)),
        quality={"extraction_completeness": 1.0 if extracted_docs else 0.0},
    )
