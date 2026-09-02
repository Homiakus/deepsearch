"""Unit tests for Budget Manager (§50) and Extraction Engine (§31, §35, §36)."""

import pytest

from scraper.control.budget import BudgetExceededError, BudgetTracker, JobBudget
from scraper.extraction.markdown import process_markdown_pipeline
from scraper.extraction.table_extractor import extract_tables_from_html


@pytest.mark.asyncio
async def test_budget_exceeded():
    tracker = BudgetTracker(budget=JobBudget(max_pages=2))
    await tracker.record_page(bytes_size=100, depth=1)
    await tracker.record_page(bytes_size=100, depth=1)
    with pytest.raises(BudgetExceededError):
        await tracker.record_page(bytes_size=100, depth=1)


@pytest.mark.asyncio
async def test_expired_deadline_is_atomic():
    """FRAG-005: Usage event after expired deadline must fail atomically without mutating counters."""
    sim_time = 1000.0
    tracker = BudgetTracker(
        budget=JobBudget(max_pages=10, deadline_timestamp=990.0),
        now_wall=lambda: sim_time,
    )
    with pytest.raises(BudgetExceededError, match="Job deadline reached"):
        await tracker.record_page(bytes_size=500, depth=1)

    assert tracker.pages_processed == 0
    assert tracker.bytes_downloaded == 0


@pytest.mark.asyncio
async def test_atomic_rejection_across_all_budget_dimensions():
    """FRAG-STATE/FRAG-NUMERIC: Every budget violation must fail atomically without partial counter mutation."""
    budget = JobBudget(
        max_pages=3,
        max_depth=2,
        max_bytes=1000,
        max_browser_seconds=10.0,
        max_visual_pages=2,
        max_llm_tokens=500,
    )
    tracker = BudgetTracker(budget=budget)

    # Initial valid record
    await tracker.record_page(
        bytes_size=200,
        depth=1,
        was_browser=True,
        browser_sec=2.0,
        was_visual=True,
        llm_tokens=100,
    )
    snap1 = await tracker.get_summary()

    # 1. Depth violation
    with pytest.raises(BudgetExceededError, match="Depth limit"):
        await tracker.record_page(bytes_size=100, depth=3)
    assert await tracker.get_summary() == snap1

    # 2. Byte limit violation
    with pytest.raises(BudgetExceededError, match="Byte limit"):
        await tracker.record_page(bytes_size=900, depth=1)
    assert await tracker.get_summary() == snap1

    # 3. Browser execution time violation
    with pytest.raises(BudgetExceededError, match="Browser execution time"):
        await tracker.record_page(
            bytes_size=100, depth=1, was_browser=True, browser_sec=9.0
        )
    assert await tracker.get_summary() == snap1

    # 4. Visual pages violation
    await tracker.record_page(bytes_size=100, depth=1, was_visual=True)
    snap2 = await tracker.get_summary()
    assert tracker.visual_pages_processed == 2

    with pytest.raises(BudgetExceededError, match="Visual page limit"):
        await tracker.record_page(bytes_size=100, depth=1, was_visual=True)
    assert await tracker.get_summary() == snap2

    # 5. LLM token limit violation
    with pytest.raises(BudgetExceededError, match="LLM token limit"):
        await tracker.record_page(bytes_size=100, depth=1, llm_tokens=450)
    assert await tracker.get_summary() == snap2

    # 6. Page limit violation
    # Currently 2 pages processed (page limit 3)
    await tracker.record_page(bytes_size=50, depth=1)
    assert tracker.pages_processed == 3
    snap3 = await tracker.get_summary()

    with pytest.raises(BudgetExceededError, match="Page limit"):
        await tracker.record_page(bytes_size=50, depth=1)
    assert await tracker.get_summary() == snap3


@pytest.mark.asyncio
async def test_budget_tracker_simulated_clock_summary():
    """FRAG-TIME: Validate elapsed time reporting using simulated clock."""
    sim_time = 2000.0

    def clock() -> float:
        return sim_time

    tracker = BudgetTracker(budget=JobBudget(max_pages=5), now_wall=clock)
    await tracker.record_page(bytes_size=100, depth=1)

    summary1 = await tracker.get_summary()
    assert summary1["elapsed_seconds"] == 0.0

    sim_time = 2042.567
    summary2 = await tracker.get_summary()
    assert summary2["elapsed_seconds"] == 42.57


def test_markdown_pipeline():
    html = """
    <html>
      <head><title>Test</title></head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <h1>Main Heading</h1>
        <p>This is paragraph text.</p>
        <footer>Footer text</footer>
      </body>
    </html>
    """
    raw_md, clean_md, fit_md = process_markdown_pipeline(html)
    assert "# Main Heading" in raw_md
    assert "# Main Heading" in clean_md
    assert "Footer text" not in clean_md


def test_table_extraction():
    html = """
    <table>
      <tr><th>Name</th><th>Price</th></tr>
      <tr><td>Item A</td><td>10</td></tr>
      <tr><td>Item B</td><td>20</td></tr>
    </table>
    """
    tables = extract_tables_from_html(html)
    assert len(tables) == 1
    t = tables[0]
    assert t.headers == ["Name", "Price"]
    assert t.json_data == [
        {"Name": "Item A", "Price": "10"},
        {"Name": "Item B", "Price": "20"},
    ]
    assert "| Name | Price |" in t.markdown
