"""Unit tests for Budget Manager (§50) and Extraction Engine (§31, §35, §36)."""

import pytest
from scraper.control.budget import BudgetTracker, JobBudget, BudgetExceededError
from scraper.extraction.markdown import process_markdown_pipeline
from scraper.extraction.table_extractor import extract_tables_from_html


@pytest.mark.asyncio
async def test_budget_exceeded():
    tracker = BudgetTracker(budget=JobBudget(max_pages=2))
    await tracker.record_page(bytes_size=100, depth=1)
    await tracker.record_page(bytes_size=100, depth=1)
    with pytest.raises(BudgetExceededError):
        await tracker.record_page(bytes_size=100, depth=1)


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
