# Техническое задание

## Adaptive Web Scraping & Retrieval Platform

**Версия:** 1.0
**Класс системы:** production-grade web crawling / scraping / extraction / visual retrieval platform
**Основной принцип:** *использовать минимально дорогой механизм, достаточный для корректного извлечения данных.*

---

# 1. Назначение системы

Разработать универсальную высокопроизводительную программу для:

* обхода отдельных URL, сайтов и групп доменов;
* массового crawling;
* скачивания HTML, JSON, XML, PDF, изображений и файлов;
* работы с динамическими JavaScript-сайтами;
* обнаружения внутренних API;
* извлечения структурированных данных;
* преобразования страниц в чистый Markdown;
* сохранения исходного состояния страницы;
* отслеживания изменений;
* построения наборов данных;
* подготовки информации для LLM/RAG;
* визуального поиска по web-страницам, PDF, таблицам, схемам и графикам;
* автоматического выбора наиболее производительного метода scraping.

Система должна одинаково хорошо поддерживать:

1. одну страницу;
2. сайт из сотен страниц;
3. миллионы URL;
4. периодический monitoring;
5. структурированный scraping;
6. AI research;
7. подготовку knowledge base;
8. visual/PixelRAG retrieval.

---

# 2. Главный архитектурный принцип

Запрещается использовать полноценный браузер для каждой страницы по умолчанию.

Система должна реализовывать:

```text
                 URL
                  │
                  ▼
          ┌───────────────┐
          │ Crawl Planner │
          └───────┬───────┘
                  │
             HTTP request
                  │
         ┌────────▼────────┐
         │ Page classifier │
         └────────┬────────┘
                  │
     ┌────────────┼─────────────┐
     │            │             │
     ▼            ▼             ▼
   HTTP        Browser      Direct API
     │            │             │
     └────────────┼─────────────┘
                  ▼
             Raw Capture
                  │
       ┌──────────┴───────────┐
       │                      │
       ▼                      ▼
  DOM/Text pipeline      Visual pipeline
       │                      │
       ▼                      ▼
 HTML/JSON/XML          Screenshot/PDF
       │                      │
       ▼                      ▼
Extraction/RAG           PixelRAG
       │                      │
       └──────────┬───────────┘
                  ▼
           Normalized data
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
     JSON      Markdown    Vectors
```

Crawlee уже предлагает `AdaptivePlaywrightCrawler`, способный переключаться между HTTP-only и browser-based crawling; документация отдельно подчёркивает, что HTTP crawler следует предпочитать там, где JavaScript не требуется.

---

# 3. Приоритеты

В порядке важности:

1. **корректность полученных данных;**
2. **минимальная стоимость страницы;**
3. **максимальная производительность;**
4. **устойчивость к изменениям сайта;**
5. **воспроизводимость результата;**
6. **контролируемое масштабирование;**
7. **удобство разработки extraction-схем;**
8. **наблюдаемость;**
9. **возможность работы без облачных сервисов;**
10. **AI используется только там, где он реально улучшает результат.**

---

# 4. Референсный технологический стек

## 4.1 Основной язык

### Python 3.13+

Основной crawler/extraction runtime рекомендуется реализовать на Python.

Причины:

* Crawlee Python;
* Playwright;
* Crawl4AI;
* PixelRAG;
* библиотеки ML/VLM;
* Pydantic;
* большая экосистема обработки документов.

Не переписывать критические компоненты на Go/Rust до появления результатов профилирования.

Допускается создание отдельных Rust-модулей для доказанных CPU bottleneck.

---

# 5. Базовые компоненты

```text
scraper/
├── control/
│   ├── scheduler
│   ├── planner
│   ├── policies
│   └── budgets
│
├── acquisition/
│   ├── http
│   ├── browser
│   ├── api_capture
│   ├── files
│   └── sessions
│
├── discovery/
│   ├── links
│   ├── sitemap
│   ├── robots
│   └── feeds
│
├── extraction/
│   ├── html
│   ├── json
│   ├── tables
│   ├── markdown
│   ├── schema
│   └── semantic
│
├── visual/
│   ├── screenshots
│   ├── tiling
│   ├── embeddings
│   └── retrieval
│
├── normalization/
│
├── deduplication/
│
├── storage/
│
├── search/
│
├── monitoring/
│
├── api/
│
├── cli/
│
└── ui/
```

---

# 6. Adaptive Acquisition Engine

Это главный модуль системы.

Для каждого URL необходимо определить минимально достаточный способ получения данных.

## 6.1 Уровни acquisition

### L0 — cache

Если ресурс уже существует и не протух:

```text
cache → extraction
```

Никакого сетевого запроса.

---

### L1 — direct HTTP

Первый рабочий вариант:

```text
HTTP GET
```

Использовать для:

* HTML;
* JSON;
* XML;
* RSS;
* sitemap;
* файлов;
* статических сайтов.

