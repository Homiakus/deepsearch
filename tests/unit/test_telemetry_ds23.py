"""Unit tests for Unified Observability & Telemetry (§DS-23)."""

import pytest
import concurrent.futures
from httpx import AsyncClient, ASGITransport

from scraper.monitoring.telemetry import telemetry
from scraper.api.app import app as fastapi_app


def test_telemetry_concurrent_increments():
    """Verify thread-safety of TelemetryTracker during concurrent record updates."""
    telemetry.reset()

    num_threads = 10
    increments_per_thread = 50

    def worker():
        for _ in range(increments_per_thread):
            telemetry.record_request(
                strategy="http",
                bytes_downloaded=100,
                useful_text_bytes=50,
                retries=1,
            )
            telemetry.record_provider_outcome(provider="arxiv", outcome="success")
            telemetry.record_skip_reason(reason="duplicate")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for f in futures:
            f.result()

    summary = telemetry.get_summary()
    expected_total = num_threads * increments_per_thread
    assert summary["total_requests"] == expected_total
    assert summary["http_requests"] == expected_total
    assert summary["total_bytes_downloaded"] == expected_total * 100
    assert summary["useful_bytes_extracted"] == expected_total * 50
    assert summary["retries_total"] == expected_total
    assert summary["provider_stats"]["arxiv"]["success"] == expected_total
    assert summary["skip_stats"]["duplicate"] == expected_total


def test_telemetry_run_metrics_and_stage_durations():
    """Verify tracking metrics by run_id."""
    telemetry.reset()
    run_id = "test-run-123"

    telemetry.record_request(
        strategy="browser",
        bytes_downloaded=5000,
        useful_text_bytes=1200,
        run_id=run_id,
    )
    telemetry.record_stage_duration(
        run_id=run_id, stage="discovery", duration_seconds=1.234
    )
    telemetry.record_stage_duration(
        run_id=run_id, stage="acquisition", duration_seconds=3.456
    )

    run_metrics = telemetry.get_run_metrics(run_id)
    assert run_metrics is not None
    assert run_metrics["requests"] == 1
    assert run_metrics["bytes"] == 5000
    assert run_metrics["browser_escalations"] == 1
    assert run_metrics["stages"]["discovery"] == 1.234
    assert run_metrics["stages"]["acquisition"] == 3.456


@pytest.mark.asyncio
async def test_api_metrics_prometheus_and_summary_consistency():
    """Verify /metrics returns Prometheus text and /api/v1/metrics/summary returns JSON."""
    telemetry.reset()
    telemetry.record_request(
        strategy="http", bytes_downloaded=2048, useful_text_bytes=1024
    )

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Prometheus exposition
        resp_prom = await client.get("/metrics")
        assert resp_prom.status_code == 200
        assert "text/plain" in resp_prom.headers["content-type"]
        assert "scraper_requests_total" in resp_prom.text
        assert "scraper_bytes_downloaded_total" in resp_prom.text

        # 2. JSON summary
        resp_summary = await client.get("/api/v1/metrics/summary")
        assert resp_summary.status_code == 200
        data = resp_summary.json()
        assert data["total_requests"] >= 1
        assert data["total_bytes_downloaded"] >= 2048
        assert data["useful_bytes_extracted"] >= 1024
