"""Unit tests for Host-Aware Rate Limiter (§12, §23)."""

import pytest
from scraper.control.rate_limiter import HostRateLimiter, TokenBucket


@pytest.mark.asyncio
async def test_token_bucket():
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    wait1 = await bucket.acquire(1.0)
    assert wait1 == 0.0


@pytest.mark.asyncio
async def test_host_rate_limiter_adaptive():
    limiter = HostRateLimiter()
    host = "example.com"

    await limiter.acquire(host)

    # Record 429 response -> should trigger rate backoff (§23)
    await limiter.record_result(host, status=429, latency_sec=0.5)

    stats = await limiter._get_host_stats(host)
    assert stats.requests_429 == 1
    assert stats.current_rps < 5.0  # RPS reduced on 429


@pytest.mark.asyncio
async def test_exponential_backoff_calculation():
    limiter = HostRateLimiter()
    backoff1 = await limiter.calculate_backoff(attempt=1)
    backoff3 = await limiter.calculate_backoff(attempt=3)
    assert backoff1 > 0
    assert backoff3 > backoff1
