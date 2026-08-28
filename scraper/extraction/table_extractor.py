"""Table Extraction Engine (§36)."""

import csv
import io
from typing import List, Dict, Any, Optional
from selectolax.parser import HTMLParser
from pydantic import BaseModel, Field


class TableData(BaseModel):
    table_index: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    html: str = ""
    json_data: List[Dict[str, Any]] = Field(default_factory=list)
    csv: str = ""
    markdown: str = ""


def _clean_cell_text(text: Optional[str]) -> str:
    """Sanitize cell text: normalize whitespace and remove lone control characters."""
    if not text:
        return ""
    return " ".join(text.strip().split())


def _escape_markdown_cell(text: str) -> str:
    """Escape pipes and linebreaks for safe single-line markdown table cells."""
    if not text:
        return ""
    # Replace line breaks with space to prevent breaking markdown table rows
    sanitized = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    # Escape pipe characters
    sanitized = sanitized.replace("|", r"\|")
    return " ".join(sanitized.strip().split())


def extract_tables_from_html(raw_html: str) -> List[TableData]:
    """Extracts tables from HTML simultaneously into HTML, JSON, CSV, and Markdown (§36).

    Correctly handles rowspan, colspan, unequal rows, and escaped characters.
    """
    if not raw_html:
        return []

    parser = HTMLParser(raw_html)
    tables: List[TableData] = []

    for idx, table_node in enumerate(parser.css("table")):
        table_html = table_node.html or ""

        # 2D Grid representing normalized table cells
        grid: List[List[Optional[str]]] = []
        is_header_grid: List[List[bool]] = []
        is_thead_row: List[bool] = []

        all_trs = table_node.css("tr")
        if not all_trs:
            continue

        row_idx = 0
        for tr in all_trs:
            # Determine if this row is inside <thead>
            in_thead = False
            curr = tr.parent
            while curr is not None:
                if curr.tag == "thead":
                    in_thead = True
                    break
                if curr.tag == "table":
                    break
                curr = curr.parent

            while len(grid) <= row_idx:
                grid.append([])
                is_header_grid.append([])
                is_thead_row.append(False)

            is_thead_row[row_idx] = in_thead

            col_idx = 0
            # Process th and td elements
            cells = tr.css("th, td")
            for cell in cells:
                # Advance to next unoccupied column in this row
                while (
                    col_idx < len(grid[row_idx]) and grid[row_idx][col_idx] is not None
                ):
                    col_idx += 1

                # Parse rowspan and colspan
                try:
                    rowspan = int(cell.attributes.get("rowspan", 1) or 1)
                except (ValueError, TypeError):
                    rowspan = 1
                try:
                    colspan = int(cell.attributes.get("colspan", 1) or 1)
                except (ValueError, TypeError):
                    colspan = 1

                rowspan = max(1, min(rowspan, 100))
                colspan = max(1, min(colspan, 50))

                cell_text = _clean_cell_text(cell.text())
                is_th = (cell.tag == "th") or in_thead

                # Populate grid
                while len(grid) < row_idx + rowspan:
                    grid.append([])
                    is_header_grid.append([])
                    is_thead_row.append(False)

                for r in range(row_idx, row_idx + rowspan):
                    while len(grid[r]) < col_idx + colspan:
                        grid[r].append(None)
                        is_header_grid[r].append(False)
                    for c in range(col_idx, col_idx + colspan):
                        grid[r][c] = cell_text
                        is_header_grid[r][c] = is_th

                col_idx += colspan

            row_idx += 1

        # Calculate max columns across all rows
        max_cols = max((len(r) for r in grid), default=0)
        if max_cols == 0:
            continue

        # Normalize grid (fill None and pad unequal rows with "")
        normalized_grid: List[List[str]] = []
        for r_cells in grid:
            norm_r = [c if c is not None else "" for c in r_cells]
            while len(norm_r) < max_cols:
                norm_r.append("")
            normalized_grid.append(norm_r)

        # Detect header rows vs data rows
        header_row_count = 0
        for r_idx, (r_thead, r_hdrs) in enumerate(zip(is_thead_row, is_header_grid)):
            if r_thead or (r_hdrs and all(r_hdrs)):
                header_row_count += 1
            else:
                break

        if header_row_count > 0:
            # If multi-row header, the last header row has the lowest-level headers with rowspans carried over
            headers = [
                h if h else f"col_{c_idx + 1}"
                for c_idx, h in enumerate(normalized_grid[header_row_count - 1])
            ]
            data_rows = normalized_grid[header_row_count:]
        else:
            # No distinct header row: check if row 0 has any <th>
            if is_header_grid and any(is_header_grid[0]):
                headers = [
                    h if h else f"col_{c_idx + 1}"
                    for c_idx, h in enumerate(normalized_grid[0])
                ]
                data_rows = normalized_grid[1:]
            else:
                headers = [f"col_{i + 1}" for i in range(max_cols)]
                data_rows = normalized_grid

        # Ensure headers length matches max_cols
        while len(headers) < max_cols:
            headers.append(f"col_{len(headers) + 1}")

        # 1. JSON representation
        # Ensure unique dictionary keys
        seen_keys: Dict[str, int] = {}
        unique_headers = []
        for h in headers:
            base_key = h or "col"
            count = seen_keys.get(base_key, 0)
            if count == 0:
                unique_headers.append(base_key)
            else:
                unique_headers.append(f"{base_key}_{count + 1}")
            seen_keys[base_key] = count + 1

        json_data = []
        for r in data_rows:
            row_dict = {}
            for i, val in enumerate(r):
                key = unique_headers[i] if i < len(unique_headers) else f"col_{i + 1}"
                row_dict[key] = val
            json_data.append(row_dict)

        # 2. CSV representation
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        if headers:
            writer.writerow(headers)
        writer.writerows(data_rows)
        csv_str = csv_buffer.getvalue()

        # 3. Markdown representation
        md_lines = []
        if headers:
            md_lines.append(
                "| " + " | ".join(_escape_markdown_cell(h) for h in headers) + " |"
            )
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for r in data_rows:
            md_lines.append(
                "| " + " | ".join(_escape_markdown_cell(cell) for cell in r) + " |"
            )
        md_str = "\n".join(md_lines)

        tables.append(
            TableData(
                table_index=idx,
                headers=headers,
                rows=data_rows,
                html=table_html,
                json_data=json_data,
                csv=csv_str,
                markdown=md_str,
            )
        )

    return tables
