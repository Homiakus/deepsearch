# DeepSearch — дополнение к плану Rust Browser Execution Layer

**Дата ревизии:** 2026-08-27  
**Статус:** обязательное корректирующее дополнение к `RUST_BROWSER_EXECUTION_PLAN.md`  
**Приоритет:** P0 до продолжения rollout Rust acquisition worker  
**Связанные документы:**

- `docs/architecture/RUST_BROWSER_EXECUTION_PLAN.md`
- `docs/architecture/SEARCH_SOURCE_INTELLIGENCE_PLAN.md`
- `docs/architecture/IMPROVEMENT_PLAN_AXIOM.md`
- `docs/architecture/CYCLIC_DEVELOPMENT_LOOP.md`

Если это дополнение противоречит старому статусу реализации backend в основном плане, **источником истины является это дополнение до прохождения новых acceptance gates**.

---

# 1. Причина ревизии

Аудит фактического runtime показал существенный разрыв между архитектурными контрактами и реально исполняемыми движками.

## 1.1. Зафиксированные reality gaps

1. `rust/acquisition-worker/src/backends/http_spider.rs` пока не использует `spider-rs/spider`: `SpiderBackend` делегирует выполнение `HttpBackend` и только меняет metadata результата.
2. `rust/acquisition-worker/src/backends/chromium.rs` объявляет `BrowserCapabilities::full_browser()`, но фактически вызывает `HttpBackend`. Таким образом planner может принять HTTP-запрос за полноценный browser execution.
3. `rust/acquisition-worker/src/backends/browseroxide.rs` аналогично является HTTP fallback, хотя descriptor объявляет частичные browser capabilities.
4. `rust/acquisition-worker/Cargo.toml` не содержит реальных runtime dependencies для Spider, Chromium/CDP, Servo или BrowserOxide; наличие backend-класса пока не является доказательством наличия движка.
5. `scraper/acquisition/crawlee_adapter.py` не использует Crawlee RequestQueue/AutoscaledPool/session machinery: текущая реализация — bounded `asyncio.gather` поверх `AdaptiveAcquisitionEngine`.
6. `scraper/acquisition/http_fetcher.py` создаёт новый `AsyncHTTPTransport` и новый `AsyncClient` на каждый `fetch()`, теряя connection pooling, HTTP/2 connection reuse, TLS session reuse и часть выигрыша от долгоживущего crawler runtime.
7. `scraper/acquisition/browser_pool.py` содержит статический browser fingerprint (`Chrome/130`, фиксированные Client Hints, timezone/locale). Этот код допустим только как legacy/reference path, но не как долгосрочная anti-detection архитектура.
8. `scraper/control/ranked_frontier.py` уже содержит важную исследовательскую семантику — goal-aware priority, leases, retry и domain fairness. Эту роль нельзя без доказанного выигрыша передавать Spider/Crawlee или дублировать несколькими равноправными frontier.

## 1.2. Главный вывод

Нужно не добавлять ещё один монолитный scraper, а довести текущую capability-oriented архитектуру до состояния, где каждый advertised backend действительно выполняет заявленные capabilities.

Целевая ответственность:

```text
DeepSearch / Axiom
= ЧТО, ЗАЧЕМ и С КАКИМ ПРИОРИТЕТОМ получать

Rust acquisition worker
= КАК получить URL с минимальной expected successful cost

Spider.rs
= высокопроизводительный HTTP/crawl execution engine

Chromium/CDP
= реальный compatibility browser tier

Scrapling
= дорогой optional difficult-page / stealth fallback

Python DeepSearch
= extraction / normalization / evidence / retrieval / synthesis
```

---

# 2. Новые обязательные архитектурные инварианты

## INV-RB-A. Capability Truthfulness

Backend **не имеет права** объявлять `SUPPORTED`, если capability не доказана executable conformance test.

```text
Descriptor capability
        ↓
conformance fixture
        ↓
observable proof
        ↓
SUPPORTED
```

Наличие struct/class/file не является реализацией capability.

## INV-RB-B. Один production owner URL scheduling

Основной владелец research-level frontier — DeepSearch `RankedFrontier`.

Spider/Crawlee могут иметь внутренние bounded execution queues, но не должны независимо решать исследовательский приоритет, goal coverage или создавать второй durable visited-state.

## INV-RB-C. Один escalation authority

Решение HTTP → browser → difficult-page fallback принимает capability/cost planner. Нельзя одновременно включать независимый smart-routing Spider и отдельный smart-routing DeepSearch для одного request path.

