"""Minimal Effective Browser Planner (§4, §8, DS-RB06, DS-RB07).

Selects the least expensive backend satisfying hard capability requirements,
learning domain-level routing history without premature linear escalation.
"""

from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from scraper.acquisition.capabilities import BackendDescriptor
from scraper.acquisition.models import AcquisitionRequest, AcquisitionResult


class DomainTelemetry:
    """EWMA tracking of domain-level success and latency for backends."""

    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha
        # (domain, backend) -> {attempts, successes, quality_ewma, latency_ewma}
        self.stats: Dict[Tuple[str, str], Dict[str, float]] = {}

    def record(
        self,
        domain: str,
        backend: str,
        success: bool,
        quality: float,
        latency_ms: float,
    ):
        key = (domain.lower(), backend.lower())
        if key not in self.stats:
            self.stats[key] = {
                "attempts": 1.0,
                "successes": 1.0 if success else 0.0,
                "quality_ewma": quality,
                "latency_ewma": latency_ms,
            }
        else:
            entry = self.stats[key]
            entry["attempts"] += 1.0
            if success:
                entry["successes"] += 1.0
            entry["quality_ewma"] = (1 - self.alpha) * entry[
                "quality_ewma"
            ] + self.alpha * quality
            entry["latency_ewma"] = (1 - self.alpha) * entry[
                "latency_ewma"
            ] + self.alpha * latency_ms

    def get_success_probability(self, domain: str, backend: str) -> float:
        key = (domain.lower(), backend.lower())
        if key not in self.stats:
            return 0.95  # Optimistic prior
        entry = self.stats[key]
        if entry["attempts"] < 3:
            return 0.95
        return max(0.05, min(0.99, entry["successes"] / entry["attempts"]))


class BackendPlanner:
    """Capability-oriented planner selecting minimal effective execution backend."""

    def __init__(self, telemetry: Optional[DomainTelemetry] = None):
        self.telemetry = telemetry or DomainTelemetry()

    def select_backend(
        self,
        request: AcquisitionRequest,
        available_backends: List[BackendDescriptor],
    ) -> Optional[BackendDescriptor]:
        if not available_backends:
            return None

        domain = urlparse(request.url).netloc.split(":")[0]

        # 1. Filter by hard capabilities
        eligible: List[BackendDescriptor] = []
        for desc in available_backends:
            if desc.capabilities.satisfies(request.required_capabilities):
                eligible.append(desc)

        if not eligible:
            return None

        # 2. Score eligible backends by expected cost
        scored: List[Tuple[float, BackendDescriptor]] = []
        for desc in eligible:
            p_success = self.telemetry.get_success_probability(domain, desc.name)
            # Cost model (§8): expected_cost = base_cost / p_success
            expected_cost = (desc.base_cost + desc.startup_cost * 0.1) / p_success
            scored.append((expected_cost, desc))

        scored.sort(key=lambda x: x[0])
        return scored[0][1]

    def should_escalate(
        self,
        result: AcquisitionResult,
        current_backend: BackendDescriptor,
        available_backends: List[BackendDescriptor],
    ) -> Tuple[bool, Optional[BackendDescriptor]]:
        """Determines whether quality signals mandate escalation to a higher tier backend."""
        # If quality is adequate, no escalation needed
        if (
            result.quality.score >= 0.7
            and not result.quality.blocked
            and not result.quality.likely_unrendered
        ):
            return False, None

        suggested = result.quality.suggested_escalation
        candidates = [
            b
            for b in available_backends
            if b.name != current_backend.name
            and b.base_cost >= current_backend.base_cost
        ]

        if suggested:
            for b in candidates:
                if b.engine_family == suggested or b.name == suggested:
                    return True, b

        # Fallback to the next higher-capability tier
        if candidates:
            candidates.sort(key=lambda b: b.base_cost)
            return True, candidates[0]

        return False, None
