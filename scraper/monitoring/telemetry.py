"""Telemetry and Metrics (§68, §69 Browser Escalation Ratio, §70 Useful Data Ratio, DS-23).

Provides thread/task-safe telemetry tracking with unified Prometheus metrics
and structured JSON execution summary, run contexts, provider outcomes, retries,
stage durations, and skip reasons.
"""

import time
import threading
from typing import Dict, Any, Optional
from prometheus_client import Counter, Gauge, generate_latest

# --- Unified Prometheus Metrics (§68, DS-23) ---
REQUESTS_TOTAL = Counter(
    "scraper_requests_total",
    "Total requests attempted",
    ["method", "strategy", "status"],
)
BYTES_DOWNLOADED = Counter(
    "scraper_bytes_downloaded_total",
    "Total network bytes downloaded",
)
USEFUL_BYTES = Counter(
    "scraper_useful_bytes_total",
    "Total useful text bytes extracted",
)
BROWSER_ESCALATIONS = Counter(
    "scraper_browser_escalations_total",
    "Total browser escalations",
)
RETRIES_TOTAL = Counter(
    "scraper_retries_total",
    "Total retry attempts across acquisition",
    ["strategy"],
)
PROVIDER_OUTCOMES = Counter(
    "scraper_provider_outcomes_total",
    "Outcomes by discovery / acquisition provider",
    ["provider", "outcome"],
)
SKIP_REASONS = Counter(
    "scraper_skip_reasons_total",
    "Reasons pages or queries were skipped",
    ["reason"],
)

BROWSER_ESCALATION_RATIO_GAUGE = Gauge(
    "scraper_browser_escalation_ratio",
    "Browser Escalation Ratio (§69)",
)
USEFUL_DATA_RATIO_GAUGE = Gauge(
    "scraper_useful_data_ratio",
    "Useful Data / Downloaded Byte Ratio (§70)",
)


