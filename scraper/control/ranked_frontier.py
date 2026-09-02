"""Goal-Aware Ranked Request Frontier (DS-SI23, DS-SI24, DS-SI25, DS-SI26, DS-SI27).

Manages prioritized, domain-fair crawl candidates with lease-based lifecycle tracking
and explicit transient failure retry semantics.
"""

import asyncio
import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field

from scraper.search.candidates import SourceCandidate
from scraper.search.features import CandidateFeatureVector


class CandidateState(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    ACQUIRING = "ACQUIRING"
    ACQUIRED = "ACQUIRED"
    ASSESSING = "ASSESSING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    RETRY = "RETRY"
    DEAD = "DEAD"


class FrontierItem(BaseModel):
    id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:10]}")
    candidate: SourceCandidate
    priority: float = 0.5
    depth: int = 0
    goal_id: str | None = None
    state: CandidateState = CandidateState.DISCOVERED
    attempt: int = 0
    max_attempts: int = 4
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    lease_expires_at: float | None = None
    error_message: str | None = None
    features: CandidateFeatureVector | None = None


class RankedFrontier:
    """Async bounded priority frontier with domain fairness and goal coverage scheduling."""

    def __init__(
        self,
        max_capacity: int = 10000,
        max_active_per_domain: int = 3,
        same_domain_penalty: float = 0.05,
    ):
        self.max_capacity = max_capacity
        self.max_active_per_domain = max_active_per_domain
        self.same_domain_penalty = same_domain_penalty

        self._queue: list[FrontierItem] = []
        self._items_by_url: dict[str, FrontierItem] = {}
        self._items_by_id: dict[str, FrontierItem] = {}
        self._active_per_domain: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)

    async def add_candidate(
        self,
        candidate: SourceCandidate,
        priority: float = 0.5,
        depth: int = 0,
        goal_id: str | None = None,
        features: CandidateFeatureVector | None = None,
    ) -> bool:
        """Adds or updates candidate in frontier preserving state and provenance."""
        async with self._condition:
            c_url = candidate.canonical_url or candidate.url
            if c_url in self._items_by_url:
                existing = self._items_by_url[c_url]
                # Merge goal IDs and boost priority if higher
                if goal_id and goal_id not in existing.candidate.goal_ids:
                    existing.candidate.goal_ids.append(goal_id)
                if priority > existing.priority:
                    existing.priority = priority
                    self._queue.sort(key=lambda item: item.priority, reverse=True)
                return False

            if len(self._queue) >= self.max_capacity:
                # Drop or reject lowest priority
                return False

            item = FrontierItem(
                candidate=candidate,
                priority=priority,
                depth=depth,
                goal_id=goal_id
                or (candidate.goal_ids[0] if candidate.goal_ids else None),
                state=CandidateState.QUEUED,
                features=features,
            )

            self._items_by_url[c_url] = item
            self._items_by_id[item.id] = item
            self._queue.append(item)
            self._queue.sort(key=lambda it: it.priority, reverse=True)
            self._condition.notify_all()
            return True

    async def lease_next(self, lease_duration_sec: float = 30.0) -> FrontierItem | None:
        """Leases the highest priority candidate respecting domain concurrency limits (DS-SI26)."""
        async with self._condition:
            now = time.time()

            # Clean expired leases
            for item in self._items_by_id.values():
                if (
                    item.state == CandidateState.LEASED
                    and item.lease_expires_at
                    and item.lease_expires_at < now
                ):
                    item.state = CandidateState.QUEUED
                    item.lease_expires_at = None
                    dom = item.candidate.domain
                    self._active_per_domain[dom] = max(
                        0, self._active_per_domain.get(dom, 1) - 1
                    )
                    if item not in self._queue:
                        self._queue.append(item)
                        self._queue.sort(key=lambda it: it.priority, reverse=True)

            if not self._queue:
                return None

            # Find top priority item that does not exceed domain concurrency limit
            selected_idx = -1
            for idx, item in enumerate(self._queue):
                dom = item.candidate.domain
                active = self._active_per_domain.get(dom, 0)
                if active < self.max_active_per_domain:
                    selected_idx = idx
                    break

            if selected_idx == -1:
                # Fall back to first item if all top domains are active
                selected_idx = 0

            item = self._queue.pop(selected_idx)
            item.state = CandidateState.LEASED
            item.attempt += 1
            item.updated_at = now
            item.lease_expires_at = now + lease_duration_sec

            dom = item.candidate.domain
            self._active_per_domain[dom] = self._active_per_domain.get(dom, 0) + 1
            return item

    async def mark_state(
        self,
        item_id: str,
        state: CandidateState,
        error: str | None = None,
        is_transient_error: bool = False,
    ):
        """Updates candidate state and handles retry semantics without permanent visited loss (DS-SI25)."""
        async with self._condition:
            if item_id not in self._items_by_id:
                return

            item = self._items_by_id[item_id]
            dom = item.candidate.domain
            self._active_per_domain[dom] = max(
                0, self._active_per_domain.get(dom, 1) - 1
            )
            item.lease_expires_at = None
            item.updated_at = time.time()

            if is_transient_error and item.attempt < item.max_attempts:
                item.state = CandidateState.RETRY
                item.priority = max(
                    0.05, item.priority - 0.10
                )  # Gentle penalty on retry
                item.error_message = error
                self._queue.append(item)
                self._queue.sort(key=lambda it: it.priority, reverse=True)
                self._condition.notify_all()
            else:
                item.state = state
                if error:
                    item.error_message = error

    def size(self) -> int:
        return len(self._queue)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self._items_by_id.values():
            counts[item.state.value] = counts.get(item.state.value, 0) + 1
        return counts
