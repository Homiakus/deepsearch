"""Contract tests for Acquisition Data Models and Capabilities (DS-RB02, DS-RB03, DS-RB42)."""

from scraper.acquisition.capabilities import (
    BrowserCapabilities,
    CapabilityLevel,
)
from scraper.acquisition.models import (
    AcquisitionRequest,
    AcquisitionResult,
    ArtifactReference,
    CostReport,
    QualityReport,
)


def test_capability_level_resolution():
    assert CapabilityLevel.from_value("supported") == CapabilityLevel.SUPPORTED
    assert CapabilityLevel.from_value(True) == CapabilityLevel.SUPPORTED
    assert CapabilityLevel.from_value("partial") == CapabilityLevel.PARTIAL
    assert CapabilityLevel.from_value("unsupported") == CapabilityLevel.UNSUPPORTED
    assert CapabilityLevel.from_value(False) == CapabilityLevel.UNSUPPORTED

    # Satisfaction checks
    assert CapabilityLevel.SUPPORTED.is_satisfied_by(CapabilityLevel.SUPPORTED)
    assert CapabilityLevel.SUPPORTED.is_satisfied_by(CapabilityLevel.PARTIAL)
    assert CapabilityLevel.SUPPORTED.is_satisfied_by(CapabilityLevel.UNSUPPORTED)
    assert CapabilityLevel.PARTIAL.is_satisfied_by(CapabilityLevel.PARTIAL)
    assert not CapabilityLevel.PARTIAL.is_satisfied_by(CapabilityLevel.SUPPORTED)
    assert not CapabilityLevel.UNSUPPORTED.is_satisfied_by(CapabilityLevel.SUPPORTED)


def test_browser_capabilities_satisfaction():
    minimal = BrowserCapabilities.create_minimal()
    full = BrowserCapabilities.create_full_browser()

    assert full.satisfies(minimal)
    assert not minimal.satisfies(full)

    js_req = BrowserCapabilities(
        html=CapabilityLevel.SUPPORTED, javascript=CapabilityLevel.SUPPORTED
    )
    assert full.satisfies(js_req)
    assert not minimal.satisfies(js_req)


def test_acquisition_request_serialization():
    req = AcquisitionRequest(
        url="https://example.com/target",
        canonical_url="https://example.com/target",
        mode="balanced",
        budget_max_ms=10000.0,
        trace_context={"run_id": "r-123"},
    )
    dumped = req.model_dump()
    assert dumped["url"] == "https://example.com/target"
    assert dumped["mode"] == "balanced"
    assert dumped["budget_max_ms"] == 10000.0
    assert dumped["trace_context"]["run_id"] == "r-123"

    restored = AcquisitionRequest.model_validate(dumped)
    assert restored.url == req.url
    assert restored.trace_context == req.trace_context


def test_acquisition_result_serialization():
    result = AcquisitionResult(
        requested_url="https://example.com/start",
        final_url="https://example.com/final",
        backend="servo-offscreen",
        backend_version="1.0.0",
        status_code=200,
        headers={"content-type": "text/html"},
        content_type="text/html",
        text_preview="Extracted page text",
        artifact_refs=[
            ArtifactReference(
                content_hash="112233445566",
                uri="cas://11/112233445566.html",
                media_type="text/html",
                size_bytes=4096,
            )
        ],
        quality=QualityReport(score=0.9, completeness=0.95, blocked=False),
        cost=CostReport(base_cost=4.0, execution_time_ms=120.0),
        elapsed_sec=0.12,
        capabilities_used=["html", "javascript"],
    )

    dumped = result.model_dump()
    assert dumped["backend"] == "servo-offscreen"
    assert dumped["artifact_refs"][0]["content_hash"] == "112233445566"
    assert dumped["quality"]["score"] == 0.9

    restored = AcquisitionResult.model_validate(dumped)
    assert restored.backend == result.backend
    assert restored.artifact_refs[0].uri == "cas://11/112233445566.html"