---

### L2 — API extraction

Если найден внутренний JSON/GraphQL endpoint:

```text
API → JSON
```

Он должен иметь приоритет над рендерингом браузера при наличии разрешённого и стабильного API.

---

### L3 — browser

Использовать Playwright:

```text
Chromium
   ↓
DOM
network
cookies
storage
screenshots
```

Только если предыдущие варианты недостаточны.

Playwright позволяет отслеживать XHR и `fetch`, поэтому браузерный worker должен не просто получать DOM, а анализировать сетевые ответы страницы.

---

### L4 — semantic browser

Использовать AI browser automation только для:

* динамической навигации;
* нестабильных элементов;
* сложных форм;
* страниц, где невозможно создать устойчивый selector.

Stagehand поддерживает смешанный режим: обычные browser-команды плюс AI-примитивы `act`, `extract`, `observe`.

AI browser запрещается применять там, где подходит deterministic selector.

---

### L5 — visual extraction

Последний специализированный уровень:

```text
screenshot
   ↓
tiles
   ↓
vision embeddings
   ↓
PixelRAG
```

Используется для:

* canvas;
* WebGL;
* графиков;
* диаграмм;
* инфографики;
* сложных таблиц;
* страниц с пространственно значимым layout;
* сканированных документов;
* PDF со сложной версткой.

PixelRAG непосредственно представляет web-страницы в визуальной форме и выполняет retrieval в pixel space вместо обязательной линеаризации HTML в текст.

---

# 7. Page Intelligence Engine

После первой загрузки каждой страницы вычисляется набор характеристик.

```json
{
  "content_type": "html",
  "static_score": 0.91,
  "js_dependency_score": 0.12,
  "api_score": 0.73,
  "visual_score": 0.18,
  "content_quality": 0.95,
  "block_score": 0.01
}
```

## 7.1 Анализировать

* HTTP Content-Type;
* размер ответа;
* количество текста;
* количество DOM-элементов;
* `script`;
* hydration markers;
* React/Vue/Angular/Next/Nuxt признаки;
* JSON-LD;
* embedded state;
* `<canvas>`;
* SVG;
* таблицы;
* iframe;
* lazy-loaded элементы;
* placeholder DOM;
* XHR/fetch;
* GraphQL;
* изменения DOM после загрузки;
* redirects;
* HTTP status;
* признаки ошибки/заглушки.

---

# 8. Adaptive decision policy

Пример:

```text
HTTP
 │
 ├── content_quality >= threshold
 │       └── ACCEPT
 │
 ├── structured API available
 │       └── API
 │
 ├── JS required
 │       └── PLAYWRIGHT
 │
 └── visual information important
         └── SCREENSHOT + VISUAL
```

Пороговые значения должны быть конфигурируемыми.

Пример:

```yaml
adaptive:
  browser_threshold: 0.70
  visual_threshold: 0.65
  api_preference: true
  retry_http_before_browser: true
```

---

# 9. Browser Pool

Не запускать Chromium на каждый URL.

Использовать постоянный pool браузеров.

```text
BrowserPool
   │
   ├── Chromium 1
   │     ├── Context 1
   │     ├── Context 2
   │     └── Context N
   │
   ├── Chromium 2
   └── Chromium N
```

Каждая логическая сессия должна использовать изолированный BrowserContext.

Playwright BrowserContext предназначен именно для независимых browser sessions.

---

# 10. Управление ресурсами браузера

Реализовать:

* максимальное количество браузеров;
* количество Context/browser;
* количество Page/context;
* TTL context;
* max requests/context;
* restart браузера;
* watchdog;
* memory threshold;
* CPU threshold;
* browser crash recovery.

Отключаемые ресурсы:

* видео;
* audio;
* fonts;
* tracking;
* third-party scripts;
* большие изображения.

Но:

```text
если visual_mode = true
```

изображения и стили отключать нельзя.

---

# 11. Autoscaling

Concurrency должен изменяться динамически.

Учитывать:

* CPU;
* RAM;
* network throughput;
* error rate;
* 429;
* timeout;
* latency;
* browser memory;
* host rate limits.

Crawlee использует autoscaled pool для управления concurrency и позволяет контролировать его состояние и уровень параллелизма.

---

# 12. Host-aware scheduler

Нельзя иметь только глобальный:

```text
concurrency = 100
```

Необходимо:

```text
Global scheduler
   │
   ├── example.com
   │     concurrency = 4
   │
   ├── docs.site.com
   │     concurrency = 16
   │
   └── slow.site.com
         concurrency = 1
```

Для каждого host вычислять:

```text
latency
error_rate
429_rate
timeout_rate
success_rate
```

На основании результатов автоматически регулировать скорость.

---

# 13. Backpressure

Все pipeline должны иметь bounded queues.

Запрещено:

