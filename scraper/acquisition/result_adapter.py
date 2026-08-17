"""Result Adapter: AcquisitionResult & ArtifactReference -> CapturedArtifact (§4, DS-RB26)."""

import os
from typing import Optional, Dict, Any, List
from scraper.acquisition.models import AcquisitionResult, ArtifactReference
from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import classify_page, PageIntelligence


def adapt_acquisition_result_to_captured_artifact(
    result: AcquisitionResult,
    canonical_url: str,
    cas_storage_dir: Optional[str] = None,
) -> CapturedArtifact:
    """Transforms an AcquisitionResult from Rust/Playwright into the standard CapturedArtifact."""
    raw_content = result.raw_content

    # If raw content was offloaded to CAS, attempt local file resolution
    if raw_content is None and result.artifact_refs and cas_storage_dir:
        for ref in result.artifact_refs:
            if ref.media_type.startswith("text/html"):
                prefix = ref.content_hash[:2]
                file_path = os.path.join(cas_storage_dir, prefix, f"{ref.content_hash}.html")
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        raw_content = f.read()
                    break

    if raw_content is None:
        raw_content = b""

    text_content = result.text_preview or raw_content.decode("utf-8", errors="ignore")

    pi = classify_page(
        result.final_url,
        result.status_code,
        result.headers,
        text_content,
    )

    return CapturedArtifact(
        url=result.final_url,
        canonical_url=canonical_url,
        strategy_used=result.backend,
        status_code=result.status_code,
        content_type=result.content_type,
        raw_content=raw_content,
        text_content=text_content,
        screenshot_bytes=result.screenshot_bytes,
        page_intelligence=pi,
        network_logs=[],
        elapsed_sec=result.elapsed_sec,
    )
