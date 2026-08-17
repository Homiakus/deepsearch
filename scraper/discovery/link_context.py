"""Link Context Extractor (DS-SI13).

Extracts rich semantic context (ancestor headings, surrounding paragraphs,
semantic section) around discovered links for pre-ranking.
"""

from typing import List, Optional
from selectolax.parser import HTMLParser, Node
from scraper.discovery.links import DiscoveredLink


class LinkContextExtractor:
    """Extracts semantic context and parent headings for HTML links."""

    @staticmethod
    def extract_link_contexts(raw_html: str, base_url: str) -> List[DiscoveredLink]:
        if not raw_html:
            return []

        parser = HTMLParser(raw_html)
        results: List[DiscoveredLink] = []

        for idx, a_node in enumerate(parser.css("a[href]"), start=1):
            href = a_node.attributes.get("href", "")
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            import urllib.parse
            full_url = urllib.parse.urljoin(base_url, href)

            # Find nearest ancestor heading
            heading_text = None
            cur = a_node
            while cur:
                prev_sibling = cur.prev
                while prev_sibling:
                    if prev_sibling.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                        heading_text = prev_sibling.text(strip=True)
                        break
                    prev_sibling = prev_sibling.prev
                if heading_text:
                    break
                cur = cur.parent

            # Extract paragraph text
            p_text = ""
            p_ancestor = a_node
            while p_ancestor:
                if p_ancestor.tag in ("p", "li", "td", "article", "section"):
                    p_text = p_ancestor.text(strip=True)[:250]
                    break
                p_ancestor = p_ancestor.parent

            results.append(
                DiscoveredLink(
                    url=full_url,
                    canonical_url=full_url,
                    anchor_text=a_node.text(strip=True) or "",
                    surrounding_text=p_text,
                    dom_position=idx,
                    section_heading=heading_text,
                    rel=a_node.attributes.get("rel"),
                )
            )

        return results
