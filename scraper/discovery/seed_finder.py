"""Multi-Source Seed Discovery Engine (§19).

Discovers seeds dynamically across ArXiv, Academic repos, News portals,
and Domain-specific knowledge bases.
"""

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional
import httpx

from scraper.config import settings

logger = logging.getLogger(__name__)


async def fetch_arxiv_seeds(query: str, max_results: int = 5) -> List[str]:
    """Queries ArXiv API for scientific papers related to query."""
    url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}"
    urls = []
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            res = await client.get(url)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                    id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
                    if id_elem is not None and id_elem.text:
                        urls.append(id_elem.text.strip())
    except Exception as exc:
        logger.warning("ArXiv seed discovery error for query '%s': %s", query, exc)
    return urls


async def fetch_wikipedia_search_seeds(query: str, lang: str = "en", max_results: int = 5) -> List[str]:
    """Queries Wikipedia API for top matching article pages."""
    url = f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(query)}&limit={max_results}&namespace=0&format=json"
    urls = []
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                if len(data) >= 4 and isinstance(data[3], list):
                    urls = data[3]
    except Exception as exc:
        logger.warning("Wikipedia API search error for query '%s': %s", query, exc)
    return urls


async def fetch_europe_pmc_seeds(query: str, max_results: int = 5) -> List[str]:
    """Queries Europe PMC REST API for peer-reviewed medical and biological research papers."""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(query)}&format=json&pageSize={max_results}"
    urls = []
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                results = data.get("resultList", {}).get("result", [])
                for item in results:
                    pmcid = item.get("pmcid")
                    pmid = item.get("pmid")
                    if pmcid:
                        urls.append(f"https://europepmc.org/article/PMC/{pmcid}")
                    elif pmid:
                        urls.append(f"https://europepmc.org/abstract/MED/{pmid}")
                    elif item.get("doi"):
                        urls.append(f"https://doi.org/{item.get('doi')}")
    except Exception as exc:
        logger.warning("Europe PMC seed discovery error for query '%s': %s", query, exc)
    return urls


async def fetch_pubmed_seeds(query: str, max_results: int = 5) -> List[str]:
    """Queries NCBI PubMed E-utilities API for scientific medical publications via Europe PMC fallback."""
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term={urllib.parse.quote(query)}&retmode=json&retmax={max_results}"
    urls = []
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                id_list = data.get("esearchresult", {}).get("idlist", [])
                for pmc_id in id_list:
                    urls.append(f"https://europepmc.org/article/PMC/PMC{pmc_id}")
    except Exception as exc:
        logger.warning("NCBI PubMed seed discovery error for query '%s': %s", query, exc)
    return urls


async def fetch_annas_archive_seeds(query: str, max_results: int = 5) -> List[str]:
    """Queries Anna's Archive (annas-archive.cc) for books, papers, and open literature."""
    base_url = getattr(settings, "annas_archive_url", "https://annas-archive.cc").rstrip("/")
    encoded = urllib.parse.quote(query)
    urls = []
    headers = {
        "User-Agent": getattr(settings.robots, "user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    }

    endpoints = [
        f"{base_url}/s/?q={encoded}",
        f"{base_url}/articles?q={encoded}",
    ]

    try:
        from selectolax.parser import HTMLParser
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            for ep in endpoints:
                res = await client.get(ep, headers=headers, follow_redirects=True)
                if res.status_code == 200 and res.text:
                    parser = HTMLParser(res.text)
                    for a in parser.css("a"):
                        href = a.attributes.get("href") or ""
                        if any(k in href for k in ["/book/", "/article/", "/md5/", "/db/"]):
                            full_url = href if href.startswith("http") else f"{base_url}{href}"
                            if full_url not in urls:
                                urls.append(full_url)
                                if len(urls) >= max_results:
                                    break
                if len(urls) >= max_results:
                    break
    except Exception as exc:
        logger.warning("Anna's Archive seed discovery error for query '%s': %s", query, exc)

    return urls


async def discover_diverse_seeds(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    category: Optional[str] = None
) -> List[str]:
    """Discovers diverse seed URLs from multiple academic, medical, news, open library (Anna's Archive), and technical providers."""
    discovered: List[str] = []
    
    # 1. Add user preferred sources first
    if preferred_sources:
        discovered.extend(preferred_sources)

    # 2. Check query intent or category for targeted discovery
    q_lower = query.lower()
    
    is_medical = any(k in q_lower for k in ["alopecia", "hair loss", "облысени", "алопеци", "finasteride", "minoxidil", "jak", "follicle", "dht", "scalp", "dermatol", "medical", "disease"])
    is_scientific = any(k in q_lower for k in ["quantum", "algorithm", "learning", "neural", "physics", "model", "science", "paper", "arxiv", " смол", "полимер", "фотополимер", " resin", "photopolymer"]) or is_medical
    is_news = any(k in q_lower for k in ["war", "news", "timeline", "ukraine", "conflict", "russia", "event"])
    is_engineering = any(k in q_lower for k in ["cutting", "speed", "feed", "machining", "режим", "резани", "токарн", "фрезер", "3d", "печать", "смола", "полимер", "фотополимер", " resin", "photopolymer", "sla", "dlp", "lcd"])

    if category == "medical" or is_medical:
        pmc_urls = await fetch_europe_pmc_seeds(query, max_results=5)
        pubmed_urls = await fetch_pubmed_seeds(query, max_results=5)
        discovered.extend(pmc_urls)
        discovered.extend(pubmed_urls)

    if category == "science" or is_scientific:
        arxiv_urls = await fetch_arxiv_seeds(query, max_results=4)
        discovered.extend(arxiv_urls)

    if category == "news" or is_news:
        wiki_en_news = await fetch_wikipedia_search_seeds(query, lang="en", max_results=3)
        discovered.extend(wiki_en_news)

    if category == "engineering" or is_engineering:
        wiki_ru = await fetch_wikipedia_search_seeds(query, lang="ru", max_results=3)
        wiki_en = await fetch_wikipedia_search_seeds(query, lang="en", max_results=3)
        discovered.extend(wiki_ru)
        discovered.extend(wiki_en)

    # Fetch Anna's Archive seeds as open library/article source
    annas_urls = await fetch_annas_archive_seeds(query, max_results=4)
    discovered.extend(annas_urls)

    # Always fetch relevant Wikipedia articles as grounding context
    wiki_en = await fetch_wikipedia_search_seeds(query, lang="en", max_results=3)
    wiki_ru = await fetch_wikipedia_search_seeds(query, lang="ru", max_results=3)
    discovered.extend(wiki_en)
    discovered.extend(wiki_ru)

    # Fallback: if main query fetched 0 seeds, try sub-topic keywords
    if not discovered:
        keywords = []
        if "фотополимер" in q_lower or "смол" in q_lower:
            keywords.extend(["фотополимеры", "стереолитография", "3D-печать", "photopolymer"])
        for kw in keywords:
            w_ru = await fetch_wikipedia_search_seeds(kw, lang="ru", max_results=3)
            w_en = await fetch_wikipedia_search_seeds(kw, lang="en", max_results=3)
            discovered.extend(w_ru)
            discovered.extend(w_en)

    # Deduplicate while preserving order
    seen = set()
    final_seeds = []
    for u in discovered:
        if u not in seen:
            seen.add(u)
            final_seeds.append(u)

    logger.info("Discovered %d diverse seed URLs for query '%s': %s", len(final_seeds), query, final_seeds)
    return final_seeds