```text
crawler produces 1M pages
         ↓
extractor cannot keep up
         ↓
RAM explosion
```

Должно быть:

```text
crawler
  ↓
bounded queue
  ↓
extractor
  ↓
bounded queue
  ↓
storage
```

При переполнении downstream:

```text
upstream concurrency ↓
```

---

# 14. Request Queue

Каждый запрос:

```json
{
  "id": "...",
  "url": "...",
  "canonical_url": "...",
  "depth": 3,
  "priority": 50,
  "parent": "...",
  "domain": "...",
  "method": "GET",
  "attempt": 1,
  "mode": "adaptive"
}
```

Состояния:

```text
DISCOVERED
QUEUED
LEASED
FETCHING
FETCHED
EXTRACTING
INDEXING
DONE

RETRY
DEAD
SKIPPED
```

---

# 15. Delivery semantics

Очередь:

**at-least-once**

Запись результата:

**idempotent**

Это позволяет безопасно переживать падение worker.

---

# 16. URL canonicalization

Перед добавлением URL:

* lowercase hostname;
* убрать fragment;
* нормализовать default ports;
* нормализовать percent encoding;
* сортировать query parameters при допустимой политике;
* удалять tracking parameters;
* применять canonical URL;
* учитывать `<link rel="canonical">`.

Настраиваемый список:

```yaml
remove_query:
  - utm_source
  - utm_medium
  - utm_campaign
  - fbclid
  - gclid
```

---

# 17. Три уровня дедупликации

## URL-level

Canonical URL hash.

## Content-level

Cryptographic hash контента.

```text
BLAKE3
```

## Near-duplicate

Использовать:

```text
SimHash / MinHash
```

для обнаружения почти одинаковых страниц.

---

# 18. Crawl Frontier

URL должны иметь приоритет.

Факторы:

```text
priority =
    relevance
  + depth
  + link_position
  + sitemap_priority
  + freshness
  + content_type
  - cost_estimate
```

---

# 19. Discovery Engine

Источники URL:

* HTML links;
* sitemap.xml;
* sitemap index;
* RSS/Atom;
* canonical;
* alternate;
* pagination;
* API;
* JSON;
* embedded route manifests;
* JavaScript navigation;
* user URL lists.

---

# 20. Crawl strategies

Поддержать:

```text
BFS
DFS
Best-first
Priority
Query-focused
Sitemap-first
Changed-only
```

---

# 21. Scope rules

Пример:

```yaml
scope:
  domains:
    - example.com

  include:
    - "/docs/**"

  exclude:
    - "/login/**"
    - "/account/**"

  max_depth: 8
  max_pages: 100000
```

---

# 22. robots.txt и crawling policy

По умолчанию:

```yaml
robots:
  respect: true
```

Поддержать:

* User-Agent rules;
* Allow;
* Disallow;
* Crawl-delay, если используется сайтом;
* sitemap references.

Для явно разрешённых владельцем ресурсов возможно изменение политики на уровне проекта.

---

# 23. Rate limiting

Алгоритм:

**token bucket + adaptive feedback**

Настройки:

```yaml
limits:
  global_rps: 500

  per_host:
    default_rps: 5
    max_concurrency: 8
```

При:

```text
429
503
latency spike
```

вводить:

```text
exponential backoff + jitter
```

---

# 24. Retry Engine

Retry выполняется только для recoverable ошибок.

Повторять:

* timeout;
* connection reset;
* 408;
* 429;
* 500;
* 502;
* 503;
* 504.

Не повторять бесконечно:

* 400;
* 401;
* 403 без изменившихся условий;
* 404;
* malformed URL.

---

# 25. Session Manager

Сессия содержит:

```json
{
  "session_id": "...",
  "cookies": {},
  "local_storage": {},
  "headers": {},
  "proxy_id": null,
  "created_at": "...",
  "request_count": 41,
  "health_score": 0.94
}
```

Crawlee SessionPool связывает cookies и параметры сессии и поддерживает их ротацию.

---

# 26. Authentication

Поддержать:

* Basic Auth;
* Bearer token;
* API key;
* cookies;
* imported browser session;
* user-provided login workflow;
* OAuth session import.

Секреты запрещено хранить открытым текстом.

---

# 27. CAPTCHA policy

В базовой системе:

```text
CAPTCHA detected
       ↓
 PAUSE / SKIP
```

Допускается ручное продолжение авторизованного crawl.

Автоматический обход CAPTCHA не является частью базового ТЗ.

---

# 28. Proxy Manager

Поддерживать:

* HTTP;
* HTTPS;
* SOCKS5;
* direct connection.

Режимы:

```text
DIRECT
ROUND_ROBIN
SESSION_STICKY
DOMAIN_POOL
CUSTOM
```

Crawlee нативно поддерживает proxy configuration и связывание proxy с session.

---

