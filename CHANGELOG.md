# Changelog & Release Audit Notes

All notable changes to DeepSearch are documented in this file in accordance with [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0-rc1] - 2026-09-02 (Pre-release)

### Architecture & Security Hardening (DS-01 .. DS-26)
- **Single Composition Root & Application Service (DS-04, DS-11)**: Introduced unified `DeepSearchService` managing bounded thread pools, HTTP client reuse, in-memory job persistence, and graceful lifecycle shutdown.
- **Hermetic Tests & Minimum CI Gates (DS-02, DS-03)**: Zero external network leakage in test suites; hermetic mocking across Playwright, HTTPX, and Vector storage.
- **SSRF & Network Boundary (DS-07, DS-08)**: Comprehensive private IP, IPv6 mapped IPv4, and loopback resolution blocking in `scraper.security.url_policy`.
- **Unified Configuration Contract (DS-06)**: Consolidated all environment variables, timeouts, and storage paths into a single validated Pydantic model (`DeepSearchSettings`).
- **Research & Discovery Pipeline (DS-12, DS-13, DS-14, DS-15)**: Multi-stage query decomposition, concurrent media/PDF extraction, and deterministic provenance recording (`FieldProvenance`).
- **Surface Harmonization (DS-20, DS-21)**: Parity across CLI (`scraper`), REST API (`/api/v1`), and Model Context Protocol (MCP) server endpoints.
- **Observability & Health (DS-22, DS-23)**: Real-time web dashboard (`/dashboard`), Prometheus exposition (`/metrics`, `/metrics/summary`), and structured execution logs.
- **Container Hardening (DS-24)**: Multi-stage Docker build, non-root `appuser` (UID 10001), isolated Compose profiles, and frozen dependencies.
- **Performance Budgets & Concurrency Bounds (DS-25)**: Deterministic HTML extraction benchmarks, bounded concurrency semaphores, and N+1 API elimination.

### Capability Matrix
| Feature | Status | Protocol / Endpoint | Notes |
|---|---|---|---|
| Page Inspection | Stable | `POST /api/v1/inspect`, CLI `inspect`, MCP `inspect_page` | Headless & HTTP inspection |
| Adaptive Crawling | Stable | `POST /api/v1/crawl`, CLI `crawl`, MCP `crawl_domain` | Respects budget & robots.txt |
| Autonomous Research | Stable | `POST /api/v1/research`, CLI `research`, MCP `deep_research` | Asynchronous JobService |
| Job Status & Management | Stable | `GET /api/v1/jobs/{job_id}`, `DELETE /api/v1/jobs/{job_id}` | In-memory + durable store |
| Metrics Exposition | Stable | `GET /metrics`, `GET /metrics/summary` | Prometheus text + JSON summary |
| Vector & Hybrid Search | Stable | FastEmbed + Qdrant | Dense/sparse embeddings |
| Multi-stage Docker | Stable | `Dockerfile`, `docker-compose.yml` | Non-root security profile |

### Upgrade & Downgrade Notes
- **Upgrading from 0.x**: Configuration must be provided via `DEEPSEARCH_*` environment variables or `.env` file conforming to `DeepSearchSettings`. Legacy config dictionaries are deprecated.
- **Downgrading**: If rolling back to previous prototypes, ensure persistent SQLite DB schemas in `~/.deepsearch` are backed up or migrated.
