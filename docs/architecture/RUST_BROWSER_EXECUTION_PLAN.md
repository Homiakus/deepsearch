# DeepSearch — план внедрения Rust browser execution layer

**Статус:** ✅ Реализовано (Core Execution Layer, Capabilities, Planner, Security, Backends, ADGO Integration, CI/CD)  
**Ветка:** `main`  
**Связан с:** `docs/architecture/IMPROVEMENT_PLAN_AXIOM.md`  
**Область:** acquisition / crawling / browser rendering / Axiom ADGO workers

---

# 0. Цель

Цель этого плана — уменьшить стоимость и хрупкость web acquisition в DeepSearch за счёт специализированного Rust execution layer, не теряя совместимость с современными JavaScript-сайтами.

Текущую схему:

```text
HTTPX
  ↓
эвристика
  ↓
Playwright + Chromium
```

нужно постепенно заменить на:

```text
                              ┌─ HTTP / Spider
URL → capability planner ─────┼─ Servo
                              ├─ experimental backend
                              └─ Chromium fallback
```

при этом:

```text
Axiom ADGO
= durable coarse-grained orchestration

Rust acquisition worker
= URL acquisition / browser selection / rendering

Python DeepSearch
= extraction / normalization / evidence / retrieval / synthesis
```

Главный принцип:

> Chromium не удаляется. Он перестаёт быть первым и единственным полноценным browser backend и становится compatibility fallback.

---

# 1. Почему изменение нужно делать архитектурно, а не заменой одной библиотеки

В текущем `scraper/acquisition/engine.py` browser escalation напрямую предполагает один `BrowserPoolProtocol`, а default implementation — `BrowserPoolManager` на Playwright Chromium.

Текущий `BrowserPoolProtocol` описывает не capability contract браузера, а конкретную форму `fetch_page(...)`. Поэтому простая замена Playwright на Servo создаст вторую реализацию того же монолитного контракта и быстро приведёт к условиям вида:

```python
if backend == "servo":
    ...
elif backend == "chromium":
    ...
```

Это запрещённый целевой результат.

Нужно сначала отделить:

1. **что требуется от страницы**;
2. **какие возможности предоставляет backend**;
3. **какая стоимость backend**;
4. **какой результат считается достаточным**;
5. **когда необходим escalation**.

---

# 2. Целевая архитектура

```text
CLI / REST / MCP
        │
        ▼
ResearchApplicationService
        │
        ▼
Axiom ADGO Coordinator
        │
        │ durable AcquireBatch activity
        ▼
┌──────────────────────────────────────────────────┐
│ Rust Acquisition Worker                          │
│                                                  │
│  Request Normalizer                              │
│         ↓                                        │
│  Security Policy                                 │
│         ↓                                        │
│  Backend Planner                                 │
│         ↓                                        │
│  ┌────────┬────────┬──────────────┬────────────┐  │
│  │ HTTP   │ Servo  │ Experimental │ Chromium   │  │
│  │ Spider │        │ BrowserOxide │ fallback   │  │
│  └────────┴────────┴──────────────┴────────────┘  │
│         ↓                                        │
│  Quality Evaluator                               │
│         ↓                                        │
│  Escalate / Accept                               │
│         ↓                                        │
│  CAS Artifact Writer                             │
└───────────────┬──────────────────────────────────┘
                │
                ▼
         ArtifactReference
                │
                ▼
Python extraction / normalization / evidence / index
```

---

# 3. Роли движков

## 3.1 HTTP / Spider

Назначение:

- самый дешёвый сетевой путь;
- статические HTML/JSON/XML/PDF ресурсы;
- discovery и URL crawling;
- concurrency / retry / host-level scheduling;
- не запускать browser runtime без доказанной необходимости.

Приоритет: **P0**.

Рассматривать `spider-rs/spider` как основной кандидат для Rust HTTP/crawl worker, но не связывать domain contract DeepSearch с API Spider.

---

## 3.2 Servo

Назначение:

- независимый Rust browser engine;
- DOM + CSS + JS execution;
- offscreen rendering;
- промежуточный browser tier между HTTP и Chromium.

Приоритет: **P0 experimental → production candidate**.

Servo не должен становиться обязательной зависимостью всего DeepSearch до прохождения benchmark gates.

---

## 3.3 Chromium fallback

Назначение:

- максимальная compatibility;
- сложные SPA;
- проблемные Web APIs;
- anti-bot-sensitive flows;
- fallback при недостаточном качестве Servo.

Приоритет: **P0 mandatory fallback**.

Rust adapter выбирать между:

- `chromiumoxide`;
- `Chromey`;
- другим CDP adapter только после benchmark.

Playwright сохранить на переходный период как reference backend и аварийный rollback path.

---

## 3.4 BrowserOxide

Назначение:

- R&D backend;
- тестирование возможности ещё более дешёвого native browser execution;
- сравнение с Servo и Chromium.

Приоритет: **P1 experimental only**.

Нельзя включать его в production routing до прохождения corpus benchmark, security review и crash/leak soak tests.

---

## 3.5 Blitz

Назначение:

- дешёвый HTML/CSS layout renderer;
- screenshot/layout use cases, где полноценный JavaScript runtime не нужен;
- потенциальная оптимизация visual extraction.

Приоритет: **P2**.