## INV-RB-D. Browser fallback не является default

Дорогой browser runtime используется только при доказанной необходимости: hard capability requirement, low-quality HTTP result, likely-unrendered result или проверенный domain profile.

## INV-RB-E. Security-before-engine

URL/DNS/redirect/network policy применяется до передачи URL любому engine и повторно защищается внутри external sidecar boundary.

---

# PHASE RB20 — Runtime Reality Gate

## DS-RB56. Ввести `ImplementationState` и запретить ложную рекламу capabilities

### Что изменить

Rust:

- `rust/acquisition-worker/src/capabilities.rs`
- `rust/acquisition-worker/src/backends/mod.rs`
- `rust/acquisition-worker/src/lib.rs`
- `rust/acquisition-worker/src/service/local_api.rs`

Python contract:

- `scraper/acquisition/capabilities.py`
- `scraper/contracts/capabilities.py`

### Как

Расширить `BackendDescriptor` полями:

```text
implementation_state:
  unavailable | stub | experimental | production

health_state:
  unknown | healthy | degraded | unhealthy

capability_evidence_version
```

Planner должен фильтровать `stub` и `unavailable` из active routing независимо от их nominal cost.

`GET /v1/backends` обязан показывать фактический implementation state.

`create_default_registry()` не должен регистрировать placeholder backend как production-capable.

### Тесты

Добавить:

- `rust/acquisition-worker/tests/backend_registry.rs`
- `tests/contract/test_backend_descriptor.py`

Проверить:

1. `stub` backend никогда не выбирается planner-ом;
2. disabled feature отсутствует в active registry;
3. `/v1/backends` не сообщает `production` для HTTP-заглушки;
4. Python/Rust JSON fixtures сохраняют новые enum без потерь;
5. unknown future enum/version обрабатывается fail-closed или negotiated-version path.

### DoD

Невозможно получить ситуацию «descriptor говорит full browser, implementation делает HTTP».

---

## DS-RB57. Добавить executable capability conformance suite

### Где

Добавить fixtures:

```text
tests/fixtures/acquisition_site/
├── static.html
├── js_required.html
├── dom_mutation.html
├── cookie_roundtrip.html
├── iframe.html
├── shadow_dom.html
├── websocket.html
├── network_capture.html
└── screenshot_target.html
```

Rust:

- `rust/acquisition-worker/tests/capability_conformance.rs`

Python/reference:

- `tests/contract/test_acquisition_capability_conformance.py`

### Как

Для каждой capability создать наблюдаемый probe.

Примеры:

```text
javascript
→ значение появляется только после выполнения JS

dom_mutation
→ DOM меняется после async mutation

cookies
→ server устанавливает cookie, второй request обязан вернуть её

network_capture
→ страница выполняет XHR к fixture endpoint, URL должен присутствовать в network summary

screenshot
→ PNG signature + ненулевой размер + ожидаемые dimensions
```

`SUPPORTED` разрешается только если соответствующий probe проходит.

### Mutation test

Мутация descriptor `UNSUPPORTED → SUPPORTED` должна быть убита conformance suite.

### DoD

Capabilities становятся проверяемым контрактом, а не документацией.

---

## DS-RB58. Исправить текущие placeholder descriptors до появления реальных engines

### Где

- `rust/acquisition-worker/src/backends/chromium.rs`
- `rust/acquisition-worker/src/backends/browseroxide.rs`
- `rust/acquisition-worker/src/backends/servo.rs`
- `rust/acquisition-worker/src/backends/blitz.rs`
- `rust/acquisition-worker/src/backends/http_spider.rs`
- `rust/acquisition-worker/src/lib.rs`

### Как

До реальной реализации:

- `chromium-cdp` → `implementation_state=stub`, не `full_browser()` в active registry;
- `browseroxide-experimental` → `stub` или feature-disabled;
- Servo/Blitz → регистрировать только если feature реально компилирует engine;
- `spider-crawler` → `stub` до подключения crate `spider`.

Нельзя маскировать fallback сменой `res.backend`.

### Тест

`BackendPlanner` с required `javascript=SUPPORTED` при наличии только HTTP/stub backends обязан вернуть `None/UnsupportedCapability`, а не HTTP результат под именем Chromium.

---

## DS-RB59. Добавить architecture reality audit в CI

### Где

- `.github/workflows/ci.yml`
- `tools/` или `rust/acquisition-worker/tests/`

### Как

CI gate проверяет:

```text
registered production backend
→ feature enabled
→ runtime dependency exists
→ conformance suite exists
→ conformance suite green
```

