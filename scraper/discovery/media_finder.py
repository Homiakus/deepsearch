"""Media Discovery Engine (§19).

Extracts downloadable documents (PDF, DOCX, XLSX, PPTX, CSV) and topic-relevant images/diagrams from HTML content,
plus topic-focused open media sources (Wikimedia Commons). Scores and ranks images from 5 to 25 per topic.
"""

import re
import urllib.parse
import logging
from typing import List, Dict, Any, Set, Optional
import httpx
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".csv",
    ".xml",
}
DOCUMENT_PATH_PATTERNS = [
    r"/pdf/",
    r"ptpmcrender\.fcgi",
    r"/articles/PMC\d+/pdf",
    r"download=pdf",
    r"format=pdf",
    r"/pdf$",
]

EXCLUDE_KEYWORDS = {
    "logo",
    "avatar",
    "icon",
    "badge",
    "banner",
    "button",
    "footer",
    "header",
    "nav",
    "tracking",
    "pixel",
    "cookie",
    "sprite",
    "spinner",
    "loader",
    "social",
    "facebook",
    "twitter",
    "instagram",
    "linkedin",
    "share",
}
MIN_ACCEPTED_IMAGE_DIMENSION = 160
MIN_ACCEPTED_IMAGE_RELEVANCE = 0.55

AUTHORITY_DOMAINS = {
    "wikimedia",
    "wikipedia",
    "pubmed",
    "ncbi",
    "arxiv",
    "nature.com",
    "sciencedirect",
    "biorxiv",
    "medrxiv",
    "springer",
    "ieee",
    "wiley",
    "acm.org",
    "mdpi",
    "frontiersin",
    "cell.com",
    "thelancet",
    "github",
}


def _pick_best_srcset_url(srcset_str: str, base_url: str) -> Optional[str]:
    """Picks the highest resolution image URL from a srcset attribute."""
    if not srcset_str:
        return None
    candidates = []
    for part in srcset_str.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        url_part = tokens[0]
        full_url = urllib.parse.urljoin(base_url, url_part)
        score = 1
        if len(tokens) > 1:
            desc = tokens[1].lower()
            if desc.endswith("w"):
                try:
                    score = int(desc[:-1])
                except ValueError:
                    score = 1
            elif desc.endswith("x"):
                try:
                    score = int(float(desc[:-1]) * 1000)
                except ValueError:
                    score = 1
        candidates.append((score, full_url))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def extract_document_links(raw_html: str, base_url: str) -> List[str]:
    """Extracts downloadable document URLs (PDF, Word, Excel, etc.) from HTML."""
    if not raw_html:
        return []

    parser = HTMLParser(raw_html)
    discovered_docs: Set[str] = set()

    for node in parser.css("a[href]"):
        href = node.attributes.get("href")
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full_url)
        path = parsed.path.lower()

        # Check extension
        has_doc_ext = any(path.endswith(ext) for ext in DOCUMENT_EXTENSIONS)

        # Check URL pattern (e.g. ArXiv or PMC PDF renderers)
        has_doc_pattern = any(
            re.search(pat, full_url, re.IGNORECASE) for pat in DOCUMENT_PATH_PATTERNS
        )

        if has_doc_ext or has_doc_pattern:
            discovered_docs.add(full_url)

    # Check base_url or raw_html for PMC ID (e.g. PMC13299106)
    pmc_match = re.search(r"PMC\d+", base_url, re.IGNORECASE) or re.search(
        r"PMC\d+", raw_html
    )
    if pmc_match:
        pmcid = pmc_match.group(0).upper()
        discovered_docs.add(
            f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
        )

    # Check base_url for ArXiv ID (e.g. arxiv.org/abs/2301.12345)
    arxiv_match = re.search(
        r"arxiv\.org/(?:abs|html)/(\d+\.\d+(?:v\d+)?)", base_url, re.IGNORECASE
    )
    if arxiv_match:
        arxiv_id = arxiv_match.group(1)
        discovered_docs.add(f"https://arxiv.org/pdf/{arxiv_id}.pdf")

    return list(discovered_docs)


