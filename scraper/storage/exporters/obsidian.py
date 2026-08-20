"""Obsidian Vault Exporter Plugin for DeepSearch Research Archives.

Exports structured research documents into an interconnected Obsidian markdown vault
with YAML frontmatter, [[Wikilinks]], backlink references, and tags.
"""

import os
import re
import json
import time
from typing import List, Dict, Any, Optional

from scraper.extraction.engine import ExtractionResult


def slugify(text: str) -> str:
    """Convert text to safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[-\s]+", "-", text)[:80] or "note"


class ObsidianVaultExporter:
    """Exports research artifacts into an Obsidian Knowledge Vault."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.notes_dir = os.path.join(self.output_dir, "Notes")
        self.evidence_dir = os.path.join(self.output_dir, "Evidence")
        self.media_dir = os.path.join(self.output_dir, "Media")
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        os.makedirs(self.notes_dir, exist_ok=True)
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.media_dir, exist_ok=True)

    def export_vault(
        self,
        query: str,
        extractions: List[ExtractionResult],
        evidence_claims: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate and export the complete Obsidian vault. Returns path to vault index."""
        metadata = metadata or {}
        created_at_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        created_date_str = time.strftime("%Y-%m-%d", time.gmtime())

        # 1. Export Notes
        note_links = []
        for idx, ext in enumerate(extractions, 1):
            title = getattr(ext, "title", None) or f"Source {idx}"
            note_slug = f"{idx:02d}_{slugify(title)}"
            note_filename = f"{note_slug}.md"
            note_path = os.path.join(self.notes_dir, note_filename)

            # YAML Frontmatter
            frontmatter = [
                "---",
                f"title: {json.dumps(title)}",
                f"source_url: {json.dumps(ext.url)}",
                f"domain: {json.dumps(ext.url.split('/')[2] if '://' in ext.url else '')}",
                f"date_captured: {created_date_str}",
                "tags:",
                "  - deepsearch",
                "  - research",
                f"  - query/{slugify(query)[:30]}",
                "---",
                "",
            ]

            body = [
                f"# {title}",
                "",
                f"> **Source URL**: [{ext.url}]({ext.url})  ",
                f"> **Domain**: `{ext.url.split('/')[2] if '://' in ext.url else ''}`  ",
                f"> **Captured**: {created_at_str}",
                "",
                "## Summary",
                "",
                ext.clean_markdown or ext.fit_markdown or "No content extracted.",
                "",
                "## References & Wikilinks",
                f"- [[00_Index|Back to Research Index: {query}]]",
            ]

            with open(note_path, "w", encoding="utf-8") as f:
                f.write("\n".join(frontmatter + body))

            note_links.append((title, note_slug, ext.url))

        # 2. Export Evidence Claims
        claim_links = []
        if evidence_claims:
            for c_idx, claim in enumerate(evidence_claims, 1):
                claim_text = claim.get("text", f"Claim {c_idx}")
                claim_slug = f"claim_{c_idx:03d}_{slugify(claim_text)[:40]}"
                claim_path = os.path.join(self.evidence_dir, f"{claim_slug}.md")

                c_content = [
                    "---",
                    f"claim_id: {json.dumps(claim.get('id', str(c_idx)))}",
                    f"confidence: {claim.get('confidence', 1.0)}",
                    "tags:",
                    "  - deepsearch/evidence",
                    "---",
                    "",
                    f"# Claim: {claim_text[:100]}",
                    "",
                    f"**Full Claim:** {claim_text}",
                    "",
                    f"**Confidence Score:** `{claim.get('confidence', 'N/A')}`  ",
                    f"**Source Origin:** [[Notes/{slugify(claim.get('source_title', ''))}|{claim.get('source_title', 'Source')}]]",
                    "",
                    "## Provenance",
                    f"- URL: {claim.get('source_url', 'N/A')}",
                    f"- Verified: `{claim.get('verified', True)}`",
                ]
                with open(claim_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(c_content))
                claim_links.append((claim_text, claim_slug))

        # 3. Export 00_Index.md
        index_path = os.path.join(self.output_dir, "00_Index.md")
        index_content = [
            "---",
            f'title: "Research Index: {query}"',
            f"date: {created_date_str}",
            "tags:",
            "  - deepsearch/index",
            "---",
            "",
            f"# Research Index: {query}",
            "",
            f"**Execution Timestamp**: `{created_at_str}`  ",
            f"**Total Sources Extracted**: `{len(extractions)}`  ",
            f"**Total Evidence Claims**: `{len(evidence_claims or [])}`",
            "",
            "## Collected Notes",
            "",
        ]

        for title, slug, url in note_links:
            index_content.append(f"- [[Notes/{slug}|{title}]] — *[{url}]({url})*")

        if claim_links:
            index_content.extend(
                [
                    "",
                    "## Evidence & Claims Graph",
                    "",
                ]
            )
            for text, slug in claim_links:
                index_content.append(f"- [[Evidence/{slug}|{text[:120]}...]]")

        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(index_content))

        return index_path
