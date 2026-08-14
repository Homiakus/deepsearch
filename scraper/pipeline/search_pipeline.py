"""DeepSearch Pipeline Orchestrator.

Combines query interpretation, preferred sources seed discovery, depth crawl control,
adaptive page acquisition, content extraction, and dual-format archive generation.
"""

import os
import re
import json
import shutil
import tempfile
import logging
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field

from scraper.config import settings, ExecutionMode
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine, CapturedArtifact
from scraper.extraction.engine import ExtractionEngine, ExtractionResult
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata
from scraper.discovery.links import extract_links_from_html
from scraper.discovery.seed_finder import discover_diverse_seeds

from scraper.discovery.media_finder import (
    extract_document_links,
    extract_image_candidates,
    fetch_wikimedia_topic_images,
    fetch_wikipedia_article_images,
    score_and_rank_images
)
from scraper.acquisition.media_downloader import download_media_file
from scraper.extraction.pdf_extractor import extract_text_from_pdf_file

logger = logging.getLogger(__name__)


class DeepSearchPipelineOptions(BaseModel):
    query: str
    domain: Optional[str] = None
    preferred_sources: List[str] = Field(default_factory=list)
    depth: int = 3
    max_pages: int = 50
    mode: ExecutionMode = ExecutionMode.BALANCED
    take_screenshot: bool = False
    output_archive_path: Optional[str] = None
    output_dir_path: Optional[str] = None
    auto_discover_sources: bool = True
    category: Optional[str] = None  # science | news | engineering | None (auto-detect)
    enable_media_archiving: bool = True
    min_media_count: int = 5
    max_media_count: int = 25


class DeepSearchPipelineResult(BaseModel):
    query: str
    total_pages_processed: int
    total_rag_chunks: int
    archive_path: Optional[str] = None
    dir_path: Optional[str] = None
    manifest: Dict[str, Any] = Field(default_factory=dict)