### Тест-of-tests

Добавить отрицательную fixture/compile configuration, где fake backend заявляет browser capability без implementation evidence. CI обязан падать.

---

# PHASE RB21 — Настоящий Spider.rs execution layer

## DS-RB60. Подключить реальный `spider-rs/spider` как optional Rust dependency

### Где

- `rust/acquisition-worker/Cargo.toml`
- `rust/acquisition-worker/Cargo.lock`

### Как

Добавить feature:

```text
spider-backend = ["dep:spider"]
```

Версию Spider pin-ить к конкретной протестированной release/version; не использовать плавающий Git `main` для production.

`default` сначала не включает Spider до прохождения benchmark gate.

### Проверка

```bash
cargo build --no-default-features --features http-backend
cargo build --features spider-backend
cargo test --features spider-backend
```

Minimal build обязан собираться без Spider.

---

## DS-RB61. Переписать `SpiderBackend` с HTTP wrapper на реальный crawler adapter

### Где

Основной файл:

- `rust/acquisition-worker/src/backends/http_spider.rs`

При необходимости добавить:

- `rust/acquisition-worker/src/backends/spider_session.rs`
- `rust/acquisition-worker/src/backends/spider_mapper.rs`

### Как

`SpiderBackend` должен:

1. получать нормализованный `AcquisitionRequest`;
2. применять уже проверенную DeepSearch `NetworkPolicy`;
3. создавать/переиспользовать bounded Spider execution context;
4. стримить полученные страницы по мере завершения;
5. преобразовывать page → `AcquisitionResult`;
6. возвращать discovered links отдельно от research scheduling;
7. корректно реагировать на cancellation;
8. не запускать внутренний browser smart-routing в первом production варианте — browser escalation остаётся у DeepSearch planner;
9. не хранить второй durable visited-state.

### Новый DTO

Добавить в Rust/Python models:

```text
DiscoveredLink {
  url
  canonical_url
  source_url
  depth_delta
  rel
  anchor_text
}
```

И в `AcquisitionResult`:

```text
discovered_links[]
```

### Изменить mapping

- `rust/acquisition-worker/src/models.rs`
- `scraper/acquisition/models.py`
- `scraper/acquisition/result_adapter.py`
- `orchestrator/internal/mapping/acquisition.go`

### Тесты

Добавить локальный fixture-site graph:

```text
/index → /a → /a/1
      ↘ /b → /shared
```

Проверить:

- link discovery completeness;
- canonicalization;
- duplicate suppression;
- bounded depth;
- same-domain policy;
- robots behavior;
- redirect handling;
- 429 retry/backoff;
- cancellation;
- max body limit;
- no private-IP escape after redirect.

### Benchmark gate

Сравнить реальный Spider с Rust `HttpBackend` и Python `HTTPFetcher`:

```text
accepted pages/sec
p50/p95/p99 latency
RSS
CPU-sec/1000 URLs
connections reused
bytes/accepted document
retry rate
failure rate
cancel latency
```

---

## DS-RB62. Оставить research ranking за `RankedFrontier`

### Где

- `scraper/control/ranked_frontier.py`
- `scraper/application/activities/discovery.py`
- `scraper/application/activities/acquisition.py`
- `orchestrator/internal/plan/research.go`

### Как

Discovered links из Spider возвращаются в DeepSearch, затем проходят:

```text
canonicalization
→ source policy
→ feature extraction
→ information-gain / relevance score
→ RankedFrontier.add_candidate()
```

Spider не должен сам автоматически уходить в глубокий unlimited crawl, если research budget не разрешает это.

### Тест

URL с высоким Spider traversal order, но низкой research relevance, не должен вытеснить высокоценный URL из `RankedFrontier`.

Property test: изменение внутреннего порядка Spider не меняет research priority при одинаковом наборе discovered links.

---

## DS-RB63. Добавить crawl budget contract специально для Spider

### Где

- `rust/acquisition-worker/src/models.rs`
- `scraper/acquisition/models.py`
- `scraper/control/budget.py`
- `orchestrator/internal/mapping/acquisition.go`

### Поля

```text
max_pages
max_depth
max_links_per_page
max_total_bytes
max_domain_pages
max_wall_time
max_inflight
```

### Тесты

Граничное многомерное пространство:

```text
max_pages × max_depth × body_size × redirect_count × domains × concurrency
```

Использовать pairwise + targeted boundary cases:

- 0/1/max/max+1;
- huge fan-out;
- cyclic graph;
- redirect cycle;
- one huge page among small pages;
- cancellation на 0%, 50%, 99% batch.

