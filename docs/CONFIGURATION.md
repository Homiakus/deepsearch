# DeepSearch Configuration Reference

Configuration is managed via Environment Variables or a local `.env` file using **Pydantic BaseSettings**.

Nested settings utilize double underscores (`__`) as delimiters (e.g., `ADAPTIVE__BROWSER_THRESHOLD=0.75`).

---

## 1. Application & Server Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `APP_NAME` | `str` | `"DeepSearch Adaptive Scraper"` | Application name |
| `APP_VERSION` | `str` | `"1.0.0"` | Platform version |
| `MODE` | `str` | `"balanced"` | Default execution mode: `fast`, `balanced`, `complete`, `research`, `archive` |
| `DEBUG` | `bool` | `false` | Enable verbose debug logging |
| `API_HOST` | `str` | `"0.0.0.0"` | Host IP binding for FastAPI REST server |
| `API_PORT` | `int` | `8080` | Port number for FastAPI REST server |
| `API_KEY` | `str` | `"dev-secret"` | Authentication Bearer token |

---

## 2. Infrastructure & Storage Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | `str` | `postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch` | PostgreSQL connection string |
| `REDIS_URL` | `str` | `redis://localhost:6379/0` | Redis DSN for Request Frontier locks & queue |
| `QDRANT_URL` | `str` | `http://localhost:6333` | Qdrant vector database URL |
| `STORAGE_PATH` | `str` | `./data/storage` | Path for Content Addressable Storage (CAS) |

---

## 3. Operational Sub-Configurations

### 3.1 Adaptive Decision Policy (`ADAPTIVE__*`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `ADAPTIVE__BROWSER_THRESHOLD` | `float` | `0.70` | JS dependency score threshold to trigger Playwright Browser escalation |
| `ADAPTIVE__VISUAL_THRESHOLD` | `float` | `0.65` | Visual need score threshold for PixelRAG screenshot indexing |
| `ADAPTIVE__API_PREFERENCE` | `bool` | `true` | Prefer detected direct JSON API over browser rendering |
| `ADAPTIVE__RETRY_HTTP_BEFORE_BROWSER` | `bool` | `true` | Retry HTTP requests with headers prior to Playwright escalation |

### 3.2 Robots & Crawler Identity (`ROBOTS__*`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `ROBOTS__RESPECT` | `bool` | `true` | Enforce `robots.txt` disallow rules |
| `ROBOTS__USER_AGENT` | `str` | `Mozilla/5.0 ... Chrome/122.0.0.0` | Default User-Agent string |

### 3.3 Rate Limiting & Concurrency (`LIMITS__*`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `LIMITS__GLOBAL_RPS` | `float` | `500.0` | Global maximum requests per second |
| `LIMITS__DEFAULT_HOST_RPS` | `float` | `5.0` | Default maximum requests per second per host |
| `LIMITS__MAX_HOST_CONCURRENCY` | `int` | `8` | Maximum concurrent requests per host |
| `LIMITS__AUTO_CONCURRENCY` | `bool` | `true` | Autoscale host concurrency based on latency |
| `LIMITS__PER_HOST_ADAPTIVE` | `bool` | `true` | Dynamically lower rate limits on 429/503 responses |

### 3.4 Security & SSRF Protection (`SECURITY__*`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `SECURITY__MAX_RESPONSE_SIZE_BYTES` | `int` | `104857600` (100MB) | Max raw HTTP response size |
| `SECURITY__MAX_DECOMPRESSED_SIZE_BYTES` | `int` | `524288000` (500MB) | Max decompressed size (zip bomb protection) |
| `SECURITY__MAX_REDIRECTS` | `int` | `10` | Max HTTP redirects allowed |
| `SECURITY__BLOCK_PRIVATE_IPS` | `bool` | `true` | Pre-check DNS resolution to block private IPs (SSRF protection) |
| `SECURITY__ALLOWED_PROTOCOLS` | `list[str]` | `["http", "https"]` | Allowed URI schemes |

### 3.5 Resource Budgeting (`BUDGET__*`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `BUDGET__MAX_PAGES` | `int` | `50000` | Maximum pages processed per crawl job |
| `BUDGET__MAX_DEPTH` | `int` | `10` | Maximum crawl depth |
| `BUDGET__MAX_BYTES` | `int` | `10737418240` (10GB) | Maximum total network bytes per job |
| `BUDGET__BROWSER_SECONDS` | `int` | `3600` | Max Playwright execution time in seconds |
| `BUDGET__LLM_TOKENS` | `int` | `1000000` | Max LLM token budget |
| `BUDGET__VISUAL_PAGES` | `int` | `5000` | Max visual pages for PixelRAG |

### 3.6 Strategy Cost Weights (`COST__*`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `COST__CACHE` | `float` | `0.0` | Relative cost of CAS lookup |
| `COST__HTTP` | `float` | `1.0` | Relative cost of static HTTP request |
| `COST__API` | `float` | `1.0` | Relative cost of Direct API call |
| `COST__BROWSER` | `float` | `10.0` | Relative cost of Playwright Chromium execution |
| `COST__LLM` | `float` | `30.0` | Relative cost of LLM processing |
| `COST__VISUAL_VLM` | `float` | `50.0` | Relative cost of Visual VLM processing |

---

## 4. Production `.env` Example

```env
APP_NAME="DeepSearch Production"
MODE="balanced"
DEBUG=false

API_HOST="0.0.0.0"
API_PORT=8080
API_KEY="your-secure-random-secret-key"

DATABASE_URL="postgresql+asyncpg://deepsearch:secretpass@postgres.prod:5432/deepsearch"
REDIS_URL="redis://redis.prod:6379/0"
QDRANT_URL="http://qdrant.prod:6333"
STORAGE_PATH="/var/data/deepsearch/storage"

ADAPTIVE__BROWSER_THRESHOLD=0.70
LIMITS__DEFAULT_HOST_RPS=10.0
SECURITY__BLOCK_PRIVATE_IPS=true
BUDGET__MAX_PAGES=100000
```
