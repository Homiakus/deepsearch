"""DeepSearch Pipeline Orchestrator with Search Intelligence & Ranked Frontier (DS-SI23, DS-SI81).

Combines query intelligence, multi-provider discovery, ranked frontier crawl control,
adaptive page acquisition, content quality filtering, and dual-format archive generation.
"""

import os
import json
import asyncio
import tempfile
import logging
import urllib.parse
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Set
from pydantic import BaseModel, Field


from scraper.config import ExecutionMode
from scraper.application.run_context import RunContext, RunContextOptions
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
from scraper.control.ranked_frontier import (
    RankedFrontier,
    CandidateState,
    FrontierItem,
)
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
from scraper.visual.pdf_figure_extractor import pdf_figure_extractor
from scraper.extraction.pdf_extractor import (
    async_extract_text_from_pdf_file,
)
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
    max_pdfs_per_page: int = 3
    max_pdfs_per_run: int = 20
    max_pdf_pages: int = 50
    concurrency: int = 4


class DeepSearchPipelineResult(BaseModel):
    query: str
    total_pages_processed: int
    total_rag_chunks: int
    archive_path: Optional[str] = None
    dir_path: Optional[str] = None
    manifest: Dict[str, Any] = Field(default_factory=dict)
    quality_gate_passed: bool = False


class PipelineWorkspace:
    """Manages temporary and output directory lifecycles for pipeline runs (DS-12)."""

    def __init__(self, output_dir_path: Optional[str] = None):
        self._output_dir_path = output_dir_path
        self._managed_temp_dirs: List[str] = []

    def __enter__(self) -> "PipelineWorkspace":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        import shutil

        keep_output = exc_type is None and self._output_dir_path is not None
        for d in self._managed_temp_dirs:
            if (
                keep_output
                and self._output_dir_path
                and os.path.abspath(d) == os.path.abspath(self._output_dir_path)
            ):
                continue
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
        self._managed_temp_dirs.clear()

    def create_temp_dir(self, prefix: str = "ds_tmp_") -> str:
        tmp = tempfile.mkdtemp(prefix=prefix)
        self._managed_temp_dirs.append(tmp)
        return tmp

    def resolve_output_dir(self) -> str:
        if self._output_dir_path:
            Path(self._output_dir_path).mkdir(parents=True, exist_ok=True)
            return self._output_dir_path
        return self.create_temp_dir(prefix="deepsearch_run_")


class DiscoveryStageOutput(BaseModel):
    intent: ResearchIntent
    goal_graph: Any
    query_variants: List[Any]
    ranked_pool: List[Any]
    rejections: List[Dict[str, Any]]


class ScheduleStageOutput(BaseModel):
    frontier: Any
    enqueued_count: int


class AcquisitionStageOutput(BaseModel):
    acquired_results: List[Any]
    downloaded_pdfs: List[Dict[str, Any]]
    raw_image_candidates: List[Dict[str, Any]]
    rejections: List[Dict[str, Any]]
    source_lineage: Any


class MediaCollectionStageOutput(BaseModel):
    downloaded_media: List[Dict[str, Any]]
    media_rejections: List[Dict[str, Any]]


class ExportStageOutput(BaseModel):
    dir_path: str
    archive_path: Optional[str]
    manifest: Dict[str, Any]
    quality_gate_passed: bool
    total_pages_processed: int
    total_rag_chunks: int


