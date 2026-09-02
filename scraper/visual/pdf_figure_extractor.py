"""PDF Figure & Scientific Diagram Extractor.

Extracts embedded raster/vector figures, diagrams, and illustrations directly
from scientific PDF papers to enrich multi-modal RAG context when web assets
are sparse or low-resolution.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIN_FIGURE_SIZE_BYTES = 8192  # Ignore icons/logos < 8KB


class PDFFigureExtractor:
    """Extracts scientific diagrams, figures, and charts from PDF document pages."""

    def extract_figures_from_pdf(
        self,
        pdf_path: str,
        output_media_dir: str,
        doc_id: str,
        max_figures: int = 5,
    ) -> list[dict[str, Any]]:
        """Extracts up to max_figures meaningful figures from a PDF file."""
        if not os.path.exists(pdf_path):
            return []

        extracted_media: list[dict[str, Any]] = []
        out_dir = Path(output_media_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            from pypdf import PdfReader

            reader = PdfReader(pdf_path, strict=False)
            figure_counter = 0

            for page_idx, page in enumerate(reader.pages, start=1):
                if figure_counter >= max_figures:
                    break

                for img_idx, img_obj in enumerate(page.images, start=1):
                    if figure_counter >= max_figures:
                        break

                    try:
                        raw_bytes = img_obj.data
                        img_name = getattr(img_obj, "name", f"img_{img_idx}.png")

                        if len(raw_bytes) < MIN_FIGURE_SIZE_BYTES:
                            continue

                        sha256 = hashlib.sha256(raw_bytes).hexdigest()
                        ext = os.path.splitext(img_name)[1].lower() or ".png"
                        if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
                            ext = ".png"

                        file_name = (
                            f"fig_{doc_id}_p{page_idx}_{img_idx}_{sha256[:8]}{ext}"
                        )
                        target_file_path = out_dir / file_name

                        with open(target_file_path, "wb") as f:
                            f.write(raw_bytes)

                        caption = f"Figure from {doc_id}, Page {page_idx}"
                        extracted_media.append(
                            {
                                "id": f"pdf_fig_{doc_id}_{page_idx}_{img_idx}",
                                "filename": file_name,
                                "file_path": str(target_file_path),
                                "caption": caption,
                                "type": "image",
                                "source_doc_id": doc_id,
                                "page_number": page_idx,
                                "size_bytes": len(raw_bytes),
                                "sha256": sha256,
                                "relevance_score": 0.85,
                            }
                        )
                        figure_counter += 1
                    except Exception as img_err:
                        logger.debug(
                            "Error extracting image from page %d: %s", page_idx, img_err
                        )
                        continue

            return extracted_media
        except Exception as exc:
            logger.warning("Failed extracting figures from PDF %s: %s", pdf_path, exc)
            return []

    async def async_extract_figures_from_pdf(
        self,
        pdf_path: str,
        output_media_dir: str,
        doc_id: str,
        max_figures: int = 5,
    ) -> list[dict[str, Any]]:
        """Non-blocking asynchronous thread execution for PDF figure extraction."""
        import asyncio

        return await asyncio.to_thread(
            self.extract_figures_from_pdf,
            pdf_path=pdf_path,
            output_media_dir=output_media_dir,
            doc_id=doc_id,
            max_figures=max_figures,
        )


pdf_figure_extractor = PDFFigureExtractor()
