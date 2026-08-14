"""Crawl Request Scheduler and Frontier Management (§14, §15, §18)."""

import asyncio
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional, Set
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
    priority: float = 50.0  # Formula: relevance + depth + sitemap_priority - cost_estimate (§18)
    parent_id: Optional[str] = None
    method: str = "GET"
    attempt: int = 1
    max_attempts: int = 5
    mode: str = "adaptive"
    state: RequestState = RequestState.DISCOVERED
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    lease_expires_at: Optional[float] = None
    error_message: Optional[str] = None


class RequestFrontier:
    """In-memory & async bounded request queue frontier with lease semantics (§15)."""

    def __init__(self, max_capacity: int = 100000):
        self.max_capacity = max_capacity
        self._queue: List[CrawlRequest] = []
        self._discovered_urls: Set[str] = set()
        self._requests_by_id: Dict[str, CrawlRequest] = {}
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
            req.updated_at = time.time()
            self._discovered_urls.add(req.canonical_url)
            self._requests_by_id[req.id] = req
            self._queue.append(req)
            # Keep queue sorted by priority descending
            self._queue.sort(key=lambda r: r.priority, reverse=True)
            self._condition.notify_all()
            return True

    async def lease_request(self, lease_duration_sec: float = 60.0) -> Optional[CrawlRequest]:
        """Lease the highest priority available request (§15 at-least-once)."""
        async with self._condition:
            now = time.time()
            # First clean up expired leases
            for req in self._requests_by_id.values():
                if req.state == RequestState.LEASED and req.lease_expires_at and req.lease_expires_at < now:
                    req.state = RequestState.QUEUED
                    req.lease_expires_at = None
                    if req not in self._queue:
                        self._queue.append(req)
                        self._queue.sort(key=lambda r: r.priority, reverse=True)

            while not self._queue:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    return None

            req = self._queue.pop(0)
            req.state = RequestState.LEASED
            req.updated_at = now
            req.lease_expires_at = now + lease_duration_sec
            return req

    async def update_state(self, req_id: str, state: RequestState, error: Optional[str] = None):
        """Update request lifecycle state."""
        async with self._lock:
            if req_id in self._requests_by_id:
                req = self._requests_by_id[req_id]
                req.state = state
                req.updated_at = time.time()
                if error:
                    req.error_message = error
                if state in (RequestState.DONE, RequestState.DEAD, RequestState.SKIPPED):
                    req.lease_expires_at = None

    async def retry_request(self, req_id: str, delay_sec: float = 2.0):
        """Schedule request retry with incremented attempt count (§24)."""
        async with self._lock:
            if req_id in self._requests_by_id:
                req = self._requests_by_id[req_id]
                req.attempt += 1
                if req.attempt > req.max_attempts:
                    req.state = RequestState.DEAD
                else:
                    req.state = RequestState.QUEUED
                    req.lease_expires_at = None
                    req.priority = max(0.0, req.priority - 5.0)  # Lower priority on retry
                    self._queue.append(req)
                    self._queue.sort(key=lambda r: r.priority, reverse=True)
                    self._condition.notify_all()

    async def stats(self) -> Dict[str, int]:
        """Return count of requests by state."""
        async with self._lock:
            counts: Dict[str, int] = {}
            for req in self._requests_by_id.values():
                counts[req.state.value] = counts.get(req.state.value, 0) + 1
            return counts
