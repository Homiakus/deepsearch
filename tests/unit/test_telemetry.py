"""Unit tests for Telemetry (§68), Browser Escalation Ratio (§69), and Useful Data Ratio (§70)."""

from scraper.monitoring.telemetry import TelemetryTracker


def test_telemetry_ratios():
    tracker = TelemetryTracker()

    # Record 3 HTTP requests (1000 bytes each, 500 useful bytes)
    tracker.record_request(strategy="L1_HTTP", bytes_downloaded=1000, useful_text_bytes=500)
    tracker.record_request(strategy="L1_HTTP", bytes_downloaded=1000, useful_text_bytes=500)
    tracker.record_request(strategy="L1_HTTP", bytes_downloaded=1000, useful_text_bytes=500)

    # Record 1 Browser escalation (2000 bytes downloaded)
    tracker.record_request(strategy="L3_BROWSER", bytes_downloaded=2000, useful_text_bytes=500)

    # 1 out of 4 total requests was browser => 25% escalation ratio (§69)
    assert tracker.get_browser_escalation_ratio() == 25.0

    # Useful bytes (2000) / total bytes (5000) = 0.40 ratio (§70)
    assert tracker.get_useful_data_ratio() == 0.40