def extract_image_candidates(raw_html: str, base_url: str) -> List[Dict[str, Any]]:
    """Extracts candidate image nodes from HTML with rich context (alt, title, figcaption, dimensions, og:image)."""
    if not raw_html:
        return []

    parser = HTMLParser(raw_html)
    candidates: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    # 1. Check OpenGraph / Twitter meta images (editorial primary visual)
    for meta_sel in [
        'meta[property="og:image"]',
        'meta[name="og:image"]',
        'meta[name="twitter:image"]',
        'meta[property="twitter:image"]',
    ]:
        og_node = parser.css_first(meta_sel)
        if og_node:
            og_content = og_node.attributes.get("content")
            if og_content and not og_content.startswith("data:"):
                full_og_url = urllib.parse.urljoin(base_url, og_content)
                if full_og_url not in seen_urls:
                    seen_urls.add(full_og_url)
                    title_node = parser.css_first("title") or parser.css_first(
                        'meta[property="og:title"]'
                    )
                    page_title = (
                        (
                            title_node.text(strip=True)
                            if hasattr(title_node, "text")
                            else str(title_node.attributes.get("content", ""))
                        )
                        if title_node
                        else ""
                    )
                    candidates.append(
                        {
                            "url": full_og_url,
                            "caption": page_title or "Main Article Image",
                            "alt": page_title or "Main Article Image",
                            "title": page_title or "Main Article Image",
                            "figcaption": page_title or "",
                            "width": 800,
                            "height": 500,
                            "source_domain": urllib.parse.urlparse(full_og_url).netloc,
                            "page_url": base_url,
                            "is_primary": True,
                            "license": "UNKNOWN_LICENSE",
                            "author": "UNKNOWN_AUTHOR",
                        }
                    )
                break

    # 2. Extract standard and responsive images
    for img in parser.css("img"):
        src = (
            img.attributes.get("src")
            or img.attributes.get("data-src")
            or img.attributes.get("data-original")
        )
        srcset = img.attributes.get("srcset")
        if srcset:
            best_srcset = _pick_best_srcset_url(srcset, base_url)
            if best_srcset:
                src = best_srcset

        # Check enclosing picture tag for source srcset
        parent = img.parent
        if parent and parent.tag == "picture":
            for src_tag in parent.css("source[srcset]"):
                p_srcset = src_tag.attributes.get("srcset")
                best_p = _pick_best_srcset_url(p_srcset or "", base_url)
                if best_p:
                    src = best_p
                    break

        if not src or src.startswith("data:"):
            continue

        full_url = urllib.parse.urljoin(base_url, src)
        if full_url in seen_urls:
            continue

        # Basic exclusions based on URL & CSS class
        url_lower = full_url.lower()
        img_class = (img.attributes.get("class") or "").lower()
        if any(kw in url_lower or kw in img_class for kw in EXCLUDE_KEYWORDS):
            continue

        alt = (img.attributes.get("alt") or "").strip()
        title = (img.attributes.get("title") or "").strip()

        # Skip tiny SVG icons without alt text
        if url_lower.endswith(".svg") and not alt:
            continue

        # Parse width/height attributes if available
        w_val = img.attributes.get("width")
        h_val = img.attributes.get("height")
        width, height = None, None
        try:
            if w_val:
                width = int(re.sub(r"\D", "", w_val))
            if h_val:
                height = int(re.sub(r"\D", "", h_val))
        except ValueError:
            pass

        if (width and width < 80) or (height and height < 80):
            continue

        # Extract parent figure caption if enclosed in <figure>
        figcaption = ""
        p_node = img.parent
        while p_node:
            if p_node.tag == "figure":
                fig_node = p_node.css_first("figcaption")
                if fig_node:
                    figcaption = fig_node.text(strip=True)
                break
            p_node = p_node.parent

        caption = alt or title or figcaption or "Topic Image / Diagram"

        seen_urls.add(full_url)
        candidates.append(
            {
                "url": full_url,
                "caption": caption,
                "alt": alt,
                "title": title,
                "figcaption": figcaption,
                "width": width,
                "height": height,
                "source_domain": urllib.parse.urlparse(full_url).netloc,
                "page_url": base_url,
                "license": "UNKNOWN_LICENSE",
                "author": "UNKNOWN_AUTHOR",
            }
        )

    return candidates


