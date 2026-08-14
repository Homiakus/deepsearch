"""Table Extraction Engine (§36)."""

import csv
import io
from typing import List, Dict, Any
from selectolax.parser import HTMLParser


from pydantic import BaseModel


class TableData(BaseModel):
    table_index: int
    headers: List[str]
    rows: List[List[str]]
    html: str
    json_data: List[Dict[str, Any]]
    csv: str
    markdown: str


def extract_tables_from_html(raw_html: str) -> List[TableData]:
    """Extracts tables from HTML simultaneously into HTML, JSON, CSV, and Markdown (§36)."""
    if not raw_html:
        return []

    parser = HTMLParser(raw_html)
    tables: List[TableData] = []

    for idx, table_node in enumerate(parser.css("table")):
        table_html = table_node.html or ""

        # Extract headers
        headers = []
        for th in table_node.css("th"):
            headers.append(th.text().strip())

        # Extract rows
        rows = []
        for tr in table_node.css("tr"):
            row_cells = [td.text().strip() for td in tr.css("td")]
            if row_cells:
                rows.append(row_cells)

        if not headers and rows:
            # Fallback headers if th tag was missing
            headers = [f"col_{i+1}" for i in range(len(rows[0]))]

        # 1. JSON representation
        json_data = []
        for r in rows:
            row_dict = {}
            for i, val in enumerate(r):
                key = headers[i] if i < len(headers) else f"col_{i+1}"
                row_dict[key] = val
            json_data.append(row_dict)

        # 2. CSV representation
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        if headers:
            writer.writerow(headers)
        writer.writerows(rows)
        csv_str = csv_buffer.getvalue()

        # 3. Markdown representation
        md_lines = []
        if headers:
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for r in rows:
            md_lines.append("| " + " | ".join(r) + " |")
        md_str = "\n".join(md_lines)

        tables.append(TableData(
            table_index=idx,
            headers=headers,
            rows=rows,
            html=table_html,
            json_data=json_data,
            csv=csv_str,
            markdown=md_str
        ))

    return tables
