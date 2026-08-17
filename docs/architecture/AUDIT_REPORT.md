# Audit Report (Architecture & Code Quality Baseline)

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Audit Date:** 2026-08-16  
**Orchestration Engine:** Axiom ADGO (`github.com/Homiakus/axiom/adgo`)  

---

## 1. Executive Summary

The DeepSearch codebase is structured with clear subsystem separation. Architectural refinement is focused on:
1. Unifying user interfaces (CLI, REST, MCP) behind a single `ResearchApplicationService`.
2. Transitioning long-running orchestration to Axiom ADGO as the durable control plane.
3. Replacing mock search/retrieval with real Qdrant hybrid retrieval (dense + sparse + reranker).
4. Integrating Crawlee for URL frontier management and enforcing budget, rate limits, robots, and SSRF security across all network paths.

---

## 2. Subsystem Status Matrix

| Subsystem | Primary Path | Classification | Status |
| :--- | :--- | :--- | :--- |
| `application/research_service.py` | Unified application boundary | `ACTIVE` | Operational |
| `orchestration/` | Axiom ADGO remote worker & coordinator | `ACTIVE` | Operational |
| `security/url_policy.py` | Comprehensive SSRF & network policy | `ACTIVE` | Verified & Enforced |
| `control/rate_limiter.py` | Host rate limiter & concurrency bounds | `ACTIVE` | Enforced |
| `control/budget.py` | Resource metering & hard limit enforcement | `ACTIVE` | Enforced |
| `retrieval/` | FastEmbed dense/sparse & Qdrant hybrid search | `ACTIVE` | Integrated |
| `evidence/` | Claims, contradiction analysis & coverage evaluation | `ACTIVE` | Integrated |
| `acquisition/crawlee_adapter.py` | Bounded batch crawling via Crawlee RequestQueue | `ACTIVE` | Integrated |
| `visual/pixel_rag.py` | Visual multivector retrieval | `EXPERIMENTAL` | Gated Feature |
| `control/scheduler.py` (legacy) | Unbounded in-memory queue | `DEPRECATED` | Replaced by Crawlee/ADGO |
