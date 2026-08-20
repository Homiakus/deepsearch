from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.extraction.engine import ExtractionResult
from scraper.search.quality_report import SourceQualityEvaluator
from benchmarks.search.metrics import evaluate_quality_gate_report


def _source(url: str, title: str, source_type: str = "PRIMARY_RESEARCH"):
    artifact = CapturedArtifact(
        url=url,
        canonical_url=url,
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"ok",
        text_content="evidence",
        page_intelligence=PageIntelligence(),
    )
    extraction = ExtractionResult(
        url=url,
        raw_markdown="evidence",
        clean_markdown="evidence " * 100,
        fit_markdown="evidence " * 100,
        source_id=url,
        source_title=title,
        provider="test",
        source_type=source_type,
        authority_score=0.9,
        relevance_score=0.9,
    )
    return artifact, extraction


def test_quality_report_marks_single_domain_corpus_insufficient():
    evaluator = SourceQualityEvaluator()
    report = evaluator.evaluate(
        [
            _source("https://arxiv.org/abs/1.1", "Ragas evaluation benchmark"),
            _source("https://arxiv.org/abs/2.2", "Faithfulness evaluation"),
        ]
    )
    assert report["passed"] is False
    assert "MIN_INDEPENDENT_DOMAINS" in report["missing_requirements"]
    assert report["summary"]["direct_evidence_count"] == 2


def test_quality_report_passes_diverse_evidence_corpus():
    report = SourceQualityEvaluator().evaluate(
        [
            _source("https://arxiv.org/abs/1.1", "Ragas evaluation benchmark"),
            _source("https://link.springer.com/article/2", "Faithfulness evaluation"),
            _source("https://europepmc.org/article/PMC/3", "RAG clinical evaluation"),
        ]
    )
    assert report["passed"] is True
    assert report["summary"]["independent_domain_count"] == 3


def test_quality_gate_rejects_run_with_block_pages_and_low_precision():
    report = {
        "status": "INSUFFICIENT_EVIDENCE",
        "summary": {
            "accepted_source_count": 4,
            "rejected_candidate_count": 2,
            "direct_evidence_rate": 0.5,
        },
        "sources": [],
        "rejections": [
            {"document_type": "BLOCK_PAGE", "reason_code": "BLOCK_OR_ACCESS_DENIED"}
        ],
    }
    result = evaluate_quality_gate_report(report)
    assert result["passed"] is False
    assert result["checks"]["direct_evidence_rate"] is False
    assert result["checks"]["block_page_rate"] is False
