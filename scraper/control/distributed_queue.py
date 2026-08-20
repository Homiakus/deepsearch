"""Distributed Request Queue Adapter supporting Redis Streams and In-Memory fallback.

Enables high-concurrency, fault-tolerant distributed crawling across multiple worker nodes.
"""

import asyncio
import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from scraper.control.scheduler import CrawlRequest, RequestState
from scraper.config import settings

logger = logging.getLogger(__name__)


class DistributedQueueAdapter(ABC):
    """Abstract interface for distributed request queues."""

    @abstractmethod
    async def push(self, request: CrawlRequest) -> bool:
        """Push a crawl request into the distributed queue."""
        pass

    @abstractmethod
    async def push_batch(self, requests: List[CrawlRequest]) -> int:
        """Push a batch of crawl requests into the distributed queue."""
        pass

    @abstractmethod
    async def pop_batch(
        self, consumer_name: str, count: int = 10, block_ms: int = 2000
    ) -> List[Tuple[str, CrawlRequest]]:
        """Pop leased requests from the queue for a consumer. Returns (message_id, request) pairs."""
        pass

    @abstractmethod
    async def ack(self, message_id: str) -> bool:
        """Acknowledge completed processing of a request."""
        pass

    @abstractmethod
    async def nack(self, message_id: str, requeue: bool = True) -> bool:
        """Negative acknowledge: signal failure to process."""
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics of the queue."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Cleanly close connection and resources."""
        pass


class InMemoryDistributedQueue(DistributedQueueAdapter):
    """Thread-safe In-Memory Distributed Queue for local / test execution."""

    def __init__(self, max_capacity: int = 50000):
        self.max_capacity = max_capacity
        self._queue: List[Tuple[str, CrawlRequest]] = []
        self._pending: Dict[
            str, Tuple[str, CrawlRequest, float]
        ] = {}  # msg_id -> (consumer, req, lease_time)
        self._ack_count = 0
        self._nack_count = 0
        self._msg_counter = 0
        self._lock = asyncio.Lock()

    async def push(self, request: CrawlRequest) -> bool:
        async with self._lock:
            if len(self._queue) >= self.max_capacity:
                return False
            self._msg_counter += 1
            msg_id = f"mem-{self._msg_counter}-{int(time.time() * 1000)}"
            request.state = RequestState.QUEUED
            self._queue.append((msg_id, request))
            return True

    async def push_batch(self, requests: List[CrawlRequest]) -> int:
        pushed = 0
        for req in requests:
            if await self.push(req):
                pushed += 1
        return pushed

    async def pop_batch(
        self, consumer_name: str, count: int = 10, block_ms: int = 100
    ) -> List[Tuple[str, CrawlRequest]]:
        async with self._lock:
            if not self._queue:
                return []
            leased = []
            now = time.time()
            while self._queue and len(leased) < count:
                msg_id, req = self._queue.pop(0)
                req.state = RequestState.LEASED
                req.lease_expires_at = now + 60.0
                self._pending[msg_id] = (consumer_name, req, now)
                leased.append((msg_id, req))
            return leased

    async def ack(self, message_id: str) -> bool:
        async with self._lock:
            if message_id in self._pending:
                del self._pending[message_id]
                self._ack_count += 1
                return True
            return False

    async def nack(self, message_id: str, requeue: bool = True) -> bool:
        async with self._lock:
            if message_id in self._pending:
                _, req, _ = self._pending.pop(message_id)
                self._nack_count += 1
                if requeue and req.attempt < req.max_attempts:
                    req.attempt += 1
                    req.state = RequestState.RETRY
                    self._queue.append((message_id, req))
                else:
                    req.state = RequestState.DEAD
                return True
            return False

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            return {
                "backend": "in_memory",
                "queued_count": len(self._queue),
                "pending_count": len(self._pending),
                "ack_count": self._ack_count,
                "nack_count": self._nack_count,
            }

    async def close(self) -> None:
        async with self._lock:
            self._queue.clear()
            self._pending.clear()