class TelemetryTracker:
    """Thread-safe unified telemetry and metrics tracker (DS-23)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self.total_requests = 0
        self.http_requests = 0
        self.browser_requests = 0
        self.api_requests = 0
        self.total_bytes = 0
        self.useful_bytes = 0
        self.retries_count = 0
        self.provider_stats: Dict[str, Dict[str, int]] = {}
        self.skip_stats: Dict[str, int] = {}
        self.run_metrics: Dict[str, Dict[str, Any]] = {}

    def record_request(
        self,
        strategy: str,
        bytes_downloaded: int,
        useful_text_bytes: int = 0,
        status: str = "success",
        run_id: Optional[str] = None,
        retries: int = 0,
    ):
        """Records an individual acquisition request event."""
        with self._lock:
            self.total_requests += 1
            self.total_bytes += bytes_downloaded
            self.useful_bytes += useful_text_bytes
            self.retries_count += retries

            REQUESTS_TOTAL.labels(method="GET", strategy=strategy, status=status).inc()
            BYTES_DOWNLOADED.inc(bytes_downloaded)
            USEFUL_BYTES.inc(useful_text_bytes)
            if retries > 0:
                RETRIES_TOTAL.labels(strategy=strategy).inc(retries)

            if strategy in ("L3_BROWSER", "L4_SEMANTIC", "L5_VISUAL", "browser"):
                self.browser_requests += 1
                BROWSER_ESCALATIONS.inc()
            elif strategy in ("L1_HTTP", "http"):
                self.http_requests += 1
            elif strategy in ("L2_API", "api"):
                self.api_requests += 1

            # Update Prometheus gauges (§69, §70)
            esc_ratio = self._calculate_browser_escalation_ratio()
            data_ratio = self._calculate_useful_data_ratio()
            BROWSER_ESCALATION_RATIO_GAUGE.set(esc_ratio)
            USEFUL_DATA_RATIO_GAUGE.set(data_ratio)

            if run_id:
                if run_id not in self.run_metrics:
                    self.run_metrics[run_id] = {
                        "requests": 0,
                        "bytes": 0,
                        "useful_bytes": 0,
                        "retries": 0,
                        "browser_escalations": 0,
                        "stages": {},
                    }
                r = self.run_metrics[run_id]
                r["requests"] += 1
                r["bytes"] += bytes_downloaded
                r["useful_bytes"] += useful_text_bytes
                r["retries"] += retries
                if strategy in ("L3_BROWSER", "L4_SEMANTIC", "L5_VISUAL", "browser"):
                    r["browser_escalations"] += 1

    def record_provider_outcome(
        self, provider: str, outcome: str = "success", run_id: Optional[str] = None
    ):
        """Records outcome for a search/seed provider."""
        with self._lock:
            PROVIDER_OUTCOMES.labels(provider=provider, outcome=outcome).inc()
            if provider not in self.provider_stats:
                self.provider_stats[provider] = {
                    "success": 0,
                    "failed": 0,
                    "skipped": 0,
                }
            if outcome in self.provider_stats[provider]:
                self.provider_stats[provider][outcome] += 1
            else:
                self.provider_stats[provider][outcome] = 1

    def record_skip_reason(self, reason: str, run_id: Optional[str] = None):
        """Records a skip reason (e.g. url_filter, duplicate, invalid_content_type)."""
        with self._lock:
            SKIP_REASONS.labels(reason=reason).inc()
            self.skip_stats[reason] = self.skip_stats.get(reason, 0) + 1

    def record_stage_duration(self, run_id: str, stage: str, duration_seconds: float):
        """Records elapsed duration for a pipeline stage under a specific run."""
        with self._lock:
            if run_id not in self.run_metrics:
                self.run_metrics[run_id] = {
                    "requests": 0,
                    "bytes": 0,
                    "useful_bytes": 0,
                    "retries": 0,
                    "browser_escalations": 0,
                    "stages": {},
                }
            self.run_metrics[run_id]["stages"][stage] = round(duration_seconds, 4)

    def _calculate_browser_escalation_ratio(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round((self.browser_requests / self.total_requests) * 100, 2)

    def _calculate_useful_data_ratio(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return round(self.useful_bytes / self.total_bytes, 4)

    def get_browser_escalation_ratio(self) -> float:
        with self._lock:
            return self._calculate_browser_escalation_ratio()

    def get_useful_data_ratio(self) -> float:
        with self._lock:
            return self._calculate_useful_data_ratio()

    def get_summary(self) -> Dict[str, Any]:
        """Returns structured JSON telemetry summary matching Prometheus counters."""
        with self._lock:
            elapsed = max(0.1, time.time() - self.start_time)
            return {
                "total_requests": self.total_requests,
                "http_requests": self.http_requests,
                "browser_requests": self.browser_requests,
                "api_requests": self.api_requests,
                "retries_total": self.retries_count,
                "browser_escalation_ratio_percent": self._calculate_browser_escalation_ratio(),
                "useful_data_ratio": self._calculate_useful_data_ratio(),
                "requests_per_second": round(self.total_requests / elapsed, 2),
                "total_bytes_downloaded": self.total_bytes,
                "useful_bytes_extracted": self.useful_bytes,
                "provider_stats": dict(self.provider_stats),
                "skip_stats": dict(self.skip_stats),
                "runs_tracked_count": len(self.run_metrics),
            }

    def get_run_metrics(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.run_metrics.get(run_id)

    def get_prometheus_exposition(self) -> bytes:
        """Renders Prometheus format text exposition."""
        return generate_latest()

    def reset(self):
        """Resets in-memory counters (primarily for hermetic unit testing)."""
        with self._lock:
            self.total_requests = 0
            self.http_requests = 0
            self.browser_requests = 0
            self.api_requests = 0
            self.total_bytes = 0
            self.useful_bytes = 0
            self.retries_count = 0
            self.provider_stats.clear()
            self.skip_stats.clear()
            self.run_metrics.clear()
            self.start_time = time.time()


telemetry = TelemetryTracker()
