"""Archive Exporter Engine for DeepSearch.

Generates dual-format output structured archive:
1. `files/`: Human-readable Markdown/HTML files with explicit origin links for users.
2. `rag/`: LLM-optimized dataset (JSONL chunks, context markdown, vector index metadata) for LLMs.
3. `manifest.json`: Root metadata manifest summarizing search config and inventory.
4. Export to directory or packed `.zip` file.
"""

import os
import json
import zipfile
import shutil
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel, Field

from scraper.acquisition.engine import CapturedArtifact
from scraper.extraction.engine import ExtractionResult
from scraper.normalization.text import recursive_sanitize, sanitize_unicode_string
from scraper.search.chunking import StructureAwareChunker, StructuredChunk


class SearchRunMetadata(BaseModel):
    query: str
    domain: Optional[str] = None
    preferred_sources: List[str] = Field(default_factory=list)
    depth: int = 3
    max_pages: int = 100
    mode: str = "balanced"
    created_at: float = Field(default_factory=time.time)


class RAGChunk(BaseModel):
    chunk_id: str
    source_url: str
    canonical_url: str
    title: str
    domain: str
    text: str
    token_estimate: int
    relevance_score: Optional[float] = None
    heading_path: List[str] = Field(default_factory=list)
    parent_section_id: Optional[str] = None
    ordinal: int = 0
    provenance: Dict[str, Any] = Field(default_factory=dict)