---

# PHASE RB22 — HTTP hot path до полной миграции на Rust

## DS-RB64. Исправить connection pooling Python `HTTPFetcher`

### Где

- `scraper/acquisition/http_fetcher.py`

### Изменить функции

- `HTTPFetcher.__init__`
- добавить `_get_client()` / `initialize()`;
- `HTTPFetcher.fetch()`;
- `HTTPFetcher.close()`.

### Как

Не создавать `httpx.AsyncClient` внутри каждого `fetch()`.

Сделать долгоживущий клиент на instance:

```text
HTTPFetcher
  └─ AsyncClient
       ├─ connection pool
       ├─ HTTP/2 reuse
       └─ bounded limits
```

Использовать `httpx.Limits` с явными `max_connections`, `max_keepalive_connections`, `keepalive_expiry` из config.

При proxy, требующем отдельного transport/client, использовать bounded client pool keyed по proxy identity либо отдельный explicit session object, а не бесконтрольное создание clients.

### Где config

- `scraper/config.py`

Добавить параметры:

```text
http_max_connections
http_max_keepalive_connections
http_keepalive_expiry_seconds
```

### Тесты

- `tests/unit/test_http_fetcher_pool.py`

Проверить:

1. 100 последовательных fetch используют один client lifecycle;
2. concurrent fetch соблюдает connection limit;
3. `close()` идемпотентен;
4. после close следующий explicit initialize создаёт новый pool;
5. redirect SSRF hooks не теряются при reuse;
6. proxy pool bounded.

### Benchmark

Сравнить TLS-heavy fixture / repeated-host workload до и после.

---

## DS-RB65. Ввести batch/stream boundary для Rust worker

### Где

- `rust/acquisition-worker/src/service/local_api.rs`
- `rust/acquisition-worker/src/adgo/activity.rs`
- `scraper/acquisition/rust_worker_client.py`

### Как

Сохранить `POST /v1/acquire` для единичной диагностики.

Добавить coarse-grained API:

```text
POST /v1/acquire-batch
```

или streaming-equivalent boundary для dev/benchmark режима.

Batch request содержит budget и policy, а результаты могут поступать по мере выполнения. В ADGO production boundary использовать существующую концепцию `AcquireBatch`, не создавать durable node на каждый URL.

### Тесты

- backpressure при медленном consumer;
- cancellation mid-stream;
- один failed URL не отменяет весь batch без policy;
- batch budget atomic accounting;
- порядок completion не обязан совпадать с input order, identity сохраняется по request id.

---

# PHASE RB23 — Настоящий Chromium/CDP backend

## DS-RB66. Провести короткий benchmark выбора Rust CDP adapter

### Где

- `rust/acquisition-worker/benches/chromium_adapter.rs`
- `docs/benchmarks/CHROMIUM_RUST_ADAPTER.md`

### Кандидаты

На implementation date сравнить поддерживаемые Rust CDP adapters; baseline candidate — `chromiumoxide`, альтернативу включать только если она реально поддерживает необходимые capabilities.

### Проверять

```text
launch/attach
navigation
DOM serialization
JS execution
network interception
cookies
iframe
screenshot
parallel pages
cancellation
process recovery
maintenance/activity
```

### Gate

Не выбирать adapter только по throughput; hard capability completeness и crash recovery обязательны.

---

## DS-RB67. Заменить HTTP fallback внутри `ChromiumBackend` реальным CDP execution

### Где

- `rust/acquisition-worker/src/backends/chromium.rs`

Добавить при необходимости:

- `rust/acquisition-worker/src/backends/chromium_pool.rs`
- `rust/acquisition-worker/src/backends/chromium_page.rs`

### Как

Удалить использование `HttpBackend` как execution implementation.

Реализовать:

- bounded browser process pool;
- bounded page/context semaphore;
- navigation wait policy;
- DOM snapshot;
- screenshot;
- response/final URL/status;
- cookie/session mapping;
- network summary;
- subresource security interception;
- timeout/cancellation;
- child process health/restart;
- deterministic cleanup.

### Тесты

`capability_conformance.rs` обязан доказать все capabilities, которые descriptor объявляет `SUPPORTED`.

Дополнительно:

- kill child Chromium during navigation → typed retryable error;
- cancellation → page/context closed;
- 1000 sequential pages → bounded RSS trend;
- 100 parallel requests → concurrency cap не превышается;
- browser restart не теряет worker health endpoint.

---

## DS-RB68. Сделать registration feature-gated