class DeepSearchPipeline:
    """Evidence-driven research & extraction pipeline powered by Ranked Frontier (DS-12)."""

    def __init__(self, acquisition_engine: Optional[AdaptiveAcquisitionEngine] = None):
        self.acquisition_engine = acquisition_engine or AdaptiveAcquisitionEngine()

    async def stage_discover(
        self,
        opts: DeepSearchPipelineOptions,
        trace: Optional[SearchTrace] = None,
    ) -> DiscoveryStageOutput:
        tr = trace or SearchTrace()
        tr.record(TraceEventType.QUERY_ANALYZED, entity_id=opts.query, stage="init")

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
            tr.record(
                TraceEventType.GOAL_CREATED,
                entity_id=g.id,
                stage="planning",
                metadata={"question": g.question},
            )

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
                provider_reqs, trace=tr
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

        # Filter discovery URLs by policy
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

        # Normalize and rank candidates
        normalized_pool = candidate_normalizer.normalize_candidates(candidate_pool)
        ranked_pool = candidate_ranker.rank_pool(normalized_pool, intent, trace=tr)

        return DiscoveryStageOutput(
            intent=intent,
            goal_graph=goal_graph,
            query_variants=query_variants,
            ranked_pool=ranked_pool,
            rejections=rejections,
        )

    async def stage_schedule(
        self,
        ranked_pool: List[Any],
        max_capacity: int = 10000,
        max_active_per_domain: int = 3,
    ) -> ScheduleStageOutput:
        frontier = RankedFrontier(
            max_capacity=max_capacity,
            max_active_per_domain=max_active_per_domain,
        )
        count = 0
        for rc in ranked_pool:
            await frontier.add_candidate(
                candidate=rc.candidate,
                priority=rc.final_score,
                depth=0,
                goal_id=rc.candidate.goal_ids[0] if rc.candidate.goal_ids else None,
                features=rc.features,
            )
            count += 1
        return ScheduleStageOutput(frontier=frontier, enqueued_count=count)

    async def stage_acquire_and_extract(
        self,
        opts: DeepSearchPipelineOptions,
        frontier: RankedFrontier,
        intent: ResearchIntent,
        run_context: RunContext,
        pdf_temp_dir: str,
        rejections: List[Dict[str, Any]],
        trace: Optional[SearchTrace] = None,
    ) -> AcquisitionStageOutput:
        tr = trace or SearchTrace()
        acquired_results: List[Tuple[CapturedArtifact, ExtractionResult]] = []
        downloaded_pdfs: List[Dict[str, Any]] = []
        accepted_pdf_hashes: Set[str] = set()
        raw_image_candidates: List[Dict[str, Any]] = []
        rej_list: List[Dict[str, Any]] = list(rejections)
        source_lineage = SourceLineage()

        concurrency_limit = max(1, min(getattr(opts, "concurrency", 4) or 4, 6))
        active_workers = 0
        stop_event = asyncio.Event()
        frontier_lock = asyncio.Lock()

        async def _process_item(item: FrontierItem):
            nonlocal acquired_results, downloaded_pdfs, raw_image_candidates, rej_list
            current_url = item.candidate.canonical_url or item.candidate.url
            c_url = canonicalize_url(current_url)

            # 1. Cooperative cancellation and deadline check (§DS-10)
            run_context.check_active()

            # 2. Filter by domain only when auto_discover_sources is disabled
            if (
                not opts.auto_discover_sources
                and opts.domain
                and opts.domain.lower() not in current_url.lower()
            ):
                await frontier.mark_state(
                    item.id, CandidateState.REJECTED, error="OUT_OF_DOMAIN_SCOPE"
                )
                return

            # 3. URL Deduplication check (§17, §DS-10)
            if run_context.deduplicator.is_url_duplicate(c_url):
                await frontier.mark_state(
                    item.id, CandidateState.REJECTED, error="URL_DUPLICATE"
                )
                return

            # 4. Robots.txt policy check (§22, §DS-10)
            parsed_u = urllib.parse.urlparse(current_url)
            if not run_context.robots_manager.is_allowed(
                current_url, domain=parsed_u.netloc
            ):
                rejection = {
                    "stage": "robots",
                    "url": current_url,
                    "canonical_url": c_url,
                    "candidate_title": item.candidate.title,
                    "provider": item.candidate.provider,
                    "document_type": "ROBOTS_DENIED",
                    "reason_code": "ROBOTS_TXT_DISALLOWED",
                    "signals": ["robots.txt disallow rule"],
                    "status_code": 403,
                    "strategy": "policy",
                }
                async with frontier_lock:
                    rej_list.append(rejection)
                await frontier.mark_state(
                    item.id, CandidateState.REJECTED, error="ROBOTS_TXT_DISALLOWED"
                )
                return

            # 5. Host Rate Limiter token acquisition (§12, §DS-10)
            if parsed_u.netloc:
                await run_context.rate_limiter.acquire(parsed_u.netloc)

            try:
                local_pending_pdfs: List[Dict[str, Any]] = []
                artifact = await self.acquisition_engine.acquire_page(
                    url=current_url,
                    canonical_url=c_url,
                    mode=opts.mode,
                    take_screenshot=opts.take_screenshot,
                )

                # Record rate limiter response metrics (§12)
                if parsed_u.netloc:
                    await run_context.rate_limiter.record_result(
                        parsed_u.netloc, artifact.status_code, artifact.elapsed_sec
                    )

                # Record budget tracker consumption (§50, §DS-10)
                was_browser = artifact.strategy_used in ("L3_BROWSER", "L5_VISUAL")
                await run_context.budget_tracker.record_page(
                    bytes_size=len(artifact.raw_content),
                    depth=item.depth,
                    was_browser=was_browser,
                    browser_sec=artifact.elapsed_sec if was_browser else 0.0,
                    was_visual=(artifact.strategy_used == "L5_VISUAL"),
                )

                # Content Deduplication check (§17, §DS-10)
                if run_context.deduplicator.is_content_duplicate(artifact.raw_content):
                    await frontier.mark_state(
                        item.id, CandidateState.REJECTED, error="CONTENT_DUPLICATE"
                    )
                    return

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
                                oa_paper.pdf_url,
                                output_dir=pdf_temp_dir,
                                license=getattr(oa_paper, "license", "UNKNOWN_LICENSE"),
                                author=getattr(oa_paper, "author", "UNKNOWN_AUTHOR"),
                                source_domain=urllib.parse.urlparse(
                                    oa_paper.pdf_url
                                ).netloc,
                            )
                            if pdf_info:
                                pdf_text = await async_extract_text_from_pdf_file(
                                    pdf_info["file_path"], max_pages=opts.max_pdf_pages
                                )
                                if pdf_text and len(pdf_text.strip()) > 300:
                                    local_pending_pdfs.append(pdf_info)
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
                        async with frontier_lock:
                            rej_list.append(rejection)
                        tr.record(
                            TraceEventType.DOCUMENT_REJECTED,
                            entity_id=current_url,
                            reason=pre_classification.reason_code,
                        )
                        await frontier.mark_state(
                            item.id,
                            CandidateState.REJECTED,
                            error=pre_classification.reason_code,
                        )
                        return

                # PDF document discovery & acquisition (with per-page and per-run limits)
                doc_links = extract_document_links(
                    artifact.text_content, base_url=artifact.url
                )
                extracted_pdf_text = ""
                page_pdf_count = 0
                for doc_url in doc_links:
                    if page_pdf_count >= opts.max_pdfs_per_page:
                        break
                    if (
                        len(downloaded_pdfs) + len(local_pending_pdfs)
                        >= opts.max_pdfs_per_run
                    ):
                        break
                    if (
                        doc_url.lower().endswith(".pdf")
                        or "ptpmcrender.fcgi" in doc_url.lower()
                        or "/pdf" in doc_url.lower()
                    ):
                        pdf_info = await download_media_file(
                            doc_url,
                            output_dir=pdf_temp_dir,
                            source_domain=urllib.parse.urlparse(doc_url).netloc,
                        )
                        if pdf_info:
                            page_pdf_count += 1
                            local_pending_pdfs.append(pdf_info)
                            pdf_text = await async_extract_text_from_pdf_file(
                                pdf_info["file_path"], max_pages=opts.max_pdf_pages
                            )
                            if pdf_text:
                                extracted_pdf_text += (
                                    f"\n\n### Document Source PDF: {pdf_info['filename']}\n\n"
                                    + pdf_text
                                )

                if extracted_pdf_text:
                    extraction.abstract_markdown = extraction.clean_markdown
                    extraction.full_text_markdown = extracted_pdf_text.strip()
                    extraction.fit_markdown = extraction.full_text_markdown

                # Document Assessment & Quality Gates
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
                    async with frontier_lock:
                        rej_list.append(rejection)
                    tr.record(
                        TraceEventType.DOCUMENT_REJECTED,
                        entity_id=current_url,
                        reason=classification.reason_code,
                    )
                    await frontier.mark_state(
                        item.id,
                        CandidateState.REJECTED,
                        error=classification.reason_code,
                    )
                    return

                if not doc_quality.is_accepted:
                    rejection = {
                        "url": current_url,
                        "canonical_url": c_url,
                        "candidate_title": item.candidate.title,
                        "provider": item.candidate.provider,
                        "document_type": classification.document_type.value,
                        "reason_code": doc_quality.reject_reason,
                        "signals": [f"relevance={doc_quality.topical_relevance}"],
                        "status_code": artifact.status_code,
                        "strategy": artifact.strategy_used,
                    }
                    async with frontier_lock:
                        rej_list.append(rejection)
                    tr.record(
                        TraceEventType.DOCUMENT_REJECTED,
                        entity_id=current_url,
                        reason=doc_quality.reject_reason,
                    )
                    await frontier.mark_state(
                        item.id,
                        CandidateState.REJECTED,
                        error=doc_quality.reject_reason,
                    )
                    return

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

                # Deduplication filter
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
                    tr.record(
                        TraceEventType.CANDIDATE_DEDUPED,
                        entity_id=current_url,
                        reason=f"Near-duplicate of {dup_of}",
                    )

                page_images = []
                if opts.enable_media_archiving:
                    page_images = extract_image_candidates(
                        artifact.text_content, base_url=artifact.url
                    )

                async with frontier_lock:
                    for pdf_info in local_pending_pdfs:
                        pdf_hash = pdf_info.get("sha256", "")
                        if pdf_hash and pdf_hash in accepted_pdf_hashes:
                            continue
                        if pdf_hash:
                            accepted_pdf_hashes.add(pdf_hash)
                        downloaded_pdfs.append(pdf_info)

                    if page_images:
                        raw_image_candidates.extend(page_images)

                    acquired_results.append((artifact, extraction))
                    if len(acquired_results) >= opts.max_pages:
                        stop_event.set()

                tr.record(
                    TraceEventType.DOCUMENT_ACCEPTED,
                    entity_id=current_url,
                    metrics={"relevance": doc_quality.topical_relevance},
                )
                await frontier.mark_state(item.id, CandidateState.ACCEPTED)

                # Prioritized Link Expansion
                if item.depth < opts.depth and not stop_event.is_set():
                    discovered_links = extract_discovered_links(
                        artifact.text_content, base_url=artifact.url
                    )
                    link_candidates = []
                    for dlink in discovered_links:
                        if candidate_url_policy.is_binary_document(dlink.url):
                            asyncio.create_task(
                                download_media_file(dlink.url, output_dir=pdf_temp_dir)
                            )
                            continue
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
                rejection = {
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
                async with frontier_lock:
                    rej_list.append(rejection)
                await frontier.mark_state(
                    item.id,
                    CandidateState.DEAD,
                    error=str(exc),
                    is_transient_error=is_transient,
                )

        async def _worker():
            nonlocal active_workers
            while not stop_event.is_set():
                async with frontier_lock:
                    if len(acquired_results) >= opts.max_pages:
                        stop_event.set()
                        break

                item = await frontier.lease_next(lease_duration_sec=30.0)
                if not item:
                    if active_workers == 0 and frontier.size() == 0:
                        stop_event.set()
                        break
                    await asyncio.sleep(0.05)
                    continue

                active_workers += 1
                try:
                    await _process_item(item)
                finally:
                    active_workers -= 1

        workers = [_worker() for _ in range(concurrency_limit)]
        await asyncio.gather(*workers)

        return AcquisitionStageOutput(
            acquired_results=acquired_results,
            downloaded_pdfs=downloaded_pdfs,
            raw_image_candidates=raw_image_candidates,
            rejections=rej_list,
            source_lineage=source_lineage,
        )

    async def stage_collect_media(
        self,
        opts: DeepSearchPipelineOptions,
        acq_output: AcquisitionStageOutput,
        media_temp_dir: str,
    ) -> MediaCollectionStageOutput:
        downloaded_media: List[Dict[str, Any]] = []
        media_rejections: List[Dict[str, Any]] = []
        if not opts.enable_media_archiving:
            return MediaCollectionStageOutput(
                downloaded_media=downloaded_media,
                media_rejections=media_rejections,
            )

        raw_candidates = list(acq_output.raw_image_candidates)
        try:
            wiki_media = await fetch_wikimedia_topic_images(
                opts.query, max_results=opts.max_media_count
            )
            wiki_art_media = await fetch_wikipedia_article_images(
                opts.query, max_results=opts.max_media_count
            )
            raw_candidates.extend(wiki_media)
            raw_candidates.extend(wiki_art_media)

            ranked_images = score_and_rank_images(
                candidates=raw_candidates,
                query=opts.query,
                min_count=opts.min_media_count,
                max_count=opts.max_media_count,
            )

            sem = asyncio.Semaphore(6)

            async def _download_candidate(
                idx: int, img: Dict[str, Any]
            ) -> Tuple[int, Dict[str, Any], Optional[Dict[str, Any]]]:
                async with sem:
                    m_res = await download_media_file(
                        url=img["url"],
                        output_dir=media_temp_dir,
                        filename_prefix=f"img_{idx:02d}",
                        caption=img.get("caption", ""),
                        license=img.get("license", "UNKNOWN_LICENSE"),
                        author=img.get("author", "UNKNOWN_AUTHOR"),
                        source_domain=img.get("source_domain"),
                    )
                    return idx, img, m_res

            dl_tasks = [
                _download_candidate(idx, img)
                for idx, img in enumerate(ranked_images, start=1)
            ]
            dl_results = await asyncio.gather(*dl_tasks, return_exceptions=True)

            for res in dl_results:
                if isinstance(res, Exception):
                    continue
                idx, img, m_info = res
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

            if acq_output.downloaded_pdfs:
                for pdf_doc in acq_output.downloaded_pdfs:
                    p_path = pdf_doc.get("file_path")
                    if p_path and os.path.exists(p_path):
                        doc_id = pdf_doc.get("filename", "doc").replace(".pdf", "")
                        try:
                            extracted_figs = await asyncio.to_thread(
                                pdf_figure_extractor.extract_figures_from_pdf,
                                pdf_path=p_path,
                                output_media_dir=media_temp_dir,
                                doc_id=doc_id,
                                max_figures=3,
                            )
                            downloaded_media.extend(extracted_figs)
                        except Exception as pdf_fig_err:
                            logger.debug(
                                "PDF figure extraction error for %s: %s",
                                p_path,
                                pdf_fig_err,
                            )

        except Exception as media_exc:
            logger.warning("Topic media selection error: %s", media_exc)

        return MediaCollectionStageOutput(
            downloaded_media=downloaded_media,
            media_rejections=media_rejections,
        )

    async def stage_export(
        self,
        opts: DeepSearchPipelineOptions,
        acq_output: AcquisitionStageOutput,
        media_output: MediaCollectionStageOutput,
        output_dir: str,
        trace: Optional[SearchTrace] = None,
    ) -> ExportStageOutput:
        tr = trace or SearchTrace()

        quality_report = source_quality_evaluator.evaluate(
            acq_output.acquired_results, rejections=acq_output.rejections
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

        built_dir = await asyncio.to_thread(
            exporter.build_archive_structure,
            results=acq_output.acquired_results,
            output_dir=output_dir,
            pdf_files=acq_output.downloaded_pdfs,
            media_files=media_output.downloaded_media,
            rejections=acq_output.rejections,
            quality_report=quality_report,
            media_quality={
                "requested_count": opts.min_media_count,
                "max_count": opts.max_media_count,
                "accepted_count": len(media_output.downloaded_media),
                "shortfall": max(
                    0, opts.min_media_count - len(media_output.downloaded_media)
                ),
                "rejections": media_output.media_rejections,
            },
        )

        archive_zip_path = None
        if opts.output_archive_path:
            archive_zip_path = await asyncio.to_thread(
                exporter.pack_zip_archive,
                input_dir=built_dir,
                output_zip_path=opts.output_archive_path,
            )

        manifest_file = os.path.join(built_dir, "manifest.json")
        manifest_data = {}
        if os.path.exists(manifest_file):
            with open(manifest_file, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)

        total_chunks = manifest_data.get("summary", {}).get("total_rag_chunks", 0)

        tr.record(
            TraceEventType.STOP_DECISION,
            entity_id=opts.query,
            decision="SUFFICIENT_EVIDENCE",
            metrics={"processed_pages": len(acq_output.acquired_results)},
        )

        return ExportStageOutput(
            dir_path=built_dir,
            archive_path=archive_zip_path,
            manifest=manifest_data,
            quality_gate_passed=bool(quality_report.get("passed")),
            total_pages_processed=len(acq_output.acquired_results),
            total_rag_chunks=total_chunks,
        )

    async def execute(
        self,
        opts: DeepSearchPipelineOptions,
        run_context: Optional[RunContext] = None,
    ) -> DeepSearchPipelineResult:
        """Executes the research pipeline through modular, typed stages within a managed workspace."""
        logger.info(
            "Starting DeepSearch Pipeline for query='%s', domain='%s', depth=%d",
            opts.query,
            opts.domain,
            opts.depth,
        )

        if run_context is None:
            run_context = RunContext.create(
                RunContextOptions(
                    run_id="ds_pipeline_run",
                    query=opts.query,
                    domain=opts.domain,
                    depth=opts.depth,
                    max_pages=opts.max_pages,
                    mode=opts.mode,
                )
            )

        trace = SearchTrace()

        with PipelineWorkspace(output_dir_path=opts.output_dir_path) as workspace:
            # 1. Discover Stage
            disc_out = await self.stage_discover(opts, trace=trace)

            # 2. Schedule Stage
            sched_out = await self.stage_schedule(disc_out.ranked_pool)

            # 3. Acquire & Extract Stage
            pdf_temp_dir = workspace.create_temp_dir(prefix="deepsearch_pdfs_")
            acq_out = await self.stage_acquire_and_extract(
                opts=opts,
                frontier=sched_out.frontier,
                intent=disc_out.intent,
                run_context=run_context,
                pdf_temp_dir=pdf_temp_dir,
                rejections=disc_out.rejections,
                trace=trace,
            )

            # 4. Collect Media Stage
            media_temp_dir = workspace.create_temp_dir(prefix="deepsearch_media_")
            media_out = await self.stage_collect_media(
                opts=opts,
                acq_output=acq_out,
                media_temp_dir=media_temp_dir,
            )

            # 5. Export Stage
            out_dir = workspace.resolve_output_dir()
            export_out = await self.stage_export(
                opts=opts,
                acq_output=acq_out,
                media_output=media_out,
                output_dir=out_dir,
                trace=trace,
            )

            return DeepSearchPipelineResult(
                query=opts.query,
                total_pages_processed=export_out.total_pages_processed,
                total_rag_chunks=export_out.total_rag_chunks,
                archive_path=export_out.archive_path,
                dir_path=export_out.dir_path,
                manifest=export_out.manifest,
                quality_gate_passed=export_out.quality_gate_passed,
            )


class DiscoveryStage:
    def __init__(self, pipeline: Optional[DeepSearchPipeline] = None):
        self.pipeline = pipeline or DeepSearchPipeline()

    async def execute(
        self,
        query: str,
        domain: Optional[str] = None,
        preferred_sources: Optional[List[str]] = None,
        category: Optional[str] = None,
        auto_discover_sources: bool = True,
        max_pages: int = 50,
        trace: Optional[SearchTrace] = None,
    ) -> DiscoveryStageOutput:
        opts = DeepSearchPipelineOptions(
            query=query,
            domain=domain,
            preferred_sources=preferred_sources or [],
            category=category,
            auto_discover_sources=auto_discover_sources,
            max_pages=max_pages,
        )
        return await self.pipeline.stage_discover(opts, trace=trace)


class ScheduleStage:
    def __init__(self, pipeline: Optional[DeepSearchPipeline] = None):
        self.pipeline = pipeline or DeepSearchPipeline()

    async def execute(
        self,
        ranked_pool: List[Any],
        max_capacity: int = 10000,
        max_active_per_domain: int = 3,
    ) -> ScheduleStageOutput:
        return await self.pipeline.stage_schedule(
            ranked_pool,
            max_capacity=max_capacity,
            max_active_per_domain=max_active_per_domain,
        )


class AcquisitionExtractionStage:
    def __init__(self, acquisition_engine: Optional[AdaptiveAcquisitionEngine] = None):
        self.pipeline = DeepSearchPipeline(acquisition_engine=acquisition_engine)

    async def execute(
        self,
        frontier: RankedFrontier,
        intent: ResearchIntent,
        run_context: RunContext,
        pdf_temp_dir: str,
        depth: int = 3,
        max_pages: int = 50,
        mode: ExecutionMode = ExecutionMode.BALANCED,
        take_screenshot: bool = False,
        auto_discover_sources: bool = True,
        domain: Optional[str] = None,
        concurrency: int = 4,
        enable_media_archiving: bool = True,
        rejections: Optional[List[Dict[str, Any]]] = None,
        trace: Optional[SearchTrace] = None,
    ) -> AcquisitionStageOutput:
        opts = DeepSearchPipelineOptions(
            query=intent.original_query,
            domain=domain,
            depth=depth,
            max_pages=max_pages,
            mode=mode,
            take_screenshot=take_screenshot,
            auto_discover_sources=auto_discover_sources,
            concurrency=concurrency,
            enable_media_archiving=enable_media_archiving,
        )
        return await self.pipeline.stage_acquire_and_extract(
            opts,
            frontier,
            intent,
            run_context,
            pdf_temp_dir,
            rejections or [],
            trace=trace,
        )


class MediaCollectionStage:
    def __init__(self, pipeline: Optional[DeepSearchPipeline] = None):
        self.pipeline = pipeline or DeepSearchPipeline()

    async def execute(
        self,
        query: str,
        enable_media_archiving: bool,
        min_media_count: int,
        max_media_count: int,
        raw_image_candidates: List[Dict[str, Any]],
        downloaded_pdfs: List[Dict[str, Any]],
        media_temp_dir: str,
    ) -> MediaCollectionStageOutput:
        opts = DeepSearchPipelineOptions(
            query=query,
            enable_media_archiving=enable_media_archiving,
            min_media_count=min_media_count,
            max_media_count=max_media_count,
        )
        acq_mock = AcquisitionStageOutput(
            acquired_results=[],
            downloaded_pdfs=downloaded_pdfs,
            raw_image_candidates=raw_image_candidates,
            rejections=[],
            source_lineage=None,
        )
        return await self.pipeline.stage_collect_media(opts, acq_mock, media_temp_dir)


class ExportStage:
    def __init__(self, pipeline: Optional[DeepSearchPipeline] = None):
        self.pipeline = pipeline or DeepSearchPipeline()

    async def execute(
        self,
        query: str,
        domain: Optional[str],
        preferred_sources: List[str],
        depth: int,
        max_pages: int,
        mode: ExecutionMode,
        acquired_results: List[Tuple[CapturedArtifact, ExtractionResult]],
        downloaded_pdfs: List[Dict[str, Any]],
        downloaded_media: List[Dict[str, Any]],
        rejections: List[Dict[str, Any]],
        media_rejections: List[Dict[str, Any]],
        output_dir: str,
        output_archive_path: Optional[str],
        min_media_count: int,
        max_media_count: int,
        trace: Optional[SearchTrace] = None,
    ) -> ExportStageOutput:
        opts = DeepSearchPipelineOptions(
            query=query,
            domain=domain,
            preferred_sources=preferred_sources,
            depth=depth,
            max_pages=max_pages,
            mode=mode,
            output_archive_path=output_archive_path,
            min_media_count=min_media_count,
            max_media_count=max_media_count,
        )
        acq_mock = AcquisitionStageOutput(
            acquired_results=acquired_results,
            downloaded_pdfs=downloaded_pdfs,
            raw_image_candidates=[],
            rejections=rejections,
            source_lineage=None,
        )
        media_mock = MediaCollectionStageOutput(
            downloaded_media=downloaded_media,
            media_rejections=media_rejections,
        )
        return await self.pipeline.stage_export(
            opts, acq_mock, media_mock, output_dir, trace=trace
        )
