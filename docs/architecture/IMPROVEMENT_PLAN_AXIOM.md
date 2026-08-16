# DeepSearch — подробный план улучшения кодовой базы с Axiom ADGO

**Статус:** целевой поэтапный план реализации  
**Ветка:** `main`  
**Основная цель:** превратить DeepSearch из набора сильных, но частично разобщённых подсистем в единый evidence-driven research engine с одним рабочим execution path, реальным hybrid retrieval и durable orchestration на базе `Homiakus/axiom/adgo`.

---

## 0. Главный принцип изменения системы

DeepSearch не нужно переписывать целиком и не нужно добавлять ещё один слой абстракций поверх уже существующих слоёв.

Главная проблема текущей кодовой базы — не отсутствие механизмов, а то, что многие полезные механизмы существуют рядом с основным `DeepSearchPipeline`, но не определяют его фактическое поведение.

Целевой принцип:

```text
один пользовательский запрос
        ↓
один application service
        ↓
одно durable execution
        ↓
один набор общих runtime policies
        ↓
discovery → acquisition → extraction → evidence → retrieval → synthesis/export
```

CLI, REST API и MCP не должны содержать собственную бизнес-логику. Они должны быть адаптерами над одним application boundary.

Для long-running orchestration вместо Temporal использовать **Axiom ADGO** (`github.com/Homiakus/axiom/adgo`).

Важно разделять:

```text
Axiom ADGO
= durable control plane
= состояние research execution
= граф работ
= retries / leases / heartbeats / fencing
= budgets / admission / provider routing
= recovery / history / explain

Python DeepSearch
= execution plane
= web/API acquisition
= Crawlee / HTTPX / Playwright
= extraction
= PDF/OCR
= embeddings / Qdrant
= evidence analysis
= export
```

Базовый `axiom.Engine` сам по себе не следует использовать как замену распределённому scheduler. Для DeepSearch нужен именно `axiom/adgo`, где уже реализованы coordinator/worker split, durable tasks, leases, heartbeat, stale-worker fencing, recovery, budgets и remote worker protocol.

---

# 1. Целевая архитектура

```text
                      ┌────────────────────┐
                      │ CLI / REST / MCP   │
                      └─────────┬──────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ ResearchApplication  │
                    │ Service              │
                    └─────────┬────────────┘
                              │ Start / Get / Cancel
                              ▼
                 ┌─────────────────────────────┐
                 │ Axiom ADGO Coordinator      │
                 │ Go                          │
                 │                             │
                 │ immutable Research Plan     │
                 │ durable execution state     │
                 │ task queue                  │
                 │ leases / heartbeats         │
                 │ retry / repair              │
                 │ budget / admission          │
                 │ history / explain           │
                 └──────────────┬──────────────┘
                                │
                ADGO remote worker protocol
             poll / heartbeat / complete / fail
                                │
                  ┌─────────────┴─────────────┐
                  │                           │
                  ▼                           ▼
       ┌────────────────────┐      ┌────────────────────┐
       │ Python worker A    │      │ Python worker B    │
       │                    │      │                    │
       │ discovery          │      │ acquisition        │
       │ extraction         │      │ indexing           │
       │ evidence           │      │ export             │
       └─────────┬──────────┘      └─────────┬──────────┘
                 │                           │
                 └────────────┬──────────────┘
                              ▼
              ┌──────────────────────────────┐
              │ Shared application services  │
              │                              │
              │ Crawlee / HTTPX / Playwright │
              │ extraction / PDF / OCR       │
              │ CAS / dedup                  │
              │ Qdrant / FastEmbed           │
              │ evidence store               │
              └──────────────────────────────┘
```

## Источники истины

Нужно явно закрепить:

- **Axiom ADGO store** — источник истины для состояния research execution, node/task status, retry, lease, history, budget и workflow progress;
- **PostgreSQL** — источник истины для прикладных метаданных документов, источников, chunks, claims/evidence и индексации;
- **CAS/filesystem/object storage** — source of truth для бинарных/сырьевых artifacts;
- **Qdrant** — retrieval index, а не authoritative data store;
- **Redis** не должен хранить уникальное состояние, без которого невозможно восстановление execution.

---

# 2. Целевой research lifecycle

```text
RECEIVED
   ↓
NORMALIZE_QUERY
   ↓
PLAN_RESEARCH
   ↓
DISCOVER_SOURCES
   ↓
RANK_SEEDS
   ↓
CRAWL / ACQUIRE
   ↓
EXTRACT
   ↓
NORMALIZE / DEDUP
   ↓
INDEX
   ↓
BUILD_EVIDENCE
   ↓
EVALUATE_COVERAGE
   ├── enough ──────────────→ SYNTHESIZE / EXPORT
   │
   └── gaps remain
          ↓
      PLAN_FOLLOWUP
          ↓
      DISCOVER / ACQUIRE
          ↓
         ...
```

Research должен останавливаться не только по `max_pages`, но и по evidence sufficiency / marginal information gain / budget.

---

# 3. Правила выполнения плана

Каждый пункт ниже должен проходить цепочку:

```text
Наблюдение
→ подтверждение текущего поведения
→ минимальное изменение
→ unit tests
→ integration/contract tests
→ runtime verification
→ документация
```

Запрещено:

- одновременно переписывать несколько независимых подсистем без промежуточного green state;
- вводить второй parallel execution path;
- оставлять fake/demo result там, где внешний интерфейс выглядит production-ready;
- дублировать job state между FastAPI и Axiom;
- делать Axiom-specific детали частью extraction/acquisition domain API;
- смешивать Axiom orchestration с Qdrant retrieval logic;
- хранить необратимые внешние side effects без idempotency contract.