class ArchiveExporter:
    """Exports DeepSearch execution results into user-facing files and LLM RAG formats."""

    def __init__(self, metadata: SearchRunMetadata):
        self.metadata = metadata
        self._chunker = StructureAwareChunker(target_words=250, min_words=25)

    def _chunk_text(
        self,
        text: str,
        doc_id: str = "doc",
        source_url: str = "",
        title: str = "",
        max_words: int = 250,
    ) -> List[StructuredChunk]:
        """Structure-aware chunking for RAG ingestion."""
        if not text:
            return []
        chunker = (
            self._chunker
            if max_words == self._chunker.target_words
            else StructureAwareChunker(target_words=max_words, min_words=25)
        )
        return chunker.chunk_markdown(
            markdown_text=text,
            document_id=doc_id,
            source_url=source_url,
            title=title,
        )

    def build_archive_structure(
        self,
        results: List[Tuple[CapturedArtifact, ExtractionResult]],
        output_dir: str,
        pdf_files: Optional[List[Dict[str, Any]]] = None,
        media_files: Optional[List[Dict[str, Any]]] = None,
        rejections: Optional[List[Dict[str, Any]]] = None,
        quality_report: Optional[Dict[str, Any]] = None,
        media_quality: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Builds the uncompressed folder structure containing `files/`, `pdfs/`, `media/`, `rag/`, and `manifest.json`."""
        out_path = Path(output_dir)
        files_dir = out_path / "files"
        pdfs_dir = out_path / "pdfs"
        media_dir = out_path / "media"
        rag_dir = out_path / "rag"

        files_dir.mkdir(parents=True, exist_ok=True)
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)
        rag_dir.mkdir(parents=True, exist_ok=True)

        manifest_files = []
        all_rag_chunks: List[RAGChunk] = []
        rag_context_lines = [
            "# DeepSearch RAG Context Corpus",
            f"> Search Query: {self.metadata.query}",
            f"> Subject Domain: {self.metadata.domain or 'Global'}",
            f"> Sources: {', '.join(self.metadata.preferred_sources) if self.metadata.preferred_sources else 'All'}",
            f"> Total Documents: {len(results)}",
            "\n---\n",
        ]

        structured_records = []

        for idx, (artifact, extraction) in enumerate(results, start=1):
            domain_name = (
                artifact.url.split("/")[2] if "//" in artifact.url else "domain"
            )
            safe_title = f"doc_{idx:03d}_{domain_name.replace('.', '_')}"

            # --- 1. User File Generation (`files/`) ---
            user_md_filename = f"{safe_title}.md"
            user_md_path = files_dir / user_md_filename

            user_content = (
                f"# Document {idx}: {artifact.url}\n\n"
                f"> **Source Link**: [{artifact.url}]({artifact.url})\n"
                f"> **Canonical URL**: {artifact.canonical_url}\n"
                f"> **Acquisition Strategy**: {artifact.strategy_used}\n"
                f"> **Quality Score**: {artifact.page_intelligence.content_quality:.2f}\n"
                f"> **Source Type**: {extraction.source_type}\n"
                f"> **Authority Score**: {extraction.authority_score:.2f}\n"
                f"> **Relevance Score**: {extraction.relevance_score if extraction.relevance_score is not None else 'n/a'}\n"
                f"> **HTTP Status**: {artifact.status_code}\n\n"
                f"---\n\n"
                f"## Content Summary & Text\n\n"
                f"{extraction.abstract_markdown or extraction.clean_markdown}\n"
            )

            if extraction.full_text_markdown:
                user_content += (
                    f"\n\n## Full-text Evidence\n\n{extraction.full_text_markdown}\n"
                )

            if extraction.tables:
                user_content += "\n\n## Extracted Tables\n\n"
                for t_idx, table in enumerate(extraction.tables, start=1):
                    user_content += f"### Table {t_idx}\n{table.markdown}\n\n"

            user_md_path.write_text(
                sanitize_unicode_string(user_content), encoding="utf-8"
            )
            manifest_files.append(
                {
                    "id": safe_title,
                    "file_path": f"files/{user_md_filename}",
                    "url": artifact.url,
                    "title": safe_title,
                    "strategy": artifact.strategy_used,
                }
            )

            # --- 2. LLM RAG Dataset Generation (`rag/`) ---
            text_for_rag = (
                extraction.full_text_markdown
                or extraction.fit_markdown
                or extraction.clean_markdown
            )
            structured_chunks = self._chunk_text(
                text=text_for_rag,
                doc_id=safe_title,
                source_url=artifact.url,
                title=safe_title,
                max_words=250,
            )

            for c_idx, s_chunk in enumerate(structured_chunks):
                chunk_id = f"{safe_title}_c{c_idx + 1:03d}"
                token_est = s_chunk.token_estimate or int(
                    len(s_chunk.text.split()) * 1.3
                )
                rag_chunk = RAGChunk(
                    chunk_id=chunk_id,
                    source_url=artifact.url,
                    canonical_url=artifact.canonical_url,
                    title=safe_title,
                    domain=domain_name,
                    text=s_chunk.text,
                    token_estimate=token_est,
                    relevance_score=extraction.relevance_score,
                    heading_path=s_chunk.heading_path,
                    parent_section_id=s_chunk.parent_section_id,
                    ordinal=s_chunk.ordinal,
                    provenance={
                        "strategy": artifact.strategy_used,
                        "status_code": artifact.status_code,
                        "static_score": artifact.page_intelligence.static_score,
                        "source_type": extraction.source_type,
                        "authority_score": extraction.authority_score,
                        "published_at": extraction.published_at,
                        "document_type": extraction.document_type,
                        "full_text": bool(extraction.full_text_markdown),
                        "heading_path": s_chunk.heading_path,
                    },
                )
                all_rag_chunks.append(rag_chunk)

            # RAG Context markdown block
            rag_context_lines.append(
                f"## Document [{idx}]: {artifact.url}\n"
                f"**Source URL**: [{artifact.url}]({artifact.url})\n\n"
                f"{text_for_rag}\n\n"
                f"---\n"
            )

            # Structured records
            if extraction.extracted_records:
                structured_records.append(
                    {
                        "url": artifact.url,
                        "records": {
                            k: v.model_dump()
                            for k, v in extraction.extracted_records.items()
                        },
                    }
                )

        # --- 3. Process PDF Files (`pdfs/`) ---
        total_pdf_files = 0
        if pdf_files:
            for pdf_info in pdf_files:
                src_file = pdf_info.get("file_path")
                filename = pdf_info.get("filename")
                if src_file and os.path.exists(src_file) and filename:
                    dst_path = pdfs_dir / filename
                    shutil.copy2(src_file, dst_path)
                    manifest_files.append(
                        {
                            "id": filename,
                            "file_path": f"pdfs/{filename}",
                            "url": pdf_info.get("url", ""),
                            "title": filename,
                            "type": "pdf",
                            "size_bytes": pdf_info.get("size_bytes", 0),
                            "sha256": pdf_info.get("sha256", ""),
                            "license": pdf_info.get("license", "UNKNOWN_LICENSE"),
                            "author": pdf_info.get("author", "UNKNOWN_AUTHOR"),
                            "source_domain": pdf_info.get("source_domain", ""),
                        }
                    )
                    total_pdf_files += 1

        # --- 4. Process Topic Media Files (`media/`) ---
        total_media_files = 0
        if media_files:
            rag_context_lines.append("\n## Topic Visual Media Gallery\n")
            for m_idx, media_info in enumerate(media_files, start=1):
                src_file = media_info.get("file_path")
                filename = media_info.get("filename")
                if src_file and os.path.exists(src_file) and filename:
                    dst_path = media_dir / filename
                    shutil.copy2(src_file, dst_path)
                    caption = media_info.get("caption") or f"Topic Media {m_idx}"
                    score = media_info.get("relevance_score", 1.0)
                    lic = media_info.get("license", "UNKNOWN_LICENSE")
                    auth = media_info.get("author", "UNKNOWN_AUTHOR")
                    manifest_files.append(
                        {
                            "id": f"media_{m_idx:03d}_{filename}",
                            "file_path": f"media/{filename}",
                            "url": media_info.get("url", ""),
                            "title": caption,
                            "type": "image",
                            "relevance_score": score,
                            "size_bytes": media_info.get("size_bytes", 0),
                            "sha256": media_info.get("sha256", ""),
                            "mime_type": media_info.get("content_type", ""),
                            "width": media_info.get("width"),
                            "height": media_info.get("height"),
                            "license": lic,
                            "author": auth,
                            "source_domain": media_info.get("source_domain", ""),
                        }
                    )
                    total_media_files += 1
                    rag_context_lines.append(
                        f"- ![Image {m_idx}: {caption}](media/{filename})  \n"
                        f"  *Source*: [{media_info.get('url')}]({media_info.get('url')}) | *License*: {lic} | *Author*: {auth} | *Relevance Score*: {score:.2f}\n"
                    )

        # Save `rag/rag_chunks.jsonl`
        jsonl_path = rag_dir / "rag_chunks.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for chunk in all_rag_chunks:
                clean_chunk = recursive_sanitize(chunk.model_dump())
                f.write(json.dumps(clean_chunk, ensure_ascii=False) + "\n")

        # Save `rag/dataset.jsonl` (HuggingFace / LlamaIndex standardized format)
        dataset_jsonl_path = rag_dir / "dataset.jsonl"
        with open(dataset_jsonl_path, "w", encoding="utf-8") as f:
            for chunk in all_rag_chunks:
                record = {
                    "id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": {
                        "query": self.metadata.query,
                        "domain": self.metadata.domain or "Global",
                        "source_url": chunk.source_url,
                        "canonical_url": chunk.canonical_url,
                        "title": chunk.title,
                        "token_estimate": chunk.token_estimate,
                        "relevance_score": chunk.relevance_score,
                        **chunk.provenance,
                    },
                }
                record = recursive_sanitize(record)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Save `rag/rag_context.md`
        context_path = rag_dir / "rag_context.md"
        context_path.write_text(
            sanitize_unicode_string("\n".join(rag_context_lines)), encoding="utf-8"
        )

        # Save `rag/rag_dataset.json`
        dataset_path = rag_dir / "rag_dataset.json"
        dataset_path.write_text(
            json.dumps(
                recursive_sanitize(structured_records), indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )

        # Save `rag/vector_index.json`
        vector_index_path = rag_dir / "vector_index.json"
        vector_meta = {
            "total_vectors": len(all_rag_chunks),
            "dimensions": 1536,
            "metric": "cosine",
            "vectors": [
                {
                    "id": c.chunk_id,
                    "payload": {
                        "source_url": c.source_url,
                        "title": c.title,
                        "text": c.text[:200],
                    },
                }
                for c in all_rag_chunks
            ],
        }
        vector_index_path.write_text(
            json.dumps(recursive_sanitize(vector_meta), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # --- 5. Root Manifest (`manifest.json`) ---
        rejection_records = rejections or []
        if rejection_records:
            rejection_path = out_path / "rejections.jsonl"
            with rejection_path.open("w", encoding="utf-8") as f:
                for record in rejection_records:
                    clean_record = recursive_sanitize(record)
                    f.write(json.dumps(clean_record, ensure_ascii=False) + "\n")

        if quality_report is not None:
            (out_path / "source_quality_report.json").write_text(
                json.dumps(
                    recursive_sanitize(quality_report), indent=2, ensure_ascii=False
                ),
                encoding="utf-8",
            )

        manifest_data = {
            "deepsearch_version": "1.0",
            "metadata": self.metadata.model_dump(),
            "summary": {
                "total_documents": len(results),
                "total_rag_chunks": len(all_rag_chunks),
                "total_user_files": len(manifest_files),
                "total_pdfs": total_pdf_files,
                "total_media_files": total_media_files,
                "total_rejections": len(rejection_records),
            },
            "inventory": manifest_files,
            "rejections": rejection_records,
            "quality_gate": quality_report or {},
            "media_quality": media_quality or {},
        }
        manifest_path = out_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(recursive_sanitize(manifest_data), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return str(out_path)

    def pack_zip_archive(self, input_dir: str, output_zip_path: str) -> str:
        """Packs the directory into a standalone `.zip` archive."""
        zip_path = Path(output_zip_path)
        if zip_path.suffix != ".zip":
            zip_path = zip_path.with_suffix(".zip")

        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            root_path = Path(input_dir)
            for file in root_path.rglob("*"):
                if file.is_file():
                    arcname = file.relative_to(root_path)
                    zipf.write(file, arcname)

        return str(zip_path)

    def export_obsidian_vault(
        self,
        results: List[Tuple[CapturedArtifact, ExtractionResult]],
        output_dir: str,
        evidence_claims: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Export research results directly to an Obsidian Vault directory."""
        from scraper.storage.exporters.obsidian import ObsidianVaultExporter

        extractions = [ext for _, ext in results]
        exporter = ObsidianVaultExporter(output_dir)
        return exporter.export_vault(
            query=self.metadata.query,
            extractions=extractions,
            evidence_claims=evidence_claims,
            metadata=self.metadata.model_dump(),
        )

    def export_zotero_library(
        self,
        results: List[Tuple[CapturedArtifact, ExtractionResult]],
        output_dir: str,
    ) -> Dict[str, str]:
        """Export research results to Zotero CSL-JSON and RIS files."""
        from scraper.storage.exporters.zotero import ZoteroLibraryExporter

        extractions = [ext for _, ext in results]
        exporter = ZoteroLibraryExporter(output_dir)
        return exporter.export_all(extractions, query=self.metadata.query)