### Где

- `rust/acquisition-worker/Cargo.toml`
- `rust/acquisition-worker/src/lib.rs`

### Как

`ChromiumBackend` регистрируется только при:

```text
feature enabled
AND runtime executable available
AND startup self-test passed
```

Иначе backend либо отсутствует, либо имеет `health_state=unhealthy`, но planner его не выбирает.

### Тест

Запуск worker без Chromium binary не должен выдавать ложную `healthy full_browser` capability.

---

## DS-RB69. Укрепить legacy Playwright reference path

### Где

- `scraper/acquisition/browser_pool.py`
- `scraper/acquisition/legacy/playwright_backend.py`

### Как

Пока legacy path используется:

1. убрать ручную фиксацию Chrome/130;
2. не отправлять Client Hints, противоречащие фактическому browser version/platform;
3. формировать consistent profile из фактического runtime либо минимизировать ручные overrides;
4. сохранить legacy backend как reference/rollback, а не production stealth foundation.

### Тест

Fixture возвращает `navigator.userAgent`, `navigator.userAgentData` и request headers. Проверить внутреннюю согласованность browser identity.

---

# PHASE RB24 — Scrapling как high-cost difficult-page fallback

## DS-RB70. Добавить Scrapling только как optional external backend

### Почему

Scrapling 0.4.x предоставляет persistent browser sessions, dynamic/stealth fetchers и развитый difficult-page path. Для DeepSearch его ценность — не замена Spider/frontier, а последний дорогой tier.

### Где

Добавить Python sidecar boundary:

```text
scraper/acquisition/stealth/
├── __init__.py
├── scrapling_backend.py
├── service.py
└── models.py
```

Rust bridge:

- `rust/acquisition-worker/src/backends/external.rs`
- `rust/acquisition-worker/src/backends/scrapling.rs`

Config:

- `scraper/config.py`
- `.env.example`
- `docker-compose.yml`

Dependency:

- добавить optional extra, а не base hot-path dependency, например отдельную группу `stealth` с pinned Scrapling 0.4.x release после compatibility test.

### Как

Planner видит Scrapling как обычный `BackendDescriptor`:

```text
engine_family = scrapling
implementation_state = experimental
base_cost = high
concurrency_class = very_low
```

Rust worker передаёт URL в sidecar только после своей security validation; sidecar повторно применяет fail-closed URL policy.

### Нельзя

- делать Scrapling default HTTP fetcher;
- отдавать ему research frontier;
- включать Cloudflare/difficult-page solver для всего трафика;
- обходить authentication/access control, robots/policy или ограничения, для которых нет разрешённого режима исследования.

---

## DS-RB71. Использовать persistent lazy Scrapling session

### Где

- `scraper/acquisition/stealth/scrapling_backend.py`

### Как

Создавать `AsyncStealthySession` лениво только при первом запросе fallback tier и переиспользовать её в рамках bounded worker lifecycle.

Добавить:

```text
max_sessions
max_pages_per_session
session_ttl
navigation_timeout
max_stealth_seconds_per_run
```

### Тесты

- 50 sequential fallback requests не создают 50 browser processes;
- session TTL/restart;
- failed session удаляется из pool;
- cancellation очищает page;
- proxy/session identity не смешиваются между security contexts.

---

## DS-RB72. Добавить отдельный escalation reason `DIFFICULT_PAGE`

### Где

- `rust/acquisition-worker/src/quality.rs`
- `rust/acquisition-worker/src/planner.rs`
- `scraper/acquisition/quality.py`
- `scraper/acquisition/models.py`

### Сигналы

Scrapling рассматривается только если обычный browser result:

```text
blocked == true
OR challenge/interstitial confidently detected
OR repeated browser quality failure
```

Нельзя эскалировать по одному HTTP 403 без классификации причины.

### Тест

Mutation `blocked=false → true` должна быть обнаружена routing test, чтобы accidental mutation не отправляла массовый трафик в дорогой fallback.

---

## DS-RB73. Ввести budget и observability для difficult-page tier

### Метрики

```text
stealth_attempts_total
stealth_success_total
stealth_seconds_total
stealth_escalation_reason
stealth_session_restarts_total
stealth_cost_per_accepted_document
```

### Gate

Fallback допускается в ACTIVE только если:

- повышает accepted-document rate на целевом difficult-page corpus;
- не ухудшает security policy;
- имеет bounded resource use;
- доля stealth traffic остаётся контролируемой budget/routing policy.

---

# PHASE RB25 — Crawlee и единый scheduler ownership

