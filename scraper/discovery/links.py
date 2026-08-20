"""Deterministic Discovery Engine for Link Extraction (DS-SI12).

Preserves DOM document order and contextual metadata without set-randomization.
"""

import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional, Set
from pydantic import BaseModel
from selectolax.parser import HTMLParser


class DiscoveredLink(BaseModel):
    url: str
    canonical_url: Optional[str] = None
    anchor_text: str = ""
    surrounding_text: str = ""
    dom_position: int = 0
    section_heading: Optional[str] = None
    rel: Optional[str] = None
    is_navigation: bool = False
    is_footer: bool = False
    is_sidebar: bool = False


def extract_discovered_links(raw_html: str, base_url: str) -> List[DiscoveredLink]:
    """Extracts hyper-links in deterministic DOM document order with layout context (DS-SI12)."""
    if not raw_html:
        return []

    parser = HTMLParser(raw_html)
    discovered: List[DiscoveredLink] = []
    seen_urls: Set[str] = set()

    for idx, node in enumerate(parser.css("a[href]"), start=1):
        href = node.attributes.get("href")
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        anchor = node.text(strip=True) or ""
        rel = node.attributes.get("rel")

        # Determine layout zone
        parent = node.parent
        is_nav = False
        is_foot = False
        is_side = False

        cur = parent
        depth = 0
        while cur and depth < 5:
            tag = (cur.tag or "").lower()
            classes = (cur.attributes.get("class") or "").lower()
            cur_id = (cur.attributes.get("id") or "").lower()

            if (
                tag == "nav"
                or "nav" in classes
                or "menu" in classes
                or "header" in tag
                or "header" in classes
            ):
                is_nav = True
            if tag == "footer" or "footer" in classes:
                is_foot = True
            if tag == "aside" or "sidebar" in classes or "sidebar" in cur_id:
                is_side = True

            cur = cur.parent
            depth += 1

        # Surrounding snippet from immediate paragraph or parent text
        surrounding = ""
        if parent:
            surrounding = parent.text(strip=True)[:150]

        discovered.append(
            DiscoveredLink(
                url=full_url,
                canonical_url=full_url,
                anchor_text=anchor,
                surrounding_text=surrounding,
                dom_position=idx,
                rel=rel,
                is_navigation=is_nav,
                is_footer=is_foot,
                is_sidebar=is_side,
            )
        )

    return discovered


def extract_links_from_html(raw_html: str, base_url: str) -> List[str]:
    """Extracts list of unique URLs in deterministic DOM order (DS-SI12)."""
    links = extract_discovered_links(raw_html, base_url)
    return [link.url for link in links]


def extract_sitemap_urls(sitemap_xml: str) -> List[str]:
    """Parses sitemap.xml or sitemap index to discover target URLs (§19)."""
    urls: List[str] = []
    if not sitemap_xml:
        return urls

    try:
        root = ET.fromstring(sitemap_xml)
        for elem in root.iter():
            if elem.tag.endswith(("loc", "url")):
                if elem.text and elem.text.startswith("http"):
                    urls.append(elem.text.strip())
    except ET.ParseError:
        pass

    return urls


def extract_canonical_link(raw_html: str) -> Optional[str]:
    """Extracts <link rel="canonical"> from HTML header."""
    if not raw_html:
        return None
    parser = HTMLParser(raw_html)
    node = parser.css_first("link[rel='canonical']")
    if node and "href" in node.attributes:
        return node.attributes["href"]
    return None