Blitz не должен стоять в обязательной линейной цепочке acquisition. Он выбирается только при наличии capability `layout_render` / `screenshot_static`.

---

# 4. Главный architectural invariant

Не использовать линейное предположение:

```text
HTTP < Servo < Chromium
```

Вместо этого использовать capabilities.

Пример:

```text
required:
  javascript: true
  screenshot: false
  network_capture: true
  webgl: false

Servo:
  javascript: true
  screenshot: true
  network_capture: true
  webgl: partial

Chromium:
  javascript: true
  screenshot: true
  network_capture: true
  webgl: true
```

Planner выбирает минимально дорогой backend, удовлетворяющий hard requirements.

---

# 5. Целевое дерево новых файлов

```text
rust/
└── acquisition-worker/
    ├── Cargo.toml
    ├── Cargo.lock
    ├── README.md
    ├── src/
    │   ├── main.rs
    │   ├── lib.rs
    │   │
    │   ├── config.rs
    │   ├── error.rs
    │   ├── models.rs
    │   ├── capabilities.rs
    │   ├── planner.rs
    │   ├── quality.rs
    │   ├── telemetry.rs
    │   │
    │   ├── security/
    │   │   ├── mod.rs
    │   │   ├── url_policy.rs
    │   │   ├── dns_policy.rs
    │   │   ├── redirect_policy.rs
    │   │   └── network_policy.rs
    │   │
    │   ├── backends/
    │   │   ├── mod.rs
    │   │   ├── http.rs
    │   │   ├── servo.rs
    │   │   ├── chromium.rs
    │   │   ├── browseroxide.rs
    │   │   └── blitz.rs
    │   │
    │   ├── artifacts/
    │   │   ├── mod.rs
    │   │   ├── writer.rs
    │   │   └── manifest.rs
    │   │
    │   ├── adgo/
    │   │   ├── mod.rs
    │   │   ├── client.rs
    │   │   ├── activity.rs
    │   │   └── heartbeat.rs
    │   │
    │   └── service/
    │       ├── mod.rs
    │       └── local_api.rs
    │
    ├── tests/
    │   ├── contract.rs
    │   ├── security.rs
    │   ├── planner.rs
    │   ├── quality.rs
    │   ├── crash_recovery.rs
    │   └── fixtures/
    │
    └── benches/
        ├── acquisition.rs
        └── corpus.rs
```

Python changes:

```text
scraper/acquisition/
├── models.py                 # shared Python-side acquisition DTO
├── capabilities.py           # Python representation of required capabilities
├── rust_worker_client.py     # only local/compatibility mode
├── result_adapter.py         # ArtifactReference → CapturedArtifact/extraction input
└── legacy/
    └── playwright_backend.py # temporary rollback adapter
```

Orchestrator changes:

```text
orchestrator/
└── internal/
    ├── plan/research.go
    ├── activities/acquisition.go
    └── mapping/acquisition.go
```

---

# PHASE RB0 — baseline и benchmark corpus

## DS-RB00. Зафиксировать baseline Playwright/HTTPX

### Что делаем

До Rust внедрения измерить реальную стоимость текущего acquisition path.

### Где

Добавить:

- `benchmarks/browser/baseline.py`
- `benchmarks/browser/corpus.yaml`
- `benchmarks/browser/report.py`
- `docs/benchmarks/BROWSER_BASELINE.md`

### Метрики

Для каждого URL:

```text
success
status_code
final_url
content_bytes
useful_text_chars
links_count
screenshot_valid
network_requests
elapsed_ms
cpu_time_ms
rss_peak_mb
browser_process_count
bytes_received
quality_score
failure_class
```

### Corpus

Минимум 500 URL, целевой размер 1000+.

Обязательные группы:

- static HTML;
- SSR React/Next;
- SPA React;
- Vue/Nuxt;
- Angular;
- documentation;
- Wikipedia-like;
- news;
- ecommerce;
- infinite scroll;
- login wall;
- anti-bot page;
- heavy canvas;
- tables;
- iframe;
- Shadow DOM;
- downloadable PDF;
- malformed HTML;
- redirects;
- multilingual pages;
- very large pages.

### Проверка

Baseline report воспроизводим локально и в отдельном CI benchmark job.

### DoD

Есть цифры, с которыми можно сравнивать любой Rust backend.

---

## DS-RB01. Ввести golden page expectations

### Что делаем

Не сравнивать engines только по HTTP 200.

### Где

Добавить:

- `benchmarks/browser/expectations/*.yaml`
- `benchmarks/browser/golden/`

### Для каждой тестовой страницы описать

```yaml
must_contain_text:
  - "..."
min_text_chars: 500
min_links: 10
requires_js: true
requires_screenshot: false
must_not_be_block_page: true
```

### Проверка

Текущий Chromium reference формирует expected envelope, но golden не должен быть побайтовой копией Chromium DOM.

---

# PHASE RB1 — новый acquisition contract

## DS-RB02. Заменить `BrowserPoolProtocol` на capability-oriented contract

### Что делаем

`BrowserPoolProtocol` оставить deprecated adapter, новый код строить вокруг `AcquisitionBackend`.

### Где

Изменить:

- `scraper/contracts/__init__.py`

Добавить:

- `scraper/acquisition/models.py`
- `scraper/acquisition/capabilities.py`

### Новый contract

Концептуально:

