"""Discovery Engine for Link Extraction (§19)."""

import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Set, Optional
from selectolax.parser import HTMLParser


def extract_links_from_html(raw_html: str, base_url: str) -> List[str]:
    """Extracts all hyper-links (<a href>) from HTML string (§19)."""
    if not raw_html:
        return []

    parser = HTMLParser(raw_html)
    found_urls: Set[str] = set()

    for node in parser.css("a[href]"):
        href = node.attributes.get("href")
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        full_url = urllib.parse.urljoin(base_url, href)
        found_urls.add(full_url)

    return list(found_urls)


def extract_sitemap_urls(sitemap_xml: str) -> List[str]:
    """Parses sitemap.xml or sitemap index to discover target URLs (§19)."""
    urls: List[str] = []
    if not sitemap_xml:
        return urls

    try:
        root = ET.fromstring(sitemap_xml)
        # Handle default XML namespaces
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