---

# PHASE 0 — зафиксировать воспроизводимую baseline

## DS-A00. Зафиксировать текущую версию и сделать CI обязательным

### Что делаем

Создать воспроизводимую точку до архитектурных изменений.

### Где

- `.github/workflows/ci.yml`
- `pyproject.toml`
- `README.md`
- `README.ru.md`
- `docs/architecture/AUDIT_REPORT.md`

### Как

CI должен отдельно запускать:

1. dependency install/frozen check;
2. `python -m compileall scraper`;
3. `ruff check`;
4. formatter check;
5. mypy/pyright выбранного набора production modules;
6. unit tests без сети;
7. integration tests отдельным job;
8. package build;
9. import smoke test wheel-пакета.

Не объявлять CI green, пока network-dependent tests находятся в unit suite.

### Проверка

- PR/commit с синтаксической ошибкой падает;
- unit suite работает offline;
- integration suite явно маркирована;
- README не заявляет число passing tests вручную без CI source.

### Definition of Done

`main` имеет один официальный CI pipeline, соответствующий фактическому состоянию проекта.

---

## DS-A01. Синхронизировать документацию с реальным runtime

### Что делаем

Убрать заявления `STABLE/production-ready` для подсистем, которые не участвуют в основном execution path или являются placeholder.

### Где

- `docs/architecture/MODULE_INDEX.md`
- `docs/architecture/AUDIT_REPORT.md`
- `docs/architecture/SYSTEM_MAP.md`
- `README.md`
- `README.ru.md`

### Как

Ввести статусы:

```text
ACTIVE      — используется основным execution path
EXPERIMENTAL — запускается только отдельным opt-in path
STUB        — API существует, полезного результата нет
DEPRECATED  — оставлено только на время миграции
```

### Проверка

Для каждого `ACTIVE` модуля существует хотя бы один integration test, доказывающий достижимость из пользовательского entrypoint.

---

# PHASE 1 — один application boundary

## DS-A02. Ввести `ResearchApplicationService`

### Что делаем

Убрать orchestration logic из API/CLI/MCP и создать единый application service.

### Где

Добавить:

- `scraper/application/__init__.py`
- `scraper/application/research_service.py`
- `scraper/application/models.py`

Изменить:

- `scraper/api/routes.py`
- `scraper/cli/main.py`
- `scraper/mcp/server.py`

### Как

Публичный контракт:

```python
class ResearchApplicationService(Protocol):
    async def start(request: ResearchRequest) -> ResearchHandle: ...
    async def status(run_id: str) -> ResearchStatus: ...
    async def result(run_id: str) -> ResearchResult | None: ...
    async def cancel(run_id: str) -> None: ...
```

CLI/API/MCP не создают `DeepSearchPipeline()` напрямую.

### Проверка

Contract test вызывает одинаковый use case через CLI/API/MCP и проверяет одинаковую application semantics.

---

## DS-A03. Удалить фиктивное успешное поведение Search

### Что делаем

До реализации настоящего retrieval прекратить возврат `example.com` demo results.

### Где

- `scraper/search/search_engine.py`
- `scraper/storage/vector_store.py`
- `scraper/visual/pixel_rag.py`
- `scraper/api/routes.py`
- `scraper/mcp/server.py`

### Как

Незавершённая возможность должна возвращать typed feature state:

```text
NOT_CONFIGURED
NOT_IMPLEMENTED
INDEX_EMPTY
READY
```

### Проверка

Ни один API/MCP endpoint не может вернуть synthetic result, не помеченный как fixture в test environment.

---

# PHASE 2 — Axiom ADGO как durable control plane

## DS-A04. Добавить Go-модуль orchestration на базе Axiom ADGO

### Что делаем

Создать отдельный компактный Go service внутри monorepo.

### Где

Добавить:

```text
orchestrator/
├── go.mod
├── go.sum
├── cmd/deepsearch-orchestrator/main.go
├── internal/plan/research.go
├── internal/server/api.go
├── internal/server/workers.go
├── internal/config/config.go
├── internal/mapping/models.go
└── tests/
```

### Как

Использовать:

```go
github.com/Homiakus/axiom/adgo
```

Пиновать конкретную совместимую версию/commit через `go.mod`; не использовать плавающий branch.

Первый production profile:

- `adgo.OpenProduction`;
- durable Pebble backend;
- один coordinator process;
- remote Python workers;
- configurable worker auth token;
- TLS/reverse proxy в deployment profile.

### Проверка

1. старт execution;
2. coordinator restart;
3. execution восстанавливается;
4. pending task не теряется;
5. history сохраняется.

---

## DS-A05. Описать immutable `ResearchPlan` в ADGO

### Что делаем

Перенести lifecycle research job из неявного Python while-loop в явный durable graph.

### Где

- `orchestrator/internal/plan/research.go`

### Минимальные nodes

```text
NormalizeQuery
PlanResearch
DiscoverSources
RankSeeds
AcquireBatch
ExtractBatch
NormalizeBatch
IndexBatch
BuildEvidence
EvaluateCoverage
PlanFollowup
BuildArchive
CompleteResearch
```

Дополнительные nodes после стабилизации:

```text
ExtractPDF
ExtractTables
ExtractVisualEvidence
ResolveContradictions
Synthesize
HumanReview
```

### Как