```python
class AcquisitionBackend(Protocol):
    @property
    def descriptor(self) -> BackendDescriptor: ...

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult: ...
```

### `AcquisitionRequest`

```text
url
canonical_url
required_capabilities
optional_capabilities
mode
budget
security_context
session_ref
wait_condition
artifact_policy
trace_context
```

### `AcquisitionResult`

```text
requested_url
final_url
backend
status_code
headers
content_type
artifact_refs
text_preview
network_summary
quality
cost
failure
elapsed
capabilities_used
```

### Проверка

Unit tests не импортируют Playwright.

---

## DS-RB03. Описать `BrowserCapabilities`

### Где

- `scraper/acquisition/capabilities.py`
- `rust/acquisition-worker/src/capabilities.rs`

### Поля первой версии

```text
html
javascript
dom_mutation
css_layout
screenshot
network_capture
cookies
local_storage
session_persistence
iframe
shadow_dom
websocket
service_worker
canvas
webgl
pdf_print
file_download
user_interaction
```

Для capability хранить не только bool, если поддержка частичная:

```text
UNSUPPORTED
PARTIAL
SUPPORTED
```

### Проверка

Python и Rust contract fixtures сериализуются взаимно без потери полей.

---

## DS-RB04. Ввести `BackendDescriptor`

### Поля

```text
name
version
engine_family
capabilities
experimental
base_cost
startup_cost
memory_class
concurrency_class
security_profile
```

### Цель

Planner не должен знать типы `ServoBackend` / `ChromiumBackend` напрямую.

---

# PHASE RB2 — quality-driven escalation

## DS-RB05. Создать настоящий `AcquisitionQualityEvaluator`

### Что делаем

Не использовать `status == 200` как достаточное доказательство успеха.

### Где

Python reference:

- `scraper/acquisition/quality.py`

Rust production:

- `rust/acquisition-worker/src/quality.rs`

### Сигналы качества

```text
HTTP status quality
block/captcha probability
useful text amount
text/content ratio
DOM completeness
expected selectors
link extraction completeness
JS error count
navigation errors
network failures
hydration markers
empty-root detection
cookie/login wall detection
redirect sanity
content-type agreement
```

### Результат

```text
QualityReport {
    score
    completeness
    blocked
    likely_unrendered
    reasons[]
    suggested_escalation
}
```

### Проверка

Golden corpus должен содержать false-200 страницы: status 200, но реального содержимого нет.

---

## DS-RB06. Создать `BackendPlanner`

### Где

- `rust/acquisition-worker/src/planner.rs`
- reference tests в `scraper/acquisition/planner_reference.py`

### Алгоритм v1

1. отфильтровать backend, не удовлетворяющие hard capabilities;
2. отфильтровать запрещённые security/policy;
3. применить domain history;
4. оценить ожидаемые:
   - success probability;
   - quality;
   - latency;
   - memory;
   - monetary/resource cost;
5. выбрать backend с минимальной expected cost of successful acquisition;
6. после результата пересчитать необходимость escalation.

### Нельзя

```text
if js_score > 0.7: chromium
```

как финальную архитектуру.

### Проверка

Property tests:

- backend без hard capability никогда не выбирается;
- более дорогой backend не выбирается при равных прогнозах;
- backend с доказанной плохой domain history понижается;
- Chromium остаётся доступен как fallback.

---

## DS-RB07. Хранить domain/backend performance profile

### Что делаем

Planner должен учиться на фактической телеметрии без ML-модели на первом этапе.

### Где

Добавить storage contract:

- `rust/acquisition-worker/src/telemetry.rs`
- DB migration для агрегатов либо отдельный telemetry store.

### Минимальные агрегаты

```text
domain
backend
attempts
successes
quality_ewma
latency_ewma
rss_ewma
block_rate
js_failure_rate
last_failure_class
updated_at
```

### Проверка

После серии плохих Servo результатов для одного домена planner может сразу предпочесть Chromium, не проходя заведомо неудачный tier каждый раз.

---

# PHASE RB3 — нормализовать текущий Playwright path

## DS-RB08. Выделить Playwright из `BrowserPoolManager` в legacy backend

### Что делаем

Сначала сделать существующее поведение обычным backend, чтобы новый planner можно было внедрять без изменения поведения.

### Где

Перенести/адаптировать:

- `scraper/acquisition/browser_pool.py`

в:

- `scraper/acquisition/legacy/playwright_backend.py`

### Проверка

До включения Rust:

```text
new planner + PlaywrightBackend only
```

должен давать функционально эквивалентный результат старому execution path.

---

## DS-RB09. Исправить pool semantics reference backend

### Что делаем

Пока Playwright используется, `max_browsers` и `contexts_per_browser` должны реально ограничивать ресурсы.

### Где

- `scraper/acquisition/legacy/playwright_backend.py`

### Реализовать

- semaphore;
- bounded browser instances;
- bounded contexts;
- context timeout;
- forced cleanup;
- browser restart on unhealthy state;
- per-context resource accounting.

### Проверка

100 параллельных requests не создают 100 неограниченных contexts/processes.

---

# PHASE RB4 — Rust acquisition-worker skeleton

## DS-RB10. Создать Rust workspace/component

### Где

- `rust/acquisition-worker/Cargo.toml`
- `rust/acquisition-worker/src/main.rs`
- `rust/acquisition-worker/src/lib.rs`