## DS-RB74. Перестать называть текущий asyncio wrapper полноценным Crawlee adapter

### Где

- `scraper/acquisition/crawlee_adapter.py`
- `tests/unit/test_crawlee_adapter.py`
- `docs/architecture/MODULE_INDEX.md`

### Вариант A — предпочтительный для Rust-centric target

Переименовать реализацию в нейтральный bounded batch adapter и удалить обязательную Crawlee dependency, если реального Crawlee API больше нигде нет.

### Вариант B

Если Crawlee нужен как reference/experimental backend — реализовать настоящий adapter через его RequestQueue/session/autoscaling APIs и пометить `EXPERIMENTAL`.

### Gate решения

Сделать repo-wide import/runtime usage audit. Нельзя держать тяжёлую dependency только из-за имени файла.

---

## DS-RB75. Зафиксировать `RankedFrontier` как research-level owner

### Где

- `scraper/control/ranked_frontier.py`
- `docs/architecture/SYSTEM_MAP.md`
- `docs/architecture/TARGET_ARCHITECTURE.md`

### Как

Явно разделить:

```text
Research Frontier
= relevance / information gain / goal coverage / domain fairness

Execution Queue
= bounded worker-local concurrency/backpressure
```

Spider/Crawlee execution queue не хранит canonical research truth.

### Тест

Crash/restart execution worker не должен терять research candidate, потому что durable/retry semantics остаются над execution queue.

---

## DS-RB76. Удалить двойную дедупликацию как источник расхождения state

### Где аудит

- `scraper/control/ranked_frontier.py`
- `scraper/control/distributed_queue.py`
- `scraper/acquisition/crawlee_adapter.py`
- Spider adapter
- `scraper/normalization/canonicalizer.py`

### Как

Определить один canonical URL identity и один durable visited/accepted state. Локальные engine-level seen sets допустимы только как cache и не имеют authoritative semantics.

### Property tests

Разные URL variants:

```text
utm params
fragment
case where relevant
trailing slash
redirect aliases
percent encoding
Unicode/IDN
```

должны давать одинаковое решение независимо от выбранного execution backend.

---

# PHASE RB26 — Routing intelligence и cost model

## DS-RB77. Изменить planner score на expected cost of accepted evidence

### Где

- `rust/acquisition-worker/src/planner.rs`
- `rust/acquisition-worker/src/telemetry.rs`
- `scraper/search/information_gain.py`
- `scraper/search/cost.py`

### Как

Вместо только:

```text
base_cost / p_success
```

ввести поэтапно:

```text
ExpectedAcceptedCost =
  expected_execution_cost
  / max(P(usable_content) × P(accepted_after_quality), epsilon)
```

Research-level score остаётся выше acquisition planner:

```text
ExpectedResearchUtility =
  expected_information_gain / ExpectedAcceptedCost
```

Planner acquisition не должен сам решать семантическую релевантность документа — он получает priority/budget context из research plane.

### Тесты

Property tests:

- при одинаковом quality более дешёвый backend выигрывает;
- высокий raw success, но низкий usable-content rate не считается хорошим backend;
- дорогой browser выбирается, если дешёвый backend исторически почти всегда даёт unrendered shell;
- hard capability всегда сильнее cost score.

---

## DS-RB78. Сделать domain telemetry persistent и version-aware

### Где

- `rust/acquisition-worker/src/telemetry.rs`
- storage adapter рядом с worker либо существующая PostgreSQL boundary
- migration при необходимости

### Key

```text
domain + backend_name + backend_version + policy_version
```

### Как

Хранить EWMA/rolling stats с TTL. Не переносить плохую историю старой версии backend на новую без controlled decay.

### Тест

После обновления `backend_version` старый negative profile не блокирует probe новой версии навсегда.

---

## DS-RB79. Добавить observability ключевой метрики DeepSearch

### Метрика

```text
information_gain_per_acquisition_cost
```

Дополнительно:

```text
accepted_documents_per_100_fetches
browser_escalation_rate
false_success_rate
duplicate_fetch_rate
cost_per_evidence_item
```

### Где

- `scraper/monitoring/telemetry.py`
- Rust telemetry/OpenTelemetry export
- benchmark reports

### Gate

Оптимизация throughput не принимается, если она ухудшает accepted evidence / cost.

---

# PHASE RB27 — Расширенный test-of-tests для acquisition

## DS-RB80. Добавить multidimensional edge-space corpus

### Где

