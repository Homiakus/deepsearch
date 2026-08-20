"""Semantic Scholar Discovery Provider (DS-SI08).

Leverages the Semantic Scholar Graph API for high-impact papers, citation counts,
influential citations, TLDRs, and direct open-access PDF links.
"""

import logging
import urllib.parse
import httpx
from typing import List
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class SemanticScholarProvider:
    descriptor = ProviderDescriptor(
        name="semantic_scholar",
        supported_domains=["semanticscholar.org", "api.semanticscholar.org"],
        supported_source_types=["PRIMARY_RESEARCH", "SYSTEMATIC_REVIEW", "PREPRINT"],
        languages=["en"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        query_encoded = urllib.parse.quote(request.query)
        fields = "title,abstract,authors,year,citationCount,influentialCitationCount,openAccessPdf,externalIds,venue,publicationTypes"
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query_encoded}&limit={request.max_results}&fields={fields}"

        candidates = []
        try:
            headers = {"User-Agent": "DeepSearch-Academic-Engine/1.0"}
            async with httpx.AsyncClient(
                timeout=request.timeout_sec, headers=headers, trust_env=False
            ) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    papers = data.get("data", [])
                    for idx, paper in enumerate(papers, start=1):
                        paper_id = paper.get("paperId", "")
                        title = paper.get("title", "")
                        abstract = paper.get("abstract", "") or ""
                        year = paper.get("year")
                        citations = paper.get("citationCount", 0) or 0
                        influential_citations = (
                            paper.get("influentialCitationCount", 0) or 0
                        )
                        venue = paper.get("venue", "") or ""
                        pub_types = paper.get("publicationTypes") or []
                        oa_pdf = paper.get("openAccessPdf") or {}
                        pdf_url = (
                            oa_pdf.get("url") if isinstance(oa_pdf, dict) else None
                        )

                        ext_ids = paper.get("externalIds") or {}
                        doi = ext_ids.get("DOI")
                        pmid = ext_ids.get("PubMed")
                        arxiv_id = ext_ids.get("ArXiv")

                        # Determine primary landing url
                        target_url = None
                        if doi:
                            target_url = f"https://doi.org/{doi}"
                        elif paper_id:
                            target_url = (
                                f"https://www.semanticscholar.org/paper/{paper_id}"
                            )
                        elif pdf_url:
                            target_url = pdf_url

                        if not target_url:
                            continue

                        # Determine evidence source type
                        source_type = "PRIMARY_RESEARCH"
                        if any(
                            "Review" in pt or "MetaAnalysis" in pt for pt in pub_types
                        ):
                            source_type = "SYSTEMATIC_REVIEW"
                        elif "ClinicalTrial" in pub_types:
                            source_type = "PRIMARY_RESEARCH"

                        # High authority baseline for peer-reviewed venues & high citations
                        auth_prior = 0.92
                        if citations > 100 or influential_citations > 10:
                            auth_prior = 0.98
                        elif citations > 20:
                            auth_prior = 0.95

                        snippet = abstract[:350]
                        if venue:
                            snippet = f"[{venue}, {year or ''}] " + snippet

                        candidates.append(
                            SourceCandidate(
                                url=target_url,
                                canonical_url=target_url,
                                title=title,
                                snippet=snippet,
                                provider=self.descriptor.name,
                                provider_rank=idx,
                                source_type=source_type,
                                published_at=str(year) if year else None,
                                goal_ids=[request.goal_id] if request.goal_id else [],
                                authority_prior=auth_prior,
                                provider_metadata={
                                    "paper_id": paper_id,
                                    "doi": doi or "",
                                    "pmid": pmid or "",
                                    "arxiv_id": arxiv_id or "",
                                    "citations": citations,
                                    "influential_citations": influential_citations,
                                    "pdf_url": pdf_url or "",
                                    "venue": venue,
                                },
                            )
                        )
        except Exception as exc:
            logger.warning(
                "SemanticScholarProvider search error for query '%s': %s",
                request.query,
                exc,
            )

        return candidates
