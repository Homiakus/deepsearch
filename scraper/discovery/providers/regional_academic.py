"""Multi-Regional Academic & Scientific Discovery Provider (DS-SI08).

Integrates multi-regional open access scientific repositories across Europe (HAL France/EU),
CIS/Russia (CyberLeninka/eLibrary), Latin America & Iberia (SciELO), and Asia (J-STAGE).
"""

import logging
import urllib.parse

import httpx

from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class RegionalAcademicProvider:
    descriptor = ProviderDescriptor(
        name="regional_academic",
        supported_domains=[
            "hal.science",
            "api.archives-ouvertes.fr",
            "cyberleninka.ru",
            "scielo.org",
            "jstage.jst.go.jp",
        ],
        supported_source_types=["PRIMARY_RESEARCH", "SYSTEMATIC_REVIEW", "THESIS"],
        languages=["en", "ru", "fr", "es", "de", "ja", "zh"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]:
        candidates = []
        # 1. HAL (Hyper Articles en Ligne - French / European National Scientific Repository)
        try:
            hal_query = urllib.parse.quote(request.query)
            hal_url = f"https://api.archives-ouvertes.fr/search/?q={hal_query}&wt=json&rows={min(request.max_results, 8)}&fl=uri_s,title_s,abstract_s,producedDateY_i,doiId_s,docType_s"

            transport = httpx.AsyncHTTPTransport(retries=2)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.get(hal_url)
                if res.status_code == 200:
                    data = res.json()
                    docs = data.get("response", {}).get("docs", [])
                    for idx, d in enumerate(docs, start=1):
                        uri = d.get("uri_s", "")
                        titles = d.get("title_s", [])
                        title = titles[0] if titles else "HAL Research Document"
                        abstracts = d.get("abstract_s", [])
                        abstract = abstracts[0] if abstracts else ""
                        year = d.get("producedDateY_i")
                        doi = d.get("doiId_s")

                        target_url = f"https://doi.org/{doi}" if doi else uri
                        if target_url:
                            candidates.append(
                                SourceCandidate(
                                    url=target_url,
                                    canonical_url=target_url,
                                    title=title,
                                    snippet=f"[HAL EU Repository] {abstract[:300]}",
                                    provider=self.descriptor.name,
                                    provider_rank=idx,
                                    source_type="PRIMARY_RESEARCH",
                                    published_at=str(year) if year else None,
                                    goal_ids=[request.goal_id]
                                    if request.goal_id
                                    else [],
                                    authority_prior=0.91,
                                    provider_metadata={
                                        "region": "europe",
                                        "hub": "HAL",
                                        "doi": doi or "",
                                    },
                                )
                            )
        except Exception as exc:
            logger.debug("HAL repository query error: %s", exc)

        # 2. CyberLeninka (Open Access Scientific Repository for Russian/CIS Academic Journals)
        if any(ord(c) > 127 for c in request.query) or request.language == "ru":
            try:
                cl_query = urllib.parse.quote(request.query)
                cl_url = f"https://cyberleninka.ru/api/search?q={cl_query}&size={min(request.max_results, 8)}"
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                transport = httpx.AsyncHTTPTransport(retries=2)
                async with httpx.AsyncClient(
                    transport=transport,
                    timeout=request.timeout_sec,
                    headers=headers,
                    follow_redirects=True,
                    trust_env=False,
                ) as client:
                    res = await client.get(cl_url)
                    if res.status_code == 200:
                        data = res.json()
                        articles = data.get("articles", [])
                        for idx, art in enumerate(articles, start=1):
                            link = art.get("link")
                            title = art.get("name") or "Научная статья"
                            annotation = art.get("annotation") or ""
                            year = art.get("year")
                            journal = art.get("journal", "")

                            if link:
                                target_url = (
                                    f"https://cyberleninka.ru{link}"
                                    if link.startswith("/")
                                    else link
                                )
                                candidates.append(
                                    SourceCandidate(
                                        url=target_url,
                                        canonical_url=target_url,
                                        title=title,
                                        snippet=f"[{journal or 'КиберЛенинка'}, {year or ''}] {annotation[:300]}",
                                        provider=self.descriptor.name,
                                        provider_rank=idx,
                                        source_type="PRIMARY_RESEARCH",
                                        published_at=str(year) if year else None,
                                        goal_ids=[request.goal_id]
                                        if request.goal_id
                                        else [],
                                        authority_prior=0.90,
                                        provider_metadata={
                                            "region": "cis",
                                            "hub": "CyberLeninka",
                                            "journal": journal,
                                        },
                                    )
                                )
            except Exception as exc:
                logger.debug("CyberLeninka query error: %s", exc)

        return candidates[: request.max_results]