# 29. Network Intelligence

Browser worker должен сохранять информацию:

```text
Document
XHR
fetch
GraphQL
JSON
WebSocket metadata
```

Для каждого сетевого ответа:

```json
{
  "url": "...",
  "method": "GET",
  "status": 200,
  "mime": "application/json",
  "size": 12344
}
```

---

# 30. API Discovery

Если браузер обнаружил:

```text
GET /api/products?page=1
```

и ответ содержит данные страницы:

система должна предложить перевод дальнейшего crawl:

```text
Browser → API crawler
```

Это одно из главных средств экономии ресурсов.

---

# 31. Extraction Engine

Поддержать несколько стратегий.

## E0 — direct JSON

Наиболее предпочтительный.

---

## E1 — deterministic extraction

* CSS;
* XPath;
* JSONPath;
* attributes;
* regex как вспомогательный механизм.

---

## E2 — semantic HTML extraction

Выделить:

* main content;
* header;
* navigation;
* article;
* tables;
* code;
* lists;
* metadata.

Crawl4AI умеет возвращать HTML, Markdown, structured extraction, links, media и таблицы.

---

## E3 — schema extraction

Пользователь задаёт:

```json
{
  "name": "string",
  "price": "number",
  "currency": "string",
  "availability": "boolean"
}
```

Результат обязательно валидируется.

---

## E4 — LLM extraction

Использовать только когда deterministic extraction недостаточен.

```text
page
 ↓
filtered relevant content
 ↓
LLM
 ↓
JSON schema
 ↓
validation
```

---

# 32. Schema system

Использовать:

* JSON Schema;
* Pydantic.

Поля:

```yaml
Product:
  name:
    type: string
    required: true

  price:
    type: number
    required: true

  manufacturer:
    type: string
    required: false
```

---

# 33. Extraction confidence

Каждое поле может иметь:

```json
{
  "value": 149.99,
  "confidence": 0.97,
  "source": {
    "url": "...",
    "selector": "...",
    "artifact": "..."
  }
}
```

---

# 34. Provenance

Критически важное требование.

Для любого результата должно быть возможно определить:

```text
откуда взялись данные?
```

Хранить:

* URL;
* timestamp;
* response hash;
* extraction rule;
* selector;
* source DOM;
* screenshot coordinates при visual extraction;
* extraction version.

---

# 35. Markdown pipeline

Формировать:

1. `raw_markdown`;
2. `clean_markdown`;
3. `fit_markdown`.

Crawl4AI реализует генерацию структурированного Markdown и отдельный Fit Markdown для уменьшения boilerplate перед downstream AI processing.

---

# 36. Table extraction

Таблицы должны одновременно сохраняться как:

```text
HTML
JSON
CSV
Markdown
```

Не преобразовывать сложную таблицу только в текст.

---

# 37. Document pipeline

Для:

* PDF;
* DOCX;
* XLSX;
* PPTX;
* EPUB;
* CSV;
* изображения.

Результат:

```text
native extraction
+
render
+
visual extraction
```

---

# 38. Visual Intelligence Engine

Вычислять:

```text
visual_need_score
```

Факторы:

* canvas;
* charts;
* SVG complexity;
* tables;
* diagrams;
* spatial relationships;
* OCR/native-text discrepancy;
* low text/high visual area;
* screenshots explicitly requested.

---

# 39. PixelRAG pipeline

```text
Rendered page
      ↓
Full screenshot
      ↓
Tile generator
      ↓
Visual embedding
      ↓
Multivector index
      ↓
Query embedding
      ↓
Visual retrieval
      ↓
VLM
```

PixelRAG предназначен для retrieval непосредственно по screenshot representation, сохраняя layout, таблицы, графики и визуальные связи, которые могут потеряться при переводе страницы в линейный текст.

---

# 40. Visual tile

Каждый tile:

```json
{
  "page_id": "...",
  "tile_id": 17,
  "x": 0,
  "y": 2048,
  "width": 1280,
  "height": 1024,
  "image_hash": "...",
  "embedding_id": "..."
}
```

---

# 41. Hybrid RAG

Не использовать PixelRAG вместо text RAG.

Использовать:

```text
               Query
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
 Text retrieval       Visual retrieval
       │                   │
       ▼                   ▼
 dense/sparse          multivector
       │                   │
       └─────────┬─────────┘
                 ▼
              rerank
                 ▼
                VLM
```

---

# 42. Vector database

Рекомендуется:

**Qdrant**

Хранить отдельно:

```text
text_dense
text_sparse
visual_multivector
```

Qdrant поддерживает multivector, включая late-interaction представления, где один объект описывается множеством vectors — например image patches.

---

# 43. Storage architecture

Разделить данные.

## PostgreSQL

Метаданные:

```text
projects
jobs
requests
pages
links
sessions
extractors
records
errors
```

## Object Storage