### Требования

- Tokio async runtime;
- `tracing` structured logs;
- `serde` contracts;
- `thiserror` typed errors;
- graceful shutdown;
- cancellation-safe task handling;
- no browser engine dependency in core module.

### Проверка

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
```

---

## DS-RB11. Ввести backend trait на Rust

### Где

- `rust/acquisition-worker/src/backends/mod.rs`

### Контракт

Концептуально:

```rust
#[async_trait]
pub trait AcquisitionBackend: Send + Sync {
    fn descriptor(&self) -> &BackendDescriptor;
    async fn acquire(&self, req: &AcquisitionRequest)
        -> Result<AcquisitionResult, AcquisitionError>;
}
```

### Инвариант

Ни planner, ни ADGO activity handler не импортируют конкретные engine internals.

---

## DS-RB12. Ввести backend registry

### Где

- `rust/acquisition-worker/src/backends/mod.rs`

### Нужно

```text
register
get
available
healthy
capabilities
```

Experimental backend может быть отключён config feature flag без recompilation orchestration layer.

---

# PHASE RB5 — Rust HTTP first path

## DS-RB13. Реализовать `HttpBackend`

### Где

- `rust/acquisition-worker/src/backends/http.rs`

### Варианты

1. сначала `reqwest`/низкоуровневый HTTP adapter для минимального риска;
2. затем экспериментально Spider.

Не привязывать public contract к конкретной библиотеке.

### Реализовать

- streaming body limit;
- compressed body;
- HTTP/2 where available;
- redirects через security policy;
- timeout;
- charset decoding;
- MIME detection;
- response size limit;
- body hash;
- metrics.

### Проверка

Parity tests с текущим `HTTPFetcher`.

---

## DS-RB14. Добавить Spider adapter

### Где

- `rust/acquisition-worker/src/backends/http_spider.rs`

### Цель

Проверить Spider как URL-level crawl execution engine.

### Важное правило

Не заменять Crawlee в production одним commit.

Сначала Spider работает в benchmark/shadow mode.

### Сравнить

```text
throughput
RSS
CPU
queue fairness
host rate limiting
retry behavior
robots behavior
URL dedup
cancellation
```

### Gate

Spider становится default URL execution backend только если имеет измеримое преимущество и не ухудшает policy semantics.

---

# PHASE RB6 — единая security boundary

## DS-RB15. Перенести SSRF policy перед любой backend navigation

### Где

- `rust/acquisition-worker/src/security/url_policy.rs`
- `dns_policy.rs`
- `redirect_policy.rs`
- `network_policy.rs`

### Требования

Проверять:

- scheme;
- hostname;
- resolved addresses;
- IPv4/IPv6 private/local ranges;
- redirect destination;
- DNS re-resolution;
- browser subresource policy;
- download destinations;
- maximum redirects;
- maximum response size.

### Инвариант

Servo и Chromium не имеют собственного более слабого SSRF path.

---

## DS-RB16. Ввести NetworkPolicy

### Поля

```text
allow_http
allow_https
allowed_hosts
denied_hosts
allow_private_networks
max_redirects
max_body_bytes
max_subresource_bytes
max_total_bytes
allow_websocket
allow_downloads
```

### Проверка

Один и тот же security corpus проходит через HTTP, Servo и Chromium backend.

---

# PHASE RB7 — Servo backend

## DS-RB17. Добавить Servo как feature-gated dependency

### Где

- `rust/acquisition-worker/Cargo.toml`
- `rust/acquisition-worker/src/backends/servo.rs`

### Требования

Servo build pin должен быть фиксирован конкретной версией/commit.

Нельзя использовать плавающий `main` в production build.

### Feature

```text
servo-backend
```

### Проверка

Worker собирается и без Servo:

```bash
cargo build --no-default-features
```

---

## DS-RB18. Реализовать offscreen Servo session

### Где

- `backends/servo.rs`

### Функции v1

- navigate;
- await document readiness;
- final URL;
- DOM serialization;
- text extraction preview;
- network summary;
- JS error summary;
- screenshot where supported;
- timeout/cancellation.

### Не делать в v1

- сложную automation DSL;
- login scripting;
- form automation;
- browser extension model.

### Проверка

100 последовательных navigation cycles не показывают неограниченный RSS growth.

---

## DS-RB19. Servo compatibility benchmark

### Где

- `rust/acquisition-worker/benches/corpus.rs`
- `docs/benchmarks/SERVO_COMPATIBILITY.md`

### Сравнивать с Chromium reference

Не DOM equality, а:

```text
usable success rate
quality score
text recall
link recall
screenshot validity
JS error rate
latency
RSS
CPU
network bytes
```

### Gate для shadow production

Пример целевого минимального gate, который можно уточнить после baseline:

```text
static/SSR usable success ≥ 95%
SPA usable success ≥ 80%
false-success rate < 1%
no critical security regressions
no unbounded memory leak in soak test
```

Это не обещание Servo capability; это критерий допуска backend в routing.

---

## DS-RB20. Включить Servo только в shadow mode

### Что делаем

Для части URL:

```text
production result = existing backend
shadow result = Servo
```

Shadow result не влияет на пользовательский ответ.

### Собирать

- quality delta;
- latency delta;
- memory delta;
- fallback reason;
- compatibility classes.

### Gate

Не переходить к активному routing до накопления статистически полезного объёма.

---

# PHASE RB8 — Chromium Rust fallback

## DS-RB21. Выбрать CDP adapter benchmark-ом

### Кандидаты

- `chromiumoxide`;
- `Chromey`.

### Где

- `rust/acquisition-worker/benches/chromium_adapter.rs`
- `docs/benchmarks/CHROMIUM_RUST_ADAPTER.md`

### Сравнить

```text
startup
navigation latency
CDP stability
network interception
screenshot
large DOM
parallel pages
memory overhead outside Chromium
shutdown correctness
API maintenance risk
```

### Решение

В production остаётся один Rust Chromium adapter.

---

## DS-RB22. Реализовать `ChromiumBackend`

### Где

- `rust/acquisition-worker/src/backends/chromium.rs`

### Обязательные функции

- bounded browser pool;
- bounded contexts/pages;
- network interception;
- SSRF subresource enforcement where technically possible;
- screenshot;
- DOM;
- network logs;
- wait policies;
- download policy;
- process health checks;
- automatic restart;
- cleanup after cancellation.

### Проверка

Kill Chromium child process во время navigation → typed retryable failure, worker остаётся жив.

---

## DS-RB23. Сохранить Playwright rollback window

### Что делаем

На время миграции environment flag:

```text
DEEPSEARCH_BROWSER_PATH=legacy-playwright|rust
```

### Где

- `scraper/config.py`
- deployment env examples

### Удаление

Legacy path удалять только после стабилизационного периода и сравнения production metrics.

---

# PHASE RB9 — experimental BrowserOxide / Blitz

## DS-RB24. BrowserOxide adapter только под feature flag

### Где

- `rust/acquisition-worker/src/backends/browseroxide.rs`

### Feature

```text
browseroxide-experimental
```

### Ограничение

Backend не входит в default release artifact до прохождения security и compatibility gates.

### Проверка

Отдельный CI job допускает его нестабильность без блокирования production build, но фиксирует regressions.

---

## DS-RB25. Blitz adapter для static visual requests

### Где

- `rust/acquisition-worker/src/backends/blitz.rs`

### Выбирать только если

```text
requires:
  css_layout: true
  screenshot: true
  javascript: false