class DeepSearchPipeline:
    """End-to-end DeepSearch research & extraction pipeline."""

    def __init__(self, acquisition_engine: Optional[AdaptiveAcquisitionEngine] = None):
        self.acquisition_engine = acquisition_engine or AdaptiveAcquisitionEngine()

    async def execute(self, opts: DeepSearchPipelineOptions) -> DeepSearchPipelineResult:
        logger.info("Starting DeepSearch Pipeline for query='%s', domain='%s', depth=%d", opts.query, opts.domain, opts.depth)

        # 1. Determine seed URLs via multi-source discovery
        if opts.auto_discover_sources:
            seed_urls = await discover_diverse_seeds(
                query=opts.query,
                domain=opts.domain,
                preferred_sources=opts.preferred_sources or None,
                category=opts.category
            )
        else:
            seed_urls = list(opts.preferred_sources)
            if not seed_urls:
                seed_urls = [f"https://{opts.domain or 'wikipedia.org'}/wiki/{opts.query.replace(' ', '_')}"]

        logger.info("Resolved %d seed URLs: %s", len(seed_urls), seed_urls)
        queued_urls: List[Tuple[str, int]] = [(url, 0) for url in seed_urls]
        visited_canonical: set = set()
        acquired_results: List[Tuple[CapturedArtifact, ExtractionResult]] = []
        downloaded_pdfs: List[Dict[str, Any]] = []
        raw_image_candidates: List[Dict[str, Any]] = []
        pdf_temp_dir = tempfile.mkdtemp(prefix="deepsearch_pdfs_")

        # 2. Iterative Depth Crawl & Acquisition Loop
        while queued_urls and len(acquired_results) < opts.max_pages:
            current_url, current_depth = queued_urls.pop(0)
            c_url = canonicalize_url(current_url)

            if c_url in visited_canonical:
                continue
            visited_canonical.add(c_url)

            # Filter by domain only when auto_discover_sources is disabled (strict mode)
            if not opts.auto_discover_sources and opts.domain and opts.domain.lower() not in current_url.lower():
                logger.debug("Skipping URL %s - does not match domain scope %s", current_url, opts.domain)
                continue

            try:
                artifact = await self.acquisition_engine.acquire_page(
                    url=current_url,
                    canonical_url=c_url,
                    mode=opts.mode,
                    take_screenshot=opts.take_screenshot
                )

                extraction = ExtractionEngine.extract_from_html(
                    url=artifact.url,
                    raw_html=artifact.text_content
                )

                # EuropePMC REST Full Text XML Fallback if HTML text is an empty shell
                pmc_match = re.search(r'PMC\d+', artifact.url, re.IGNORECASE)
                if pmc_match and (len(extraction.clean_markdown.strip()) < 400 or artifact.page_intelligence.content_quality < 0.2):
                    pmcid = pmc_match.group(0).upper()
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                            # 1. Fetch EuropePMC REST Full Text XML
                            xml_res = await client.get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
                            if xml_res.status_code == 200 and len(xml_res.text) > 500:
                                from selectolax.parser import HTMLParser as XMLParser
                                xml_p = XMLParser(xml_res.text)
                                body_node = xml_p.css_first("body")
                                if body_node:
                                    xml_text = body_node.text(strip=True, separator="\n\n")
                                    if len(xml_text) > 300:
                                        extraction.clean_markdown = f"# Article {pmcid}\n\n" + xml_text
                                        extraction.fit_markdown = extraction.clean_markdown

                            # 2. Download NCBI PMC PDF as source PDF backup
                            ncbi_pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                            pdf_info = await download_media_file(ncbi_pdf_url, output_dir=pdf_temp_dir, filename_prefix=pmcid)
                            if pdf_info:
                                downloaded_pdfs.append(pdf_info)
                                pdf_text = extract_text_from_pdf_file(pdf_info["file_path"])
                                if pdf_text and len(extraction.clean_markdown.strip()) < 400:
                                    extraction.clean_markdown = pdf_text
                                    extraction.fit_markdown = pdf_text
                    except Exception as pmc_exc:
                        logger.warning("PMC REST/PDF fallback error for %s: %s", pmcid, pmc_exc)

                # PDF document discovery & acquisition
                doc_links = extract_document_links(artifact.text_content, base_url=artifact.url)
                extracted_pdf_text = ""
                for doc_url in doc_links:
                    if doc_url.lower().endswith(".pdf") or "ptpmcrender.fcgi" in doc_url.lower() or "/pdf" in doc_url.lower():
                        pdf_info = await download_media_file(doc_url, output_dir=pdf_temp_dir)
                        if pdf_info:
                            downloaded_pdfs.append(pdf_info)
                            # Extract text from downloaded PDF
                            pdf_text = extract_text_from_pdf_file(pdf_info["file_path"])
                            if pdf_text:
                                extracted_pdf_text += f"\n\n### Document Source PDF: {pdf_info['filename']}\n\n" + pdf_text

                # If extracted HTML text is trivial/empty shell (<300 chars or quality score <0.2) and PDF text is available
                if (len(extraction.clean_markdown.strip()) < 300 or artifact.page_intelligence.content_quality < 0.2) and extracted_pdf_text:
                    extraction.clean_markdown = extracted_pdf_text
                    extraction.fit_markdown = extracted_pdf_text

                # Collect image candidates from acquired HTML page
                if opts.enable_media_archiving:
                    page_images = extract_image_candidates(artifact.text_content, base_url=artifact.url)
                    raw_image_candidates.extend(page_images)

                acquired_results.append((artifact, extraction))

                # Discovery for next depth if depth budget permits
                if current_depth < opts.depth and len(acquired_results) < opts.max_pages:
                    discovered_links = extract_links_from_html(artifact.text_content, base_url=artifact.url)
                    for link in discovered_links[:10]:  # Limit link expansion per page
                        c_link = canonicalize_url(link)
                        if c_link not in visited_canonical:
                            queued_urls.append((link, current_depth + 1))

            except Exception as exc:
                logger.warning("Failed acquisition/extraction for %s: %s", current_url, exc)

        # 3. Topic Media Discovery, Scoring & Acquisition (5 to 25 images)
        downloaded_media: List[Dict[str, Any]] = []
        if opts.enable_media_archiving:
            try:
                # Discover open media via Wikimedia Commons API & Wikipedia Article Images API for the topic
                wiki_media = await fetch_wikimedia_topic_images(opts.query, max_results=opts.max_media_count)
                wiki_art_media = await fetch_wikipedia_article_images(opts.query, max_results=opts.max_media_count)
                raw_image_candidates.extend(wiki_media)
                raw_image_candidates.extend(wiki_art_media)

                # Score & rank image candidates against query topic
                ranked_images = score_and_rank_images(
                    candidates=raw_image_candidates,
                    query=opts.query,
                    min_count=opts.min_media_count,
                    max_count=opts.max_media_count
                )


                logger.info("Selected %d top-ranked media images for topic '%s'", len(ranked_images), opts.query)

                # Download top-ranked images
                media_temp_dir = tempfile.mkdtemp(prefix="deepsearch_media_")
                for idx, img in enumerate(ranked_images, start=1):
                    m_info = await download_media_file(
                        url=img["url"],
                        output_dir=media_temp_dir,
                        filename_prefix=f"img_{idx:02d}",
                        caption=img.get("caption", "")
                    )
                    if m_info:
                        m_info["relevance_score"] = img.get("relevance_score", 1.0)
                        downloaded_media.append(m_info)

            except Exception as media_exc:
                logger.warning("Topic media selection/download error: %s", media_exc)

        # 4. Export Archive & RAG Datasets
        metadata = SearchRunMetadata(
            query=opts.query,
            domain=opts.domain,
            preferred_sources=opts.preferred_sources,
            depth=opts.depth,
            max_pages=opts.max_pages,
            mode=opts.mode.value
        )
        exporter = ArchiveExporter(metadata=metadata)

        # Use temporary or target output directory
        temp_dir = opts.output_dir_path or tempfile.mkdtemp(prefix="deepsearch_run_")
        built_dir = exporter.build_archive_structure(
            acquired_results,
            output_dir=temp_dir,
            pdf_files=downloaded_pdfs,
            media_files=downloaded_media
        )

        archive_zip_path = None
        if opts.output_archive_path:
            archive_zip_path = exporter.pack_zip_archive(built_dir, opts.output_archive_path)

        manifest_file = os.path.join(built_dir, "manifest.json")
        manifest_data = {}
        if os.path.exists(manifest_file):
            with open(manifest_file, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)

        total_chunks = manifest_data.get("summary", {}).get("total_rag_chunks", 0)

        return DeepSearchPipelineResult(
            query=opts.query,
            total_pages_processed=len(acquired_results),
            total_rag_chunks=total_chunks,
            archive_path=archive_zip_path,
            dir_path=built_dir,
            manifest=manifest_data
        )