S3/MinIO:

```text
HTML
JSON
PDF
screenshots
HAR
files
```

## Qdrant

Embeddings.

## Cache

Redis/Valkey.

---

# 44. Content-addressable storage

Все крупные artifacts сохранять:

```text
hash(content)
```

Если одинаковый объект уже существует:

```text
reference++
```

вместо повторного сохранения.

---

# 45. Compression

Использовать:

```text
Zstandard
```

для:

* HTML;
* JSON;
* HAR;
* extracted text.

Изображения хранить в подходящем web-efficient формате без потери информации, необходимой visual pipeline.

---

# 46. Snapshot model

Для каждой страницы:

```text
Page
 ├── Response
 ├── Raw HTML
 ├── Rendered DOM
 ├── Markdown
 ├── Network log
 ├── Screenshot
 ├── Extracted records
 └── Embeddings
```

---

# 47. Versioning

Любое повторное посещение:

```text
Page
 ├── Snapshot 1
 ├── Snapshot 2
 └── Snapshot N
```

---

# 48. Change Detection

Сравнивать:

* HTTP ETag;
* Last-Modified;
* hash;
* DOM hash;
* main-content hash;
* extracted JSON;
* screenshot perceptual hash.

---

# 49. Smart recrawl

Если ресурс не меняется:

```text
recrawl interval ↑
```

Если часто меняется:

```text
recrawl interval ↓
```

---

# 50. Crawl Budget Manager

Для любого задания задавать ограничения:

```yaml
budget:
  max_pages: 50000
  max_depth: 10

  max_bytes: 10GB

  browser_seconds: 3600
  llm_tokens: 1000000
  visual_pages: 5000

  deadline: 2h
```

---

# 51. Cost-aware planner

Каждому действию присваивать приблизительную стоимость:

```text
cache       0
HTTP        1
API         1
browser    10
LLM        30
visual VLM 50
```

Значения являются относительными configurable weights, а не денежными тарифами.

Planner должен минимизировать:

```text
Cost
```

при условии:

```text
ExtractionQuality >= required_quality
```

---

# 52. Quality Score

После extraction рассчитывать:

```text
completeness
validity
consistency
schema_match
content_density
```

Пример:

```text
quality_score = 0.93
```

Если:

```text
quality_score < required
```

выполнять escalation:

```text
HTTP
 ↓
browser
 ↓
semantic extraction
 ↓
visual
```

---

# 53. Error taxonomy

Не использовать один `scrape failed`.

Категории:

```text
NETWORK
DNS
TLS
TIMEOUT
HTTP_4XX
HTTP_5XX
RATE_LIMIT
ROBOTS
AUTH
BLOCK
BROWSER_CRASH
NAVIGATION
EXTRACTION
SCHEMA
STORAGE
LLM
VISUAL
INTERNAL
```

---

# 54. Dead Letter Queue

После исчерпания retry:

```text
DLQ
```

UI должен позволять:

* посмотреть ошибку;
* изменить параметры;
* replay request.

---

# 55. API

REST API.

## Projects

```text
POST   /projects
GET    /projects
GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}
```

## Crawl

```text
POST /crawl
GET  /crawl/{id}
POST /crawl/{id}/pause
POST /crawl/{id}/resume
POST /crawl/{id}/cancel
```

## Data

```text
GET /pages
GET /pages/{id}
GET /records
GET /datasets/{id}
```

## Search

```text
POST /search/text
POST /search/visual
POST /search/hybrid
```

---

# 56. CLI

Обязательный CLI:

```bash
scraper crawl https://example.com
```

```bash
scraper crawl https://example.com \
  --depth 5 \
  --max-pages 10000
```

```bash
scraper extract https://example.com/product/1 \
  --schema product.json
```

```bash
scraper inspect https://example.com
```

```bash
scraper visual-index ./documents
```

```bash
scraper search "pump pressure diagram"
```

---

# 57. Inspect mode

Очень важный режим.

```bash
scraper inspect URL
```

Показывает:

```text
HTTP status             200
Content type            HTML
Static content          92%
JS dependency           8%
Detected APIs           3
Tables                   2
Canvas                   0
Visual score            21%
Recommended strategy    HTTP
Estimated cost          LOW
```

---

# 58. Web UI

Основные экраны:

### Dashboard

* активные jobs;
* pages/sec;
* queue;
* successes;
* retries;
* errors;
* browser usage;
* bandwidth;
* storage;
* estimated cost.

### Projects

Конфигурация проекта.

### Crawl Builder

Пошаговое создание задания.

### Live Crawl

Граф сайта и поток URL.

### Page Inspector

Показывать рядом:

```text
Raw
DOM
Markdown
JSON
Screenshot
Network
```

### Extraction Studio

Пользователь кликает по элементу страницы и назначает ему поле schema.

### Datasets

