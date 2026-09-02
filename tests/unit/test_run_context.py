"""Unit and integration tests for RunContext and pipeline constraints (§DS-10)."""

import asyncio
import time

import pytest

from scraper.application.run_context import RunContext, RunContextOptions
from scraper.control.budget import JobBudget
from scraper.exceptions import BudgetExceededError


@pytest.mark.asyncio
async def test_run_context_creation_and_defaults():
    opts = RunContextOptions(
        run_id="run_test_10",
        query="quantum algorithms",
        domain="arxiv.org",
        depth=2,
        max_pages=5,
        timeout_seconds=30.0,
    )
    ctx = RunContext.create(opts)
    assert ctx.run_id == "run_test_10"
    assert ctx.query == "quantum algorithms"
    assert ctx.domain == "arxiv.org"
    assert ctx.budget_tracker.budget.max_pages == 5
    assert ctx.budget_tracker.budget.max_depth == 2
    assert not ctx.is_cancelled()


@pytest.mark.asyncio
async def test_run_context_cooperative_cancellation():
    opts = RunContextOptions(run_id="run_cancel", query="cancel query")
    ctx = RunContext.create(opts)

    ctx.check_active()  # Initial state is active
    ctx.cancel()
    assert ctx.is_cancelled()

    with pytest.raises(asyncio.CancelledError, match="was cancelled"):
        ctx.check_active()


@pytest.mark.asyncio
async def test_run_context_deadline_expiry():
    budget = JobBudget(
        max_pages=10,
        deadline_timestamp=time.time() - 1.0,  # Expired in past
    )
    ctx = RunContext(run_id="run_deadline", query="expired query", budget=budget)

    with pytest.raises(BudgetExceededError, match="exceeded execution deadline"):
        ctx.check_active()


@pytest.mark.asyncio
async def test_run_context_budget_tracking_and_limits():
    budget = JobBudget(max_pages=2, max_depth=1, max_bytes=1000)
    ctx = RunContext(run_id="run_budget", query="budget query", budget=budget)

    # First page ok
    await ctx.budget_tracker.record_page(bytes_size=400, depth=0)
    assert ctx.budget_tracker.pages_processed == 1

    # Second page ok
    await ctx.budget_tracker.record_page(bytes_size=400, depth=1)
    assert ctx.budget_tracker.pages_processed == 2

    # Third page exceeds page limit
    with pytest.raises(BudgetExceededError, match="Page limit exceeded"):
        await ctx.budget_tracker.record_page(bytes_size=100, depth=1)


@pytest.mark.asyncio
async def test_run_context_robots_disallow():
    opts = RunContextOptions(run_id="run_robots", query="robots test")
    ctx = RunContext.create(opts)

    robots_txt = """
User-agent: *
Disallow: /private/
Disallow: /admin
Allow: /public/
"""
    ctx.robots_manager.parse_robots_txt("example.com", robots_txt)

    assert ctx.robots_manager.is_allowed(
        "https://example.com/public/doc", "example.com"
    )
    assert not ctx.robots_manager.is_allowed(
        "https://example.com/private/secret", "example.com"
    )
    assert not ctx.robots_manager.is_allowed("https://example.com/admin", "example.com")


@pytest.mark.asyncio
async def test_run_context_deduplication():
    opts = RunContextOptions(run_id="run_dedup", query="dedup test")
    ctx = RunContext.create(opts)

    url = "https://example.com/page1"
    content = b"<html><h1>Unique</h1></html>"

    # URL Dedup
    assert not ctx.deduplicator.is_url_duplicate(url)
    assert ctx.deduplicator.is_url_duplicate(url)

    # Content Dedup
    assert not ctx.deduplicator.is_content_duplicate(content)
    assert ctx.deduplicator.is_content_duplicate(content)
