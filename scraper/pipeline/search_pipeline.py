"""DeepSearch Pipeline Orchestrator with Search Intelligence & Ranked Frontier (DS-SI23, DS-SI81).

Combines query intelligence, multi-provider discovery, ranked frontier crawl control,
adaptive page acquisition, content quality filtering, and dual-format archive generation.
"""

import os
import re
import json
import tempfile
import logging
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field

from scraper.config import ExecutionMode
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine, CapturedArtifact
from scraper.extraction.engine import ExtractionEngine, ExtractionResult
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata
from scraper.discovery.links import extract_discovered_links
from scraper.discovery.providers.registry import provider_registry
from scraper.discovery.provider_policy import provider_policy
from scraper.research.intent import ResearchIntent
from scraper.research.query_normalizer import normalize_query
from scraper.research.entities import extract_entities_from_query
from scraper.research.decomposer import decompose_intent
from scraper.search.query_generator import QueryGenerator
from scraper.search.candidates import SourceCandidate
from scraper.search.candidate_normalizer import candidate_normalizer
from scraper.search.ranking.candidate_ranker import candidate_ranker
from scraper.control.ranked_frontier import RankedFrontier, CandidateState
from scraper.search.document_relevance import document_relevance_evaluator
from scraper.extraction.content_filter import content_filter
from scraper.extraction.document_type import DocumentType, document_type_classifier
from scraper.normalization.near_duplicate import near_duplicate_detector
from scraper.normalization.content_hash import compute_content_hash
from scraper.search.source_lineage import SourceLineage
from scraper.search.url_policy import candidate_url_policy
from scraper.search.source_policy import calculate_authority_prior
from scraper.search.quality_report import source_quality_evaluator
from scraper.search.trace import SearchTrace, TraceEventType

from scraper.discovery.media_finder import (
    extract_document_links,
    extract_image_candidates,
    fetch_wikimedia_topic_images,
    fetch_wikipedia_article_images,
    score_and_rank_images,
    is_accepted_media_file,
)
from scraper.acquisition.media_downloader import download_media_file
from scraper.extraction.pdf_extractor import extract_text_from_pdf_file
from scraper.acquisition.open_access_resolver import open_access_resolver

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
    quality_gate_passed: bool = False