Для каждого node определить:

- input facts;
- output facts;
- permissions;
- external effect flag;
- timeout;
- retry policy;
- idempotency key;
- cost estimate;
- risk level;
- next transitions;
- repair strategy.

### Проверка

Compiler tests должны ловить:

- missing dependencies;
- циклы без bounds;
- node без timeout/idempotency для внешнего effect;
- conflicting parallel writes.

---

## DS-A06. Создать Python ADGO Remote Worker Client

### Что делаем

Связать Python DeepSearch с Axiom ADGO без FFI и без переписывания acquisition/extraction на Go.

### Где

Добавить:

```text
scraper/orchestration/
├── __init__.py
├── axiom_client.py
├── axiom_worker.py
├── protocol.py
├── registry.py
└── handlers/
```

### Как

Реализовать ADGO worker protocol:

```text
POST /v1/poll
POST /v1/heartbeat
POST /v1/complete
POST /v1/fail
```

Worker обязан сохранять/передавать fencing identity:

```text
ExecutionID
TaskID
WorkerID
Attempt
WorkToken / lease identity
```

Handler registry связывает activity name с Python function.

### Проверка

Contract suite поднимает Go coordinator и Python worker и проверяет:

1. poll;
2. task claim;
3. heartbeat;
4. complete;
5. transient fail + retry;
6. lease expiry;
7. stale result получает conflict и не коммитится;
8. protocol version mismatch обнаруживается явно.

---

## DS-A07. Перевести `/research` на durable job semantics

### Что делаем

HTTP request больше не держится до завершения всего исследования.

### Где

- `scraper/api/routes.py`
- `scraper/application/research_service.py`
- `orchestrator/internal/server/api.go`

### Новый контракт

```text
POST /api/v1/research
→ 202 Accepted
→ run_id

GET /api/v1/research/{run_id}
→ state/progress/budget/current nodes

GET /api/v1/research/{run_id}/result
→ result when available

POST /api/v1/research/{run_id}/cancel
```

### Проверка

- API process restart не теряет research job;
- повторный `start` с одинаковым idempotency key использует `StartOrLoad` semantics;
- cancel виден worker'ам и не создаёт новые tasks.

---

## DS-A08. Удалить ложный `/crawl` RUNNING state

### Что делаем

Текущий `/crawl` не должен возвращать `RUNNING`, если worker execution фактически не начат.

### Где

- `scraper/api/routes.py`
- `scraper/control/scheduler.py`

### Как

Выбрать один путь:

1. crawl становится отдельным ADGO plan/subflow;
2. либо endpoint временно отключается как unsupported.

Не сохранять глобальный in-memory `RequestFrontier` как job source of truth.

### Проверка

Каждый `RUNNING` job соответствует существующему durable execution.

---

# PHASE 3 — decomposition текущего монолитного pipeline

## DS-A09. Разрезать `DeepSearchPipeline.execute` на application activities

### Что делаем

Убрать функцию, которая одновременно делает discovery, crawl, PDF, media и export.

### Где

Изменить:

- `scraper/pipeline/search_pipeline.py`

Добавить:

```text
scraper/application/activities/
├── discovery.py
├── acquisition.py
├── extraction.py
├── normalization.py
├── indexing.py
├── evidence.py
└── export.py
```

### Как

Каждая activity:

- принимает immutable input DTO;
- возвращает typed output DTO;
- не знает о FastAPI/MCP;
- не знает о graph transitions;
- принимает runtime dependencies через constructor/context;
- сообщает usage отдельно от результата.

### Проверка

Cyclomatic complexity orchestration-функций ≤ 10; отдельные activities тестируются без запуска полного research job.

---

## DS-A10. Ввести `ResearchExecutionContext`

### Что делаем

Все runtime policies должны поступать через один context/dependency container.

### Где

- `scraper/application/context.py`

### Состав

```text
budget
security policy
source policy
rate limiter
deduplicator
cache/CAS
telemetry
retriever
evidence store
clock
cancellation
```

### Как

Запретить прямой импорт глобального `settings` из core activities там, где значение должно быть per-run.

### Проверка

В unit test можно создать контекст с fake clock/fake fetcher/fake store и полностью воспроизвести activity.

---

# PHASE 4 — реально подключить существующие control mechanisms

## DS-A11. Подключить `BudgetTracker` к фактической работе

### Что делаем

Budget перестаёт быть отдельным тестируемым классом и начинает ограничивать network/browser/LLM/visual work.

### Где

- `scraper/control/budget.py`
- acquisition/extraction/indexing activities
- Axiom ADGO plan budget mapping

### Как

Разделить:

- ADGO workflow-level budget: cumulative cost/deadline/admission;
- DeepSearch domain metrics: bytes/pages/browser seconds/tokens.

Каждая activity возвращает `ResourceUsage`.

ADGO coordinator принимает usage и решает, можно ли планировать следующую expensive node.

### Проверка

Property tests: ни один путь не превышает configured hard budget без terminal budget state.

---

## DS-A12. Подключить rate limiter и host concurrency

### Где

- `scraper/control/rate_limiter.py`
- `scraper/acquisition/http_fetcher.py`
- `scraper/acquisition/browser_pool.py`
- Crawlee adapter

### Как

Все внешние запросы проходят через общий host admission boundary.

Для глобальных provider limits использовать ADGO AdmissionController; для URL-host crawling — DeepSearch host limiter/Crawlee concurrency.

### Проверка

Load test доказывает:

- per-host RPS;
- global RPS;
- 429 вызывает controlled backoff;
- нет burst выше configured bound.

---

## DS-A13. Подключить robots policy к acquisition/discovery

### Где

- `scraper/discovery/robots.py`
- discovery activities
- acquisition activity

### Как

Robots decision фиксировать в provenance:

```text
allowed
blocked
unknown/error
policy override
```

### Проверка

Запрещённый robots URL не доходит до fetcher в default profile.

---

## DS-A14. Подключить CAS и dedup в основной path

### Где

- `scraper/storage/cas.py`
- `scraper/normalization/deduplicator.py`
- acquisition/extraction activities

### Как

Перед повторной дорогой обработкой проверять:

1. canonical URL;
2. content hash;
3. near duplicate;
4. cache namespace/version.

### Проверка

Две разные URL с одинаковым content не создают два независимых embedding corpus без явной причины.

---

# PHASE 5 — Crawlee становится реальным crawl runtime

## DS-A15. Заменить самодельную list-queue на Crawlee RequestQueue

### Что делаем

Использовать уже подключённый `crawlee` для queue lifecycle, retries, sessions и concurrency.

### Где

Добавить:

- `scraper/acquisition/crawlee_adapter.py`

Изменить/депрекейтить:

- `scraper/control/scheduler.py`
- queue logic внутри `search_pipeline.py`

### Как

DeepSearch сохраняет собственные:

- Page Intelligence;
- AcquisitionPlanner;
- source/evidence policy;
- quality gates.

Crawlee отвечает за:

- request queue;
- crawl concurrency;
- retries;
- session/browser lifecycle.

### Проверка

- больше нет `list.pop(0)` в production crawl;
- queue переживает локальный worker restart согласно выбранной storage semantics;
- duplicate URL не обрабатывается повторно без policy reason.

---

## DS-A16. Разделить crawl frontier и research graph

### Что делаем

Не превращать каждый URL в отдельный ADGO workflow node.

### Как

ADGO node `AcquireBatch` управляет bounded batch crawl, а Crawlee управляет внутренним URL frontier.

Boundary:

```text
ADGO = coarse-grained research tasks
Crawlee = fine-grained URL scheduling
```

### Проверка

Research на 10 000 URL не создаёт 10 000 static ADGO graph nodes.

---

# PHASE 6 — исправить adaptive acquisition

## DS-A17. Сделать `CostPlanner` единственным decision engine эскалации

### Где

- `scraper/control/planner.py`
- `scraper/acquisition/engine.py`
- `scraper/acquisition/page_classifier.py`

### Как

Ввести модели:

```text
PageSignals
AcquisitionCandidate
AcquisitionDecision
AcquisitionOutcome
```

Planner получает candidate costs и predicted quality/success.

### Целевая функция

```text
utility =
  success_probability × expected_quality
  - latency_weight × latency
  - cost_weight × monetary_cost
  - token_weight × token_cost
  - risk_weight × failure_risk
```

Начать с deterministic heuristics; ML не требуется.

### Проверка

Decision table tests для static HTML, SPA, blocked page, JSON API, PDF, visual-heavy page.

---

## DS-A18. Сделать Direct API tier реально достижимым

### Проблема

API discovery сейчас зависит в основном от browser network logs, но решение о L2 принимается до полноценного browser capture.

### Как

Добавить lightweight network probe tier:

```text
HTTP
 ↓
quality sufficient? → return
 ↓ no
lightweight browser/network probe
 ↓
structured API found? → HTTP replay API
 ↓ no
full browser render
```

### Где

- `scraper/acquisition/engine.py`
- `scraper/acquisition/browser_pool.py`
- `scraper/acquisition/page_classifier.py`

### Проверка

Fixture SPA с XHR API выбирает API replay без full visual browser path.

---

## DS-A19. Заменить `content_quality = 1 - block_score` на реальный quality evaluator

### Где

Добавить:

- `scraper/quality/content_quality.py`
- `scraper/quality/models.py`

### Метрики

- main text length/density;
- boilerplate ratio;
- query relevance;
- language confidence;
- extraction completeness;
- schema completeness;
- duplicate probability;
- source authority signal;
- publication/freshness metadata;
- obvious shell/challenge detection.

### Выход

```text
ACCEPT
RETRY
ESCALATE
DISCARD
```

### Проверка

Golden pages: empty SPA shell не получает высокий quality score.

---

# PHASE 7 — security boundary

## DS-A20. Сделать единый URL SecurityPolicy

### Что делаем

SSRF validation должна применяться ко всем network paths, а не только initial HTTP fetch.

### Где

Добавить:

- `scraper/security/url_policy.py`

Подключить к:

- HTTPFetcher;
- redirects;
- media downloader;
- PDF downloader;
- browser navigation;
- browser subresources/API replay;
- discovery providers.

### Как

Проверять destination после каждого redirect resolution и перед открытием нового origin.

### Проверка

Security tests:

- direct private IP;
- DNS resolving to private IP;
- public → private redirect;
- IPv6 loopback/link-local;
- browser subresource to private host;
- oversized response.

---

## DS-A21. Закрыть API control plane

### Где

- `scraper/api/app.py`
- `scraper/api/routes.py`
- orchestrator API

### Как

- реальная API key/auth middleware;
- убрать permissive credentialed CORS;
- ограничить output path server-side;
- request-size limits;
- per-user/run quotas;
- operator endpoints Axiom отдельно от public research API.

### Проверка

Unauthorized request не может стартовать costly research job или изменить execution state.

---

