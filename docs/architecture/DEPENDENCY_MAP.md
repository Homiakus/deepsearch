# Dependency Map & Package Graph

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  

---

## 1. Package Dependencies

```text
scraper.cli ──┐
scraper.api ──┼──> scraper.pipeline ──> scraper.acquisition ──> scraper.config
scraper.mcp ──┤                           │
scraper.ui  ──┘                           ├──> scraper.control
                                          ├──> scraper.extraction
                                          ├──> scraper.normalization
                                          └──> scraper.storage
```

---

## 2. External Third-Party Dependencies

- **FastAPI / Uvicorn**: REST API web framework and ASGI server.
- **Crawlee / Playwright**: Async headless browser automation engine.
- **HTTPX**: Async HTTP client for static content and APIs.
- **SQLAlchemy [asyncio] / AsyncPG**: Async ORM & PostgreSQL driver.
- **Qdrant-Client**: Vector database SDK for text and visual multivectors.
- **Redis**: Async cache and distributed lock store.
- **Zstandard (`zstd`)**: High-ratio stream compression for CAS.
- **FastMCP**: Model Context Protocol stdio server framework.
- **Selectolax / Trafilatura / BeautifulSoup4**: HTML parser and Markdown extraction engines.
- **Typer / Rich**: CLI command parsing and terminal formatting.
- **Pytest / Pytest-AsyncIO**: Unit test framework.
