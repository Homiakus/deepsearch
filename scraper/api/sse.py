"""Server-Sent Events (SSE) Event Broker for Live Research Telemetry and Web UI.

Broadcasts live crawler metrics, stage transitions, URL discoveries, and evidence updates
to connected web clients and UI dashboards.
"""

import asyncio
import json
import time
from typing import Dict, List, Set, AsyncGenerator, Any, Optional
from pydantic import BaseModel, Field


class ResearchEvent(BaseModel):
    """Event model broadcasted over Server-Sent Events stream."""

    job_id: str
    event_type: str  # stage_change, url_discovered, page_crawled, evidence_found, completed, error
    timestamp: float = Field(default_factory=time.time)
    data: Dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format event in standard SSE wire format."""
        payload = json.dumps(
            {
                "job_id": self.job_id,
                "event_type": self.event_type,
                "timestamp": self.timestamp,
                "data": self.data,
            }
        )
        return f"event: {self.event_type}\ndata: {payload}\n\n"


class SSEEventBroker:
    """In-memory event hub for managing SSE client subscriptions per research job."""

    def __init__(self):
        self._listeners: Dict[str, Set[asyncio.Queue]] = {}
        self._history: Dict[str, List[ResearchEvent]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, job_id: str, include_history: bool = True
    ) -> AsyncGenerator[str, None]:
        """Subscribe client to real-time events for a job."""
        queue: asyncio.Queue = asyncio.Queue()

        async with self._lock:
            if job_id not in self._listeners:
                self._listeners[job_id] = set()
            self._listeners[job_id].add(queue)

            # Send historical events first if requested
            if include_history and job_id in self._history:
                for past_ev in self._history[job_id]:
                    await queue.put(past_ev.to_sse())

        try:
            # Yield initial connection ping
            yield f"event: connected\ndata: {json.dumps({'job_id': job_id, 'status': 'connected'})}\n\n"

            while True:
                msg = await queue.get()
                yield msg
        finally:
            async with self._lock:
                if job_id in self._listeners:
                    self._listeners[job_id].discard(queue)
                    if not self._listeners[job_id]:
                        del self._listeners[job_id]

    async def publish(
        self, job_id: str, event_type: str, data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Publish event to all active subscribers of job_id and record in history."""
        ev = ResearchEvent(job_id=job_id, event_type=event_type, data=data or {})
        msg = ev.to_sse()

        async with self._lock:
            if job_id not in self._history:
                self._history[job_id] = []
            self._history[job_id].append(ev)
            # Limit history to 500 events
            if len(self._history[job_id]) > 500:
                self._history[job_id].pop(0)

            if job_id in self._listeners:
                for queue in list(self._listeners[job_id]):
                    await queue.put(msg)

    async def clear_job(self, job_id: str) -> None:
        """Clean up history and listeners for a finished job."""
        async with self._lock:
            self._history.pop(job_id, None)
            self._listeners.pop(job_id, None)


# Global singleton SSE broker
sse_broker = SSEEventBroker()
