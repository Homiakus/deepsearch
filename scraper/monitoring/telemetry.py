"""Telemetry and Metrics (§68, §69 Browser Escalation Ratio, §70 Useful Data Ratio)."""

import time
from typing import Dict, Any
from prometheus_client import Counter, Gauge

# Prometheus Metrics (§68)
REQUESTS_TOTAL = Counter("scraper_requests_total", "Total requests attempted", ["method", "strategy"])
REQUESTS_SUCCESS = Counter("scraper_requests_success", "Total successful requests")
REQUESTS_FAILED = Counter("scraper_requests_failed", "Total failed requests")
BYTES_DOWNLOADED = Counter("scraper_bytes_downloaded_total", "Total network bytes downloaded")
USEFUL_BYTES = Counter("scraper_useful_bytes_total", "Total useful text bytes extracted")

BROWSER_ESCALATIONS = Counter("scraper_browser_escalations_total", "Total browser escalations")
QUEUE_DEPTH_GAUGE = Gauge("scraper_queue_depth", "Current URL queue depth")
BROWSER_ESCALATION_RATIO_GAUGE = Gauge("scraper_browser_escalation_ratio", "Browser Escalation Ratio (§69)")
USEFUL_DATA_RATIO_GAUGE = Gauge("scraper_useful_data_ratio", "Useful Data / Downloaded Byte Ratio (§70)")


class TelemetryTracker:
    """Tracks metrics and computes Browser Escalation Ratio (§69) and Useful Data Ratio (§70)."""

    def __init__(self):
        self.total_requests = 0
        self.http_requests = 0
        self.browser_requests = 0
        self.api_requests = 0
        self.total_bytes = 0
        self.useful_bytes = 0
        self.start_time = time.time()

    def record_request(self, strategy: str, bytes_downloaded: int, useful_text_bytes: int = 0):
        self.total_requests += 1
        self.total_bytes += bytes_downloaded
        self.useful_bytes += useful_text_bytes

        REQUESTS_TOTAL.labels(method="GET", strategy=strategy).inc()
        BYTES_DOWNLOADED.inc(bytes_downloaded)
        USEFUL_BYTES.inc(useful_text_bytes)

        if strategy in ("L3_BROWSER", "L4_SEMANTIC", "L5_VISUAL"):
            self.browser_requests += 1
            BROWSER_ESCALATIONS.inc()
        elif strategy == "L1_HTTP":
            self.http_requests += 1
        elif strategy == "L2_API":
            self.api_requests += 1

        # Update ratios (§69, §70)
        esc_ratio = self.get_browser_escalation_ratio()
        data_ratio = self.get_useful_data_ratio()

        BROWSER_ESCALATION_RATIO_GAUGE.set(esc_ratio)
        USEFUL_DATA_RATIO_GAUGE.set(data_ratio)

    def get_browser_escalation_ratio(self) -> float:
        """Browser Escalation Ratio (§69). Target < 25% on standard static corpora."""
        if self.total_requests == 0:
            return 0.0
        return round((self.browser_requests / self.total_requests) * 100, 2)

    def get_useful_data_ratio(self) -> float:
        """Useful Data / Downloaded Byte Ratio (§70)."""
        if self.total_bytes == 0:
            return 0.0
        return round(self.useful_bytes / self.total_bytes, 4)

    def get_summary(self) -> Dict[str, Any]:
        elapsed = max(0.1, time.time() - self.start_time)
        return {
            "total_requests": self.total_requests,
            "http_requests": self.http_requests,
            "browser_requests": self.browser_requests,
            "api_requests": self.api_requests,
            "browser_escalation_ratio_percent": self.get_browser_escalation_ratio(),
            "useful_data_ratio": self.get_useful_data_ratio(),
            "pages_per_second": round(self.total_requests / elapsed, 2),
            "total_bytes_downloaded": self.total_bytes
        }


telemetry = TelemetryTracker()
