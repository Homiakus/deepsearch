# DeepSearch — User Guide & Manual

---

## Table of Contents

1. [Installation & Setup](#installation--setup)
2. [CLI Usage Guide](#cli-usage-guide)
3. [REST API Service](#rest-api-service)
4. [DeepSearch Research Pipeline](#deepsearch-research-pipeline)
5. [Model Context Protocol (MCP) Integration](#model-context-protocol-mcp-integration)
6. [Docker Production Deployment](#docker-production-deployment)
7. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Installation & Setup

### Requirements
- **Python**: 3.11, 3.12, or 3.13
- **OS**: Windows, macOS, or Linux
- **Optional Services**: PostgreSQL 16+ (with pgvector), Redis 7+, Qdrant 1.8+

### Step-by-Step Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-repo/deepsearch.git
cd deepsearch

# 2. Create and activate a virtual environment (optional but recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Install the package in editable mode
pip install -e .

# 4. Install Playwright Chromium headless browser engine
playwright install chromium

# 5. Verify installation by running unit tests
python -m pytest tests/unit
```

---

## CLI Usage Guide

The platform provides a unified command line interface via `scraper`.

### 1. URL Inspection (`scraper inspect`)
Analyzes target URL heuristics (static content, JS dependencies, API endpoints, visual score, canvas elements) and outputs recommended acquisition strategies:

```bash
scraper inspect https://news.ycombinator.com
```

### 2. Adaptive Crawling (`scraper crawl`)
Executes an adaptive crawling task:

```bash
scraper crawl https://example.com --depth 3 --max-pages 100 --mode balanced
```

Options:
- `--depth` / `-d`: Maximum link follow depth (default: 5)
- `--max-pages` / `-m`: Maximum pages to crawl (default: 100)
- `--mode`: Execution mode (`fast`, `balanced`, `complete`, `research`, `archive`)

### 3. Content Extraction (`scraper extract`)
Fetches and converts target page content into token-optimized Clean Markdown:

```bash
scraper extract https://example.com/article
```

### 4. Hybrid Multivector Search (`scraper search`)
Searches local indexed content using text vector similarity and PixelRAG visual multivectors:

```bash
scraper search "machine learning pipeline"
```

### 5. Research Pipeline (`scraper research`)
Runs an autonomous deep research pipeline and packages findings into a `.zip` archive:

```bash
scraper research --query "quantum computing algorithms" --depth 3 --max-pages 50 --output quantum_research.zip
```

### 6. MCP Server (`scraper mcp`)
Launches the Model Context Protocol stdio server:

```bash
scraper mcp
```

---

## REST API Service

### Launching the API Server

```bash
uvicorn scraper.api.app:app --host 0.0.0.0 --port 8080
```

- **Interactive Documentation (Swagger UI)**: [`http://localhost:8080/docs`](http://localhost:8080/docs)
- **Web UI Dashboard**: [`http://localhost:8080/ui`](http://localhost:8080/ui)
- **Metrics Endpoint**: [`http://localhost:8080/api/v1/metrics/summary`](http://localhost:8080/api/v1/metrics/summary)

### Key Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Service health status |
| `GET` | `/api/v1/metrics/summary` | Telemetry & Prometheus metrics |
| `POST` | `/api/v1/inspect` | Inspect URL heuristics & cost estimate |
| `POST` | `/api/v1/crawl` | Start asynchronous domain crawl job |
| `GET` | `/api/v1/crawl/{job_id}` | Retrieve crawl job status |
| `POST` | `/api/v1/search/text` | Text vector similarity search |
| `POST` | `/api/v1/search/visual` | Visual multivector PixelRAG search |
| `POST` | `/api/v1/search/hybrid` | Combined text and visual search |
| `POST` | `/api/v1/research` | Execute full research pipeline & return zip archive |

---

## DeepSearch Research Pipeline

The Research Pipeline (`scraper.pipeline.search_pipeline.DeepSearchPipeline`) executes end-to-end knowledge acquisition:

1. **Discovery & Search**: Queries search engines or preferred domains to discover candidate URLs.
2. **Adaptive Acquisition**: Fetches pages using HTTP or Playwright Chromium based on page intelligence scores.
3. **Extraction & Sanitization**: Extracts clean Markdown, normalized tables, and media assets.
4. **RAG Chunking**: Chunks text content for LLM ingestion.
5. **Archive Packaging**: Produces a `.zip` archive with the following directory layout:

```text
research_output.zip
├── manifest.json              # Search query metadata & execution metrics
├── files/                     # Markdown files, links, and media assets
│   ├── page_1.md
│   └── page_2.md
└── rag/                       # Token-optimized LLM context chunks
    ├── chunk_001.json
    └── chunk_002.json
```

---

## Model Context Protocol (MCP) Integration

DeepSearch includes a built-in MCP server compatible with **Claude Desktop** and **Claude Code**.

### Integration with Claude Code

The `.mcp/config.json` file in the root directory enables MCP automatically when opening Claude Code in the workspace:

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "python",
      "args": ["-m", "scraper.cli.main", "mcp"]
    }
  }
}
```

### Exposed MCP Tools

1. `deepsearch_research(query, domain, preferred_sources, depth, max_pages, mode, output_archive, category, auto_discover)` — Autonomous research pipeline execution.
2. `deepsearch_discover(query, domain, preferred_sources, category)` — Discovers diverse seed URLs from ArXiv, Europe PMC, PubMed, Wikipedia, and Anna's Archive.
3. `deepsearch_inspect(url)` — Diagnostic inspection of target URL heuristics.
4. `deepsearch_extract(url)` — Converts page HTML to Clean Markdown and extracts tables.
5. `deepsearch_search(query, limit)` — Hybrid text vector and visual multivector search.

---

## Docker Production Deployment

Deploy the entire infrastructure stack using Docker Compose:

```bash
docker compose up --build -d
```

### Services Stack

- **`scraper-api`**: FastAPI service running `scraper.api.app` (`:8080`)
- **`postgres`**: PostgreSQL 16 + pgvector for metadata & embeddings (`:5432`)
- **`redis`**: Redis lock & Request Frontier queue (`:6379`)
- **`qdrant`**: Qdrant Vector Engine (`:6333`)
- **`minio`**: Object Storage for large assets (`:9000`, console `:9001`)

---

## Troubleshooting & FAQ

### 1. Playwright Browser Fails to Launch
- **Issue**: `playwright._impl._errors.Error: Executable doesn't exist at...`
- **Fix**: Run `playwright install chromium` in your environment.

### 2. High Memory Usage During Large Crawls
- **Fix**: Set `MODE=fast` or decrease `BUDGET__MAX_PAGES` and `LIMITS__MAX_HOST_CONCURRENCY` in `.env`.

### 3. DNS SSRF Errors When Scraping Local Addresses
- **Issue**: `SecurityViolationError: SSRF policy blocked access to private IP...`
- **Fix**: By default, `SECURITY__BLOCK_PRIVATE_IPS=true` prevents probing local subnets (`127.0.0.1`, `192.168.x.x`). Set `SECURITY__BLOCK_PRIVATE_IPS=false` in `.env` only if testing local mock services.