Просмотр/экспорт результатов.

### Visual Search

Запрос → найденные screenshot fragments.

---

# 59. Extraction Studio

Режим:

```text
browser preview
       +
DOM inspector
       +
schema editor
```

Пользователь выбирает:

```text
[Цена: 144 €]
```

и назначает:

```text
Product.price
```

Система автоматически пытается создать устойчивый selector.

---

# 60. Self-healing selector

Хранить не только:

```css
div:nth-child(6) > span
```

а fingerprint элемента:

```text
tag
attributes
text
nearby labels
DOM path
semantic role
```

Если selector перестал работать, искать ближайший эквивалент.

AI применять только после deterministic matching.

---

# 61. Export

Форматы:

* JSON;
* JSONL;
* CSV;
* Parquet;
* Markdown;
* SQLite;
* PostgreSQL;
* raw archive.

---

# 62. Streaming output

Не ждать завершения crawl.

Результат должен быть доступен:

```text
crawl → records stream
```

через:

* SSE;
* WebSocket;
* NDJSON API.

---

# 63. Plugin system

Интерфейсы:

```text
Fetcher
Parser
Extractor
Normalizer
Filter
Sink
Authenticator
ProxyProvider
EmbeddingProvider
LLMProvider
```

Пользователь может добавлять собственные реализации.

---

# 64. Hooks

```text
before_request
after_response
before_browser
after_browser
before_extract
after_extract
before_store
on_error
```

---

# 65. Site profiles

Для сложного ресурса можно создать профиль:

```yaml
site: example.com

strategy: adaptive

auth:
  profile: example-session

limits:
  rps: 4

extraction:
  schema: products.json

browser:
  wait_for: networkidle
```

---

# 66. Configuration precedence

```text
defaults
   ↓
global config
   ↓
project config
   ↓
site profile
   ↓
job config
   ↓
request override
```

---

# 67. Observability

Инструментировать систему через OpenTelemetry:

* traces;
* metrics;
* logs.

OpenTelemetry Collector предоставляет независимый от backend pipeline для приёма, обработки и экспорта telemetry и поддерживает отдельные pipelines для metrics, traces и logs.

---

# 68. Метрики

Минимально:

```text
requests_total
requests_success
requests_failed

pages_per_second

http_requests
browser_requests
api_requests

browser_escalation_ratio

bytes_downloaded

queue_depth
queue_latency

extract_success
schema_failure

retry_count
429_count

browser_cpu
browser_memory

cost_per_page
```

---

# 69. Ключевая метрика

Ввести:

```text
Browser Escalation Ratio
```

Например:

```text
6.4%
```

Цель оптимизации — не сделать его минимальным любой ценой, а обеспечить минимальный browser usage при сохранении требуемого quality score.

---

# 70. Вторая ключевая метрика

```text
Useful Data / Downloaded Byte
```

Позволяет обнаруживать ресурсоёмкие неэффективные стратегии.

---

# 71. Tracing

Каждая страница:

```text
crawl.request
  ├── dns
  ├── fetch
  ├── classify
  ├── browser?
  ├── extract
  ├── normalize
  ├── store
  └── index
```

---

# 72. Security

Crawler является потенциальным SSRF-инструментом.

По умолчанию запрещать:

```text
localhost
127.0.0.0/8
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
169.254.0.0/16
::1
private IPv6
```

если они явно не allowlisted администратором.

---

# 73. Protocol policy

Разрешить по умолчанию только:

```text
HTTP
HTTPS
```

Запрещать:

```text
file://
ftp://
data:
javascript:
```

на boundary пользовательского API.

---

# 74. Download safety

Настройки:

```yaml
security:
  max_response_size: 100MB
  max_redirects: 10
  max_decompressed_size: 500MB
```

Защита от:

* decompression bomb;
* бесконечных streams;
* redirect loops;
* огромных файлов.

---

# 75. Browser isolation

Browser workers запускать отдельно от control plane.

Production:

```text
API
 │
scheduler
 │
queue
 │
isolated browser workers
```

---

# 76. Secrets

Использовать:

* environment secret;
* Docker/Kubernetes secret;
* vault provider.

Никогда не выводить:

* cookies;
* tokens;
* proxy credentials;
* Authorization header

в обычный log.

---

# 77. Deployment — standalone

```text
docker compose up
```

Поднимаются:

```text
scraper-api
scraper-worker
browser-worker
postgres
redis
minio
qdrant
otel-collector
```

---

# 78. Distributed deployment

```text
                  API
                   │
               Scheduler
                   │
                  Queue
        ┌──────────┼───────────┐
        ↓          ↓           ↓
 HTTP Worker   Browser Worker AI Worker
        │          │           │
        └──────────┼───────────┘
                   ↓
              Storage
```

Workers должны быть stateless настолько, насколько возможно.

---

# 79. Horizontal scaling

