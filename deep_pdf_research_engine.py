"""Deep PDF & Multi-Source Research Engine for Laser Cutting Industrial Parameters.

Queries Anna's Archive, ArXiv, Europe PMC, NCBI, MDPI, and Open Access repos,
downloads actual PDF research papers into pdfs/ directory, parses thousands of pages,
generates RAG chunks, and packs everything into laser_cutting_research.zip.
"""

import os
import re
import sys
import json
import asyncio
import zipfile
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

import httpx
import pypdf
from selectolax.parser import HTMLParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deep_pdf_research")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

BASE_DIR = os.path.abspath("laser_research_dataset")
PDF_DIR = os.path.join(BASE_DIR, "pdfs")
FILES_DIR = os.path.join(BASE_DIR, "files")
RAG_DIR = os.path.join(BASE_DIR, "rag")
ZIP_OUTPUT_PATH = os.path.abspath("laser_cutting_research.zip")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(RAG_DIR, exist_ok=True)

# -------------------------------------------------------------------
# 1. ANNA'S ARCHIVE RESEARCH SCRAPER
# -------------------------------------------------------------------
async def search_annas_archive(queries: List[str]) -> List[Dict[str, str]]:
    """Scrapes Anna's Archive (annas-archive.cc) for book/paper entries."""
    items = []
    base_url = "https://annas-archive.cc"
    
    async with httpx.AsyncClient(timeout=15.0, trust_env=False, follow_redirects=True) as client:
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
                            full_url = href if href.startswith("http") else f"{base_url}{href}"
                            text = a.text(strip=True) or q
                            items.append({"title": text, "url": full_url, "source": "Anna's Archive"})
            except Exception as e:
                logger.warning(f"Anna's Archive search error for '{q}': {e}")
                
    logger.info(f"Discovered {len(items)} items from Anna's Archive.")
    return items

# -------------------------------------------------------------------
# 2. ARXIV PDF DISCOVERY & DOWNLOAD
# -------------------------------------------------------------------
async def fetch_arxiv_pdfs(queries: List[str], max_per_query: int = 4) -> List[Dict[str, Any]]:
    """Searches ArXiv API and collects direct PDF download links."""
    pdf_targets = []
    
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        for q in queries:
            url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(q)}&start=0&max_results={max_per_query}"
            logger.info(f"Querying ArXiv API: {url}")
            try:
                res = await client.get(url, headers=HEADERS)
                if res.status_code == 200:
                    root = ET.fromstring(res.text)
                    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                        title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
                        id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
                        summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary")
                        
                        if id_elem is not None and id_elem.text:
                            arxiv_id = id_elem.text.strip().split('/')[-1]
                            pdf_url = f"https://export.arxiv.org/pdf/{arxiv_id}.pdf"
                            title = title_elem.text.strip() if title_elem is not None else f"ArXiv Paper {arxiv_id}"
                            summary = summary_elem.text.strip() if summary_elem is not None else ""
                            
                            pdf_targets.append({
                                "id": arxiv_id,
                                "title": title,
                                "pdf_url": pdf_url,
                                "source_url": id_elem.text.strip(),
                                "summary": summary,
                                "provider": "ArXiv"
                            })
            except Exception as e:
                logger.warning(f"ArXiv query error for '{q}': {e}")
                
    return pdf_targets

# -------------------------------------------------------------------
# 3. EUROPE PMC & NCBI PMC PDF DISCOVERY
# -------------------------------------------------------------------
async def fetch_pmc_pdfs(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    """Searches Europe PMC for open access articles and obtains PMC PDF links."""
    pdf_targets = []
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(query)}+OPEN_ACCESS:Y&format=json&pageSize={max_results}"
    
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        try:
            res = await client.get(url, headers=HEADERS)
            if res.status_code == 200:
                results = res.json().get("resultList", {}).get("result", [])
                for item in results:
                    pmcid = item.get("pmcid")
                    title = item.get("title", f"PMC Paper {pmcid}")
                    doi = item.get("doi", "")
                    
                    if pmcid:
                        ncbi_pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                        pdf_targets.append({
                            "id": pmcid,
                            "title": title,
                            "pdf_url": ncbi_pdf_url,
                            "source_url": f"https://europepmc.org/article/PMC/{pmcid}",
                            "summary": item.get("abstractText", ""),
                            "doi": doi,
                            "provider": "EuropePMC / NCBI"
                        })
        except Exception as e:
            logger.warning(f"EuropePMC query error: {e}")
            
    return pdf_targets

# -------------------------------------------------------------------
# 4. DOWNLOAD PDF FILES
# -------------------------------------------------------------------
async def download_pdf(client: httpx.AsyncClient, pdf_url: str, filename: str) -> str:
    """Downloads a PDF file and returns local file path if successful."""
    dest_path = os.path.join(PDF_DIR, filename)
    logger.info(f"Downloading PDF: {pdf_url} -> {dest_path}")
    
    try:
        res = await client.get(pdf_url, headers=HEADERS, follow_redirects=True, timeout=25.0)
        if res.status_code == 200 and (len(res.content) > 2000 or res.headers.get("content-type", "").lower().count("pdf")):
            with open(dest_path, "wb") as f:
                f.write(res.content)
            logger.info(f"Successfully downloaded PDF: {filename} ({len(res.content)} bytes)")
            return dest_path
        else:
            logger.warning(f"Failed PDF download for {pdf_url}: HTTP {res.status_code}")
    except Exception as e:
        logger.warning(f"Error downloading PDF {pdf_url}: {e}")
        
    return ""

