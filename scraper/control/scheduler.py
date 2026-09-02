import asyncio
import heapq
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
    """In-memory & async bounded request queue frontier with heap-based priority scheduling and lease semantics (§15)."""

    def __init__(
        self,
        max_capacity: int = 100000,
        now_wall: Callable[[], float] = time.time,
    ):
        self.max_capacity = max_capacity
        self._now_wall = now_wall
        self._heap: list[
            tuple[float, float, str]
        ] = []  # (-priority, created_at, req_id)
        self._discovered_urls: set[str] = set()
        self._requests_by_id: dict[str, CrawlRequest] = {}
        self._leased_request_ids: set[str] = set()
        self._enqueued_ids: set[str] = set()
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)

    @property
    def _queue(self) -> list[CrawlRequest]:
        """Backward-compatible property returning list of currently queued requests."""
        return [
            self._requests_by_id[req_id]
            for req_id in self._enqueued_ids
            if req_id in self._requests_by_id
            and self._requests_by_id[req_id].state == RequestState.QUEUED
        ]

    async def add_request(self, req: CrawlRequest) -> bool:
        """Add request to frontier if canonical URL hasn't been queued/processed."""
        async with self._condition:
            if req.canonical_url in self._discovered_urls:
                return False

            if len(self._enqueued_ids) >= self.max_capacity:
                # Backpressure: reject or drop low priority (§13)
                return False

            now = self._now_wall()
            req.state = RequestState.QUEUED
            req.updated_at = now
            self._discovered_urls.add(req.canonical_url)
            self._requests_by_id[req.id] = req
            self._enqueued_ids.add(req.id)
            heapq.heappush(self._heap, (-req.priority, req.created_at, req.id))
            self._condition.notify_all()
            return True

    async def lease_request(
        self, lease_duration_sec: float = 60.0
    ) -> CrawlRequest | None:
        """Lease the highest priority available request (§15 at-least-once) in O(log N)."""
        async with self._condition:
            now = self._now_wall()
            # Clean up only currently leased requests that have expired
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
                    if req_id not in self._enqueued_ids:
                        self._enqueued_ids.add(req_id)
                        heapq.heappush(
                            self._heap, (-req.priority, req.created_at, req_id)
                        )

            while self._heap:
                _, _, req_id = heapq.heappop(self._heap)
                self._enqueued_ids.discard(req_id)
                candidate = self._requests_by_id.get(req_id)
                if candidate is None or candidate.state in (
                    RequestState.DONE,
                    RequestState.DEAD,
                    RequestState.SKIPPED,
                    RequestState.LEASED,
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
                    self._enqueued_ids.discard(req_id)

    async def retry_request(self, req_id: str, delay_sec: float = 2.0):
        """Schedule request retry with incremented attempt count (§24)."""
        async with self._condition:
            if req_id in self._requests_by_id:
                req = self._requests_by_id[req_id]
                self._leased_request_ids.discard(req_id)
                if req_id in self._enqueued_ids:
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
                    self._enqueued_ids.discard(req_id)
                else:
                    req.state = RequestState.QUEUED
                    req.lease_expires_at = None
                    req.priority = max(
                        0.0, req.priority - 5.0
                    )  # Lower priority on retry
                    self._enqueued_ids.add(req_id)
                    heapq.heappush(self._heap, (-req.priority, req.updated_at, req_id))
                    self._condition.notify_all()

    async def stats(self) -> dict[str, int]:
        """Return count of requests by state."""
        async with self._lock:
            counts: dict[str, int] = {}
            for req in self._requests_by_id.values():
                counts[req.state.value] = counts.get(req.state.value, 0) + 1
            return counts