# PHASE 8 — discovery provider architecture

## DS-A22. Удалить hard-coded intent keyword routing из core

### Где

- `scraper/discovery/seed_finder.py`

### Добавить

```text
scraper/discovery/providers/
├── base.py
├── wikipedia.py
├── arxiv.py
├── pubmed.py
├── europe_pmc.py
├── openalex.py
├── crossref.py
├── github.py
└── web.py
```

### Контракт

```python
class DiscoveryProvider(Protocol):
    async def discover(self, request: DiscoveryRequest) -> DiscoveryBatch: ...
```

### Как

`QueryAnalyzer` формирует typed `ResearchIntent`:

```text
domains
languages
freshness
source_classes
query_variants
risk
```

### Проверка

Добавление нового provider не требует изменения центрального `if category == ...`.

---

## DS-A23. Выполнять независимых discovery providers конкурентно

### Как

`asyncio.TaskGroup`/bounded concurrency с per-provider timeout.

Каждый provider возвращает отдельный status:

```text
SUCCESS
EMPTY
RATE_LIMITED
FAILED
SKIPPED
```

### Проверка

Один зависший provider не задерживает весь seed discovery до общего timeout.

---

# PHASE 9 — extraction и document model

## DS-A24. Ввести структурный Document model

### Добавить

- `scraper/domain/document.py`

### Модель

```text
Document
├── source
├── metadata
├── sections[]
├── tables[]
├── figures[]
├── citations[]
├── raw_artifact_ref
└── provenance
```

Не использовать Markdown string как единственный внутренний формат.

### Проверка

HTML/PDF adapters дают один domain contract.

---

## DS-A25. Заменить word-based chunking на structure-aware chunking

### Где

- убрать primary chunking из `ArchiveExporter._chunk_text`;
- добавить `scraper/retrieval/chunking.py`.

### Chunk metadata

```text
chunk_id
document_id
source_url
section_path
heading
ordinal
text
language
published_at
retrieved_at
content_hash
previous_chunk_id
next_chunk_id
```

### Проверка

Heading и table boundaries не разрываются случайно на лимите слов.

---

# PHASE 10 — настоящий retrieval

## DS-A26. Реализовать Qdrant adapter полностью

### Где

- `scraper/storage/vector_store.py`

### Как

Реализовать:

- collection bootstrap/versioning;
- upsert;
- delete by document;
- dense search;
- sparse search;
- payload filtering;
- health check;
- index schema validation.

Не хранить фиктивный `dimensions=1536` без связи с используемой model.

### Проверка

Integration test с настоящим Qdrant container.

---

## DS-A27. Добавить FastEmbed для local embedding/reranking path

### Где

- `pyproject.toml`
- `scraper/retrieval/embeddings.py`
- `scraper/retrieval/reranker.py`

### Архитектура

```text
query
 ├─ dense embedding
 └─ sparse embedding
        ↓
     Qdrant
        ↓
     RRF/fusion
        ↓
 candidate 30–100
        ↓
 reranker
        ↓
 top evidence 5–15
```

### Проверка

Benchmark показывает Recall@K/NDCG выше dense-only baseline на golden corpus.

---

## DS-A28. Сделать `SearchEngine` реальным façade над Retriever

### Где

- `scraper/search/search_engine.py`
- `scraper/retrieval/service.py`

### Как

SearchEngine больше не знает о demo docs; возвращает результаты только из configured index.

### Проверка

Результат содержит source/chunk provenance, а `score` имеет явно документированную semantics.

---

# PHASE 11 — evidence-driven research

## DS-A29. Добавить Evidence Store

### Добавить

```text
scraper/evidence/
├── models.py
├── store.py
├── builder.py
├── coverage.py
└── contradictions.py
```

### Основные сущности

```text
Claim
Evidence
Source
SupportRelation
Contradiction
ResearchGap
```

### Claim

```text
id
text
normalized_key
scope
confidence
status
```

### Evidence

```text
claim_id
source_id
chunk_id
relation = SUPPORTS | CONTRADICTS | CONTEXT
confidence
quote_span/provenance
```

### Проверка

Для любого финального claim можно получить список supporting/contradicting source chunks.

---

## DS-A30. Ввести EvidenceCoverageEvaluator

### Что делаем

Research перестаёт останавливаться только по количеству страниц.

### Метрики

```text
question coverage
claim coverage
source diversity
authority diversity
contradiction unresolved ratio
freshness coverage
novel evidence gain
```

### Решение

```text
SUFFICIENT
FOLLOW_UP_REQUIRED
BUDGET_EXHAUSTED
NO_PROGRESS
```

### Где

- `scraper/evidence/coverage.py`
- ADGO `EvaluateCoverage` node/gate.

### Проверка

Synthetic research scenario с явным информационным пробелом создаёт follow-up branch.

---

## DS-A31. Добавить bounded follow-up research loop

### Как

ADGO graph допускает цикл только с bounds:

- max iterations;
- max cost;
- deadline;
- epsilon/minimum evidence gain;
- no-progress counter.

### Проверка

Цикл гарантированно завершается при неизменном наборе источников.

---

# PHASE 12 — adaptive provider routing через Axiom ADGO

## DS-A32. Использовать ADGO provider routing для LLM/search providers

### Что делаем

LLM/search provider fallback не должен быть набором ad-hoc try/except.

### Где

- orchestrator plan/registry;
- Python activity handlers.

### Capability examples

```text
web-search
llm-cheap
llm-reasoning
embedding
rerank
ocr
vision
```