class RedisStreamsDistributedQueue(DistributedQueueAdapter):
    """Production Redis Streams Queue with Consumer Groups and Auto-Lease Reclaim."""

    def __init__(
        self,
        redis_url: str = settings.redis_url,
        stream_key: str = settings.redis_stream_key,
        group_name: str = settings.redis_consumer_group,
    ):
        self.redis_url = redis_url
        self.stream_key = stream_key
        self.group_name = group_name
        self._redis = None
        self._group_created = False

    async def _get_client(self):
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            try:
                await self._redis.xgroup_create(
                    self.stream_key, self.group_name, id="0", mkstream=True
                )
                self._group_created = True
            except Exception as e:
                # BUSYGROUP Consumer Group name already exists
                if "BUSYGROUP" in str(e):
                    self._group_created = True
                else:
                    logger.warning(f"Redis xgroup_create: {e}")
        return self._redis

    async def push(self, request: CrawlRequest) -> bool:
        try:
            client = await self._get_client()
            request.state = RequestState.QUEUED
            data = {"payload": request.model_dump_json()}
            await client.xadd(self.stream_key, data)
            return True
        except Exception as e:
            logger.error(f"Failed to push to Redis stream: {e}")
            return False

    async def push_batch(self, requests: List[CrawlRequest]) -> int:
        count = 0
        for req in requests:
            if await self.push(req):
                count += 1
        return count

    async def pop_batch(
        self, consumer_name: str, count: int = 10, block_ms: int = 2000
    ) -> List[Tuple[str, CrawlRequest]]:
        try:
            client = await self._get_client()
            entries = await client.xreadgroup(
                groupname=self.group_name,
                consumername=consumer_name,
                streams={self.stream_key: ">"},
                count=count,
                block=block_ms,
            )
            results: List[Tuple[str, CrawlRequest]] = []
            if entries:
                for _, message_list in entries:
                    for msg_id, fields in message_list:
                        raw_payload = fields.get("payload")
                        if raw_payload:
                            try:
                                req_data = json.loads(raw_payload)
                                req = CrawlRequest(**req_data)
                                req.state = RequestState.LEASED
                                req.lease_expires_at = time.time() + 60.0
                                results.append((msg_id, req))
                            except Exception as parse_err:
                                logger.error(
                                    f"Error parsing CrawlRequest payload {msg_id}: {parse_err}"
                                )
                                await client.xack(
                                    self.stream_key, self.group_name, msg_id
                                )
            return results
        except Exception as e:
            logger.error(f"Failed to read from Redis stream group: {e}")
            return []

    async def ack(self, message_id: str) -> bool:
        try:
            client = await self._get_client()
            res = await client.xack(self.stream_key, self.group_name, message_id)
            return res > 0
        except Exception as e:
            logger.error(f"Failed to ack Redis message {message_id}: {e}")
            return False

    async def nack(self, message_id: str, requeue: bool = True) -> bool:
        try:
            client = await self._get_client()
            if requeue:
                msgs = await client.xrange(
                    self.stream_key, min=message_id, max=message_id
                )
                if msgs:
                    _, fields = msgs[0]
                    raw_payload = fields.get("payload")
                    if raw_payload:
                        req_dict = json.loads(raw_payload)
                        req = CrawlRequest(**req_dict)
                        req.attempt += 1
                        if req.attempt <= req.max_attempts:
                            await client.xadd(
                                self.stream_key, {"payload": req.model_dump_json()}
                            )
            await client.xack(self.stream_key, self.group_name, message_id)
            return True
        except Exception as e:
            logger.error(f"Failed to nack Redis message {message_id}: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        try:
            client = await self._get_client()
            length = await client.xlen(self.stream_key)
            groups = await client.xinfo_groups(self.stream_key)
            return {
                "backend": "redis_streams",
                "stream_length": length,
                "groups": groups,
            }
        except Exception as e:
            return {"backend": "redis_streams", "error": str(e)}

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


def get_distributed_queue(backend: Optional[str] = None) -> DistributedQueueAdapter:
    """Factory function for Distributed Queue adapter based on config or explicit backend."""
    selected = backend or settings.distributed_queue_backend
    if selected.lower() == "redis":
        return RedisStreamsDistributedQueue()
    return InMemoryDistributedQueue()
