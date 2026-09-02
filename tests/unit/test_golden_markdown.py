"""Golden fixture tests for Markdown & Table extraction pipelines (§12)."""

from scraper.extraction.markdown import process_markdown_pipeline
from scraper.extraction.table_extractor import extract_tables_from_html

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
    <article>
        <h1>Main Heading</h1>
        <p>This is a paragraph with <a href="https://example.com">a link</a> and <strong>bold text</strong>.</p>
        <table>
            <thead>
                <tr><th>Header 1</th><th>Header 2</th></tr>
            </thead>
            <tbody>
                <tr><td>Cell 1</td><td>Cell 2</td></tr>
                <tr><td>Cell 3</td><td>Cell 4</td></tr>
            </tbody>
        </table>
    </article>
</body>
</html>
"""


def test_golden_markdown_conversion():
    """Verify HTML conversion to raw, clean, and fit Markdown format."""
    raw_md, clean_md, fit_md = process_markdown_pipeline(SAMPLE_HTML)
    assert "Main Heading" in clean_md
    assert "bold text" in clean_md


def test_golden_table_extraction():
    """Verify table parser extracts tabular data accurately."""
    tables = extract_tables_from_html(SAMPLE_HTML)
    assert len(tables) == 1
    table = tables[0]
    assert table.headers == ["Header 1", "Header 2"]
    assert len(table.rows) == 2
    assert table.rows[0] == ["Cell 1", "Cell 2"]
    assert table.rows[1] == ["Cell 3", "Cell 4"]