- `.deepsearch/edge-space.json`
- `benchmarks/browser/corpus.yaml`
- `rust/acquisition-worker/tests/fixtures/`

### Оси

```text
protocol
DNS result class
redirect depth
status class
content type
body size
compression
charset
JS requirement
DOM mutation delay
iframe/shadow DOM
cookies/session
network fan-out
domain fan-out
rate-limit response
connection reset
browser crash
cancellation point
budget remaining
backend health
```

### Генерация

Использовать pairwise covering array плюс обязательные corner combinations, а не полный декартов product.

---

## DS-RB81. Mutation testing planner/quality/capabilities

### Где

- `.github/workflows/mutation-testing.yml`
- Rust scheduled mutation job через `cargo-mutants` или эквивалент

### Target

```text
planner.rs
quality.rs
capabilities.rs
security/*.rs
budget-related decision code
```

### Обязательные mutants, которые должны погибать

- `>= quality threshold` → `>` / `<`;
- `blocked` boolean inversion;
- capability `SUPPORTED`/`PARTIAL` substitution;
- cost comparator inversion;
- redirect/private-IP allow inversion;
- budget `<=` boundary mutation;
- retryable/permanent error swap.

### Gate

Не требовать 100% mutation score для glue code, но decision core должен иметь высокий kill rate и не иметь surviving critical mutants.

---

## DS-RB82. Differential tests между backends

### Как

Один и тот же fixture/corpus URL выполняется через:

```text
Python HTTP reference
Rust HttpBackend
SpiderBackend
Playwright reference
Rust Chromium
Scrapling fallback (eligible subset)
```

Сравнивать не байтовый DOM, а semantic envelope:

```text
final URL
status class
required text anchors
link recall
content type
quality classification
security decision
```

---

## DS-RB83. Soak/leak matrix

### Минимум

```text
20k Rust HTTP requests
20k Spider static pages
2k Chromium navigations
500 difficult-page fallback navigations
4–8h mixed workload
```

### Следить

```text
RSS slope
FD slope
connection pool size
browser/page count
zombie processes
task count
queue length
latency drift
session restarts
```

### Gate

Не только peak value: slope после warm-up должен быть статистически близок к нулю либо объяснён bounded caches.

---

## DS-RB84. Chaos/cancellation matrix

### Сценарии

- kill Spider task;
- reset TCP mid-body;
- DNS timeout;
- 429 burst;
- kill Chromium child;
- kill Scrapling sidecar;
- cancel ADGO batch;
- CAS write success + response loss;
- worker restart при leased items.

### Инвариант

Ни один execution engine не может создать потерянный research job или stale accepted artifact.

---

# 3. Обновлённый порядок реализации

Новые findings меняют приоритет старого плана.

## P0-A — сначала восстановить правдивость runtime

```text
DS-RB56 ImplementationState
DS-RB57 capability conformance
DS-RB58 placeholder descriptor correction
DS-RB59 CI reality gate
DS-RB64 Python HTTP pooling
```

До завершения P0-A запрещено считать Rust browser execution layer production-ready.

## P0-B — реальный дешёвый execution

```text
DS-RB60 Spider dependency
DS-RB61 real SpiderBackend
DS-RB62 RankedFrontier ownership
DS-RB63 Spider budgets
DS-RB65 batch/stream boundary
```

## P0-C — реальный compatibility browser

```text
DS-RB66 CDP benchmark
DS-RB67 real ChromiumBackend
DS-RB68 runtime/feature registration
DS-RB69 legacy reference hardening
```

## P1 — difficult-page fallback

```text
DS-RB70 Scrapling external backend
DS-RB71 persistent lazy sessions
DS-RB72 difficult-page routing reason
DS-RB73 fallback budgets/metrics
```

## P1 — убрать дублирование control plane

```text
DS-RB74 Crawlee decision
DS-RB75 frontier ownership
DS-RB76 canonical visited semantics
```

## P1/P2 — intelligence и hardening

```text
DS-RB77-79 routing/cost telemetry
DS-RB80-84 multidimensional tests, mutation, differential, soak, chaos
```

---

# 4. Пересмотр первых implementation commits

После текущего состояния следующий безопасный commit sequence:

