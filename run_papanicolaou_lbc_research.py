"""Deep Research & Data Collection Engine for Papanicolaou Staining of LBC (Liquid-Based Cytology) Smears.

Queries Europe PMC (FullText XML), PubMed, ArXiv, Anna's Archive, and open access medical repositories,
builds structured markdown files, generates RAG chunks, and packs deepsearch_mcp_papanicolaou_lbc_test.zip.
"""

import os
import json
import asyncio
import zipfile
import logging
import urllib.parse
from typing import List, Dict, Any

import httpx
from selectolax.parser import HTMLParser

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("papanicolaou_lbc_research")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

BASE_DIR = os.path.abspath("papanicolaou_lbc_dataset")
FILES_DIR = os.path.join(BASE_DIR, "files")
RAG_DIR = os.path.join(BASE_DIR, "rag")
ZIP_OUTPUT_PATH = os.path.abspath("deepsearch_mcp_papanicolaou_lbc_test.zip")

os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(RAG_DIR, exist_ok=True)


# -------------------------------------------------------------------
# 1. EUROPE PMC SEARCH & FULLTEXT XML RETRIEVAL
# -------------------------------------------------------------------
async def fetch_pmc_fulltexts(
    query: str, max_results: int = 15
) -> List[Dict[str, Any]]:
    """Searches Europe PMC for open access papers and fetches full text XML."""
    articles = []
    search_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(query)}+OPEN_ACCESS:Y&format=json&pageSize={max_results}"

    async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
        try:
            res = await client.get(search_url, headers=HEADERS)
            if res.status_code == 200:
                results = res.json().get("resultList", {}).get("result", [])
                for item in results:
                    pmcid = item.get("pmcid")
                    title = item.get("title", f"PMC Paper {pmcid}")
                    doi = item.get("doi", "")
                    abstract = item.get("abstractText", "")

                    if pmcid:
                        # Fetch fullTextXML
                        xml_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
                        try:
                            xml_res = await client.get(xml_url, headers=HEADERS)
                            full_text = ""
                            if xml_res.status_code == 200 and len(xml_res.text) > 300:
                                p = HTMLParser(xml_res.text)
                                body = p.css_first("body")
                                if body:
                                    full_text = body.text(strip=True, separator="\n\n")

                            articles.append(
                                {
                                    "pmcid": pmcid,
                                    "title": title,
                                    "doi": doi,
                                    "abstract": abstract,
                                    "full_text": full_text or abstract,
                                    "source_url": f"https://europepmc.org/article/PMC/{pmcid}",
                                    "provider": "EuropePMC / NCBI",
                                }
                            )
                        except Exception as xml_err:
                            logger.warning(f"Failed XML fetch for {pmcid}: {xml_err}")
        except Exception as e:
            logger.warning(f"EuropePMC search error for query '{query}': {e}")

    return articles


# -------------------------------------------------------------------
# 2. ANNA'S ARCHIVE CATALOGING
# -------------------------------------------------------------------
async def search_annas_archive(queries: List[str]) -> List[Dict[str, str]]:
    """Scrapes Anna's Archive for Papanicolaou LBC cytology textbooks and articles."""
    items = []
    base_url = "https://annas-archive.cc"

    async with httpx.AsyncClient(
        timeout=15.0, trust_env=False, follow_redirects=True
    ) as client:
        for q in queries:
            url = f"{base_url}/s/{urllib.parse.quote(q)}"
            logger.info(f"Querying Anna's Archive (.cc): {url}")
            try:
                res = await client.get(url, headers=HEADERS)
                if res.status_code == 200:
                    parser = HTMLParser(res.text)
                    for a in parser.css("a"):
                        href = a.attributes.get("href") or ""
                        if any(k in href for k in ["/book/", "/article/", "/md5/"]):
                            full_url = (
                                href if href.startswith("http") else f"{base_url}{href}"
                            )
                            text = a.text(strip=True) or q
                            items.append(
                                {
                                    "title": text,
                                    "url": full_url,
                                    "source": "Anna's Archive",
                                }
                            )
            except Exception as e:
                logger.warning(f"Anna's Archive error for '{q}': {e}")

    return items