```

### Проверка

Static visual corpus сравнивается с Chromium screenshot не pixel-perfect, а по layout anchors / OCR / dimensions / render success.

---

# PHASE RB10 — artifact boundary

## DS-RB26. Не передавать большие HTML/screenshots через ADGO task payload

### Что делаем

Axiom ADGO хранит orchestration state, но browser artifacts должны уходить в CAS/object storage.

### Где

Rust:

- `artifacts/writer.rs`
- `artifacts/manifest.rs`

Python:

- `scraper/acquisition/result_adapter.py`

### Activity result

Возвращать:

```text
ArtifactReference {
  content_hash
  uri/key
  media_type
  size
  metadata_hash
}
```

а не многомегабайтный HTML/screenshot.

### Проверка

Размер durable ADGO history практически не зависит от размера страницы.

---

## DS-RB27. Унифицировать acquisition manifest

### Manifest

```text
request_id
requested_url
final_url
backend
backend_version
strategy
status
headers_subset
content_ref
screenshot_ref
network_log_ref
quality_report
security_report
cost_report
started_at
finished_at
trace_id
```

### Проверка

ArchiveExporter может включить manifest без знания конкретного backend.

---

# PHASE RB11 — Axiom ADGO integration

## DS-RB28. Сделать Rust worker ADGO remote worker

### Что делаем

Rust acquisition worker должен получать coarse-grained `AcquireBatch` напрямую от ADGO coordinator.

### Где

- `rust/acquisition-worker/src/adgo/client.rs`
- `adgo/activity.rs`
- `adgo/heartbeat.rs`
- `orchestrator/internal/activities/acquisition.go`

### Activity contract

```text
AcquireBatchInput {
  run_id
  batch_id
  urls[]
  acquisition_policy
  budget_slice
  artifact_policy
}