# -------------------------------------------------------------------
# 5. MAIN RESEARCH PIPELINE EXECUTION
# -------------------------------------------------------------------
async def main():
    logger.info("=== Starting Deep PDF Research Pipeline ===")
    
    # 1. Scrape Anna's Archive for literature cataloging
    annas_queries = [
        "laser cutting",
        "laser cutting parameters",
        "fiber laser cutting",
        "industrial laser processing"
    ]
    annas_items = await search_annas_archive(annas_queries)
    
    # 2. Gather scientific PDF targets from ArXiv
    arxiv_queries = [
        "laser cutting parameters",
        "laser cutting melt gas dynamics",
        "fiber laser cutting stainless steel",
        "laser machining kerf width roughness"
    ]
    arxiv_pdfs = await fetch_arxiv_pdfs(arxiv_queries)
    
    # 3. Gather PMC PDF targets
    pmc_pdfs = await fetch_pmc_pdfs("laser cutting process optimization")
    
    # Combined PDF download queue
    all_pdf_targets = arxiv_pdfs + pmc_pdfs
    
    # Additional curated high-value open access research PDFs
    curated_pdfs = [
        {
            "id": "fiber_laser_opt_2020",
            "title": "Optimization of Fiber Laser Cutting Parameters for Stainless Steel",
            "pdf_url": "https://www.mdpi.com/2075-4701/10/11/1449/pdf",
            "source_url": "https://www.mdpi.com/2075-4701/10/11/1449",
            "provider": "MDPI Metals"
        },
        {
            "id": "assist_gas_focal_2021",
            "title": "Effect of Assist Gas Pressure and Focal Position on Laser Cutting Quality",
            "pdf_url": "https://www.mdpi.com/2075-4701/11/7/1035/pdf",
            "source_url": "https://www.mdpi.com/2075-4701/11/7/1035",
            "provider": "MDPI Metals"
        }
    ]
    all_pdf_targets.extend(curated_pdfs)
    
    downloaded_pdf_files = []
    
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for idx, target in enumerate(all_pdf_targets):
            safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(target["id"]))
            filename = f"paper_{idx+1}_{safe_id}.pdf"
            local_path = await download_pdf(client, target["pdf_url"], filename)
            if local_path and os.path.exists(local_path):
                target["local_pdf_path"] = local_path
                downloaded_pdf_files.append(target)
                
    logger.info(f"Downloaded {len(downloaded_pdf_files)} PDF research papers.")
    
    # 4. Extract Text & Generate RAG Chunks from PDFs
    total_pages_parsed = 0
    total_rag_chunks = 0
    manifest_sources = []
    
    for item in downloaded_pdf_files:
        pdf_path = item["local_pdf_path"]
        pdf_title = item["title"]
        extracted_pages_text = []
        
        try:
            reader = pypdf.PdfReader(pdf_path)
            num_pages = len(reader.pages)
            total_pages_parsed += num_pages
            
            for page_num, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    extracted_pages_text.append(f"--- Page {page_num+1} ---\n{txt}")
                    
            full_pdf_text = "\n\n".join(extracted_pages_text)
            
            # Save extracted markdown file under files/
            safe_fname = os.path.basename(pdf_path).replace(".pdf", ".md")
            md_path = os.path.join(FILES_DIR, safe_fname)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# {pdf_title}\n\nProvider: {item['provider']}\nSource URL: {item['source_url']}\nPDF Path: {pdf_path}\nTotal Pages: {num_pages}\n\n{full_pdf_text}")
                
            # Create RAG chunk files under rag/
            chunks = [full_pdf_text[i:i+1500] for i in range(0, len(full_pdf_text), 1200)]
            for c_idx, chunk in enumerate(chunks):
                total_rag_chunks += 1
                rag_file = os.path.join(RAG_DIR, f"{safe_fname}_chunk_{c_idx+1}.txt")
                with open(rag_file, "w", encoding="utf-8") as rf:
                    rf.write(f"Source: {pdf_title} (Page Chunk {c_idx+1})\nURL: {item['source_url']}\n\n{chunk}")
                    
            manifest_sources.append({
                "title": pdf_title,
                "provider": item["provider"],
                "source_url": item["source_url"],
                "pdf_file": os.path.basename(pdf_path),
                "pages": num_pages,
                "rag_chunks": len(chunks)
            })
            
        except Exception as e:
            logger.warning(f"Error parsing PDF {pdf_path}: {e}")
            
    # Add Anna's Archive discovered metadata to manifest
    manifest_data = {
        "query": "особенности лазерной резки в промышленности настройки лазеров (глубокий выбор по тысячам страниц)",
        "annas_archive_sources_found": annas_items,
        "pdf_sources_processed": manifest_sources,
        "summary": {
            "total_pdfs_downloaded": len(downloaded_pdf_files),
            "total_pages_parsed": total_pages_parsed,
            "total_rag_chunks": total_rag_chunks,
            "annas_archive_items_cataloged": len(annas_items)
        }
    }
    
    manifest_path = os.path.join(BASE_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest_data, mf, ensure_ascii=False, indent=2)
        
    # 5. Zip the entire dataset including pdfs/, files/, rag/, manifest.json
    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            for file in files:
                abs_fpath = os.path.join(root, file)
                rel_fpath = os.path.relpath(abs_fpath, BASE_DIR)
                zf.write(abs_fpath, rel_fpath)
                
    logger.info(f"=== Research Pipeline Complete ===")
    logger.info(f"Downloaded PDFs: {len(downloaded_pdf_files)}")
    logger.info(f"Total Pages Parsed: {total_pages_parsed}")
    logger.info(f"Total RAG Chunks: {total_rag_chunks}")
    logger.info(f"Archive created at: {ZIP_OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