```text
Commit A01
reality audit + descriptor truthfulness

Commit A02
capability conformance fixtures/tests

Commit A03
registry feature/health gating

Commit A04
HTTPFetcher persistent client pooling

Commit A05
Spider dependency feature + compile matrix

Commit A06
real SpiderBackend single-URL path

Commit A07
Spider discovered-links DTO + mapper

Commit A08
Spider bounded batch execution + cancellation

Commit A09
Spider vs HTTP reference benchmark report

Commit A10
Rust CDP adapter benchmark

Commit A11
real ChromiumBackend minimal JS/DOM path

Commit A12
Chromium network/screenshot/session capabilities

Commit A13
Chromium crash/recovery + soak gate

Commit A14
Crawlee usage audit + single frontier decision

Commit A15
Scrapling optional sidecar contract

Commit A16
Scrapling lazy persistent session + budget

Commit A17
telemetry-driven difficult-page routing

Commit A18
mutation/differential/chaos hardening
```

Каждый commit допускается в `main` только при green tests соответствующего этапа и отсутствии regression существующего Python pipeline.

---

# 5. Новые acceptance gates

## Gate G1 — Truthful Runtime

- ни один stub не рекламирует production browser capability;
- conformance tests проверяют advertised capabilities;
- `/v1/backends` отражает реальный state;
- planner fail-closed при отсутствии required capability.

## Gate G2 — Spider Production Candidate

- настоящий Spider crate исполняется;
- security parity с `HttpBackend`;
- cancellation/budget green;
- throughput/resource advantage подтверждён benchmark;
- research priority остаётся у RankedFrontier.

## Gate G3 — Real Chromium

- JS/DOM/screenshot/network probes green;
- bounded pool;
- crash recovery green;
- no unbounded RSS/FD growth;
- legacy Playwright остаётся rollback reference до стабилизации.

## Gate G4 — Scrapling Canary

- optional dependency/sidecar;
- запускается только по explicit routing reason;
- security policy дублируется fail-closed;
- resource budget bounded;
- measurable gain на difficult-page corpus.

## Gate G5 — Single Control Plane

- ровно один research frontier owner;
- нет второго authoritative visited-state;
- Crawlee/Spider queues только execution-local;
- crash/restart не меняет research semantics.

---

# 6. Definition of Done дополнения

Дополнение считается выполненным только если:

1. Фактические runtime capabilities совпадают с descriptors.
2. `SpiderBackend` использует настоящий Spider.rs, а не `HttpBackend` wrapper.
3. `ChromiumBackend` выполняет реальный Chromium/CDP navigation.
4. Placeholder BrowserOxide/Servo/Blitz не попадают в active routing без implementation evidence.
5. Python HTTP hot path использует persistent connection pool до полного ухода на Rust.
6. DeepSearch `RankedFrontier` остаётся research-level scheduler owner.
7. Discovered links из Spider проходят обратно через DeepSearch ranking/policy.
8. Crawlee dependency либо реально используется в изолированной роли, либо удалена из base dependency set.
9. Scrapling подключён только как optional high-cost fallback и не становится вторым planner/frontier.
10. Quality/cost model оптимизирует accepted document/evidence, а не только HTTP success/throughput.
11. Domain telemetry persistent и version-aware.
12. Capability conformance, security, differential, soak, chaos и mutation gates зелёные.
13. Canonical roadmap/module index больше не называют STUB runtime стабильной production capability.
14. Документация различает `implemented contract`, `stub adapter`, `experimental engine` и `production engine`.

---

# 7. Ожидаемая конечная схема после выполнения дополнения

```text
                      Research goals
                           │
                           ▼
                Goal-aware RankedFrontier
                           │
                     priority/budget
                           │
                           ▼
                 Capability/Cost Planner
                           │
          ┌────────────────┼──────────────────┐
          │                │                  │
          ▼                ▼                  ▼
   Rust HttpBackend   Spider.rs Engine   Real Chromium/CDP
     single fetch      bounded crawl       JS/browser
          │                │                  │
          └────────────┬───┴──────────────┬───┘
                       │                  │
                       ▼                  │
                  Quality Gate            │
                       │                  │
          difficult page only            │
                       ▼                  │
               Scrapling fallback        │
                       │                  │
                       └────────┬─────────┘
                                ▼
                         CAS artifacts
                                │
                                ▼
                 extraction → evidence → index
```

Главная цель — получить не набор конкурирующих scraper framework, а **единый исследовательский control plane с несколькими специализированными execution engines, каждый из которых доказуемо выполняет заявленные capabilities и выбирается по качеству, стоимости и реальной истории домена**.

---

# 8. Reference candidates, проверяемые на implementation date

- Spider.rs: `https://github.com/spider-rs/spider`
- Scrapling: `https://github.com/D4Vinci/Scrapling`

При реализации всегда фиксировать конкретные версии и повторять compatibility/security benchmark перед обновлением major/minor runtime dependency.