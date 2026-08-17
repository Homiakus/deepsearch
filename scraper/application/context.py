"""Research Execution Context and runtime dependency container (§3, DS-A10)."""

from typing import Optional
from dataclasses import dataclass, field
import time

from scraper.config import ExecutionMode, settings
from scraper.control.budget import BudgetTracker
from scraper.control.rate_limiter import HostRateLimiter
from scraper.normalization.deduplicator import Deduplicator
from scraper.storage.cas import ContentAddressableStore
from scraper.monitoring.telemetry import TelemetryTracker, telemetry


@dataclass
class ResearchExecutionContext:
    """Carries scoped per-run dependencies, policies, meters and limits without global state pollution."""

    execution_id: str
    run_id: str
    mode: ExecutionMode = ExecutionMode.BALANCED
    budget: BudgetTracker = field(default_factory=BudgetTracker)
    rate_limiter: HostRateLimiter = field(default_factory=HostRateLimiter)
    deduplicator: Deduplicator = field(default_factory=Deduplicator)
    cas: Optional[ContentAddressableStore] = None
    telemetry_tracker: TelemetryTracker = field(default_factory=lambda: telemetry)
    created_at_epoch: float = field(default_factory=time.time)
    is_cancelled: bool = False

    def check_cancellation(self) -> None:
        if self.is_cancelled:
            from scraper.orchestration.errors import TransientFailure
            raise TransientFailure("Execution was cancelled by coordinator")

    def elapsed_seconds(self) -> float:
        return time.time() - self.created_at_epoch
