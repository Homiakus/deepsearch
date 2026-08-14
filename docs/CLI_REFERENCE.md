# DeepSearch CLI Reference Manual

The `scraper` Command Line Interface is powered by **Typer** and **Rich**.

```bash
scraper [COMMAND] [OPTIONS] [ARGS]
```

---

## 1. `scraper inspect`

Analyzes target URL heuristics (static content, JS dependencies, API endpoints, visual score, canvas elements) and outputs diagnostic metrics and recommended acquisition strategies.

### Usage
```bash
scraper inspect URL
```

### Example
```bash
scraper inspect https://example.com
```

### Sample Output
```text
┌───────────────────────── Inspect Report for https://example.com ─────────────────────────┐
│ Metric               │ Value                                                             │
├──────────────────────┼───────────────────────────────────────────────────────────────────┤
│ HTTP Status          │ 200                                                               │
│ Content Type         │ text/html; charset=utf-8                                          │
│ Static Content       │ 95.0%                                                             │
│ JS Dependency        │ 5.0%                                                              │
│ Detected APIs        │ 0                                                                 │
│ Tables Count         │ 2                                                                 │
│ Canvas Detected      │ No                                                                │
│ Visual Score         │ 10.0%                                                             │
│ Recommended Strategy │ HTTP                                                              │
│ Estimated Cost       │ LOW                                                               │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. `scraper crawl`

Crawls a URL or domain adaptively using page intelligence heuristics.

### Usage
```bash
scraper crawl URL [OPTIONS]
```

### Options
- `--depth` / `-d` (`int`): Maximum crawl depth. Default: `5`.
- `--max-pages` / `-m` (`int`): Maximum pages to process. Default: `100`.
- `--mode` (`str`): Execution mode (`fast`, `balanced`, `complete`, `research`, `archive`). Default: `balanced`.

### Example
```bash
scraper crawl https://example.com --depth 3 --max-pages 50 --mode balanced
```

---

## 3. `scraper extract`

Fetches a target URL and extracts Clean Markdown and structured records.

### Usage
```bash
scraper extract URL [OPTIONS]
```

### Options
- `--schema` / `-s` (`str`, optional): JSON schema file path for structured extraction validation.

### Example
```bash
scraper extract https://example.com/article
```

---

## 4. `scraper search`

Executes hybrid text vector and visual multivector search over local indexed content.

### Usage
```bash
scraper search QUERY
```

### Example
```bash
scraper search "token bucket rate limiting algorithm"
```

---

## 5. `scraper research`

Runs the autonomous DeepSearch research pipeline: searches queries, crawls pages adaptively, extracts Markdown & structured data, builds RAG text chunks, and outputs a `.zip` archive containing `files/` (links & media) and `rag/` (LLM-ready context).

### Usage
```bash
scraper research --query QUERY [OPTIONS]
```

### Options
- `--query` / `-q` (`str`, required): Search topic or question string.
- `--domain` / `-d` (`str`, optional): Subject domain or domain whitelist filter.
- `--sources` / `-s` (`str`, optional): Comma-separated preferred source seed URLs.
- `--depth` (`int`): Maximum search/crawl depth. Default: `3`.
- `--max-pages` / `-m` (`int`): Maximum pages limit. Default: `50`.
- `--mode` (`str`): Execution mode (`fast`, `balanced`, `complete`, `research`). Default: `balanced`.
- `--output` / `-o` (`str`): Output ZIP file path. Default: `deepsearch_results.zip`.

### Example
```bash
scraper research -q "quantum supremacy algorithms" -d "physics" --depth 2 -m 30 -o quantum_report.zip
```

---

## 6. `scraper mcp`

Launches the DeepSearch Model Context Protocol (MCP) server over standard IO (`stdio`).

### Usage
```bash
scraper mcp
```
