"""Unit tests for Host-Aware Rate Limiter (§12, §23)."""

import pytest

from scraper.control.rate_limiter import HostRateLimiter, TokenBucket


@pytest.mark.asyncio
async def test_token_bucket():
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    wait1 = await bucket.acquire(1.0)
    assert wait1 == 0.0


@pytest.mark.asyncio
async def test_token_bucket_simulated_time_and_clock_jumps():
    """FRAG-TIME/FRAG-NUMERIC: Verify TokenBucket replenishment with controlled time and clock jumps."""
    sim_time = 100.0

    def get_monotonic() -> float:
        return sim_time

    bucket = TokenBucket(rate=2.0, capacity=4.0, now_monotonic=get_monotonic)

    # 1. Acquire all 4 tokens -> available immediately
    assert await bucket.acquire(4.0) == 0.0
    assert bucket.tokens == 0.0

    # 2. Acquire 1 token immediately without time advance -> requires 0.5s wait
    wait_sec = await bucket.acquire(1.0)
    assert wait_sec == pytest.approx(0.5, rel=1e-3)

    # 3. Advance clock by 0.25s (t - ε) -> 0.5 tokens accumulated, need 0.5 more -> wait 0.25s
    sim_time = 100.25
    wait_sec = await bucket.acquire(1.0)
    assert wait_sec == pytest.approx(0.25, rel=1e-3)

    # 4. Advance clock by 0.25s more (t) -> total 1.0 token replenished, acquire succeeds with 0s wait
    sim_time = 100.5
    assert await bucket.acquire(1.0) == 0.0
    assert bucket.tokens == 0.0

    # 5. Large forward clock jump (+1000s) -> tokens capped at capacity (4.0)
    sim_time = 1100.5
    assert await bucket.acquire(0.0) == 0.0
    assert bucket.tokens == 4.0

    # 6. Backward clock jump (monotonic glitch or adjustment to 500.0) -> must not crash or corrupt tokens
    sim_time = 500.0
    wait_sec = await bucket.acquire(1.0)
    assert wait_sec == 0.0
    assert bucket.tokens == 3.0


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

    # Record successful responses -> slowly restore RPS
    initial_rps = stats.current_rps
    for _ in range(5):
        await limiter.record_result(host, status=200, latency_sec=0.1)
    assert stats.current_rps > initial_rps


@pytest.mark.asyncio
async def test_exponential_backoff_calculation():
    # Deterministic uniform_fn returning mid-range 1.0
    limiter = HostRateLimiter(uniform_fn=lambda a, b: 1.0)
    backoff1 = await limiter.calculate_backoff(attempt=1)
    backoff2 = await limiter.calculate_backoff(attempt=2)
    backoff3 = await limiter.calculate_backoff(attempt=3)

    assert backoff1 == 2.0
    assert backoff2 == 4.0
    assert backoff3 == 8.0


def test_non_positive_rate_rejected():
    """FRAG-007: Non-positive rate or capacity in TokenBucket must raise ValueError instead of ZeroDivisionError."""
    with pytest.raises(ValueError):
        TokenBucket(rate=0.0, capacity=0.0)

    with pytest.raises(ValueError):
        TokenBucket(rate=-5.0, capacity=10.0)
