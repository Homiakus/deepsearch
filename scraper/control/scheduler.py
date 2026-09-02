"""Crawl Request Scheduler and Frontier Management (§14, §15, §18)."""

import asyncio
import bisect
import time
import uuid
from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel, Field


class RequestState(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    FETCHING = "FETCHING"
    FETCHED = "FETCHED"
    EXTRACTING = "EXTRACTING"
    INDEXING = "INDEXING"
    DONE = "DONE"
    RETRY = "RETRY"
    DEAD = "DEAD"
    SKIPPED = "SKIPPED"


class CrawlRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    canonical_url: str
    domain: str
    depth: int = 0
    priority: float = (
        50.0  # Formula: relevance + depth + sitemap_priority - cost_estimate (§18)
    )
    parent_id: str | None = None
    method: str = "GET"
    attempt: int = 1
    max_attempts: int = 5
    mode: str = "adaptive"
    state: RequestState = RequestState.DISCOVERED
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    lease_expires_at: float | None = None
    error_message: str | None = None


class RequestFrontier:
    """In-memory & async bounded request queue frontier with lease semantics (§15)."""

    def __init__(
        self,
        max_capacity: int = 100000,
        now_wall: Callable[[], float] = time.time,
    ):
        self.max_capacity = max_capacity
        self._now_wall = now_wall
        self._queue: list[CrawlRequest] = []
        self._discovered_urls: set[str] = set()
        self._requests_by_id: dict[str, CrawlRequest] = {}
        self._leased_request_ids: set[str] = set()
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)

    async def add_request(self, req: CrawlRequest) -> bool:
        """Add request to frontier if canonical URL hasn't been queued/processed."""
        async with self._condition:
            if req.canonical_url in self._discovered_urls:
                return False

            if len(self._queue) >= self.max_capacity:
                # Backpressure: reject or drop low priority (§13)
                return False

            req.state = RequestState.QUEUED
            req.updated_at = self._now_wall()
            self._discovered_urls.add(req.canonical_url)
            self._requests_by_id[req.id] = req
            bisect.insort(self._queue, req, key=lambda r: -r.priority)
            self._condition.notify_all()
            return True

    async def lease_request(
        self, lease_duration_sec: float = 60.0
    ) -> CrawlRequest | None:
        """Lease the highest priority available request (§15 at-least-once)."""
        async with self._condition:
            now = self._now_wall()
            # Clean up only currently leased requests that have expired (O(leased) not O(all))
            if self._leased_request_ids:
                expired_ids = [
                    req_id
                    for req_id in self._leased_request_ids
                    if (req := self._requests_by_id.get(req_id)) is not None
                    and req.state == RequestState.LEASED
                    and req.lease_expires_at is not None
                    and req.lease_expires_at <= now
                ]
                for req_id in expired_ids:
                    req = self._requests_by_id[req_id]
                    req.state = RequestState.QUEUED
                    req.lease_expires_at = None
                    self._leased_request_ids.discard(req_id)
                    if req not in self._queue:
                        bisect.insort(self._queue, req, key=lambda r: -r.priority)

            while self._queue:
                candidate = self._queue.pop(0)
                if candidate.state in (
                    RequestState.DONE,
                    RequestState.DEAD,
                    RequestState.SKIPPED,
                ):
                    continue
                candidate.state = RequestState.LEASED
                candidate.updated_at = now
                candidate.lease_expires_at = now + lease_duration_sec
                self._leased_request_ids.add(candidate.id)
                return candidate

            return None

    async def update_state(
        self, req_id: str, state: RequestState, error: str | None = None
    ):
        """Update request lifecycle state."""
        async with self._lock:
            if req_id in self._requests_by_id:
                req = self._requests_by_id[req_id]
                req.state = state
                req.updated_at = self._now_wall()
                if error:
                    req.error_message = error
                if state in (
                    RequestState.DONE,
                    RequestState.DEAD,
                    RequestState.SKIPPED,
                ):
                    req.lease_expires_at = None
                    self._leased_request_ids.discard(req_id)
                    if req in self._queue:
                        self._queue.remove(req)

    async def retry_request(self, req_id: str, delay_sec: float = 2.0):
        """Schedule request retry with incremented attempt count (§24)."""
        async with self._condition:
            if req_id in self._requests_by_id:
                req = self._requests_by_id[req_id]
                self._leased_request_ids.discard(req_id)
                if req in self._queue:
                    return
                if req.state in (
                    RequestState.DONE,
                    RequestState.DEAD,
                    RequestState.SKIPPED,
                ):
                    return
                req.attempt += 1
                req.updated_at = self._now_wall()
                if req.attempt > req.max_attempts:
                    req.state = RequestState.DEAD
                    req.lease_expires_at = None
                else:
                    req.state = RequestState.QUEUED
                    req.lease_expires_at = None
                    req.priority = max(
                        0.0, req.priority - 5.0
                    )  # Lower priority on retry
                    if req not in self._queue:
                        bisect.insort(self._queue, req, key=lambda r: -r.priority)
                    self._condition.notify_all()

    async def stats(self) -> dict[str, int]:
        """Return count of requests by state."""
        async with self._lock:
            counts: dict[str, int] = {}
            for req in self._requests_by_id.values():
                counts[req.state.value] = counts.get(req.state.value, 0) + 1
            return counts