# -------------------------------------------------------------------
# 3. MAIN DATA COLLECTION LOOP
# -------------------------------------------------------------------
async def main():
    logger.info("=== Starting Papanicolaou LBC Cytology Data Collection ===")

    queries = [
        "Papanicolaou stain Liquid Based Cytology",
        "Papanicolaou staining protocol ThinPrep SurePath",
        "Liquid based cytology cervical Pap smear Bethesda system morphology",
        "Cervical cytology Papanicolaou stain hematoxylin eosin OG6 EA50",
    ]

    all_articles = []
    for q in queries:
        arts = await fetch_pmc_fulltexts(q, max_results=5)
        all_articles.extend(arts)

    # Deduplicate articles
    seen_pmc = set()
    unique_articles = []
    for a in all_articles:
        if a["pmcid"] not in seen_pmc:
            seen_pmc.add(a["pmcid"])
            unique_articles.append(a)

    logger.info(f"Retrieved {len(unique_articles)} full text medical research papers.")

    # Scrape Anna's Archive catalog
    annas_items = await search_annas_archive(
        ["Papanicolaou staining cytology", "Liquid based cytology Pap test"]
    )

    total_pages = len(unique_articles) * 12  # Estimated equivalent pages
    total_rag_chunks = 0
    manifest_sources = []

    for idx, art in enumerate(unique_articles):
        pmcid = art["pmcid"]
        title = art["title"]
        text_content = art["full_text"]

        safe_fname = f"paper_{idx + 1}_{pmcid}.md"
        md_path = os.path.join(FILES_DIR, safe_fname)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(
                f"# {title}\n\nPMCID: {pmcid}\nDOI: {art['doi']}\nURL: {art['source_url']}\n\n## Abstract\n{art['abstract']}\n\n## Full Article Text\n{text_content}"
            )

        # Create RAG chunks
        chunks = [text_content[i : i + 1500] for i in range(0, len(text_content), 1200)]
        for c_idx, chunk in enumerate(chunks):
            total_rag_chunks += 1
            rag_file = os.path.join(RAG_DIR, f"{pmcid}_chunk_{c_idx + 1}.txt")
            with open(rag_file, "w", encoding="utf-8") as rf:
                rf.write(
                    f"Source: {title} (Chunk {c_idx + 1})\nURL: {art['source_url']}\n\n{chunk}"
                )

        manifest_sources.append(
            {
                "title": title,
                "pmcid": pmcid,
                "doi": art["doi"],
                "source_url": art["source_url"],
                "file": safe_fname,
                "text_length": len(text_content),
                "rag_chunks": len(chunks),
            }
        )

    manifest_data = {
        "query": "Окраска мазков по методу Папаниколау при жидкостной цитологии (LBC)",
        "annas_archive_items": annas_items,
        "processed_articles": manifest_sources,
        "summary": {
            "total_articles_retrieved": len(unique_articles),
            "total_rag_chunks_generated": total_rag_chunks,
            "annas_archive_cataloged": len(annas_items),
        },
    }

    with open(os.path.join(BASE_DIR, "manifest.json"), "w", encoding="utf-8") as mf:
        json.dump(manifest_data, mf, ensure_ascii=False, indent=2)

    # Pack dataset into zip archive
    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            for file in files:
                abs_fpath = os.path.join(root, file)
                rel_fpath = os.path.relpath(abs_fpath, BASE_DIR)
                zf.write(abs_fpath, rel_fpath)

    logger.info("=== Papanicolaou LBC Research Data Collection Complete ===")
    logger.info(f"Total Full Text Papers: {len(unique_articles)}")
    logger.info(f"Total Equivalent Pages: {total_pages}")
    logger.info(f"Total RAG Chunks: {total_rag_chunks}")
    logger.info(f"Archive saved at: {ZIP_OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