async def fetch_wikimedia_topic_images(
    query: str, max_results: int = 10
) -> List[Dict[str, Any]]:
    """Queries Wikimedia Commons API for open topic-relevant images using list=search."""
    if not query:
        return []

    clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
    encoded_query = urllib.parse.quote(clean_query or query)
    search_url = (
        f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={encoded_query}&gsrnamespace=6&gsrlimit={max_results}&prop=imageinfo"
        f"&iiprop=url|size|extmetadata&format=json"
    )

    candidates: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "DeepSearchBot/1.0 (https://deepsearch.org; contact@deepsearch.org) Python/3.13"
    }

    try:
        async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
            res = await client.get(search_url, headers=headers)
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    file_title = page_info.get("title", "")
                    imageinfo = page_info.get("imageinfo", [])
                    if not imageinfo:
                        continue
                    info = imageinfo[0]
                    img_url = info.get("url")
                    if not img_url:
                        continue

                    raw_title = file_title.replace("File:", "").replace("_", " ")
                    extmetadata = info.get("extmetadata", {})
                    desc = (
                        extmetadata.get("ObjectName", {}).get("value")
                        or extmetadata.get("ImageDescription", {}).get("value")
                        or raw_title
                    )
                    clean_desc = (
                        re.sub(r"<[^>]+>", "", str(desc)).strip()[:200] or raw_title
                    )

                    license_raw = (
                        extmetadata.get("LicenseShortName", {}).get("value")
                        or extmetadata.get("UsageTerms", {}).get("value")
                        or "UNKNOWN_LICENSE"
                    )
                    artist_raw = (
                        extmetadata.get("Artist", {}).get("value")
                        or extmetadata.get("Author", {}).get("value")
                        or extmetadata.get("Credit", {}).get("value")
                        or "UNKNOWN_AUTHOR"
                    )
                    clean_author = (
                        re.sub(r"<[^>]+>", "", str(artist_raw)).strip()
                        or "UNKNOWN_AUTHOR"
                    )

                    candidates.append(
                        {
                            "url": img_url,
                            "caption": clean_desc,
                            "alt": raw_title,
                            "title": raw_title,
                            "figcaption": clean_desc,
                            "width": info.get("width"),
                            "height": info.get("height"),
                            "source_domain": "commons.wikimedia.org",
                            "page_url": info.get("descriptionurl", ""),
                            "license": str(license_raw).strip() or "UNKNOWN_LICENSE",
                            "author": clean_author,
                        }
                    )
    except Exception as exc:
        logger.warning("Wikimedia Commons media search error for '%s': %s", query, exc)

    return candidates


