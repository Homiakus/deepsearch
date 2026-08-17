# DeepSearch Browser Acquisition Baseline Reference

## Status
Established for reference against Rust acquisition worker, Servo, Chromium, and experimental engines.

## Methodology
Baseline measures:
1. Direct HTTPX (`HTTPFetcher`) path.
2. Playwright Chromium (`BrowserPoolManager`) path.
3. Memory overhead (RSS delta).
4. Text extraction recall and quality score.

## Target Gates for Rust Tier
- HTTP path: ≥ 2x throughput, < 50% RSS per worker.
- Servo Tier: ≥ 95% static/SSR recall, ≥ 80% SPA recall before promotion.
- Chromium Tier: Isolated bounded contexts, zero zombie browser processes on cancellation.
