"""Host-Aware Rate Limiter with Token Bucket and Adaptive Feedback (§12, §23)."""

import asyncio
import random
import time
from typing import Dict
from scraper.config import settings


class TokenBucket:
    """Token bucket algorithm per host."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate  # Tokens added per second
        self.capacity = capacity  # Maximum bucket capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens from bucket. Returns wait time if tokens are unavailable."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            # Replenish tokens
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            # Calculate required wait time
            needed = tokens - self.tokens
            wait_time = needed / self.rate
            return wait_time


class HostStats:
    """Tracks per-host metrics for adaptive feedback (§12)."""

    def __init__(self, host: str, rps: float, concurrency: int):
        self.host = host
        self.current_rps = rps
        self.max_concurrency = concurrency
        self.active_concurrency = 0
        self.bucket = TokenBucket(rps, rps * 2)

        self.requests_total = 0
        self.requests_success = 0
        self.requests_429 = 0
        self.requests_error = 0
        self.latency_samples = []

    def record_response(self, status: int, latency_sec: float):
        self.requests_total += 1
        self.latency_samples.append(latency_sec)
        if len(self.latency_samples) > 100:
            self.latency_samples.pop(0)

        if 200 <= status < 400:
            self.requests_success += 1
            # Slowly restore RPS if host is stable
            if self.current_rps < settings.limits.default_host_rps:
                self.current_rps = min(
                    settings.limits.default_host_rps, self.current_rps * 1.05
                )
                self.bucket.rate = self.current_rps

        elif status in (429, 503):
            self.requests_429 += 1
            # Back off RPS on rate limits (§23)
            self.current_rps = max(0.5, self.current_rps * 0.5)
            self.bucket.rate = self.current_rps

        else:
            self.requests_error += 1


class HostRateLimiter:
    """Host-aware adaptive rate limiting manager."""

    def __init__(self):
        self._hosts: Dict[str, HostStats] = {}
        self._lock = asyncio.Lock()

    async def _get_host_stats(self, host: str) -> HostStats:
        async with self._lock:
            if host not in self._hosts:
                self._hosts[host] = HostStats(
                    host=host,
                    rps=settings.limits.default_host_rps,
                    concurrency=settings.limits.max_host_concurrency,
                )
            return self._hosts[host]

    async def acquire(self, host: str):
        """Acquire permission to request host, waiting if rate limit is reached."""
        stats = await self._get_host_stats(host)
        while True:
            wait_sec = await stats.bucket.acquire(1.0)
            if wait_sec <= 0.0:
                break
            # Add jitter to backoff (§23)
            jitter = random.uniform(0.05, 0.2)
            await asyncio.sleep(wait_sec + jitter)

    async def record_result(self, host: str, status: int, latency_sec: float):
        stats = await self._get_host_stats(host)
        stats.record_response(status, latency_sec)

    async def calculate_backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter (§23)."""
        base_backoff = min(60.0, (2**attempt))
        jitter = random.uniform(0.5, 1.5)
        return base_backoff * jitter