AcquireBatchOutput {
  results[] -> ArtifactReference + QualityReport
  usage
  failures[]
}
```

### Почему batch

Не создавать один durable ADGO node на каждый URL.

ADGO остаётся coarse-grained durable orchestration; URL-level execution живёт внутри acquisition worker/crawler.

---

## DS-RB29. Heartbeat прогресса

### Что отправлять

```text
processed
successful
failed
current_backend_counts
bytes_downloaded
browser_seconds
estimated_remaining
```

### Проверка

Long batch не теряет lease при корректно работающем worker.

---

## DS-RB30. Cancellation propagation

### Требование

`ADGO Cancel` должен пройти:

```text
ADGO
→ Rust worker task
→ crawler queue
→ Servo/Chromium navigation
→ network requests
→ artifact writer
```

### Проверка

Cancel большого batch освобождает browser/context/network resources в bounded time.

---

## DS-RB31. ADGO failure classification

### Mapping

```text
DNS temporary            → transient
HTTP 429                 → rate_limit
browser crash            → transient
unsupported capability   → quality / route escalation
captcha/block page       → quality or policy-defined
invalid URL              → invalid_input
SSRF policy violation    → permanent/security
artifact write ambiguity → ambiguous_side_effect / reconcile
```

### Проверка

Не все ошибки превращаются в одинаковый retry.

---

# PHASE RB12 — resource budgets

## DS-RB32. Добавить browser-specific budget accounting

### Поля

```text
max_urls
max_total_bytes
max_browser_seconds
max_servo_seconds
max_chromium_seconds
max_screenshots
max_download_bytes
max_wall_time
```

### Где

- ADGO `ResearchPlan` budget mapping;
- Rust `models.rs` / planner.

### Проверка

Worker не может самостоятельно превысить выделенный budget slice, даже если coordinator ещё не успел остановить run.

---

## DS-RB33. Ввести concurrency classes

### Пример

```text
HTTP       high
Servo      medium
Chromium   low
Visual     very_low
```

### Где

- backend descriptors;
- Axiom admission/resource keys.

### Проверка

1000 HTTP URLs не блокируются лимитом, предназначенным для Chromium contexts, и наоборот Chromium не способен исчерпать RAM без admission control.

---

# PHASE RB13 — routing strategy

## DS-RB34. Реализовать Minimal Effective Browser policy v1

### Логика

```text
1. Try cheapest eligible backend.
2. Evaluate result quality.
3. Stop if sufficient.
4. Escalate only when expected benefit > escalation cost.
5. Never exceed budget/security constraints.
```

### Начальный порядок без domain history

```text
HTTP
→ Servo if JS/layout required
→ Chromium if Servo unavailable/insufficient
```

Experimental backends не вставлять в обязательную цепочку.

---

## DS-RB35. Добавить domain routing memory

### Пример

Если для домена за последние N попыток:

```text
Servo success < threshold
Chromium success high
```

planner может сразу пропустить Servo на ограниченный TTL.

### Защита от вечной фиксации

- TTL;
- periodic probe;
- backend version in profile key.

---

## DS-RB36. Добавить exploration только для experimental traffic

Не использовать production user request как бесконтрольный benchmark.

Допустимые режимы:

```text
OFF
SHADOW
CANARY
ACTIVE
```

для каждого backend.

---

# PHASE RB14 — Python integration

## DS-RB37. Изменить `AdaptiveAcquisitionEngine`

### Что делаем

Он больше не должен самостоятельно знать про Playwright/Servo.

### Где

- `scraper/acquisition/engine.py`

### После миграции

Python engine получает либо:

1. `ArtifactReference` из ADGO activity result;
2. локальный `AcquisitionClient` в standalone mode.

### Удалить

из production path прямой код:

```text
HTTP → classify → browser_pool.fetch_page
```

### Проверка

Unit test `AdaptiveAcquisitionEngine` полностью работает на fake acquisition client.

---

## DS-RB38. Ввести standalone local API для разработки

### Зачем

Не требовать ADGO coordinator для каждого unit/manual test Rust browser worker.

### Где

- `rust/acquisition-worker/src/service/local_api.rs`
- `scraper/acquisition/rust_worker_client.py`

### API

Минимум:

```text
POST /v1/acquire
GET  /v1/health
GET  /v1/backends
GET  /v1/metrics
```

### Ограничение

Local API — developer boundary, не второй источник orchestration state.

---

# PHASE RB15 — observability

## DS-RB39. Единые browser metrics

### Метрики

```text
acquisition_attempts_total{backend}
acquisition_success_total{backend}
acquisition_escalations_total{from,to,reason}
acquisition_latency_seconds{backend}
acquisition_quality{backend}
backend_rss_bytes{backend}
backend_active_sessions{backend}
backend_crashes_total{backend}
block_pages_total{backend}
network_bytes_total{backend}
```

### Где

- Rust tracing/OpenTelemetry;
- существующий telemetry pipeline DeepSearch.

---

## DS-RB40. Trace continuity Axiom → Rust → Python

### Требование

Один trace должен связывать:

```text
Research run
AcquireBatch ADGO node
Rust backend attempt
Artifact write
Python extraction
Evidence creation
```

### Проверка

По одному `run_id + batch_id + url` можно восстановить полный execution path.

---

# PHASE RB16 — test pyramid

## DS-RB41. Rust unit tests

Покрыть:

- capability matching;
- planner;
- quality scoring;
- policy merge;
- budget accounting;
- error classification;
- manifest serialization.

---

## DS-RB42. Contract tests Python ↔ Rust

### Где

- shared JSON fixtures;
- `tests/contracts/acquisition/`;
- Rust `tests/contract.rs`.

### Проверять

- optional fields;
- enum compatibility;
- unknown future fields;
- version negotiation;
- large IDs;
- Unicode URLs/text;
- binary artifact references.

---

## DS-RB43. Browser compatibility tests

Каждый backend прогоняется по одному и тому же corpus.

Результат сохраняется как report artifact CI, а не только pass/fail.

---

## DS-RB44. Security tests

Обязательные сценарии:

- localhost;
- RFC1918;
- IPv6 loopback/private;
- DNS rebinding simulation;
- public → private redirect;
- browser subresource private IP;
- oversized response;
- redirect loop;
- file://;
- unsupported schemes;
- malicious download path.

---

## DS-RB45. Crash/recovery tests

### Сценарии

- kill Rust worker during HTTP batch;
- kill during Servo navigation;
- kill Chromium child;
- kill coordinator;
- expire ADGO lease;
- stale worker tries complete;
- CAS write succeeds, completion response lost.

### Проверка

Нет потерянных durable jobs и нет принятия stale result.

---

## DS-RB46. Soak tests

Минимум:

```text
10k HTTP navigations
1k Servo navigations
1k Chromium navigations
mixed 4-8 hour run
```

Отслеживать:

- RSS trend;
- FD count;
- zombie processes;
- context leaks;
- task leaks;
- queue growth;
- latency degradation.

---

# PHASE RB17 — CI/CD

## DS-RB47. Добавить Rust CI

### Где

- `.github/workflows/ci.yml`

### Jobs

```text
rust-format
rust-clippy
rust-test
rust-security
rust-build-minimal
rust-build-browser
contract-tests
```

Servo/experimental heavy build можно вынести в отдельный cached job.

---

## DS-RB48. Создать reproducible container image

### Где

- `rust/acquisition-worker/Dockerfile`
- deployment compose/k8s manifests.

### Требования

- pinned Rust toolchain;
- pinned browser/runtime versions;
- non-root execution;
- read-only root where possible;
- writable temp/profile dirs explicit;
- Chromium sandbox не отключать без отдельного документированного security reason.

---

# PHASE RB18 — migration

## DS-RB49. Shadow HTTP Rust path

Production response остаётся Python HTTPX, Rust выполняется выборочно в фоне/shadow sampling.

Gate:

- response parity acceptable;
- no security regression;
- resource advantage confirmed.

---

## DS-RB50. Перевести default HTTP acquisition на Rust

После gate:

```text
HTTPX → fallback/reference
Rust HTTP → default
```

Crawlee пока можно сохранить как frontier до отдельного решения по Spider.

---

## DS-RB51. Servo canary

### Этапы

```text
0% active / shadow only
1% eligible traffic
5%
20%
50% eligible
adaptive default
```

На каждом шаге сравнивать:

- success;
- quality;
- fallback rate;
- latency;
- memory;
- user-visible research quality.

---

## DS-RB52. Rust Chromium canary

Перевести Chromium fallback с Playwright на Rust adapter только после Servo независимо от него.

Нельзя одновременно менять:

```text
HTTP implementation
Servo routing
Chromium adapter
```

одним rollout — иначе невозможно установить источник regression.

---

## DS-RB53. Решить судьбу Crawlee vs Spider по данным

### Варианты

**A. Crawlee оставить**

если его scheduling/session/policy возможности дают существенную ценность и overhead приемлем.

**B. Spider сделать URL frontier внутри Rust acquisition worker**

если benchmarks показывают значимое преимущество без потери semantics.

### Требование

Не держать два равноправных frontier в production.

Итоговый system owner URL scheduling должен быть один.

---

## DS-RB54. Удалить legacy Playwright path

Только когда одновременно выполнено:

- Rust HTTP стабилен;
- Servo routing стабилен либо безопасно bypassable;
- Rust Chromium fallback стабилен;
- crash/recovery tests green;
- security suite green;
- production rollback возможен release rollback-ом;
- наблюдался достаточный стабилизационный период.

После этого удалить:

- direct Playwright dependency из base install, если больше не нужна;
- `BrowserPoolProtocol`;
- `BrowserPoolManager`;
- legacy config flags.

Playwright можно оставить optional dev/reference dependency для benchmark suite.

---

# PHASE RB19 — cleanup документации

## DS-RB55. Обновить архитектурные документы

### Где

- `docs/architecture/SYSTEM_MAP.md`
- `docs/architecture/TARGET_ARCHITECTURE.md`
- `docs/architecture/MODULE_INDEX.md`
- `README.md`
- `README.ru.md`
- `docs/architecture/IMPROVEMENT_PLAN_AXIOM.md`

### Отразить

```text
Axiom ADGO = control plane
Rust Acquisition Worker = acquisition execution plane
Python = extraction/research plane
CAS = artifact source of truth
Chromium = compatibility fallback
```

---

# 6. Приоритет выполнения

## P0 — сначала

```text
DS-RB00 baseline
DS-RB01 golden corpus
DS-RB02 acquisition contract
DS-RB03 capabilities
DS-RB04 descriptor
DS-RB05 quality evaluator
DS-RB06 planner
DS-RB08 Playwright adapter normalization
DS-RB10 Rust worker skeleton
DS-RB11 backend trait
DS-RB13 HTTP backend
DS-RB15 security boundary
DS-RB17 Servo integration
DS-RB19 Servo benchmark
DS-RB21 Chromium adapter benchmark
DS-RB22 Chromium backend
DS-RB26 artifact boundary
DS-RB28 ADGO worker integration
```

## P1 — после устойчивого core

```text
DS-RB07 domain history
DS-RB14 Spider
DS-RB20 Servo shadow
DS-RB24 BrowserOxide experimental
DS-RB29 heartbeat
DS-RB30 cancellation
DS-RB31 failure classification
DS-RB32 budgets
DS-RB33 admission
DS-RB35 routing memory
DS-RB39 metrics
DS-RB40 traces
DS-RB45 crash recovery
DS-RB46 soak
```

## P2 — только после данных

```text
DS-RB25 Blitz
DS-RB36 controlled exploration
DS-RB49-54 production migration
```

---

# 7. Что не нужно делать

Не делать следующие изменения до получения benchmark evidence:

1. не удалять Chromium;
2. не удалять Playwright в первой фазе;
3. не переписывать extraction на Rust одновременно;
4. не переписывать весь DeepSearch на Rust;
5. не вводить BrowserOxide как default;
6. не заменять Crawlee на Spider без сравнительного теста;
7. не делать отдельный scheduler внутри каждого backend;
8. не дублировать Axiom durable state;
9. не хранить HTML/screenshots в ADGO history;
10. не выбирать backend только по user-agent/site-name hardcode;
11. не считать HTTP 200 успешной acquisition;
12. не выключать browser sandbox ради простоты deployment без отдельного security review.

---

# 8. Целевая модель стоимости

Для planner использовать не просто latency.

Концептуально:

```text
ExpectedSuccessfulCost =
    P(success)^-1
    × (
        latency_weight × expected_latency
      + cpu_weight × expected_cpu
      + memory_weight × expected_memory
      + browser_weight × browser_seconds
      + bandwidth_weight × bytes
      + failure_weight × escalation_probability
    )