Можно отдельно масштабировать:

```text
HTTP worker ×100
Browser worker ×10
Visual worker ×4
LLM worker ×2
```

Количество каждого класса не должно зависеть от остальных.

---

# 80. Graceful shutdown

При SIGTERM:

```text
stop accepting work
        ↓
finish active requests
        ↓
release leases
        ↓
flush results
        ↓
shutdown
```

---

# 81. Crash recovery

После перезапуска:

* активные lease протухают;
* URL возвращаются в очередь;
* уже сохранённые результаты не дублируются;
* crawl продолжается.

---

# 82. Тестовый стенд

Не тестировать scraper только на реальном интернете.

Создать локальный benchmark-site.

Страницы:

```text
/static
/spa
/react
/infinite-scroll
/table
/canvas
/chart
/pdf
/json
/graphql
/login
/redirect
/slow
/429
/500
/duplicate
/robots-denied
/large
```

---

# 83. Unit tests

Покрыть:

* canonicalizer;
* deduplication;
* scheduler;
* policies;
* extraction;
* schemas;
* URL filtering;
* rate limiting;
* retry;
* budgets.

---

# 84. Contract tests

Для каждого extractor:

```text
input artifact
      ↓
expected JSON
```

Использовать golden files.

---

# 85. Browser tests

Проверять:

* SPA;
* lazy load;
* interaction;
* iframe;
* cookies;
* session;
* crash/restart;
* request interception.

---

# 86. Performance benchmark

Использовать один и тот же локальный dataset.

Сравнивать режимы:

```text
Pure HTTP
Adaptive
Pure Playwright
```

---

# 87. Главный performance criterion

Adaptive режим на статическом corpus должен достигать не менее:

```text
85% throughput
```

чистого HTTP baseline на той же машине.

Это относительный acceptance criterion, поэтому он не зависит от скорости конкретного CPU или сети.

---

# 88. Browser efficiency criterion

На corpus, где 80% страниц не требуют JavaScript:

```text
browser escalation <= 25%
```

при сохранении корректного extraction результата.

---

# 89. Reliability criterion

Тест:

```text
100 000 queued URLs
```

с принудительными остановками workers.

После восстановления:

```text
lost jobs = 0
```

---

# 90. Dedup criterion

После canonicalization и content dedup:

```text
unintentional duplicate output < 0.1%
```

на benchmark corpus.

---

# 91. Extraction criterion

Для фиксированного golden dataset:

```text
required fields accuracy >= 99%
```

для deterministic schemas.

LLM-only результаты измерять отдельно.

---

# 92. Memory soak test

Browser worker:

```text
8 часов
```

постоянного crawling.

Не допускается монотонный неконтролируемый рост памяти.

Browser contexts должны периодически перерабатываться.

---

# 93. Failure injection

Искусственно проверять:

* DNS failure;
* Redis restart;
* PostgreSQL restart;
* browser crash;
* killed worker;
* timeout;
* packet loss;
* corrupt artifact.

---

# 94. Profiling

В CI benchmark сохранять:

```text
CPU/request
RAM/request
bytes/page
browser seconds/page
LLM tokens/page
visual GPU time/page
```

---

# 95. Не допускать premature AI

Порядок извлечения:

```text
JSON
 ↓
HTML selector
 ↓
structured parser
 ↓
semantic parser
 ↓
LLM
 ↓
vision
```

Нельзя делать:

```text
каждую страницу → LLM
```

---

# 96. Не допускать premature browser

Порядок получения:

```text
cache
 ↓
HTTP
 ↓
API
 ↓
browser
```

---

# 97. Не допускать premature PixelRAG

PixelRAG применять только если:

```text
visual_score >= threshold
```

или пользователь явно включил visual indexing.

---

# 98. Внешние сервисы

Система должна иметь provider abstraction.

Например:

```text
Local
Firecrawl
Browserless
Apify
custom
```

Но внешний SaaS не должен быть обязательным.

Firecrawl, например, может возвращать Markdown, HTML, screenshot и structured JSON и поэтому подходит как optional fallback/provider, а не фундамент всей системы.

---

# 99. Режимы работы

## Fast

```text
HTTP/API only
```

## Balanced

```text
Adaptive HTTP/browser
```

Рекомендуемый default.

## Complete

```text
HTTP
+
browser
+
network
+
files
```

## Research

```text
Complete
+
Markdown
+
text RAG
+
PixelRAG
```

## Archive

Сохраняется всё сырое состояние.

---

# 100. UX принцип

Пользователь при запуске простого crawl не должен видеть 100 настроек.

Основная команда:

```bash
scraper crawl https://example.com
```

Система сама выбирает стратегию.

Advanced параметры открываются только при необходимости.

---

# 101. Recommended default