### Hard constraints

- privacy;
- risk;
- permissions;
- max cost;
- latency target.

### Feedback

- EWMA latency;
- quality;
- cost;
- reliability;
- circuit state.

### Проверка

Transient failure primary provider приводит к durable retry и выбору fallback provider без потери execution state.

---

## DS-A33. Использовать ADGO result cache для pure expensive activities

### Кандидаты

- deterministic parsing;
- chunking;
- embeddings;
- normalized PDF extraction;
- deterministic source scoring.

### Не кэшировать

- необратимые внешние side effects;
- time-sensitive search без version/freshness key.

### Проверка

Два execution с одинаковым immutable input не выполняют expensive pure activity повторно при валидном cache key.

---

# PHASE 13 — ошибки и recovery semantics

## DS-A34. Убрать широкие `except Exception` из orchestration semantics

### Что делаем

Ошибка должна классифицироваться.

### Типы

```text
TransientFailure
RateLimitFailure
InvalidInputFailure
QualityFailure
PermanentFailure
SecurityFailure
BudgetFailure
AmbiguousSideEffectFailure
```

### Как

Python worker переводит исключение в ADGO failure class.

### Проверка

- network timeout → retry;
- 429 → retry-after;
- parser quality failure → repair/escalate;
- SSRF violation → terminal security failure;
- exhausted budget → controlled terminal state.

---

## DS-A35. Добавить idempotency contract для всех external activities

### Как

Ключ строится из:

```text
execution_id
activity/node
stable input digest
revision
```

Для download/index operations использовать deterministic content/document IDs.

### Проверка

Worker crash после фактического side effect, но до `complete`, не создаёт дубликат при redelivery.

---

# PHASE 14 — observability

## DS-A36. Объединить OpenTelemetry с ADGO execution identity

### Где

- `scraper/monitoring/telemetry.py`
- Python worker middleware
- Go orchestrator

### Обязательные dimensions

```text
run_id
node/activity
attempt
worker_id
source host
strategy
provider
failure_class
```

### Проверка

Из одного `run_id` можно восстановить chronology от API request до fetch/index/export.

---

## DS-A37. Сделать dashboard только из реальных данных

### Где

- `scraper/ui/dashboard.py`

### Удалить

Все hard-coded metrics/status.

### Показывать

- active executions;
- waiting/retry nodes;
- worker health;
- current budget;
- pages acquired;
- evidence coverage;
- Qdrant indexing lag;
- failure classes.

### Проверка

UI не показывает job/throughput, отсутствующий в backend state.

---

# PHASE 15 — storage consistency

## DS-A38. Устранить три источника истины schema/migrations

### Где

- `migrations/001_init.sql`
- `migrations/001_initial_schema.sql`
- SQLAlchemy models.

### Как

Выбрать один migration framework/source.

Предпочтительно:

- Alembic или единый SQL migration chain;
- monotonically numbered migrations;
- CI test разворачивает пустую DB до HEAD.

### Проверка

Fresh DB и upgraded DB получают одинаковую schema checksum.

---

## DS-A39. Отделить orchestration state от domain DB

### Правило

PostgreSQL не должен иметь конкурирующий `job_status`, который может расходиться с ADGO execution status.

Если нужен projection:

```text
Axiom execution
  ↓ events/status
read-model projection in PostgreSQL
```

Projection восстанавливаемый.

### Проверка

Удаление projection не уничтожает способность Axiom восстановить execution.

---

# PHASE 16 — конфигурация и зависимости

## DS-A40. Сделать конфигурацию typed и проверяемой на startup

### Где

- `scraper/config.py`
- `.env.example`
- orchestrator config.

### Как

Группы:

```text
runtime
network
security
crawl
retrieval
orchestrator
providers
storage
```

Startup validation проверяет обязательные URL/paths/credentials только для включённых features.

### Проверка

`.env.example` содержит только реальные поля.

---

## DS-A41. Удалить зависимости, не участвующие ни в ACTIVE, ни в EXPERIMENTAL path

### Как

Для каждой dependency зафиксировать owner module и reason.

Crawlee оставить и использовать реально.

Не добавлять LlamaIndex/LangGraph до появления измеримой необходимости.

### Проверка

Dependency inventory test/doc соответствует импортам и feature flags.

---

# PHASE 17 — test architecture

## DS-A42. Разделить test pyramid

### Структура

```text
tests/
├── unit/
├── contract/
├── integration/
├── e2e/
├── security/
├── property/
└── benchmarks/
```

### Правила

- unit: без сети и Chromium;
- contract: Python↔Go ADGO, provider contracts;
- integration: Qdrant/Postgres/Playwright;
- e2e: полный research;
- security: SSRF/auth/path traversal;
- property: canonicalization/dedup/budget/planner;
- benchmarks: retrieval + throughput.

### Проверка

`pytest tests/unit` стабильно работает offline.

---

## DS-A43. Добавить crash/recovery тесты Axiom integration

### Сценарии

1. coordinator crash до task claim;
2. worker crash после claim;
3. worker crash после external effect до complete;
4. coordinator crash после complete request;
5. lease expiry;
6. stale worker complete;
7. duplicate start request;
8. retry persisted across restart;
9. budget exhaustion during retry;
10. cancel during active task.

### Проверка

История execution остаётся объяснимой и не содержит невозможных transitions.

---

# PHASE 18 — research quality evaluation

## DS-A44. Создать golden research benchmark

### Добавить

```text
evals/
├── datasets/
├── expected/
├── scorers/
└── README.md
```

