"""Per-Run Execution Context with Budget, Rate Limiting, Deduplication, and Cancellation (§DS-10)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field

from scraper.config import ExecutionMode, settings
from scraper.control.budget import BudgetTracker, JobBudget
from scraper.control.rate_limiter import HostRateLimiter
from scraper.discovery.robots import RobotsPolicyManager
from scraper.exceptions import BudgetExceededError
from scraper.normalization.deduplicator import Deduplicator


class RunContextOptions(BaseModel):
    run_id: str
    query: str
    domain: str | None = None
    depth: int = Field(default_factory=lambda: settings.budget.max_depth)
    max_pages: int = Field(default_factory=lambda: settings.budget.max_pages)
    max_bytes: int = Field(default_factory=lambda: settings.budget.max_bytes)
    timeout_seconds: float | None = None
    mode: ExecutionMode = ExecutionMode.BALANCED


class RunContext:
    """Encapsulates all per-run limits, rate limiting, robots policy, deduplication, and lifecycle controls (§DS-10)."""

    def __init__(
        self,
        run_id: str,
        query: str,
        domain: str | None = None,
        budget: JobBudget | None = None,
        rate_limiter: HostRateLimiter | None = None,
        robots_manager: RobotsPolicyManager | None = None,
        deduplicator: Deduplicator | None = None,
    ):
        self.run_id = run_id
        self.query = query
        self.domain = domain
        self.budget_tracker = BudgetTracker(budget=budget)
        self.rate_limiter = rate_limiter or HostRateLimiter()
        self.robots_manager = robots_manager or RobotsPolicyManager()
        self.deduplicator = deduplicator or Deduplicator()
        self.cancellation_event = asyncio.Event()
        self.telemetry_events: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    @classmethod
    def create(cls, opts: RunContextOptions) -> RunContext:
        deadline = time.time() + opts.timeout_seconds if opts.timeout_seconds else None
        budget = JobBudget(
            max_pages=opts.max_pages,
            max_depth=opts.depth,
            max_bytes=opts.max_bytes,
            deadline_timestamp=deadline,
        )
        return cls(
            run_id=opts.run_id,
            query=opts.query,
            domain=opts.domain,
            budget=budget,
        )

    def cancel(self) -> None:
        """Cooperatively signal cancellation for this execution run."""
        self.cancellation_event.set()

    def is_cancelled(self) -> bool:
        return self.cancellation_event.is_set()

    def check_active(self) -> None:
        """Check if run is cancelled or deadline reached; raises if inactive."""
        if self.is_cancelled():
            raise asyncio.CancelledError(f"Run '{self.run_id}' was cancelled.")
        if (
            self.budget_tracker.budget.deadline_timestamp
            and time.time() > self.budget_tracker.budget.deadline_timestamp
        ):
            raise BudgetExceededError(
                f"Run '{self.run_id}' exceeded execution deadline."
            )

    async def record_telemetry(self, event_type: str, details: dict[str, Any]) -> None:
        async with self._lock:
            self.telemetry_events.append(
                {"event": event_type, "timestamp": time.time(), "details": details}
            )