```yaml
mode: balanced

adaptive: true

robots:
  respect: true

discovery:
  sitemap: true
  links: true

extraction:
  markdown: true
  structured: auto

visual:
  mode: auto

storage:
  raw_html: true
  screenshots: visual-only

limits:
  auto_concurrency: true
  per_host_adaptive: true
```

---

# 102. Приоритет реализации

## P0 — ядро

1. URL queue.
2. HTTP crawler.
3. adaptive scheduler.
4. Playwright.
5. DOM extraction.
6. JSON extraction.
7. Markdown.
8. PostgreSQL.
9. raw artifact storage.
10. CLI.
11. retry.
12. rate limiting.
13. deduplication.
14. observability.

После P0 система уже является полноценным production scraper.

---

## P1 — intelligence

15. Network/API discovery.
16. Browser escalation classifier.
17. automatic extraction quality.
18. session manager.
19. proxy manager.
20. schema extraction.
21. Web UI.
22. change detection.

---

## P2 — AI

23. LLM extraction.
24. self-healing selectors.
25. semantic browser.
26. RAG indexing.

---

## P3 — visual

27. screenshots.
28. visual classifier.
29. screenshot tiling.
30. visual embeddings.
31. Qdrant multivectors.
32. PixelRAG.
33. hybrid retrieval.

---

## P4 — large-scale production

34. distributed scheduler.
35. horizontal scaling.
36. remote workers.
37. multi-tenancy.
38. quotas.
39. worker autoscaling.
40. complete benchmark suite.

---

# 103. Итоговая архитектура

```text
                         ┌─────────────┐
                         │ CLI / WebUI │
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐
                         │     API     │
                         └──────┬──────┘
                                │
                    ┌───────────▼────────────┐
                    │     Crawl Planner      │
                    │ policy / budget / QoS  │
                    └───────────┬────────────┘
                                │
                       ┌────────▼────────┐
                       │ Request Frontier│
                       └────────┬────────┘
                                │
           ┌────────────────────┼────────────────────┐
           │                    │                    │
           ▼                    ▼                    ▼
     ┌───────────┐       ┌────────────┐       ┌───────────┐
     │HTTP Worker│       │API Capture │       │Playwright │
     └─────┬─────┘       └──────┬─────┘       └─────┬─────┘
           │                    │                    │
           └────────────────────┼────────────────────┘
                                │
                         ┌──────▼───────┐
                         │ Raw Artifacts│
                         └──────┬───────┘
                                │
             ┌──────────────────┼─────────────────┐
             │                  │                 │
             ▼                  ▼                 ▼
       ┌──────────┐       ┌──────────┐      ┌───────────┐
       │DOM Parser│       │ Network  │      │ Visual    │
       │Markdown  │       │ Parser   │      │ Pipeline  │
       └────┬─────┘       └────┬─────┘      └─────┬─────┘
            │                  │                  │
            ▼                  ▼                  ▼
      ┌───────────┐      ┌───────────┐      ┌──────────┐
      │Structured │      │ API Data  │      │PixelRAG  │
      │ Extraction│      └─────┬─────┘      └────┬─────┘
      └─────┬─────┘            │                 │
            └──────────────────┼─────────────────┘
                               │
                         ┌─────▼───────┐
                         │ Normalizer  │
                         └─────┬───────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
        PostgreSQL          S3/MinIO          Qdrant
```

---

# 104. Главный принцип оптимальности

Программа считается оптимальной не тогда, когда она умеет применить максимальное количество технологий.

Она считается оптимальной, если для каждой страницы выбирает **самый дешёвый путь, способный дать требуемое качество результата**:

```text
               ┌─────────┐
               │  Cache  │
               └────┬────┘
                    ↓
             ┌────────────┐
             │ HTTP / API │
             └─────┬──────┘
                   │ insufficient
                   ↓
             ┌────────────┐
             │ Playwright │
             └─────┬──────┘
                   │ insufficient
                   ↓
             ┌────────────┐
             │ LLM/Vision │
             └────────────┘
```

Именно такой подход должен обеспечивать одновременно:

**скорость + низкое потребление ресурсов + устойчивость + качество + возможность масштабирования.**

---

# 105. Финальный целевой продукт

В результате должна получиться не библиотека уровня:

```text
fetch(url)
```

а полноценная:

# Adaptive Web Intelligence Platform

которая способна автоматически определить:

> «Эту страницу можно забрать простым HTTP за минимальную стоимость.»

или:

> «Контент появляется только после JavaScript — нужен браузер.»

или:

> «Основные данные находятся в JSON API — браузер дальше не нужен.»

или:

> «Текст извлечён корректно, но здесь есть важная диаграмма — добавим visual indexing.»

И только затем применить соответствующий pipeline.

Такой design позволяет объединить сильные стороны классического crawling, Playwright, API extraction, Crawl4AI и PixelRAG, не превращая каждую страницу в дорогостоящую browser/LLM-задачу.