```

Но v1 не должен начинаться с сложной ML-модели.

Начать с нормализованной deterministic scoring function, покрытой тестами. Позже коэффициенты можно адаптировать по telemetry.

---

# 9. Definition of Done всей инициативы

Rust browser execution initiative считается завершённой только если выполняются все условия:

1. `BrowserPoolProtocol` больше не является главным production abstraction.
2. Есть единый capability-based acquisition contract.
3. Есть единый backend planner.
4. HTTP является cheapest-first path.
5. Servo может использоваться как независимый browser tier через feature/canary control.
6. Chromium остаётся надёжным fallback.
7. Experimental backends не влияют на production без explicit rollout.
8. Все backends проходят одну security boundary.
9. Redirect/DNS/subresource SSRF policy тестируется.
10. Quality evaluator обнаруживает false-200 / empty SPA shells.
11. Backend escalation объясним и записывается в telemetry.
12. Есть golden corpus минимум 500 URL.
13. Есть воспроизводимые Chromium baseline metrics.
14. Есть Servo vs Chromium compatibility report.
15. Выбор Rust Chromium adapter подтверждён benchmark-ом.
16. Rust worker имеет bounded concurrency и resource limits.
17. Cancellation корректно освобождает ресурсы.
18. Crash/recovery tests проходят.
19. Stale ADGO worker не может commit старый result.
20. Большие artifacts не хранятся в ADGO task/history payload.
21. CAS manifest содержит backend/version/quality/security metadata.
22. Python extraction не знает конкретный browser engine.
23. CLI/API/MCP не выбирают browser backend напрямую.
24. Axiom ADGO управляет coarse-grained `AcquireBatch` lifecycle.
25. URL-level scheduler имеет ровно одного production owner.
26. Domain routing memory имеет TTL/versioning и не создаёт вечный lock-in.
27. CI собирает Rust minimal и browser profiles.
28. Container запускается non-root и имеет документированную sandbox policy.
29. Legacy Playwright path удалён либо явно оставлен только как optional reference tool.
30. Документация отражает фактический runtime, а не целевую архитектуру как уже реализованную.

---

# 10. Рекомендуемый порядок первых 12 implementation commits

Чтобы не делать большой рискованный rewrite, первые изменения выполнять по одному green commit:

```text
Commit 01
benchmark corpus + current Playwright baseline

