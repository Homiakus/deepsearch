"""Operational Source Reliability & Trust History (DS-SI50)."""

from pydantic import BaseModel


class DomainStats(BaseModel):
    domain: str
    total_attempts: int = 0
    success_count: int = 0
    block_count: int = 0
    timeout_count: int = 0
    avg_latency_sec: float = 0.5


class SourceStatsTracker:
    """Tracks operational network reliability independently from epistemic authority."""

    def __init__(self):
        self._stats: dict[str, DomainStats] = {}

    def record_attempt(
        self,
        domain: str,
        success: bool,
        latency: float = 0.5,
        is_blocked: bool = False,
        is_timeout: bool = False,
    ):
        if domain not in self._stats:
            self._stats[domain] = DomainStats(domain=domain)

        st = self._stats[domain]
        st.total_attempts += 1
        if success:
            st.success_count += 1
        if is_blocked:
            st.block_count += 1
        if is_timeout:
            st.timeout_count += 1

        st.avg_latency_sec = (
            st.avg_latency_sec * (st.total_attempts - 1) + latency
        ) / st.total_attempts

    def get_success_rate(self, domain: str) -> float:
        if domain not in self._stats or self._stats[domain].total_attempts == 0:
            return 0.9  # Optimistic prior
        st = self._stats[domain]
        return round(st.success_count / st.total_attempts, 2)


source_stats_tracker = SourceStatsTracker()
