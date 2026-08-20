"""Zotero and CSL-JSON / RIS Exporter Plugin for DeepSearch Research Archives.

Exports bibliography items, metadata, abstracts, and provenance ready for direct import
into Zotero and reference managers.
"""

import os
import json
import time
from typing import List, Dict, Any
from urllib.parse import urlparse

from scraper.extraction.engine import ExtractionResult


class ZoteroLibraryExporter:
    """Exports research citations and sources into Zotero-compatible CSL-JSON and RIS files."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_csl_json(
        self,
        extractions: List[ExtractionResult],
        query: str = "",
        filename: str = "zotero_csl_data.json",
    ) -> str:
        """Generate CSL-JSON (Citation Style Language JSON) format for Zotero import."""
        csl_items: List[Dict[str, Any]] = []
        now_parts = time.gmtime()

        for idx, ext in enumerate(extractions, 1):
            domain = urlparse(ext.url).hostname or "webpage"
            title = getattr(ext, "title", None) or f"Document {idx} ({domain})"
            abstract = (ext.clean_markdown or ext.fit_markdown or "")[:500]

            item = {
                "id": f"deepsearch_ref_{idx:03d}",
                "type": "webpage",
                "title": title,
                "URL": ext.url,
                "container-title": domain,
                "abstract": abstract,
                "accessed": {
                    "date-parts": [
                        [now_parts.tm_year, now_parts.tm_mon, now_parts.tm_mday]
                    ]
                },
                "keyword": f"deepsearch, {query}".strip(", "),
                "language": "en",
            }
            csl_items.append(item)

        out_path = os.path.join(self.output_dir, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(csl_items, f, indent=2, ensure_ascii=False)

        return out_path

    def export_ris(
        self,
        extractions: List[ExtractionResult],
        query: str = "",
        filename: str = "zotero_library.ris",
    ) -> str:
        """Generate RIS (Research Information Systems) format for Zotero, EndNote, Mendeley."""
        ris_lines: List[str] = []
        now_date_str = time.strftime("%Y/%m/%d", time.gmtime())

        for idx, ext in enumerate(extractions, 1):
            domain = urlparse(ext.url).hostname or "web"
            title = ext.title or f"Document {idx}"
            abstract = (ext.clean_markdown or ext.fit_markdown or "")[:600].replace(
                "\n", " "
            )

            ris_lines.extend(
                [
                    "TY  - ELEC",
                    f"ID  - deepsearch_{idx:03d}",
                    f"TI  - {title}",
                    f"UR  - {ext.url}",
                    f"PB  - {domain}",
                    f"AB  - {abstract}",
                    f"Y2  - {now_date_str}",
                    "KW  - deepsearch",
                    f"KW  - {query}",
                    "ER  - ",
                    "",
                ]
            )

        out_path = os.path.join(self.output_dir, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ris_lines))

        return out_path

    def export_all(
        self, extractions: List[ExtractionResult], query: str = ""
    ) -> Dict[str, str]:
        """Export both CSL-JSON and RIS files."""
        csl_path = self.export_csl_json(extractions, query)
        ris_path = self.export_ris(extractions, query)
        return {"csl_json": csl_path, "ris": ris_path}