Commit 02
Python AcquisitionRequest / AcquisitionResult / Capabilities
без изменения runtime

Commit 03
PlaywrightBackend adapter под новый contract
поведение остаётся прежним

Commit 04
AcquisitionQualityEvaluator + fixtures

Commit 05
BackendPlanner только с HTTP + Playwright

Commit 06
Rust acquisition-worker skeleton + CI

Commit 07
Rust HttpBackend + contract tests

Commit 08
shared security policy tests

Commit 09
artifact manifest/CAS boundary

Commit 10
Servo backend feature-gated

Commit 11
Servo corpus benchmark/shadow mode

Commit 12
Rust Chromium adapter benchmark
```

Только после этих двенадцати commits переходить к реальному ADGO production routing.

---

# 11. Итоговая целевая схема

```text
                    ┌─────────────────────────┐
                    │ ResearchApplication     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Axiom ADGO              │
                    │ durable control plane   │
                    └────────────┬────────────┘
                                 │ AcquireBatch
                                 ▼
          ┌──────────────────────────────────────────┐
          │ Rust Acquisition Worker                  │
          │                                          │
          │ Security → Planner → Backend → Quality  │
          │                        │                 │
          │       ┌────────────────┼──────────────┐  │
          │       ▼                ▼              ▼  │
          │   HTTP/Spider        Servo        Chromium│
          │       │                │              │  │
          │       └────────────────┴──────────────┘  │
          │                        │                 │
          │                  CAS artifacts           │
          └────────────────────────┬─────────────────┘
                                   │ refs
                                   ▼
                    ┌─────────────────────────┐
                    │ Python DeepSearch       │
                    │ extraction / evidence   │
                    │ Qdrant / synthesis      │
                    └─────────────────────────┘
```

Целевой результат — не «DeepSearch на Rust», а **DeepSearch, где самый дорогой и системно сложный участок web execution вынесен в специализированный Rust worker, а Chromium используется только там, где его совместимость действительно нужна**.