class DeepSearchPipeline:
    """Evidence-driven research & extraction pipeline powered by Ranked Frontier."""

    def __init__(self, acquisition_engine: Optional[AdaptiveAcquisitionEngine] = None):
        self.acquisition_engine = acquisition_engine or AdaptiveAcquisitionEngine()

    async def execute(
        self, opts: DeepSearchPipelineOptions
    ) -> DeepSearchPipelineResult:
        logger.info(
            "Starting DeepSearch Pipeline for query='%s', domain='%s', depth=%d",
            opts.query,
            opts.domain,
            opts.depth,
        )

        trace = SearchTrace()
        trace.record(TraceEventType.QUERY_ANALYZED, entity_id=opts.query, stage="init")

        # 1. Query Intelligence & Goal Graph
        norm_q = normalize_query(opts.query)
        entities = extract_entities_from_query(opts.query)
        intent = ResearchIntent(
            original_query=opts.query,
            normalized_query=norm_q.normalized_text,
            task_type=opts.category or "general_research",
            domain=opts.domain,
            entities=entities,
            languages=norm_q.detected_languages,
        )
        goal_graph = decompose_intent(intent)
        q_gen = QueryGenerator()
        query_variants = q_gen.generate_variants(intent, goal_graph)

        for g in goal_graph.goals.values():
            trace.record(
                TraceEventType.GOAL_CREATED,
                entity_id=g.id,
                stage="planning",
                metadata={"question": g.question},
            )

        # 2. Ranked Frontier Initialization
        frontier = RankedFrontier(max_capacity=10000, max_active_per_domain=3)
        candidate_pool: List[SourceCandidate] = []
        rejections: List[Dict[str, Any]] = []

        # Add preferred sources as top seeds
        if opts.preferred_sources:
            for pref in opts.preferred_sources:
                c_pref = SourceCandidate(
                    url=pref,
                    canonical_url=canonicalize_url(pref),
                    title=f"Seed: {pref}",
                    provider="user_preference",
                    provider_rank=1,
                    authority_prior=0.95,
                )
                candidate_pool.append(c_pref)

        # Multi-provider parallel discovery if enabled
        if opts.auto_discover_sources:
            provider_reqs = []
            for goal in goal_graph.goals.values():
                reqs = provider_policy.plan_provider_requests(
                    intent, goal, query_variants, target_pool_size=opts.max_pages
                )
                provider_reqs.extend(reqs)

            discovered_cands = await provider_registry.search_parallel(
                provider_reqs, trace=trace
            )
            candidate_pool.extend(discovered_cands)

        # Fallback if 0 candidates found
        if not candidate_pool:
            fallback_url = f"https://{opts.domain or 'wikipedia.org'}/wiki/{opts.query.replace(' ', '_')}"
            candidate_pool.append(
                SourceCandidate(
                    url=fallback_url,
                    canonical_url=canonicalize_url(fallback_url),
                    title=opts.query,
                    provider="fallback",
                    provider_rank=1,
                )
            )

        # Discovery/listing pages are not terminal evidence sources. Keep a
        # diagnostic record, but do not spend acquisition budget on them.
        filtered_candidates: List[SourceCandidate] = []
        for candidate in candidate_pool:
            policy_reason = candidate_url_policy.rejection_reason(candidate.url)
            if policy_reason:
                rejections.append(
                    {
                        "stage": "discovery",
                        "url": candidate.url,
                        "canonical_url": candidate.canonical_url,
                        "candidate_title": candidate.title,
                        "provider": candidate.provider,
                        "document_type": "URL_POLICY_REJECTED",
                        "reason_code": policy_reason.value,
                        "signals": ["terminal_source_policy"],
                    }
                )
                continue
            filtered_candidates.append(candidate)
        candidate_pool = filtered_candidates

        if not candidate_pool:
            fallback_url = f"https://{opts.domain or 'wikipedia.org'}/wiki/{opts.query.replace(' ', '_')}"
            if candidate_url_policy.is_terminal_source_allowed(fallback_url):
                candidate_pool.append(
                    SourceCandidate(
                        url=fallback_url,
                        canonical_url=canonicalize_url(fallback_url),
                        title=opts.query,
                        provider="fallback",
                        provider_rank=1,
                    )
                )

        # Normalize and rank candidates into frontier
        normalized_pool = candidate_normalizer.normalize_candidates(candidate_pool)
        ranked_pool = candidate_ranker.rank_pool(normalized_pool, intent, trace=trace)

        for rc in ranked_pool:
            await frontier.add_candidate(
                candidate=rc.candidate,
                priority=rc.final_score,
                depth=0,
                goal_id=rc.candidate.goal_ids[0] if rc.candidate.goal_ids else None,
                features=rc.features,
            )

        acquired_results: List[Tuple[CapturedArtifact, ExtractionResult]] = []
        downloaded_pdfs: List[Dict[str, Any]] = []
        accepted_pdf_hashes: set[str] = set()
        raw_image_candidates: List[Dict[str, Any]] = []
        pdf_temp_dir = tempfile.mkdtemp(prefix="deepsearch_pdfs_")
        source_lineage = SourceLineage()

        # 3. Iterative Ranked Frontier Acquisition Loop
        while frontier.size() > 0 and len(acquired_results) < opts.max_pages:
            item = await frontier.lease_next(lease_duration_sec=30.0)
            if not item:
                break

            current_url = item.candidate.canonical_url or item.candidate.url
            c_url = canonicalize_url(current_url)

            # Filter by domain only when auto_discover_sources is disabled (strict mode)
            if (
                not opts.auto_discover_sources
                and opts.domain
                and opts.domain.lower() not in current_url.lower()
            ):
                await frontier.mark_state(
                    item.id, CandidateState.REJECTED, error="OUT_OF_DOMAIN_SCOPE"
                )
                continue

            try:
                pending_pdfs: List[Dict[str, Any]] = []
                pending_pdf_hashes: set[str] = set()
                artifact = await self.acquisition_engine.acquire_page(
                    url=current_url,
                    canonical_url=c_url,
                    mode=opts.mode,
                    take_screenshot=opts.take_screenshot,
                )

                extraction = ExtractionEngine.extract_from_html(
                    url=artifact.url, raw_html=artifact.text_content
                )

                pre_filter = content_filter.inspect_content(extraction.clean_markdown)
                pre_classification = document_type_classifier.classify(
                    url=artifact.url,
                    text=artifact.text_content,
                    status_code=artifact.status_code,
                    content_type=artifact.content_type,
                    title=item.candidate.title,
                    link_density=pre_filter.link_density,
                )
                if pre_classification.document_type not in (
                    DocumentType.DOCUMENT,
                    DocumentType.JS_SHELL,
                ):
                    oa_rescued = False
                    try:
                        oa_paper = await open_access_resolver.resolve_blocked_url(
                            current_url, candidate_title=item.candidate.title
                        )
                        if oa_paper and oa_paper.pdf_url:
                            pdf_info = await download_media_file(
                                oa_paper.pdf_url, output_dir=pdf_temp_dir
                            )
                            if pdf_info:
                                pdf_text = extract_text_from_pdf_file(
                                    pdf_info["file_path"]
                                )
                                if pdf_text and len(pdf_text.strip()) > 300:
                                    pending_pdfs.append(pdf_info)
                                    extraction.clean_markdown = (
                                        f"# {oa_paper.title or item.candidate.title}\n\n"
                                        + pdf_text
                                    )
                                    extraction.full_text_markdown = pdf_text.strip()
                                    extraction.fit_markdown = (
                                        extraction.full_text_markdown
                                    )
                                    pre_classification.document_type = (
                                        DocumentType.DOCUMENT
                                    )
                                    oa_rescued = True
                                    logger.info(
                                        "OpenAccessResolver rescued blocked paper: %s via %s",
                                        current_url,
                                        oa_paper.pdf_url,
                                    )
                    except Exception as oa_err:
                        logger.debug(
                            "Open Access rescue failed for %s: %s", current_url, oa_err
                        )

                    if not oa_rescued and pre_classification.document_type not in (
                        DocumentType.DOCUMENT,
                        DocumentType.JS_SHELL,
                    ):
                        rejection = {
                            "url": current_url,
                            "canonical_url": c_url,
                            "candidate_title": item.candidate.title,
                            "provider": item.candidate.provider,
                            "document_type": pre_classification.document_type.value,
                            "reason_code": pre_classification.reason_code,
                            "signals": pre_classification.signals,
                            "status_code": artifact.status_code,
                            "strategy": artifact.strategy_used,
                        }
                        rejections.append(rejection)
                        trace.record(
                            TraceEventType.DOCUMENT_REJECTED,
                            entity_id=current_url,
                            reason=pre_classification.reason_code,
                        )
                        await frontier.mark_state(
                            item.id,
                            CandidateState.REJECTED,
                            error=pre_classification.reason_code,
                        )
                        continue

                # PMC Fallback if text is empty shell
                pmc_match = re.search(r"PMC\d+", artifact.url, re.IGNORECASE)
                if pmc_match and (
                    len(extraction.clean_markdown.strip()) < 400
                    or artifact.page_intelligence.content_quality < 0.2
                ):
                    pmcid = pmc_match.group(0).upper()
                    try:
                        import httpx

                        async with httpx.AsyncClient(
                            timeout=10.0, trust_env=False
                        ) as client:
                            xml_res = await client.get(
                                f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
                            )
                            if xml_res.status_code == 200 and len(xml_res.text) > 500:
                                from selectolax.parser import HTMLParser as XMLParser

                                xml_p = XMLParser(xml_res.text)
                                body_node = xml_p.css_first("body")
                                if body_node:
                                    xml_text = body_node.text(
                                        strip=True, separator="\n\n"
                                    )
                                    if len(xml_text) > 300:
                                        extraction.clean_markdown = (
                                            f"# Article {pmcid}\n\n" + xml_text
                                        )
                                        extraction.fit_markdown = (
                                            extraction.clean_markdown
                                        )

                            ncbi_pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                            pdf_info = await download_media_file(
                                ncbi_pdf_url,
                                output_dir=pdf_temp_dir,
                                filename_prefix=pmcid,
                            )
                            if pdf_info:
                                pending_pdfs.append(pdf_info)
                                pdf_text = extract_text_from_pdf_file(
                                    pdf_info["file_path"]
                                )
                                if (
                                    pdf_text
                                    and len(extraction.clean_markdown.strip()) < 400
                                ):
                                    extraction.clean_markdown = pdf_text
                                    extraction.fit_markdown = pdf_text
                    except Exception as pmc_exc:
                        logger.warning(
                            "PMC REST fallback error for %s: %s", pmcid, pmc_exc
                        )

                # PDF document discovery & acquisition
                doc_links = extract_document_links(
                    artifact.text_content, base_url=artifact.url
                )
                extracted_pdf_text = ""
                for doc_url in doc_links:
                    if (
                        doc_url.lower().endswith(".pdf")
                        or "ptpmcrender.fcgi" in doc_url.lower()
                        or "/pdf" in doc_url.lower()
                    ):
                        pdf_info = await download_media_file(
                            doc_url, output_dir=pdf_temp_dir
                        )
                        if pdf_info:
                            pdf_hash = pdf_info.get("sha256", "")
                            if pdf_hash and pdf_hash in pending_pdf_hashes:
                                continue
                            if pdf_hash:
                                pending_pdf_hashes.add(pdf_hash)
                            pending_pdfs.append(pdf_info)
                            pdf_text = extract_text_from_pdf_file(pdf_info["file_path"])
                            if pdf_text:
                                extracted_pdf_text += (
                                    f"\n\n### Document Source PDF: {pdf_info['filename']}\n\n"
                                    + pdf_text
                                )

                if extracted_pdf_text:
                    extraction.abstract_markdown = extraction.clean_markdown
                    extraction.full_text_markdown = extracted_pdf_text.strip()
                    extraction.fit_markdown = extraction.full_text_markdown

                # 4. Document Assessment & Quality Gates (DS-SI28, DS-SI29, DS-SI30)
                main_text = extraction.clean_markdown
                c_filter = content_filter.inspect_content(main_text)
                classification = document_type_classifier.classify(
                    url=artifact.url,
                    text=main_text,
                    status_code=artifact.status_code,
                    content_type=artifact.content_type,
                    title=item.candidate.title,
                    link_density=c_filter.link_density,
                )
                rel_tier, doc_quality = document_relevance_evaluator.evaluate(
                    main_text, item.candidate.title, intent
                )

                if not classification.accepted:
                    rejection = {
                        "url": current_url,
                        "canonical_url": c_url,
                        "candidate_title": item.candidate.title,
                        "provider": item.candidate.provider,
                        "document_type": classification.document_type.value,
                        "reason_code": classification.reason_code,
                        "signals": classification.signals,
                        "status_code": artifact.status_code,
                        "strategy": artifact.strategy_used,
                    }
                    rejections.append(rejection)
                    trace.record(
                        TraceEventType.DOCUMENT_REJECTED,
                        entity_id=current_url,
                        reason=classification.reason_code,
                    )
                    await frontier.mark_state(
                        item.id,
                        CandidateState.REJECTED,
                        error=classification.reason_code,
                    )
                    continue

                if not c_filter.is_valid:
                    rejection = {
                        "url": current_url,
                        "canonical_url": c_url,
                        "candidate_title": item.candidate.title,
                        "provider": item.candidate.provider,
                        "document_type": classification.document_type.value,
                        "reason_code": c_filter.rejection_reason,
                        "signals": ["content_filter"],
                        "status_code": artifact.status_code,
                        "strategy": artifact.strategy_used,
                    }
                    rejections.append(rejection)
                    trace.record(
                        TraceEventType.DOCUMENT_REJECTED,
                        entity_id=current_url,
                        reason=c_filter.rejection_reason,
                    )
                    await frontier.mark_state(
                        item.id,
                        CandidateState.REJECTED,
                        error=c_filter.rejection_reason,
                    )
                    continue

                if not doc_quality.is_accepted:
                    trace.record(
                        TraceEventType.DOCUMENT_REJECTED,
                        entity_id=current_url,
                        reason=doc_quality.reject_reason,
                    )
                    await frontier.mark_state(
                        item.id,
                        CandidateState.REJECTED,
                        error=doc_quality.reject_reason,
                    )
                    continue

                extraction.source_type = item.candidate.source_type
                extraction.source_id = c_url
                extraction.source_title = item.candidate.title
                extraction.provider = item.candidate.provider
                extraction.extraction_completeness = c_filter.main_text_ratio
                extraction.authority_score = calculate_authority_prior(
                    item.candidate.domain,
                    item.candidate.source_type,
                    intent.task_type,
                )
                extraction.relevance_score = doc_quality.topical_relevance
                extraction.published_at = item.candidate.published_at
                extraction.document_type = classification.document_type.value

                for pdf_info in pending_pdfs:
                    pdf_hash = pdf_info.get("sha256", "")
                    if pdf_hash and pdf_hash in accepted_pdf_hashes:
                        continue
                    if pdf_hash:
                        accepted_pdf_hashes.add(pdf_hash)
                    downloaded_pdfs.append(pdf_info)

                # 5. Exact & Near Duplicate Filter (DS-SI33, DS-SI34)
                c_hash = compute_content_hash(main_text)
                is_near_dup, dup_of, cluster_id = (
                    near_duplicate_detector.register_document(c_url, main_text)
                )

                source_lineage.register_source(
                    source_id=c_url,
                    url=current_url,
                    domain=item.candidate.domain,
                    content_hash=c_hash,
                    near_dup_cluster=cluster_id,
                    is_primary=(len(acquired_results) == 0),
                )

                if is_near_dup:
                    trace.record(
                        TraceEventType.CANDIDATE_DEDUPED,
                        entity_id=current_url,
                        reason=f"Near-duplicate of {dup_of}",
                    )

                # Collect image candidates from acquired HTML page
                if opts.enable_media_archiving:
                    page_images = extract_image_candidates(
                        artifact.text_content, base_url=artifact.url
                    )
                    raw_image_candidates.extend(page_images)

                acquired_results.append((artifact, extraction))
                trace.record(
                    TraceEventType.DOCUMENT_ACCEPTED,
                    entity_id=current_url,
                    metrics={"relevance": doc_quality.topical_relevance},
                )
                await frontier.mark_state(item.id, CandidateState.ACCEPTED)

                # 6. Prioritized Link Expansion (DS-SI12, DS-SI13)
                if item.depth < opts.depth and len(acquired_results) < opts.max_pages:
                    discovered_links = extract_discovered_links(
                        artifact.text_content, base_url=artifact.url
                    )
                    link_candidates = []
                    for dlink in discovered_links:
                        if (
                            not dlink.is_navigation
                            and not dlink.is_footer
                            and candidate_url_policy.is_terminal_source_allowed(
                                dlink.url
                            )
                        ):
                            link_c = SourceCandidate(
                                url=dlink.url,
                                canonical_url=canonicalize_url(dlink.url),
                                title=dlink.anchor_text
                                or dlink.section_heading
                                or "Discovered Link",
                                snippet=dlink.surrounding_text,
                                provider="link_crawl",
                                provider_rank=dlink.dom_position,
                                goal_ids=[item.goal_id] if item.goal_id else [],
                            )
                            link_candidates.append(link_c)

                    # Pre-rank discovered links before pushing to frontier
                    norm_links = candidate_normalizer.normalize_candidates(
                        link_candidates
                    )
                    ranked_links = candidate_ranker.rank_pool(norm_links, intent)

                    for rl in ranked_links[:10]:
                        await frontier.add_candidate(
                            candidate=rl.candidate,
                            priority=rl.final_score,
                            depth=item.depth + 1,
                            goal_id=item.goal_id,
                            features=rl.features,
                        )

            except Exception as exc:
                logger.warning(
                    "Failed acquisition/extraction for %s: %s", current_url, exc
                )
                is_transient = "timeout" in str(exc).lower() or "429" in str(exc)
                rejections.append(
                    {
                        "stage": "acquisition",
                        "url": current_url,
                        "canonical_url": c_url,
                        "candidate_title": item.candidate.title,
                        "provider": item.candidate.provider,
                        "document_type": "ACQUISITION_FAILURE",
                        "reason_code": "TRANSIENT_ACQUISITION_FAILURE"
                        if is_transient
                        else "ACQUISITION_FAILURE",
                        "signals": [str(exc)[:500]],
                        "strategy": "adaptive",
                    }
                )
                await frontier.mark_state(
                    item.id,
                    CandidateState.DEAD,
                    error=str(exc),
                    is_transient_error=is_transient,
                )

        # 7. Topic Media Discovery & Scoring
        downloaded_media: List[Dict[str, Any]] = []
        media_rejections: List[Dict[str, Any]] = []
        if opts.enable_media_archiving:
            try:
                wiki_media = await fetch_wikimedia_topic_images(
                    opts.query, max_results=opts.max_media_count
                )
                wiki_art_media = await fetch_wikipedia_article_images(
                    opts.query, max_results=opts.max_media_count
                )
                raw_image_candidates.extend(wiki_media)
                raw_image_candidates.extend(wiki_art_media)

                ranked_images = score_and_rank_images(
                    candidates=raw_image_candidates,
                    query=opts.query,
                    min_count=opts.min_media_count,
                    max_count=opts.max_media_count,
                )

                logger.info(
                    "Selected %d top-ranked media images for topic '%s'",
                    len(ranked_images),
                    opts.query,
                )

                media_temp_dir = tempfile.mkdtemp(prefix="deepsearch_media_")
                for idx, img in enumerate(ranked_images, start=1):
                    m_info = await download_media_file(
                        url=img["url"],
                        output_dir=media_temp_dir,
                        filename_prefix=f"img_{idx:02d}",
                        caption=img.get("caption", ""),
                    )
                    if m_info:
                        m_info["relevance_score"] = img.get("relevance_score", 1.0)
                        if is_accepted_media_file(m_info, img):
                            downloaded_media.append(m_info)
                        else:
                            media_rejections.append(
                                {
                                    "url": img.get("url", ""),
                                    "caption": img.get("caption", ""),
                                    "reason_code": "MEDIA_QUALITY_GATE",
                                    "relevance_score": m_info.get("relevance_score"),
                                    "width": m_info.get("width"),
                                    "height": m_info.get("height"),
                                }
                            )
                    else:
                        media_rejections.append(
                            {
                                "url": img.get("url", ""),
                                "caption": img.get("caption", ""),
                                "reason_code": "MEDIA_DOWNLOAD_FAILED",
                                "relevance_score": img.get("relevance_score"),
                            }
                        )

            except Exception as media_exc:
                logger.warning("Topic media selection error: %s", media_exc)

        # 8. Export Archive & Metadata
        quality_report = source_quality_evaluator.evaluate(
            acquired_results, rejections=rejections
        )
        metadata = SearchRunMetadata(
            query=opts.query,
            domain=opts.domain,
            preferred_sources=opts.preferred_sources,
            depth=opts.depth,
            max_pages=opts.max_pages,
            mode=opts.mode.value,
        )
        exporter = ArchiveExporter(metadata=metadata)

        temp_dir = opts.output_dir_path or tempfile.mkdtemp(prefix="deepsearch_run_")
        built_dir = exporter.build_archive_structure(
            acquired_results,
            output_dir=temp_dir,
            pdf_files=downloaded_pdfs,
            media_files=downloaded_media,
            rejections=rejections,
            quality_report=quality_report,
            media_quality={
                "requested_count": opts.min_media_count,
                "max_count": opts.max_media_count,
                "accepted_count": len(downloaded_media),
                "shortfall": max(0, opts.min_media_count - len(downloaded_media)),
                "rejections": media_rejections,
            },
        )

        archive_zip_path = None
        if opts.output_archive_path:
            archive_zip_path = exporter.pack_zip_archive(
                built_dir, opts.output_archive_path
            )

        manifest_file = os.path.join(built_dir, "manifest.json")
        manifest_data = {}
        if os.path.exists(manifest_file):
            with open(manifest_file, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)

        total_chunks = manifest_data.get("summary", {}).get("total_rag_chunks", 0)

        trace.record(
            TraceEventType.STOP_DECISION,
            entity_id=opts.query,
            decision="SUFFICIENT_EVIDENCE",
            metrics={"processed_pages": len(acquired_results)},
        )

        return DeepSearchPipelineResult(
            query=opts.query,
            total_pages_processed=len(acquired_results),
            total_rag_chunks=total_chunks,
            archive_path=archive_zip_path,
            dir_path=built_dir,
            manifest=manifest_data,
            quality_gate_passed=bool(quality_report.get("passed")),
        )
