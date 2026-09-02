"""Export activity implementation (§4, DS-A09, DS-A48)."""

from typing import Any

from scraper.orchestration.protocol import ActivityResult, ResourceUsage
from scraper.pipeline.search_pipeline import ArchiveExporter


async def run_export_activity(input_data: dict[str, Any]) -> ActivityResult:
    """Exports structured research artifacts and markdown corpus to ZIP archive."""
    query = input_data.get("query", "research")
    output_zip = (
        input_data.get("output_archive_path")
        or f"deepsearch_adgo_{query[:15].replace(' ', '_')}.zip"
    )
    docs = input_data.get("extracted_docs", [])
    chunks = input_data.get("indexed_chunks", [])

    exporter = ArchiveExporter(output_zip_path=output_zip)
    manifest = exporter.export_dataset(
        query=query,
        extracted_pages=docs,
        total_chunks=len(chunks),
        media_assets=[],
    )

    return ActivityResult(
        data={
            "research_archive": {
                "archive_path": output_zip,
                "dir_path": output_zip.replace(".zip", ""),
                "manifest": manifest,
            }
        },
        usage=ResourceUsage(cost=0.01),
        quality={"export_valid": 1.0},
    )