### Набор

Минимум 100 запросов разных классов:

- scientific;
- medical;
- engineering;
- current-event-like fixtures;
- multilingual;
- conflicting sources;
- sparse evidence;
- noisy web pages.

### Метрики

```text
SourceRecall
EvidenceRecall
EvidencePrecision
ClaimSupportRate
UnsupportedClaimRate
ContradictionRecall
RetrievalRecall@K
NDCG@K
cost per successful research
latency per successful research
```

### Проверка

Любое изменение planner/retriever сравнивается с baseline.

---

## DS-A45. Подключить Pydantic Evals или Ragas только как evaluation layer

### Правило

Не использовать eval framework как runtime architecture.

### Проверка

Evaluation package можно удалить без изменения production execution behavior.

---

# PHASE 19 — PixelRAG после текстового retrieval

## DS-A46. Перевести PixelRAG в явный experimental feature

### До выполнения условий

PixelRAG не считается ready, пока нет:

- рабочего text retrieval;
- real Qdrant index;
- retrieval benchmark;
- visual dataset/eval.

### Где

- `scraper/visual/pixel_rag.py`
- feature configuration.

### Проверка

Disabled PixelRAG не влияет на text research flow.

---

## DS-A47. Реализовывать visual retrieval по уровням

```text
V1 captions/alt/table metadata
V2 OCR regions
V3 figure/image embeddings
V4 layout-aware retrieval
V5 PixelRAG multivector
```

Каждый уровень добавляется только если eval показывает прирост на visual benchmark.

---

# PHASE 20 — cleanup legacy paths

## DS-A48. Удалить root research scripts как параллельные приложения

### Кандидаты

- `deep_pdf_research_engine.py`
- `run_laser_research.py`
- `run_papanicolaou_lbc_research.py`

### Как

Перенести полезные сценарии в:

```text
examples/
```

или преобразовать в конфигурации/fixtures поверх `ResearchApplicationService`.

### Проверка

В repo остаётся один production research engine.

---

## DS-A49. Удалить или переписать старый `RequestFrontier`

После Crawlee+ADGO migration определить:

- если он нужен как pure domain priority policy — оставить только policy component;
- если queue semantics полностью покрыты Crawlee/ADGO — удалить.

### Проверка

Нет трёх независимых очередей для одной работы: Python list + RequestFrontier + Crawlee.

---

# PHASE 21 — rollout strategy

## DS-A50. Ввести feature flags миграции, но не два равноправных production path

### Флаги

```text
orchestration_backend = legacy | axiom
retrieval_backend = disabled | qdrant
visual_retrieval = disabled | experimental
```

Legacy допускается только на время migration window.

### Проверка

Есть дата/condition удаления legacy path.

---

## DS-A51. Shadow-run Axiom orchestration

На раннем этапе:

- legacy pipeline выполняет работу;
- Axiom graph получает те же synthetic/test events и строит expected transitions без внешних effects.

Сравнивать:

```text
steps
budget
retry decisions
termination
```

После parity Axiom становится primary.

---

## DS-A52. Переключить primary execution на Axiom ADGO

### Preconditions

- contract tests green;
- crash recovery green;
- no fake Search results;
- budget/rate/security wired;
- one application boundary;
- e2e research passes.

### После переключения

Удалить прямой `DeepSearchPipeline()` construction из interfaces.

---

# 4. Предлагаемый ADGO Activity Registry

| Activity | Python implementation | Effect | Retry | Idempotency |
|---|---|---|---|---|
| `NormalizeQuery` | query analyzer | pure | none/low | input digest |
| `PlanResearch` | planner | pure/LLM optional | quality/transient | query+policy digest |
| `DiscoverSources` | provider router | network | transient/rate-limit | query+provider+window |
| `RankSeeds` | scorer | pure | none | seed set digest |
| `AcquireBatch` | Crawlee/acquisition | network | transient/rate-limit | URL canonical hash |
| `ExtractBatch` | extraction engine | pure-ish | quality | content hash+extractor version |
| `ExtractPDF` | PDF pipeline | pure/network input | transient/quality | PDF hash |
| `NormalizeBatch` | canonical/dedup | pure | none | content hash |
| `IndexBatch` | Qdrant adapter | external store | transient | chunk IDs |
| `BuildEvidence` | evidence builder | pure/LLM optional | quality | corpus revision |
| `EvaluateCoverage` | coverage evaluator | pure | none | evidence revision |
| `PlanFollowup` | research planner | LLM optional | quality/transient | gaps revision |
| `BuildArchive` | archive exporter | filesystem | transient | execution+result revision |

---

# 5. Axiom-specific invariants

## AX-INV-01 — deterministic orchestration

LLM/provider result может быть probabilistic, но graph transition должен определяться typed result + deterministic gate.

## AX-INV-02 — no direct worker state mutation

Python worker не изменяет execution state напрямую. Он возвращает activity result/failure; coordinator коммитит transition.

## AX-INV-03 — stale worker cannot commit

Любой stale lease result должен отклоняться.

## AX-INV-04 — external effects are at-least-once

Все external activity handlers обязаны иметь idempotency/reconciliation strategy.

## AX-INV-05 — execution is pinned to plan digest

Изменение ResearchPlan не должно молча менять уже запущенные execution.

## AX-INV-06 — budget is monotonic

Consumed budget не уменьшается при retry/recovery.

## AX-INV-07 — cancellation is durable

Cancel должен переживать restart coordinator.

