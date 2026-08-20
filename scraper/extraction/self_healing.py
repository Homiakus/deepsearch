"""Self-Healing Selector Fingerprint Engine (§60)."""

from typing import Dict, Optional
from pydantic import BaseModel
from selectolax.parser import HTMLParser, Node


class ElementFingerprint(BaseModel):
    tag: str
    attributes: Dict[str, str]
    text: str
    nearby_text: str
    dom_path: str
    semantic_role: Optional[str] = None


class SelfHealingSelector:
    """Creates element fingerprints and matches nearest equivalent if primary CSS selector breaks (§60)."""

    @staticmethod
    def create_fingerprint(node: Node, dom_path: str = "") -> ElementFingerprint:
        text = node.text().strip()
        tag = node.tag
        attrs = dict(node.attributes)

        # Get parent text as nearby context
        parent = node.parent
        nearby_text = parent.text().strip()[:100] if parent else ""

        return ElementFingerprint(
            tag=tag,
            attributes=attrs,
            text=text[:200],
            nearby_text=nearby_text,
            dom_path=dom_path,
            semantic_role=attrs.get("role"),
        )

    @classmethod
    def match_element(
        cls,
        raw_html: str,
        selector: str,
        fingerprint: Optional[ElementFingerprint] = None,
    ) -> Optional[Node]:
        """Tries primary CSS selector first; if missing, searches for closest fingerprint match (§60)."""
        parser = HTMLParser(raw_html)
        primary_node = parser.css_first(selector)

        if primary_node:
            return primary_node

        if not fingerprint:
            return None

        # Fallback to fingerprint matching
        best_match = None
        best_score = 0.0

        for candidate in parser.css(fingerprint.tag):
            cand_fp = cls.create_fingerprint(candidate)
            score = 0.0

            # Match attribute overlap
            common_attrs = set(fingerprint.attributes.keys()) & set(
                cand_fp.attributes.keys()
            )
            if common_attrs:
                score += 0.4 * (len(common_attrs) / max(1, len(fingerprint.attributes)))

            # Match text similarity
            if fingerprint.text and cand_fp.text and fingerprint.text in cand_fp.text:
                score += 0.4

            # Match nearby context
            if (
                fingerprint.nearby_text
                and cand_fp.nearby_text
                and fingerprint.nearby_text in cand_fp.nearby_text
            ):
                score += 0.2

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = candidate

        return best_match
