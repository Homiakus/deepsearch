# DeepSearch Model Context Protocol (MCP) Integration Guide

DeepSearch provides native support for the **Model Context Protocol (MCP)**, allowing AI models, coding assistants (Claude Code, Claude Desktop, Antigravity, VS Code, Cursor), and custom **Python** or **Go** microservices to interact directly with the web scraping, search, and research engine.

---

## 1. Fast MCP Server Overview

The MCP server module (`scraper/mcp/server.py`) uses `FastMCP` over standard IO (`stdio`).

It registers 5 tools:

| MCP Tool | Function | Description |
|---|---|---|
| `deepsearch_research` | Autonomous Research Pipeline | Performs end-to-end multi-source research, crawls pages, extracts content, scores & archives 5–25 topic images in `media/`, and returns zip location (`files/` + `media/` + `rag/`). |
| `deepsearch_discover` | Multi-Source Seed Finder | Queries ArXiv, Wikipedia, and academic domain sources to return candidate seed URLs. |
| `deepsearch_inspect` | Diagnostic Page Inspection | Analyzes URL static score, JS dependency, detected APIs, canvas elements, and strategy cost. |
| `deepsearch_extract` | Clean Content Extraction | Converts HTML into LLM-optimized Clean Markdown, Fit Markdown, and extracts tables. |
| `deepsearch_search` | Hybrid Multivector Search | Performs combined text vector and PixelRAG visual multivector search over indexed content. |

---

## 2. Launching & Managing the MCP Server Locally

### 2.1 Using the Management Script (`mcp_manager.py`)

A dedicated management tool `scripts/mcp_manager.py` is included for health checks, auto-config generation, and starting the server:

```bash
# 1. Health check stdio JSON-RPC handshake
python scripts/mcp_manager.py test

# 2. Output ready-to-copy JSON configs for Claude / Cursor / VS Code
python scripts/mcp_manager.py config

# 3. Start MCP Server over stdio
python scripts/mcp_manager.py start
```

### 2.2 Using the PowerShell Helper (`run_mcp.ps1`)

On Windows, use `run_mcp.ps1`:

```powershell
# Run health check
.\run_mcp.ps1 test

# Generate client configurations
.\run_mcp.ps1 config

# Start server
.\run_mcp.ps1 start
```

---

## 3. Configuration for Standard LLM Clients

### 3.1 Claude Desktop Setup

Add to `claude_desktop_config.json`:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Programms/202-Programming-Projects/deepsearch",
        "run",
        "python",
        "-m",
        "scraper.mcp.server"
      ]
    }
  }
}
```

### 3.2 Cursor / VS Code / Antigravity Setup

Save to `.mcp/mcp.json` or your IDE settings:

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "C:/Users/KDFX Modes/AppData/Local/Programs/Python/Python313/python.exe",
      "args": [
        "-m",
        "scraper.mcp.server"
      ],
      "cwd": "D:/Programms/202-Programming-Projects/deepsearch",
      "env": {
        "PYTHONPATH": "D:/Programms/202-Programming-Projects/deepsearch"
      }
    }
  }
}
```

---

## 4. Connecting from Custom Python & Go Applications

Detailed code examples, stdio subprocess launching, and parameter parsing for external Python and Go microservices are available in the dedicated guide:

👉 **[MCP Client Connectivity Guide (Python & Go)](file:///d:/Programms/202-Programming-Projects/deepsearch/docs/MCP_CLIENT_CONNECTIVITY.md)**

---

## 5. Tool Reference & Input Models

### `deepsearch_research`
- **Parameters**:
  - `query` (str): Search topic or prompt
  - `domain` (str, optional): Target domain filter
  - `preferred_sources` (list[str], optional): Whitelisted seed URLs
  - `depth` (int, default: 3): Max crawl depth
  - `max_pages` (int, default: 50): Max pages to acquire
  - `mode` (str, default: `"balanced"`): Strategy execution mode (`fast`, `balanced`, `complete`, `research`)
  - `output_archive` (str, optional): Destination `.zip` path
  - `category` (str, optional): Category hint (`science`, `news`, `engineering`)
  - `auto_discover` (bool, default: `true`): Enable automated seed discovery
- **Return Value**: JSON string containing summary metrics, manifest, and generated archive path.

### `deepsearch_discover`
- **Parameters**:
  - `query` (str): Search query or question
  - `domain` (str, optional): Domain scope hint
  - `preferred_sources` (list[str], optional): User seed URLs
  - `category` (str, optional): Query category hint
- **Return Value**: JSON string listing discovered seed URLs from ArXiv, Wikipedia, and domain providers.

### `deepsearch_inspect`
- **Parameters**:
  - `url` (str): Target URL
- **Return Value**: JSON string containing `static_score`, `js_dependency_score`, `detected_apis_count`, `tables_count`, `visual_score`, and `recommended_strategy`.

### `deepsearch_extract`
- **Parameters**:
  - `url` (str): Target URL
- **Return Value**: JSON string containing `clean_markdown`, `fit_markdown`, `tables_count`, and `extracted_records_count`.

### `deepsearch_search`
- **Parameters**:
  - `query` (str): Search query string
  - `limit` (int, default: 10): Max results
- **Return Value**: JSON string array of `SearchResultItem` records.