## AX-INV-08 — no hidden success

Partial failure не превращается в `SUCCESS` без явного degraded/partial status и provenance.

---

# 6. Ключевые acceptance scenarios

## Scenario 1 — статическая статья

Ожидание:

```text
HTTP → quality accept → extract → index → evidence
```

Browser не запускается.

## Scenario 2 — SPA с публичным JSON API

```text
HTTP shell
→ network probe
→ API discovery
→ API replay
→ extraction
```

Full browser используется только если API replay недостаточен.

## Scenario 3 — временный 429

```text
activity fail: rate_limit
→ RetryAfter
→ durable retry checkpoint
→ coordinator restart
→ retry continues
```

## Scenario 4 — worker умер во время обработки

```text
lease expires
→ task recovery
→ second worker claims
→ first worker stale complete rejected
```

## Scenario 5 — недостаточно evidence

```text
EvaluateCoverage = FOLLOW_UP_REQUIRED
→ PlanFollowup
→ new source discovery
→ additional evidence
```

## Scenario 6 — evidence больше не растёт

```text
marginal gain < epsilon
→ NO_PROGRESS
→ finish partial/degraded with explicit gaps
```

## Scenario 7 — budget exhausted

Никакая новая expensive activity не планируется; execution завершается controlled budget state.

---

# 7. Порядок реализации

Рекомендуемый порядок commit series:

```text
1. DS-A00..A03  baseline + truthfulness + app boundary
2. DS-A04..A08  Axiom ADGO skeleton + Python remote worker
3. DS-A09..A10  split pipeline + execution context
4. DS-A11..A16  budgets/rate/robots/CAS + Crawlee
5. DS-A17..A21  acquisition quality + security
6. DS-A22..A25  discovery/document/chunking
7. DS-A26..A28  real Qdrant hybrid retrieval
8. DS-A29..A31  evidence + follow-up loop
9. DS-A32..A35  adaptive routing + recovery semantics
10. DS-A36..A43 observability/storage/tests
11. DS-A44..A47 eval + visual experimental path
12. DS-A48..A52 cleanup + migration + Axiom primary
```

После каждого блока `main` должен оставаться runnable.

---

# 8. Что не добавлять на этом этапе

Не добавлять одновременно:

- Temporal;
- Celery как второй durable orchestrator;
- LangGraph как второй control plane;
- Scrapy рядом с Crawlee;
- второй vector DB;
- LlamaIndex только ради chunking;
- Kubernetes-specific orchestration до доказанной необходимости.

Если позже потребуется agentic reasoning, он должен быть activity/subgraph внутри Axiom-controlled execution, а не отдельным владельцем lifecycle.

---

# 9. Целевое состояние проекта после выполнения плана

```text
DeepSearch
│
├── Interfaces
│   ├── CLI
│   ├── REST
│   └── MCP
│
├── Application
│   ├── ResearchApplicationService
│   ├── activities
│   └── execution context
│
├── Orchestration
│   ├── Go Axiom ADGO coordinator
│   ├── immutable ResearchPlan
│   ├── durable execution
│   ├── remote worker protocol
│   └── history/explain
│
├── Acquisition
│   ├── Crawlee
│   ├── HTTPX
│   ├── API replay
│   ├── Playwright
│   └── adaptive planner
│
├── Extraction
│   ├── HTML
│   ├── PDF
│   ├── table
│   └── OCR/visual experimental
│
├── Retrieval
│   ├── structural chunking
│   ├── FastEmbed dense/sparse
│   ├── Qdrant
│   ├── fusion
│   └── reranking
│
├── Evidence
│   ├── claims
│   ├── support/contradiction
│   ├── coverage
│   └── research gaps
│
├── Storage
│   ├── PostgreSQL domain data
│   ├── CAS artifacts
│   ├── Qdrant index
│   └── Axiom ADGO durable store
│
└── Quality
    ├── unit/contract/integration/e2e
    ├── security
    ├── property tests
    └── research eval benchmark
```

---

# 10. Итоговый Definition of Done

DeepSearch можно считать перешедшим в новую архитектуру, когда одновременно выполняются условия:

1. CLI/API/MCP используют один `ResearchApplicationService`.
2. Ни один публичный search endpoint не возвращает fake data.
3. Каждый long-running research job имеет Axiom ADGO execution ID.
4. Coordinator restart не теряет pending/retry state.
5. Python worker crash восстанавливается lease recovery.
6. Stale worker result не может быть committed.
7. Budget, rate-limit, robots, security и dedup реально участвуют в основном path.
8. Crawlee управляет URL frontier вместо Python list queue.
9. Adaptive acquisition использует единый planner и quality gate.
10. Direct API tier достижим на SPA fixture.
11. Qdrant upsert/search реализован и покрыт integration tests.
12. Hybrid dense+sparse retrieval имеет измеримый benchmark.
13. Каждый финальный claim может быть связан с evidence/provenance.
14. Research умеет инициировать bounded follow-up при недостатке evidence.
15. Ошибки классифицируются, а не скрываются широким `except Exception`.
16. Unit tests работают offline.
17. Crash/recovery contract tests Axiom↔Python проходят.
18. Dashboard показывает только фактические backend metrics.
19. Документация не обещает незавершённые возможности.
20. Legacy pipeline path удалён или явно недоступен в production profile.

После этого дальнейшие возможности — advanced PixelRAG, multi-host shared ADGO store, distributed worker pools, richer LLM planning — можно добавлять эволюционно, не меняя основной архитектурный контракт.
