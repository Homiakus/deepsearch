"""Unit tests for BackendPlanner and DomainTelemetry (DS-RB06, DS-RB07, DS-RB41)."""

import pytest
from scraper.acquisition.capabilities import (
    BackendDescriptor,
    BrowserCapabilities,
    CapabilityLevel,
)
from scraper.acquisition.models import (
    AcquisitionRequest,
    AcquisitionResult,
    QualityReport,
)
from scraper.acquisition.planner import BackendPlanner, DomainTelemetry


@pytest.fixture
def sample_descriptors():
    http_desc = BackendDescriptor(
        name="http-standard",
        version="1.0.0",
        engine_family="http",
        capabilities=BrowserCapabilities.create_minimal(),
        base_cost=1.0,
        memory_class="low",
        concurrency_class="high",
    )
    servo_desc = BackendDescriptor(
        name="servo-offscreen",
        version="1.0.0",
        engine_family="servo",
        capabilities=BrowserCapabilities(
            html=CapabilityLevel.SUPPORTED,
            javascript=CapabilityLevel.SUPPORTED,
            dom_mutation=CapabilityLevel.SUPPORTED,
            css_layout=CapabilityLevel.SUPPORTED,
        ),
        base_cost=4.0,
        memory_class="medium",
        concurrency_class="medium",
    )
    chromium_desc = BackendDescriptor(
        name="chromium-playwright",
        version="1.0.0",
        engine_family="chromium",
        capabilities=BrowserCapabilities.create_full_browser(),
        base_cost=10.0,
        memory_class="high",
        concurrency_class="low",
    )
    return [http_desc, servo_desc, chromium_desc]


def test_planner_selects_minimal_effective_backend(sample_descriptors):
    planner = BackendPlanner()
    req = AcquisitionRequest(
        url="https://example.com/static",
        required_capabilities=BrowserCapabilities.create_minimal(),
    )

    selected = planner.select_backend(req, sample_descriptors)
    assert selected is not None
    assert selected.name == "http-standard"


def test_planner_selects_servo_when_js_required(sample_descriptors):
    planner = BackendPlanner()
    js_caps = BrowserCapabilities(
        html=CapabilityLevel.SUPPORTED,
        javascript=CapabilityLevel.SUPPORTED,
    )
    req = AcquisitionRequest(
        url="https://example.com/spa",
        required_capabilities=js_caps,
    )

    selected = planner.select_backend(req, sample_descriptors)
    assert selected is not None
    # Should pick Servo (cost 4) rather than Chromium (cost 10)
    assert selected.name == "servo-offscreen"


def test_planner_domain_telemetry_penalizes_failing_backend(sample_descriptors):
    telemetry = DomainTelemetry()
    # Record 5 failures on domain for servo
    for _ in range(5):
        telemetry.record(
            "problematic.com",
            "servo-offscreen",
            success=False,
            quality=0.1,
            latency_ms=5000.0,
        )

    planner = BackendPlanner(telemetry=telemetry)
    js_caps = BrowserCapabilities(
        html=CapabilityLevel.SUPPORTED,
        javascript=CapabilityLevel.SUPPORTED,
    )
    req = AcquisitionRequest(
        url="https://problematic.com/page",
        required_capabilities=js_caps,
    )

    selected = planner.select_backend(req, sample_descriptors)
    assert selected is not None
    # Servo's expected cost will be 4.0 / 0.05 = 80.0, higher than Chromium's 10.0 / 0.95 = 10.5
    assert selected.name == "chromium-playwright"


def test_planner_escalation_triggers(sample_descriptors):
    planner = BackendPlanner()
    http_desc = sample_descriptors[0]

    blocked_res = AcquisitionResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        backend="http-standard",
        status_code=403,
        quality=QualityReport(
            score=0.3,
            blocked=True,
            reasons=["Rate limit"],
            suggested_escalation="chromium",
        ),
    )

    should_esc, target = planner.should_escalate(
        blocked_res, http_desc, sample_descriptors
    )
    assert should_esc is True
    assert target is not None
    assert target.engine_family == "chromium"
