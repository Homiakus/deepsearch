"""Unit tests for Obsidian and Zotero Exporter Plugins."""

import os
import json
from scraper.storage.exporters.obsidian import ObsidianVaultExporter
from scraper.storage.exporters.zotero import ZoteroLibraryExporter
from scraper.extraction.engine import ExtractionResult


def test_obsidian_vault_exporter(tmp_path):
    vault_dir = str(tmp_path / "vault")
    exporter = ObsidianVaultExporter(vault_dir)

    extractions = [
        ExtractionResult(
            url="https://arxiv.org/abs/2301.00001",
            title="Quantum Machine Learning Foundations",
            raw_markdown="# Quantum Computing\n\nQuantum algorithms provide speedups.",
            clean_markdown="# Quantum Computing\n\nQuantum algorithms provide speedups.",
            fit_markdown="# Quantum Computing",
            tables=[],
        ),
        ExtractionResult(
            url="https://nature.com/articles/s41586-023",
            title="Superconducting Qubits",
            raw_markdown="# Superconducting Qubits\n\nHigh fidelity gates.",
            clean_markdown="# Superconducting Qubits\n\nHigh fidelity gates.",
            fit_markdown="# Superconducting Qubits",
            tables=[],
        ),
    ]

    claims = [
        {
            "id": "c1",
            "text": "Quantum algorithms achieve exponential speedup in specific problems.",
            "confidence": 0.95,
            "source_title": "Quantum Machine Learning Foundations",
            "source_url": "https://arxiv.org/abs/2301.00001",
            "verified": True,
        }
    ]

    index_path = exporter.export_vault(
        query="quantum algorithms speedup",
        extractions=extractions,
        evidence_claims=claims,
    )

    assert os.path.exists(index_path)
    with open(index_path, "r", encoding="utf-8") as f:
        index_text = f.read()
        assert "Research Index: quantum algorithms speedup" in index_text
        assert (
            "[[Notes/01_quantum-machine-learning-foundations|Quantum Machine Learning Foundations]]"
            in index_text
        )
        assert "[[Evidence/claim_001_" in index_text
        assert "Quantum algorithms achieve exponential speedup" in index_text

    # Verify Note file created
    notes = os.listdir(exporter.notes_dir)
    assert len(notes) == 2


def test_zotero_library_exporter(tmp_path):
    out_dir = str(tmp_path / "zotero_out")
    exporter = ZoteroLibraryExporter(out_dir)

    extractions = [
        ExtractionResult(
            url="https://arxiv.org/abs/2301.00001",
            title="Quantum Machine Learning Foundations",
            raw_markdown="This paper introduces quantum algorithms for ML.",
            clean_markdown="This paper introduces quantum algorithms for ML.",
            fit_markdown="Quantum algorithms",
            tables=[],
        )
    ]

    res = exporter.export_all(extractions, query="quantum ml")
    assert os.path.exists(res["csl_json"])
    assert os.path.exists(res["ris"])

    # Check CSL JSON content
    with open(res["csl_json"], "r", encoding="utf-8") as f:
        csl_data = json.load(f)
        assert len(csl_data) == 1
        assert csl_data[0]["title"] == "Quantum Machine Learning Foundations"
        assert csl_data[0]["URL"] == "https://arxiv.org/abs/2301.00001"
        assert "deepsearch" in csl_data[0]["keyword"]

    # Check RIS content
    with open(res["ris"], "r", encoding="utf-8") as f:
        ris_text = f.read()
        assert "TY  - ELEC" in ris_text
        assert "TI  - Quantum Machine Learning Foundations" in ris_text
        assert "UR  - https://arxiv.org/abs/2301.00001" in ris_text
        assert "ER  - " in ris_text