async def fetch_wikipedia_article_images(
    query: str, max_results: int = 10
) -> List[Dict[str, Any]]:
    """Queries Wikipedia API for topic article thumbnails and images."""
    if not query:
        return []

    clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
    encoded_query = urllib.parse.quote(clean_query or query)
    api_url = (
        f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={encoded_query}&gsrlimit=5&prop=pageimages"
        f"&pithumbsize=1000&format=json"
    )

    candidates: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "DeepSearchBot/1.0 (https://deepsearch.org; contact@deepsearch.org) Python/3.13"
    }

    try:
        async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
            res = await client.get(api_url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    title = page_info.get("title", "")
                    thumb = page_info.get("thumbnail", {})
                    if thumb and thumb.get("source"):
                        img_url = thumb["source"]
                        candidates.append(
                            {
                                "url": img_url,
                                "caption": f"{title} - Main Diagram/Photo",
                                "alt": title,
                                "title": title,
                                "figcaption": f"Illustration for {title}",
                                "width": thumb.get("width"),
                                "height": thumb.get("height"),
                                "source_domain": "en.wikipedia.org",
                                "page_url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                                "license": "CC BY-SA 4.0",
                                "author": "Wikipedia Contributors",
                            }
                        )
    except Exception as exc:
        logger.warning("Wikipedia article media search error for '%s': %s", query, exc)

    return candidates


def score_and_rank_images(
    candidates: List[Dict[str, Any]],
    query: str,
    min_count: int = 5,
    max_count: int = 25,
) -> List[Dict[str, Any]]:
    """Scores candidate images by relevance to the query topic and ranks top min_count..max_count items."""
    if min_count > max_count:
        raise ValueError(
            f"min_count ({min_count}) cannot be greater than max_count ({max_count})"
        )
    if not candidates:
        return []

    # Clean and tokenize query terms (keeping meaningful short acronyms >= 2 chars, e.g. AI, 3D, ML, 5G)
    raw_query_terms = [
        t.lower() for t in re.findall(r"[\w]+", query) if len(t) >= 2 or t.isalnum()
    ]
    query_terms = raw_query_terms

    scored_images: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    for item in candidates:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        score = 0.35 if item.get("is_primary") else 0.30  # Base candidate score

        caption = (item.get("caption") or "").lower()
        alt = (item.get("alt") or "").lower()
        title = (item.get("title") or "").lower()
        figcaption = (item.get("figcaption") or "").lower()
        filename = urllib.parse.unquote(url.split("/")[-1]).lower()

        combined_text = f"{caption} {alt} {title} {figcaption} {filename}"

        # Reject technical assets before scoring: favicons, badges, tracking
        # pixels and licence marks are not topic evidence.
        if any(kw in combined_text for kw in EXCLUDE_KEYWORDS):
            continue
        w = item.get("width")
        h = item.get("height")
        if (w is not None and w < MIN_ACCEPTED_IMAGE_DIMENSION) or (
            h is not None and h < MIN_ACCEPTED_IMAGE_DIMENSION
        ):
            continue

        # 1. Topic Lexical Matching with token boundary matching to avoid false positives (e.g. art vs chart)
        text_tokens = set(re.findall(r"[\w]+", combined_text))

        def _matches_term(q_term: str) -> bool:
            if q_term in text_tokens:
                return True
            # Prefix/stem matching for words >= 4 chars (e.g. "laser" in "lasers", "algorithm" in "algorithms")
            if len(q_term) >= 4 and any(
                tok.startswith(q_term) or q_term.startswith(tok)
                for tok in text_tokens
                if len(tok) >= 4
            ):
                return True
            return False

        term_matches = sum(1 for term in query_terms if _matches_term(term))
        if query_terms:
            match_ratio = term_matches / len(query_terms)
            score += match_ratio * 0.45

        # 2. Source Domain Authority
        domain = item.get("source_domain", "").lower()
        if any(d in domain for d in AUTHORITY_DOMAINS):
            score += 0.15

        # 3. Dimensions & Aspect Ratio Heuristics
        if w and h:
            if w >= 400 and h >= 300:
                score += 0.15
            elif w < 120 or h < 120:
                score -= 0.3

            aspect_ratio = w / max(h, 1)
            if 0.4 <= aspect_ratio <= 2.5:
                score += 0.05
            else:
                score -= 0.1

        final_score = round(max(0.05, min(1.0, score)), 3)

        if query_terms and final_score < MIN_ACCEPTED_IMAGE_RELEVANCE:
            continue

        scored_item = dict(item)
        scored_item["relevance_score"] = final_score
        scored_images.append(scored_item)

    # Sort descending by relevance score with deterministic URL tie-break (§FRAG-003)
    scored_images.sort(
        key=lambda x: (x["relevance_score"], x.get("url", "")), reverse=True
    )

    # Select target count in range [min_count, max_count]
    target_count = max(min_count, min(len(scored_images), max_count))
    return scored_images[:target_count]


def is_accepted_media_file(
    media_info: Dict[str, Any], candidate: Optional[Dict[str, Any]] = None
) -> bool:
    """Validates downloaded media, including dimensions and topic score."""
    candidate = candidate or {}
    width = media_info.get("width") or candidate.get("width")
    height = media_info.get("height") or candidate.get("height")
    if width is not None and width < MIN_ACCEPTED_IMAGE_DIMENSION:
        return False
    if height is not None and height < MIN_ACCEPTED_IMAGE_DIMENSION:
        return False
    if (
        media_info.get("relevance_score", candidate.get("relevance_score", 0.0))
        < MIN_ACCEPTED_IMAGE_RELEVANCE
    ):
        return False
    combined_text = " ".join(
        str(candidate.get(key, "")) for key in ("caption", "alt", "title", "figcaption")
    ).lower()
    return not any(kw in combined_text for kw in EXCLUDE_KEYWORDS)


def extract_relevant_images(
    raw_html: str, base_url: str, max_images: int = 5
) -> List[Dict[str, str]]:
    """Legacy helper for backwards compatibility. Returns top images extracted from HTML."""
    candidates = extract_image_candidates(raw_html, base_url)
    if not candidates:
        return []
    ranked = score_and_rank_images(
        candidates, query="", min_count=1, max_count=max_images
    )
    return [{"url": img["url"], "caption": img["caption"]} for img in ranked]
