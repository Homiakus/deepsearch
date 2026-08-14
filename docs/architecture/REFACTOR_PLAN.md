# План стабилизации и упрощения DeepSearch

**Статус:** утверждённый план работ по результатам аудита

**Дата аудита:** 2026-08-14

**Проверенная ветка:** `main`

**Проверенный коммит:** `e7c264aa8c265eb8367ef9a1c9c4677aba359ee0`

## 1. Итог аудита

DeepSearch сейчас является функциональным прототипом с хорошими отдельными заготовками, но не production-ready платформой. Сильные части — воспроизводимый `uv.lock`, собираемый Python-пакет, базовые HTTP/HTML-экстракторы, каноникализация URL, формирование архива и тонкие интерфейсы CLI/FastAPI/MCP. Главный риск — разрыв между заявленной архитектурой и фактически исполняемым путём.

Документация описывает готовые L0-L5, PixelRAG, Qdrant, PostgreSQL, Redis, CAS, BLAKE3, OCR, rate limiting и фоновые crawl jobs. В рабочем сценарии большинство этих компонентов либо не вызывается, либо является заглушкой. Из-за этого система выглядит сложнее и надёжнее, чем она есть на самом деле.

Целевой поддерживаемый сценарий первой стабильной версии:

`ввод запроса/URL → проверка политики → поиск источников → ограниченная очередь → HTTP/Browser acquisition → extraction → проверяемый архив/результат`.

CLI, REST и MCP должны быть только тремя адаптерами над одним application service. Всё, что не участвует в этом пути, удаляется из основного профиля или становится явно отключаемой экспериментальной возможностью.

## 2. Воспроизводимая исходная точка

| Проверка | Фактический результат |
| --- | --- |
| `uv sync --extra dev --frozen` | проходит |
| `python -m compileall` | проходит |
| `uv pip check` | проходит |
| `uv build` | sdist и wheel собираются |
| `pytest -q` | **4 failed, 50 passed**, 2 предупреждения |
| Покрытие `pytest-cov` | 61% суммарного покрытия с ветвлениями; 0% у ряда заявленных подсистем |
| `ruff check .` | **462** замечания, из них 330 автоисправляемых |
| `black --check` | 58 файлов требуют форматирования |
| `mypy --check-untyped-defs scraper` | **10** ошибок в 7 файлах |
| McCabe, порог 10 | 10 слишком сложных функций; `DeepSearchPipeline.execute` — 29 |
| CI | workflow отсутствует |

Четыре теста падают, потому что «unit» тесты API/MCP обращаются к реальной сети и требуют установленный Chromium. Это не дефект среды тестирования, а нарушение изоляции тестов и неявный эксплуатационный контракт.

## 3. Ключевые находки

| Приоритет | Находка | Доказательство в коде | Последствие |
| --- | --- | --- | --- |
| P0 | REST crawl job не исполняется | `scraper/api/routes.py`: `BackgroundTasks` не используется; запрос только кладётся в глобальный `RequestFrontier` | API возвращает `RUNNING` для работы, которая никогда не стартует |
| P0 | Search и PixelRAG возвращают демонстрационные данные | `scraper/search/search_engine.py`, `scraper/visual/pixel_rag.py`, `scraper/storage/vector_store.py` | пользователь получает фиктивный результат или пустой список |
| P0 | SSRF-защита неполна | только первоначальный DNS pre-check в `http_fetcher.py`; downloader, browser redirects и subresources обходят общий guard | доступ к внутренним адресам через redirect, DNS rebinding или browser request |
| P0 | API фактически открыт | `api_key` не проверяется; CORS `*` вместе с credentials; исследование пишет файлы на сервер | удалённый запуск дорогих операций, DoS и запись произвольных output-файлов |
| P0 | Документация противоречит реализации | `AUDIT_REPORT.md` заявляет production-grade и полностью проходящие тесты | ложная уверенность при эксплуатации и разработке |
| P1 | Ресурсные механизмы не подключены | budget, rate limiter, robots, deduplicator, CAS и telemetry существуют отдельно от pipeline | лимиты из конфигурации не ограничивают реальную работу |
| P1 | Основной pipeline монолитен и последователен | `DeepSearchPipeline.execute`, сложность 29; `list.pop(0)`; последовательные HTTP/PDF/media вызовы | высокая задержка, блокировка event loop, трудное восстановление после ошибок |
| P1 | Ошибки превращаются в «успех с пустым результатом» | многочисленные `except Exception` в pipeline, discovery, media и OCR | невозможно отличить отсутствие данных от деградации инфраструктуры |
| P1 | Контракты расходятся с реализациями | сигнатуры `FetcherProtocol`/`BrowserPoolProtocol` не совпадают с адаптерами | подмена адаптеров хрупка; mypy подтверждает ошибки |
| P1 | Конфигурация раздвоена | `.env.example` содержит в основном несуществующие поля и несовместимый PostgreSQL DSN | установка по примеру запускает систему с неожиданными defaults |
| P1 | Схема данных имеет три несовместимых источника истины | две миграции с номером `001` и ORM-модели с другими таблицами | новая БД зависит от случайного порядка применения файлов |
| P1 | BrowserPool не является пулом | `max_browsers` и `contexts_per_browser` не используются; нет semaphore и lifespan cleanup | неконтролируемая конкуренция и утечки процесса Chromium |
| P1 | Discovery создаёт каскад последовательных запросов | `seed_finder.py` и N+1 запросы в `media_finder.py` | десятки секунд даже до начала crawl; нет частичных статусов провайдеров |
| P2 | Зависимости и инфраструктура опережают работающий продукт | Crawlee, Redis, Qdrant, SQLAlchemy, AsyncPG и часть parser stack не участвуют в основном пути | тяжёлая установка, широкая поверхность обновлений и отказов |
| P2 | В корне лежат три параллельных исследовательских приложения | `deep_pdf_research_engine.py`, `run_laser_research.py`, `run_papanicolaou_lbc_research.py` | дублирование HTTP/PDF/RAG-кода и предметные defaults в универсальном продукте |
| P2 | Dashboard показывает вымышленные метрики | `scraper/ui/dashboard.py`: статические 6.4%, 3 jobs, 48.2 pages/s; Start Crawl вызывает `alert` | интерфейс демонстрирует состояние, которого система не знает |
| P2 | MCP-конфигурация запускает установщики как серверы | `.mcp/config.json`: `pip install`, `npm install -g`, сторонние `npx`/`uvx`; endpoints не существуют | неработающие конфиги и ненужный supply-chain риск |

## 4. PHASE 1 — ALGORITHM FRAGILITY MAP

Этот раздел превращает общий аудит хрупкости в репозиторий-специфичную программу. Он не даёт права сразу переписывать алгоритм: сначала фиксируются фактический контракт и минимальный контрпример, затем выбирается наименьший достаточный уровень вмешательства. Направления DS-01…DS-26 остаются целевыми, но изменение поведения внутри них проходит evidence gate из DS-27…DS-34.

Статусы доказательств:

- `HYPOTHESIS` — риск виден статически, но нарушение ещё не воспроизведено и не доказано инвариантом;
- `EVIDENCE` — найден конкретный путь исполнения или расхождение контрактов, следующая проверка определена;
- `CONFIRMED` — есть минимальный воспроизводимый контрпример либо доказуемое нарушение контракта/инварианта;
- `REJECTED` — проверка опровергла гипотезу; результат сохраняется, чтобы не исследовать её повторно.

У каждой FRAG-записи отдельно указывается impact priority: `P0` — возможна потеря/повреждение данных либо нарушение security boundary; `P1` — неправильное решение/результат; `P2` — crash или нестабильность; `P3` — контролируемая деградация; `P4` — maintainability risk. Поле «Приоритет» у DS-пунктов задаёт порядок исполнения работ и не подменяет impact priority конкретного дефекта.

### 4.1 Инвентаризация алгоритмов

| Алгоритм | Файл/символ | Назначение | Вход → выход | Состояние и зависимости | Критичность |
| --- | --- | --- | --- | --- | --- |
| Research orchestration | `scraper/pipeline/search_pipeline.py::DeepSearchPipeline.execute` | discovery, crawl, extraction, media, export | `DeepSearchPipelineOptions` → archive/result | очередь URL, temp dirs, сеть, PDF, filesystem | critical |
| Acquisition escalation | `scraper/acquisition/engine.py::AdaptiveAcquisitionEngine.acquire_page` | выбор Cache/HTTP/API/Browser/Visual | URL, mode, cache → `CapturedArtifact` | HTTPFetcher, BrowserPool, settings | critical |
| HTTP и SSRF policy | `scraper/acquisition/http_fetcher.py::HTTPFetcher.validate_url_security/fetch` | безопасная загрузка с redirect/size limits | URL, headers, proxy → `HTTPResponse` | DNS, сеть, redirects, clock | critical |
| Browser acquisition | `scraper/acquisition/browser_pool.py::BrowserPoolManager.fetch_page` | JS rendering и network capture | URL, flags → `BrowserResponse` | Playwright process/context/routes | critical |
| Page classification | `scraper/acquisition/page_classifier.py::classify_page`, `control/planner.py::CostPlanner` | scoring и выбор следующей стратегии | HTML/status/network log → scores/strategy | thresholds из settings | high |
| Crawl frontier | `scraper/control/scheduler.py::RequestFrontier` | priority queue, lease, retry, dedup | команды над `CrawlRequest` → request/state/stats | mutable queue/maps, lock, wall clock | critical |
| Resource budget | `scraper/control/budget.py::BudgetTracker.record_page` | ограничения страниц, bytes, depth, browser, deadline | usage event → state или exception | counters, lock, wall clock | critical |
| Host rate limiting | `scraper/control/rate_limiter.py::TokenBucket/HostRateLimiter` | token bucket, adaptive RPS, backoff | host/result/attempt → wait/backoff | monotonic clock, random, shared host stats | high |
| URL normalization | `scraper/normalization/canonicalizer.py::canonicalize_url` | canonical key для scope и dedup | raw/canonical URL → canonical URL | tracking parameter policy | critical |
| Exact/near deduplication | `scraper/normalization/deduplicator.py::Deduplicator` | URL/content/SimHash dedup | URL/bytes/text → duplicate flag | mutable hash sets, optional BLAKE3 | high |
| Seed discovery | `scraper/discovery/seed_finder.py::discover_diverse_seeds` | классификация запроса и сбор seeds | query/category/domain/sources → URLs | несколько внешних API, hard-coded keywords | high |
| Media ranking | `scraper/discovery/media_finder.py::score_and_rank_images` | lexical/authority/dimension scoring | candidates/query/limits → ranked subset | weights, rounding, stable input order | high |
| Media download | `scraper/acquisition/media_downloader.py::download_media_file` | загрузка, limit, hash, filename | URL/output/limits → metadata/file | network, memory, filesystem, Pillow | critical |
| Archive construction | `scraper/storage/archive_exporter.py::ArchiveExporter` | chunking, manifest, JSONL, ZIP | artifacts/extractions/media → directory/ZIP | filesystem, ordering, timestamps | high |

### 4.2 Ранжирование для прогрессивного углубления

Для `RiskScore₀` каждый множитель `Criticality × InputVariability × StateComplexity × HiddenAssumptions × FailureImpact × LackOfTests` предварительно оценён от 1 до 4. В таблице они обозначены `C/I/S/A/F/T`. Это приоритизация следующей проверки, а не доказательство дефекта. `FI₀` — статическая оценка Fragility Index по шкале раздела 4.3; она пересчитывается после PASS 5 и после hardening.

| Ранг | Алгоритм | C/I/S/A/F/T | RiskScore₀ | FI₀ | Почему выбран в первую десятку |
| --- | --- | --- | ---: | ---: | --- |
| 1 | `DeepSearchPipeline.execute` | 4/4/4/4/4/4 | 4096 | 47 | объединяет все внешние зависимости, подавляет ошибки и создаёт persistent output |
| 2 | `HTTPFetcher.fetch` | 4/4/3/4/4/4 | 3072 | 46 | security boundary зависит от DNS, redirects и размера потока |
| 3 | `download_media_file` | 4/4/3/4/4/4 | 3072 | 45 | отдельный сетевой путь обходит общий policy и пишет на диск |
| 4 | `RequestFrontier` | 4/3/4/4/4/4 | 3072 | 46 | корректность зависит от последовательности команд, lease и времени |
| 5 | `AdaptiveAcquisitionEngine.acquire_page` | 4/4/3/4/4/4 | 3072 | 42 | малое изменение score/status переключает дорогую стратегию и fallback semantics |
| 6 | `BudgetTracker.record_page` | 4/3/4/3/4/4 | 2304 | 49 | лимит должен быть атомарным, но одновременно изменяет несколько счётчиков и deadline |
| 7 | `Deduplicator` | 3/4/4/4/3/4 | 2304 | 44 | stateful решение, environment-dependent hash и потенциальный `O(N²)` SimHash scan |
| 8 | `canonicalize_url` | 4/4/2/4/4/3 | 1536 | 40 | одно преобразование определяет scope, dedup и сетевую идентичность ресурса |
| 9 | `ArchiveExporter` | 3/4/3/3/3/4 | 1296 | 38 | формирует пользовательский persistent artifact и заявленные RAG-инварианты |
| 10 | `classify_page`/`CostPlanner` | 3/4/2/4/3/4 | 1152 | 35 | строковые эвристики и пороги резко меняют выбранную acquisition strategy |

### 4.3 Fragility Index и heatmap

Расчёт ведётся в audit report с оценками 0–4 для каждого слагаемого:

```text
Fragility Index =
  BoundarySensitivity × 2 + HiddenAssumptions × 2 +
  OrderDependence × 2 + StateDependence × 2 + TimingDependence +
  NumericSensitivity + FailureAmplification × 2 + MissingInvariants +
  MissingProperties + PoorErrorRecovery + ComplexityCliff
```

Интерпретация: `0–10` — устойчивый, `11–20` — умеренная хрупкость, `21–30` — высокая, `31+` — критическая. Высокий индекс требует доказательной проверки, но сам по себе не является основанием для архитектурного рефакторинга.

| Алгоритм | Boundary | Order | State | Time | Numeric/threshold | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| Pipeline | 🟠 | 🟠 | 🔴 | 🟠 | 🟢 | 🔴 |
| HTTP/SSRF | 🔴 | 🟢 | 🟠 | 🟠 | 🟢 | 🔴 |
| Media downloader | 🔴 | 🟠 | 🟠 | 🟠 | 🟢 | 🔴 |
| Request frontier | 🔴 | 🔴 | 🔴 | 🔴 | 🟠 | 🔴 |
| Acquisition escalation | 🔴 | 🟢 | 🟠 | 🟠 | 🔴 | 🔴 |
| Budget tracker | 🔴 | 🟠 | 🔴 | 🔴 | 🟠 | 🔴 |
| Deduplicator | 🟠 | 🔴 | 🔴 | 🟢 | 🟠 | 🟠 |
| URL canonicalizer | 🔴 | 🔴 | 🟢 | 🟢 | 🟢 | 🔴 |
| Archive exporter | 🟠 | 🟠 | 🟠 | 🟢 | 🟠 | 🟠 |
| Page classifier | 🔴 | 🟠 | 🟢 | 🟢 | 🔴 | 🟠 |

### 4.4 Предполагаемые контракты критичной десятки

| Алгоритм | Предполагаемый фактический контракт, который нужно утвердить | Первые гипотезы хрупкости |
| --- | --- | --- |
| Pipeline | каждый input URL имеет outcome; partial/failure отличимы от empty success; cancellation и ошибка не оставляют частичный архив/temp state | broad exceptions скрывают причины; последовательность media/PDF усиливает один сбой; output зависит от порядка discovery |
| HTTP/SSRF | каждый фактический socket target, включая redirects, разрешён policy; bytes никогда не превышают limit; client lifecycle закрыт | initial DNS check не защищает redirect/rebinding; синхронный DNS блокирует event loop |
| Media downloader | применяет тот же URL policy; запись атомарна; имя уникально; limit действует до накопления тела | SSRF bypass, full-body buffering, filename collision, silent `None` |
| Frontier | один canonical URL имеет не более одной активной queue entry; переходы state допустимы; retry идемпотентен; lease зависит от injected monotonic clock | double retry дублирует request; crashed `FETCHING` не возвращается; tie зависит от arrival order |
| Acquisition | ровно одна объяснимая stable strategy; non-2xx не становится success; fallback отражён как degradation | L2 недостижим из L1; пустой cache меняет ветку; browser failure возвращает любой HTTP status как artifact |
| Budget | проверка и commit usage атомарны; rejected event имеет явно выбранную семантику; deadline проверяется до дорогой работы | exception возникает после изменения counters; wall-clock jump меняет решение; отрицательные usage не валидируются |
| Deduplicator | одинаковая политика hash во всех окружениях; duplicate decision детерминирован; threshold валиден; стоимость ограничена | BLAKE3/SHA-256 зависит от install; empty text не дедуплицируется; linear SimHash scan создаёт cliff |
| Canonicalizer | идемпотентен и не объединяет URL, которые могут адресовать разные ресурсы; reserved characters сохраняют семантику | `%2F` превращается в `/`; query order и `ref/source` могут быть значимыми; userinfo lowercased |
| Archive exporter | `max_words` — реальная верхняя граница; manifest равен файлам; ZIP детерминирован при фиксированных данных; write failure не оставляет валидный-looking result | длинный paragraph превышает chunk limit; collisions перезаписывают media; vector metadata заявляет отсутствующие vectors |
| Classifier/planner | score находится в `[0,1]`; незначимый текст не переключает strategy; thresholds и tie cases имеют явную политику | substring `react` даёт false positive; 15→16 scripts создаёт cliff; L2/API thresholds не соответствуют доступным данным |

### 4.5 Реестр первых гипотез

| ID | HYPOTHESIS | EVIDENCE | COUNTEREXAMPLE | STATUS |
| --- | --- | --- | --- | --- |
| H-001 | dependency failure превращается в empty success | `execute` ловит `Exception` вокруг страницы и не возвращает errors | fake acquisition бросает `TimeoutError`; результат: 0 pages, 0 manifest documents, поля errors нет | `CONFIRMED` → FRAG-011 |
| H-002 | canonicalization объединяет разные path resources | `urllib.parse.unquote` выполняется до сборки canonical URL | `a%2Fb` становится `a/b` | `CONFIRMED` → FRAG-001 |
| H-003 | обычное слово может переключить HTTP на Browser | framework определяется substring-поиском `react` | `<p>reaction</p>` даёт `React`, `js_dependency_score=0.8` | `CONFIRMED` → FRAG-002 |
| H-004 | равный media score делает выбор зависимым от provider order | sort имеет только `relevance_score`, явного tie-break нет | при `max_count=1`: `[A,B] → A`, `[B,A] → B` | `CONFIRMED` → FRAG-003 |
| H-005 | retry одного request можно поставить в очередь дважды | `retry_request` без проверки добавляет тот же object | два retry, затем два lease возвращают один и тот же ID | `CONFIRMED` → FRAG-004 |
| H-006 | отклонённый budget event частично изменяет state | counters меняются до проверки deadline/последующих limits | expired deadline после вызова оставляет pages=1, bytes=10 | `CONFIRMED behaviour`; контракт неоднозначен → FRAG-005 |
| H-007 | chunker нарушает заявленный word bound | oversized paragraph не делится | 251 слово при `max_words=250` дают один chunk из 251 слова | `CONFIRMED` → FRAG-006 |
| H-008 | нулевая скорость rate limiter аварийна | отсутствует validation, выполняется division by rate | `TokenBucket(0,0).acquire()` → `ZeroDivisionError` | `CONFIRMED robustness gap` → FRAG-007 |
| H-009 | разные media URL могут перезаписать один файл | target строится только из prefix и basename | два `.../report.pdf` дают `doc_report.pdf` | `CONFIRMED` → FRAG-008 |
| H-010 | противоречивые min/max нарушают max contract | `max(min_count, min(len, max_count))` | `min=8,max=3,10 candidates` возвращает 8 | `CONFIRMED robustness gap` → FRAG-009 |
| H-011 | redirect/rebinding обходят SSRF policy | validation вызывается только для initial URL, `follow_redirects=True` | controlled resolver/redirect test ещё не добавлен | `CONFIRMED` control-flow violation; regression pending → FRAG-010 |
| H-012 | content hash меняется от состава окружения | optional import BLAKE3 с SHA-256 fallback | одинаковые bytes в двух dependency profiles | `EVIDENCE`; требуется differential test |
| H-013 | L2 API acquisition недостижим из L1 | `detected_apis` строится только из `network_requests`, которых L1 classifier не получает | fake HTTP HTML с API links/network absence | `CONFIRMED` control-flow proof; regression pending |
| H-014 | BrowserPool limits не ограничивают concurrency | `max_browsers`/`contexts_per_browser` сохраняются, но не участвуют в acquire | concurrent fake-context test pending | `EVIDENCE` |
| H-015 | seed/category selection чувствителен к случайным substrings и языку | hard-coded subject keywords и последовательные provider branches | query pairs с изменением одного token pending | `HYPOTHESIS` |

### 4.6 Начальный corpus минимальных контрпримеров

| ID | Impact / Severity / Confidence | Класс | Минимальный вход/сценарий | Ожидаемый контракт | Фактическое поведение | Regression test |
| --- | --- | --- | --- | --- | --- | --- |
| FRAG-001 | P1 / high / high | `FRAG-PARSING`, `FRAG-CONTRACT` | `canonicalize_url("https://example.com/a%2Fb")` | encoded reserved separator не сливается с `/` | возвращается `https://example.com/a/b` | `tests/unit/test_canonicalizer.py::test_preserves_encoded_path_separator` |
| FRAG-002 | P1 / high / high | `FRAG-HEURISTIC`, `FRAG-BOUNDARY` | HTML `<p>reaction</p>` | prose не считается React marker | `React`, JS score `0.8` | `tests/unit/test_page_classifier.py::test_framework_detection_requires_marker` |
| FRAG-003 | P1 / medium / high | `FRAG-ORDER`, `FRAG-HEURISTIC` | два изображения с одинаковым score, `max_count=1` | tie разрешается явным стабильным ключом | `[A,B]` выбирает A, `[B,A]` выбирает B | `tests/unit/test_media_selection.py::test_equal_score_has_deterministic_tie_break` |
| FRAG-004 | P1 / high / high | `FRAG-STATE`, `FRAG-RETRY` | `lease → retry → retry → lease → lease` | один request не выдаётся двум workers | оба lease возвращают один ID | `tests/unit/test_scheduler.py::test_retry_is_idempotent` |
| FRAG-005 | P1 / high / medium | `FRAG-STATE`, `FRAG-TIME`, `FRAG-CONTRACT` | usage event после deadline | reject до mutation либо документированная consumed-semantics | exception после pages=1/bytes=10 | `tests/unit/test_budget.py::test_expired_deadline_is_atomic` |
| FRAG-006 | P3 / medium / high | `FRAG-BOUNDARY`, `FRAG-INVARIANT` | один paragraph из 251 слова, limit 250 | каждый chunk `<=250` | один chunk содержит 251 слово | `tests/unit/test_search_pipeline.py::test_archive_chunk_hard_limit` |
| FRAG-007 | P2 / medium / high | `FRAG-NUMERIC`, `FRAG-RECOVERY` | `TokenBucket(rate=0, capacity=0)` | config validation или безопасное disabled state | `ZeroDivisionError` | `tests/unit/test_rate_limiter.py::test_non_positive_rate_rejected` |
| FRAG-008 | P0 / high / high | `FRAG-STATE`, `FRAG-DEPENDENCY` | два URL с basename `report.pdf` | разные sources не перезаписываются | оба target — `doc_report.pdf` | `tests/unit/test_media_downloader.py::test_distinct_urls_have_distinct_targets` |
| FRAG-009 | P2 / medium / high | `FRAG-BOUNDARY`, `FRAG-CONTRACT` | `min_count=8`, `max_count=3` | invalid range отвергается до ranking | возвращается 8, max нарушен | `tests/unit/test_media_selection.py::test_rejects_inverted_limits` |
| FRAG-010 | P0 / critical / high | `FRAG-DEPENDENCY`, `FRAG-RECOVERY` | public URL redirects на loopback/private | каждый hop блокируется до соединения | redirect target повторно не валидируется | `tests/unit/test_ssrf.py::test_redirect_target_revalidated` |
| FRAG-011 | P1 / high / high | `FRAG-RECOVERY`, `FRAG-CONTRACT` | единственная страница, acquisition timeout | explicit failed/partial outcome с причиной | успешный result с 0 pages и без errors | `tests/unit/test_search_pipeline.py::test_single_failure_is_not_empty_success` |

Контрпримеры FRAG-001…FRAG-009 и FRAG-011 воспроизведены на коммите аудита короткими детерминированными probes. FRAG-010 доказан по control flow, но до изменения HTTP-клиента обязан получить hermetic redirect test. До появления regression test этот corpus является доказательством и планом фиксации, а не заявлением об исправлении.

### 4.7 Progressive Deepening и правило остановки

| PASS | Что исследуем | Артефакт/выход | Когда углубляемся |
| --- | --- | --- | --- |
| 1 — Discovery | inventory, RiskScore₀, top-10 | разделы 4.1–4.3 | алгоритм входит в верхний risk band |
| 2 — Contracts | docs/types/code/tests, assumptions, invariants | contract/assumption register | контракт расходится или неоднозначен |
| 3 — Static | boundaries, order, state, time, constants, error paths, complexity | hypotheses со способом проверки | есть конкретный достижимый путь риска |
| 4 — Existing tests | покрытые equivalence classes и error paths | test gap matrix | класс риска реально не покрыт |
| 5 — Counterexamples | минимальный input/sequence/fault | FRAG record и deterministic reproducer | контрпример подтверждён либо invariant доказуемо нарушен |
| 6 — Generative | property, metamorphic, differential, parser fuzz | shrinking corpus и сохранённые seeds | генератор способен исследовать новый класс входов |
| 7 — Fault injection | network, filesystem, dependency, cancellation | state-after-failure assertions | внешний сбой имеет высокий blast radius |
| 8 — Mutation | boundary/operators в critical algorithms | surviving mutant register | тесты зелёные, но поведение ещё слабо специфицировано |
| 9 — Hardening | LEVEL 0…5, минимальное вмешательство | fix + regression + ADR только для LEVEL 4–5 | доказательство указывает на конкретный класс хрупкости |
| 10 — Regression | весь corpus, properties, state models, budgets | пересчитанный FI и закрытый FRAG | фикс расширил область устойчивости без нового divergence |

Ветка исследования останавливается, если контракт однозначен, критичные инварианты закреплены, relevant mutants уничтожаются, property/stateful tests не находят новых минимальных примеров и следующая проверка имеет низкую ожидаемую ценность. Для каждого hardening change выбирается минимальный уровень: `LEVEL 0 test`, `LEVEL 1 validation/invariant`, `LEVEL 2 local fix`, `LEVEL 3 algorithm`, `LEVEL 4 contract`, `LEVEL 5 architecture`. LEVEL 4–5 запрещены без отдельного доказательства, почему LEVEL 0–3 недостаточны.

Каждая новая запись в `docs/architecture/AUDIT_REPORT.md` обязана содержать: `FRAG-ID`, severity/confidence, location/symbol, contract, observed behaviour, hidden assumption, trigger, minimal reproducer, expected/actual, root cause, blast radius, existing/missing test, минимальный recommended level и verification. Неподтверждённые записи остаются `HYPOTHESIS`, а не включаются в количество дефектов.

## 5. Целевая архитектура без нового оверинжиниринга

| Слой | Ответственность | Правило |
| --- | --- | --- |
| Interfaces | CLI, REST, MCP, минимальный UI | только валидация транспорта и преобразование ответа |
| Application | `DeepSearchService`, `JobService`, единый `RunContext` | один сценарий исполнения для всех интерфейсов |
| Core | модели запроса/результата, политика эскалации, лимиты, ошибки | не импортирует FastAPI, Typer, MCP, SQLAlchemy или Playwright |
| Adapters | HTTP, Browser, providers, exporter, optional storage | каждый внешний ресурс имеет lifecycle, timeout и контрактный тест |

Ограничения для последующих изменений:

1. Не вводить Redis/Celery, пока не появится измеренное требование к нескольким процессам или машинам.
2. Не поддерживать одновременно pgvector и Qdrant. При реализации поиска выбрать один backend по измеренному сценарию.
3. Не добавлять новую абстракцию без двух реальных реализаций либо явной границы внешнего ресурса.
4. Не считать функцию реализованной, если публичный интерфейс возвращает stub/demo/fallback, не помеченный как деградация.
5. Не создавать отдельный orchestration path для CLI, REST и MCP.
6. Не сохранять большие временные файлы вне управляемого каталога запуска.

## 6. План работ

### DS-01 — Зафиксировать честную карту возможностей

**Приоритет:** P0

**Что делаем:** объявляем один список возможностей со статусами `stable`, `experimental`, `disabled`; убираем production-ready формулировки, фиктивный зелёный badge и утверждения о полностью проходящих тестах. Для search, PixelRAG, PostgreSQL/Redis/Qdrant и OCR до их реальной реализации показываем `disabled/experimental`, а не успешный ответ-заглушку.

**Где делаем:** `README.md`, `README.ru.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/architecture/AUDIT_REPORT.md`, `docs/architecture/MODULE_INDEX.md`, `docs/architecture/REQUIREMENTS_TRACEABILITY.md`, `scraper/search/search_engine.py`, `scraper/visual/pixel_rag.py`, REST/MCP/CLI descriptions. Повторяющиеся архитектурные документы после переноса актуальных сведений удаляем, оставляя `ARCHITECTURE.md` и этот план.

**Как проверить:** тест сопоставляет опубликованную capability matrix с зарегистрированными REST/MCP/CLI операциями; поиск по репозиторию не находит `IMPLEMENTED`, `STABLE` или `production-grade` для возможностей без интеграционного теста. Disabled endpoint возвращает явный `501/capability_unavailable`, а не sample result.

**Готово когда:** пользователь по любому интерфейсу видит фактический, а не предполагаемый уровень готовности.

### DS-02 — Ввести минимальный обязательный CI-gate

**Приоритет:** P0

**Что делаем:** добавляем CI для Python 3.11 и 3.12: frozen install, Ruff lint/format, mypy, unit tests с покрытием, сборка wheel/sdist и проверка установки wheel. Выбираем один formatter — `ruff format`; Black удаляем из dev dependencies после одноразового форматирования.

**Где делаем:** `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`.

**Как проверить:** локальная команда `uv sync --extra dev --frozen && uv run ruff check . && uv run ruff format --check . && uv run mypy scraper && uv run pytest` проходит; wheel устанавливается в пустое venv и команда `scraper --help` запускается. Начальный coverage gate — 70% для подключённого core, затем 80% после DS-15.

**Готово когда:** `main` нельзя считать зелёным при падении любого обязательного шага.

### DS-03 — Сделать unit tests герметичными

**Приоритет:** P0

**Что делаем:** исключаем реальную сеть, DNS и Chromium из unit suite. Внедряем fake/MockTransport для HTTP, fake browser, `pytest-socket` и временный output workspace. Реальные provider/browser проверки выносим в отдельно маркированные integration/e2e suites. Все тесты обязаны удалять созданные архивы и временные каталоги.

**Где делаем:** `tests/unit/test_api.py`, `test_mcp_server.py`, `test_discovery.py`, `test_search_pipeline.py`, общий `tests/conftest.py`; новые группы `tests/integration` и `tests/e2e` создаём только для действительно внешних контрактов.

**Как проверить:** `pytest tests/unit --disable-socket` проходит без Chromium и доступа к интернету; повторный запуск не создаёт ZIP-файлы в корне; integration tests запускаются отдельной командой и корректно skip-аются без prerequisites.

**Готово когда:** чистый `uv sync` даёт одинаковый unit-результат онлайн и офлайн.

### DS-04 — Создать один application service и composition root

**Приоритет:** P0

**Что делаем:** переносим orchestration в один `DeepSearchService` с операциями `inspect`, `extract`, `research` и, после DS-11, `start_job/get_job`. Все зависимости передаются явно через constructor/factory. Глобальные `acquisition_engine`, `frontier`, `search_engine` убираем. Создание и закрытие HTTP client, browser, job tasks выполняет единый lifecycle.

**Где делаем:** новый компактный application-модуль внутри `scraper` (без дерева из manager-классов), `scraper/api/app.py`, `api/routes.py`, `cli/main.py`, `mcp/server.py`, `acquisition/browser_pool.py`.

**Как проверить:** contract suite вызывает одинаковые fake dependencies через CLI runner, FastAPI TestClient и MCP tool functions и получает эквивалентный domain result; после завершения lifespan нет незакрытых `httpx`/Playwright ресурсов и pending asyncio tasks.

**Готово когда:** ни один interface не собирает pipeline вручную и не содержит бизнес-решений.

### DS-05 — Исправить контракты и типизированную модель ошибок

**Приоритет:** P0

**Что делаем:** синхронизируем Protocol-сигнатуры с адаптерами; вводим закрытый набор ошибок (`invalid_input`, `blocked_target`, `timeout`, `dependency_unavailable`, `budget_exceeded`, `partial_result`, `internal_error`) и структурированный `RunResult` с warnings/errors/provider statuses. Убираем возврат `Any` там, где известен тип.

**Где делаем:** `scraper/contracts/__init__.py`, `scraper/exceptions.py`, acquisition/provider/exporter adapters, application service и все interfaces.

**Как проверить:** `mypy --strict` для core/application и `mypy --check-untyped-defs` для всего пакета проходят; fake implementation каждого Protocol проходит общий contract test; REST error schema, CLI exit code и MCP error payload проверяются одной таблицей сценариев.

**Готово когда:** пустой результат невозможно спутать с отказом зависимости.

### DS-06 — Свести конфигурацию к одному проверяемому контракту

**Приоритет:** P0

**Что делаем:** удаляем устаревшие Go-переменные из `.env.example`, добавляем только реально читаемые Pydantic fields, запрещаем `dev-secret` при production mode, вводим диапазоны для timeout/concurrency/page/media limits и fail-fast проверку несовместимых опций. Версию берём из package metadata, а не дублируем строкой.

**Где делаем:** `scraper/config.py`, `.env.example`, `docs/CONFIGURATION.md`, Docker/Compose environment.

**Как проверить:** параметризованный тест загружает каждую строку `.env.example` и подтверждает изменение нужного field; неизвестные переменные в строгом режиме завершают startup ошибкой; production config без secret не запускается; `DATABASE_URL` из примера совместим с выбранным backend.

**Готово когда:** пример окружения является исполняемой спецификацией конфигурации.

### DS-07 — Закрыть единый сетевой security boundary

**Приоритет:** P0

**Что делаем:** все HTTP, media, PDF и browser navigation используют один URL policy. Проверяем scheme, userinfo, hostname, DNS-ответы, каждый redirect и фактический peer address; блокируем loopback/private/link-local/multicast/reserved/unspecified и IPv4-mapped IPv6. В Playwright перехватываем и валидируем document/subresource/download requests. Синхронный DNS выносим из event loop.

**Где делаем:** `scraper/acquisition/http_fetcher.py`, `browser_pool.py`, `media_downloader.py`, `authorized_browser.py`, provider adapters.

**Как проверить:** regression tests `redirect_to_private`, `dns_rebinding`, `ipv4_mapped_ipv6`, `userinfo_confusion`, `browser_subresource_private`, `media_private`, `unsupported_scheme`; разрешённый public URL проходит. Проверку дополняем локальным controlled HTTP server и mocked resolver.

**Готово когда:** в репозитории нет прямого `httpx`/Playwright fetch вне общего policy-aware transport.

### DS-08 — Защитить REST API и файловый вывод

**Приоритет:** P0

**Что делаем:** вводим реальную API-key dependency либо явно local-only binding; CORS становится allowlist без сочетания wildcard/credentials. Ограничиваем body/query sizes, rate/concurrency и длительность операций. Клиент задаёт логическое имя результата, но не произвольный server path; все файлы создаются внутри уникального run workspace.

**Где делаем:** `scraper/api/app.py`, `api/routes.py`, `config.py`, application/output service, `docs/openapi.yaml`.

**Как проверить:** запрос без/с неверным key получает 401/403; CORS tests проверяют разрешённый и запрещённый origin; `../`, абсолютный путь и symlink escape отвергаются; параллельные запросы сверх лимита получают 429/503; generated OpenAPI совпадает с committed spec и содержит фактическую security scheme.

**Готово когда:** публичный HTTP-интерфейс не позволяет анонимно запускать неограниченный crawl или писать вне workspace.

### DS-09 — Упростить и сделать честной acquisition policy

**Приоритет:** P1

**Что делаем:** оставляем только реально исполняемые tiers: HTTP и Browser. Параметр `cached_content`/L0 и мёртвую L2 API-ветку удаляем до появления реального cache/API adapter; L4/L5 не входят в stable path до работающих OCR/embedding. Для каждого mode задаём таблицу разрешённых стратегий, timeout и fallback semantics; неуспешный HTTP status не превращаем автоматически в успешный artifact.

**Где делаем:** `scraper/acquisition/engine.py`, `page_classifier.py`, `control/planner.py`, `config.py`.

**Как проверить:** table-driven tests покрывают static HTTP, JS escalation, browser unavailable, 3xx/4xx/5xx, block page, deadline и cancellation; каждая ветка сообщает точную strategy/reason; удалённые L0/L2 не присутствуют в public enum/config; McCabe для decision function ≤10.

**Готово когда:** диаграмма tiers в документации однозначно выводится из тестируемой таблицы переходов.

### DS-10 — Подключить ограничения в реальный RunContext

**Приоритет:** P1

**Что делаем:** создаём один per-run context с deadline, cancellation, page/byte/depth/browser/media budgets, host/global rate limiter, robots policy, exact URL/content dedup и telemetry hooks. Компоненты, которые не удаётся подключить в этом пункте, удаляем вместо хранения «на будущее». На первом этапе используем SHA-256 и in-memory dedup; BLAKE3/SimHash/CAS добавляются только при измеренной необходимости.

**Где делаем:** application service, `control/budget.py`, `rate_limiter.py`, `discovery/robots.py`, `normalization/deduplicator.py`, acquisition и pipeline. `proxy_manager.py`/`session_manager.py` удаляем, если они не получают реального потребителя.

**Как проверить:** integration test с локальным сайтом подтверждает robots deny, crawl-delay/rate limit, max pages/depth/bytes, duplicate suppression, deadline и cooperative cancellation; счётчики совпадают с фактически выполненными запросами.

**Готово когда:** изменение любого лимита в config наблюдаемо меняет реальное выполнение.

### DS-11 — Реализовать настоящий минимальный JobService

**Приоритет:** P1

**Что делаем:** заменяем фиктивный `/crawl` на bounded in-process worker для одного экземпляра приложения: состояния `queued/running/succeeded/partial/failed/cancelled`, progress, error summary и result reference. Не вводим Redis до требования multi-process. Job ID связывается с конкретным состоянием, а не с глобальной статистикой frontier. Добавляем shutdown cancellation.

**Где делаем:** application `JobService`, `scraper/api/routes.py`; `control/scheduler.py` упрощаем до `asyncio.PriorityQueue`/очереди с ограниченной ёмкостью либо удаляем.

**Как проверить:** тесты переходов состояния, двух независимых jobs, queue full, cancel, failure, partial result и graceful shutdown; `GET /crawl/{id}` для неизвестного ID возвращает 404; `POST /crawl` не обещает RUNNING до фактического старта.

**Готово когда:** каждый принятый job либо завершён, либо имеет объяснимое терминальное состояние.

### DS-12 — Разделить research pipeline на проверяемые стадии

**Приоритет:** P1

**Что делаем:** разбиваем `DeepSearchPipeline.execute` на стадии `discover → schedule → acquire/extract → collect media → export`, каждая принимает/возвращает типизированные данные и не скрывает исключения. `list.pop(0)` заменяем на deque/queue; blocking PDF/Pillow/file operations запускаем через bounded executor. Все temp dirs управляются `TemporaryDirectory`/workspace lifecycle и очищаются после упаковки.

**Где делаем:** `scraper/pipeline/search_pipeline.py`, `storage/archive_exporter.py`, `extraction/pdf_extractor.py`, application service.

**Как проверить:** unit test каждой стадии; fault-injection после каждой стадии не оставляет temp dirs; cancellation останавливает новые requests; итог детерминирован при одинаковых входах; сложность каждой функции ≤10, `execute` становится короткой координацией.

**Готово когда:** отдельную стадию можно проверить без сети и без запуска всего pipeline.

### DS-13 — Сделать discovery конкурентным, расширяемым и наблюдаемым

**Приоритет:** P1

**Что делаем:** заменяем hard-coded keyword classification и последовательные вызовы на небольшой реестр provider adapters. Провайдеры запускаются ограниченно-параллельно, имеют общий client, timeout/retry policy, стабильный порядок merge и возвращают provenance/status. `domain` становится настоящим host allowlist/filter. Anna's Archive и иные спорные/нестабильные источники — только явный opt-in, не default.

**Где делаем:** `scraper/discovery/seed_finder.py`, config, provider tests, документация. Предметные слова про алопецию/фотополимеры/лазер удаляем из универсального core.

**Как проверить:** fake providers с разной задержкой подтверждают concurrency cap, deterministic merge, timeout isolation, dedup и partial status; domain filter сравнивает parsed hostname, а не substring; один упавший provider не стирает результаты остальных.

**Готово когда:** добавление источника требует одного adapter и contract test, но не изменения orchestration.

### DS-14 — Объединить и ограничить media/PDF acquisition

**Приоритет:** P1

**Что делаем:** используем общий streaming downloader с SSRF guard, Content-Length precheck, decompressed-byte limit, MIME sniffing, уникальными content-addressed filenames и атомарной записью. Ограничиваем число документов/медиа на страницу и на run. PDF parsing получает page/time/memory limits. Для внешних изображений сохраняем license/author/source attribution; неизвестная лицензия помечается, а не подразумевается.

**Где делаем:** `acquisition/media_downloader.py`, `pipeline/search_pipeline.py`, `discovery/media_finder.py`, `extraction/pdf_extractor.py`, exporter.

**Как проверить:** тесты oversized/chunked/decompression bomb, fake MIME, duplicate filename, partial write, malicious PDF, page limit, license metadata и checksum; загрузка не держит весь файл в RAM.

**Готово когда:** все бинарные загрузки проходят один проверенный путь и имеют измеримый бюджет.

### DS-15 — Исправить extraction и формат архива

**Приоритет:** P1

**Что делаем:** убираем mutable defaults; корректно обрабатываем `rowspan/colspan`, экранирование `|`/переносов в Markdown и неравные строки. Архив получает schema version, run status, warnings/errors и точную статистику. Удаляем фиктивный `vector_index.json` с dimensions=1536 без embeddings; возвращаем его только после реального индексирования. Не дублируем полный corpus одновременно в нескольких тяжёлых форматах без опции.

**Где делаем:** `extraction/engine.py`, `markdown.py`, `table_extractor.py`, `storage/archive_exporter.py`.

**Как проверить:** golden fixtures для сложных таблиц, Unicode, malformed HTML, пустых страниц и prompt-like content; JSON Schema validation manifest; ZIP reproducibility test; `total_user_files`, PDF/media counts и checksums совпадают с инвентарём.

**Готово когда:** архив можно валидировать независимо от Python-кода и в нём нет заявленных несуществующих vectors.

### DS-16 — Вывести fake search/PixelRAG из stable surface

**Приоритет:** P1

**Что делаем:** немедленно прекращаем возврат hard-coded `example.com` результатов. До появления реального индекса search endpoints/tools скрыты feature flag или возвращают `capability_unavailable`. Для будущей реализации сначала фиксируем retrieval contract и eval corpus; выбираем один text/vector backend. Visual search включается только после реальных embeddings, upsert/search и quality eval.

**Где делаем:** `scraper/search/search_engine.py`, `storage/vector_store.py`, `visual/pixel_rag.py`, REST/MCP/CLI/UI, dependencies/Compose.

**Как проверить:** stable profile не показывает search как готовый; ни один production response не содержит sample IDs; будущий backend проходит contract tests `index → restart → retrieve`, tenant/run isolation и relevance eval выше зафиксированного baseline.

**Готово когда:** любой search result происходит из ранее проиндексированного пользовательского документа.

### DS-17 — Выбрать один источник истины для хранения и миграций

**Приоритет:** P1

**Что делаем:** для stable local-first версии оставляем filesystem workspace и in-process job state. Неиспользуемые PostgreSQL/Redis/Qdrant/MinIO удаляем из default dependencies и Compose. Если persistence подтверждён продуктовым сценарием, создаём одну последовательность Alembic migrations, синхронизированную с ORM; две конфликтующие `001_*` удаляем. `create_all` не используется как параллельная миграционная система.

**Где делаем:** `scraper/storage/db.py`, `models.py`, `vector_store.py`, `migrations/`, `pyproject.toml`, `docker-compose.yml`, docs.

**Как проверить:** default profile не пытается подключаться к внешним сервисам; optional storage profile поднимается с нуля, применяет migrations, откатывается на один шаг и повторно применяется; schema diff между ORM и БД пуст.

**Готово когда:** для каждой таблицы существует ровно один владелец и один путь создания.

### DS-18 — Сократить зависимости и количество модулей

**Приоритет:** P2

**Что делаем:** строим import/usage inventory и удаляем неиспользуемые Crawlee, BeautifulSoup, Jinja2, lxml direct dependency, OpenTelemetry SDK, Redis/AsyncPG/SQLAlchemy/Qdrant из default profile, если они не подключены предыдущими пунктами. Browser, API, MCP, PDF и OCR оформляем optional extras. Пустые manager/stub модули объединяем с реальным adapter либо удаляем.

**Где делаем:** `pyproject.toml`, `uv.lock`, package structure; кандидаты: `proxy_manager.py`, `session_manager.py`, `storage/db.py`, `models.py`, `vector_store.py`, `visual/pixel_rag.py`.

**Как проверить:** `uv tree` и import smoke tests для `core`, `api`, `mcp`, `browser` extras; default install не тянет Playwright/Qdrant/PostgreSQL; cold install size/time фиксируются как baseline и уменьшаются; все extras собираются независимо.

**Готово когда:** у каждой прямой зависимости есть импорт в stable path или документированная optional capability.

### DS-19 — Удалить предметные прототипы из product root

**Приоритет:** P2

**Что делаем:** извлекаем только действительно универсальные части, после чего удаляем `deep_pdf_research_engine.py`, `run_laser_research.py`, `run_papanicolaou_lbc_research.py`. Лазерная резка, цитология и другие предметные запросы становятся внешними входными данными/fixtures, а не параллельными приложениями. `rule.md` и `cycle-rule.md` сводим к одному актуальному product scope либо архивируем вне runtime repository.

**Где делаем:** корень репозитория, tests fixtures, основная документация.

**Как проверить:** `rg` не находит hard-coded output directories, темы и дублирующие `search_annas_archive`/PDF download loops в product code; все поддерживаемые сценарии выполняются одной командой `scraper research`.

**Готово когда:** в репозитории остаётся один путь запуска исследования.

### DS-20 — Выровнять CLI, REST и MCP

**Приоритет:** P2

**Что делаем:** генерируем transport schemas из общих request/result models. CLI `crawl` начинает использовать depth/max_pages, `extract --schema` либо реализуется, либо удаляется. MCP возвращает structured content, валидирует mode/depth/pages и не строит filename из query. REST не выполняет многочасовой research внутри request handler без job contract.

**Где делаем:** `scraper/cli/main.py`, `api/routes.py`, `mcp/server.py`, application models.

**Как проверить:** parameterized parity tests прогоняют одинаковые valid/invalid запросы через три интерфейса; CLI exit codes, HTTP codes и MCP errors соответствуют общей taxonomy; snapshot публичных schemas контролируется в CI.

**Готово когда:** интерфейсы различаются только формой транспорта.

### DS-21 — Исправить MCP lifecycle и конфигурацию

**Приоритет:** P2

**Что делаем:** `.mcp/config.json` сокращаем до DeepSearch server; удаляем команды, которые запускают `pip/npm install` вместо сервера, и вымышленные endpoints. Manager пишет служебные сообщения только в stderr, имеет timeout на handshake и гарантированно завершает subprocess. PowerShell не содержит абсолютного пути конкретного пользователя.

**Где делаем:** `.mcp/config.json`, `scripts/mcp_manager.py`, `run_mcp.ps1`, MCP docs.

**Как проверить:** официальный MCP client/session test выполняет initialize, tools/list, один tool call и shutdown; stdout содержит только protocol frames; health check завершается по timeout; configs работают из пути с пробелами на Windows и POSIX.

**Готово когда:** один сгенерированный config подключает MCP без ручного редактирования и установки случайных сторонних серверов.

### DS-22 — Сделать Dashboard честным или временно убрать

**Приоритет:** P2

**Что делаем:** до готового JobService убираем Dashboard из stable profile. После DS-11 оставляем минимальный UI: реальная health/capabilities, запуск job, progress, результат и ошибки. Удаляем статические метрики, фальшивое autoscaling, неработающие Extraction Studio/Visual Search. Внешний Google Fonts dependency убираем из local/offline UI.

**Где делаем:** `scraper/ui/dashboard.py`, `api/app.py`, UI tests.

**Как проверить:** Playwright e2e с fake backend подтверждает запуск, progress, error, cancellation; каждое число в UI происходит из API response; при offline mode интерфейс не делает внешних запросов.

**Готово когда:** UI не показывает ни одного заранее зашитого operational value.

### DS-23 — Подключить наблюдаемость к реальному пути

**Приоритет:** P2

**Что делаем:** telemetry становится thread/task-safe и вызывается из application/acquisition hooks. Разделяем Prometheus exposition и JSON summary; добавляем run ID, stage duration, provider outcomes, bytes, retries, browser escalation и причины пропуска. Не создаём два независимых набора счётчиков.

**Где делаем:** `scraper/monitoring/telemetry.py`, RunContext, API metrics endpoint, logging config.

**Как проверить:** один scripted run имеет заранее известные totals; concurrent test не теряет increments; `/metrics` выдаёт Prometheus text, `/metrics/summary` — согласованный JSON; логи не содержат API keys/cookies/query secrets.

**Готово когда:** по метрикам можно объяснить время, стоимость и частичный результат конкретного run.

### DS-24 — Укрепить контейнер и Compose

**Приоритет:** P2

**Что делаем:** Docker build использует `uv.lock`/frozen dependencies, multi-stage или очищенный runtime, non-root user, healthcheck и pinned base image digest/version policy. Не используем editable install и не оставляем compiler/git в runtime. Compose делим на default core и optional profiles; убираем host ports/default passwords/`latest` для неиспользуемых сервисов. Добавляем `.dockerignore`.

**Где делаем:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, CI image job.

**Как проверить:** `docker compose config`, image build, container health, read-only filesystem smoke, non-root assertion, graceful shutdown и vulnerability scan; browser smoke выполняется только в browser image/profile.

**Готово когда:** default container запускает ровно необходимые сервисы и не публикует внутренние БД наружу.

### DS-25 — Добавить проверяемые performance budgets

**Приоритет:** P2

**Что делаем:** измеряем discovery latency, requests/page, peak memory, archive size, event-loop lag, browser concurrency и throughput на локальном deterministic corpus. Вводим bounded concurrency по host/global, backpressure и benchmark regression thresholds. Оптимизируем N+1 Wikimedia calls через batch API и переиспользуем HTTP clients.

**Где делаем:** discovery/acquisition/pipeline, `tests/performance`, CI scheduled/manual job.

**Как проверить:** фиксированный corpus сравнивается с baseline; p95 latency/memory/request count не ухудшаются сверх согласованного порога; тест доказывает, что concurrency не превышает config и отмена освобождает ресурсы.

**Готово когда:** заявления об эффективности подтверждаются числами, а не наличием классов RateLimiter/BudgetTracker.

### DS-26 — Провести release audit и синхронизацию документации

**Приоритет:** P2

**Что делаем:** после выполнения предыдущих пунктов генерируем OpenAPI и capability matrix из кода, обновляем README/architecture/config/CLI/MCP guides, добавляем changelog и downgrade/upgrade notes. Версию `1.0.0` публикуем только после прохождения stable definition of done; до этого используем pre-release status.

**Где делаем:** `README*`, `docs/`, package metadata, generated OpenAPI, release workflow.

**Как проверить:** все команды из документации выполняются в CI; ссылки и code blocks проверяются; OpenAPI diff пуст; clean-room install проходит CLI/API/MCP smoke; текущий audit report содержит фактические результаты CI.

**Готово когда:** документацию можно использовать как исполняемую инструкцию установки и проверки.

### DS-27 — Утвердить контракты, инварианты и реестр предположений top-10

**Приоритет:** P0

**Основание:** RiskScore₀/FI₀ из разделов 4.2–4.4; текущие docstrings описывают возможности, но не определяют границы, error semantics, идемпотентность и состояние после сбоя.

**Что делаем:** для критичной десятки сопоставляем документацию, типы, реализацию и существующие тесты. Для каждого алгоритма фиксируем допустимые типы/диапазоны/размеры/порядок, выходные гарантии, side effects, повторный вызов, cancellation, time source и состояние после exception. Каждое скрытое предположение получает ID `A-001…`, severity, проверку и ссылку на тест. Не меняем алгоритм на этом шаге.

**Где делаем:** существующий `docs/architecture/AUDIT_REPORT.md`, docstrings и типы соответствующих top-10 symbols; traceability-ссылки остаются в этом плане. Новые manager/interface классы не создаём.

**Почему:** без утверждённого контракта невозможно отличить bug, fragility, robustness gap и допустимую threshold discontinuity.

**Класс хрупкости:** `FRAG-CONTRACT`, `FRAG-INVARIANT`, `FRAG-STATE`, `FRAG-TIME`.

**Как проверить:** у каждого из десяти алгоритмов заполнены input/output/error/state/time/idempotency contracts; каждое расхождение docs/types/code/tests имеет статус; ни одна P0/P1 рекомендация не ссылается только на сложность или FI.

**Regression test:** characterization tests закрепляют только подтверждённое корректное поведение; сомнительное поведение остаётся hypothesis/counterexample и не цементируется как контракт.

**Готово когда:** на 15 вопросов главного критерия аудита из пользовательской методики можно ответить для каждого top-10 алгоритма.

### DS-28 — Превратить начальный counterexample corpus в постоянные regression tests

**Приоритет:** P0

**Основание:** воспроизведённые FRAG-001…FRAG-009 и FRAG-011; control-flow proof FRAG-010.

**Что делаем:** переносим каждый минимальный reproducer из раздела 4.6 в ближайший существующий unit test и исправляем только соответствующий класс хрупкости на LEVEL 1–2. Не оставляем долгоживущие non-strict `xfail` и не объединяем несколько поведенческих исправлений в один коммит. Для FRAG-005 сначала утверждаем atomic или consumed semantics в DS-27.

**Где делаем:** существующие `tests/unit/test_canonicalizer.py`, `test_page_classifier.py`, `test_media_selection.py`, `test_scheduler.py`, `test_budget.py`, `test_search_pipeline.py`, `test_rate_limiter.py`, `test_media_downloader.py`, `test_ssrf.py` и минимальные изменения соответствующих production symbols.

**Почему:** минимальные контрпримеры — самая дешёвая защита от возврата уже доказанного дефекта при последующем упрощении архитектуры.

**Класс хрупкости:** `FRAG-PARSING`, `FRAG-BOUNDARY`, `FRAG-ORDER`, `FRAG-STATE`, `FRAG-RETRY`, `FRAG-TIME`, `FRAG-RECOVERY`, `FRAG-DEPENDENCY`.

**Как проверить:** каждый FRAG-ID упомянут ровно одним первичным regression test; test падает на коммите аудита и проходит после локального fix; FRAG-010 выполняется с controlled redirect/resolver без доступа к интернету.

**Regression test:** точные имена тестов перечислены в разделе 4.6; shrink/minimal input сохраняется непосредственно в параметрах теста, без отдельного каталога fixture-файлов.

**Готово когда:** повторный запуск всего corpus детерминирован и не требует DNS, Chromium, внешней сети или постоянной директории вывода.

### DS-29 — Добавить property, metamorphic и differential проверки чистых алгоритмов

**Приоритет:** P1

**Основание:** H-002, H-003, H-004, H-007, H-010, H-012 и отсутствие проверок целых классов входов при единичных example-based tests.

**Что делаем:** добавляем Hypothesis только как dev dependency и генерируем осмысленные классы: empty/single/duplicates, Unicode, reserved URL characters, reordered query pairs, extreme thresholds, repeated tokens, one oversized paragraph и equal scores. Проверяем `normalize(normalize(x)) == normalize(x)`, симметрию Hamming distance, exact-dedup idempotency, permutation invariance после явного tie-break, score range, chunk reassembly и hard word bound. Differential test сравнивает hash policy в двух dependency profiles и простую reference-модель ranking/dedup.

**Где делаем:** `pyproject.toml`, `uv.lock` и существующие `test_canonicalizer.py`, `test_deduplicator.py`, `test_media_selection.py`, `test_page_classifier.py`, `test_search_pipeline.py`, `test_media_downloader.py`.

**Почему:** example tests доказывают отдельные точки, но не радиус устойчивости вокруг них; shrinking автоматически даёт минимальный вход для новой FRAG-записи.

**Класс хрупкости:** `FRAG-BOUNDARY`, `FRAG-ORDER`, `FRAG-PARSING`, `FRAG-NUMERIC`, `FRAG-HEURISTIC`, `FRAG-INVARIANT`.

**Как проверить:** PR suite использует не менее 500 deterministic examples на property, nightly — не менее 5000; seed и shrunk example печатаются при падении; запрещено подавлять найденный пример через blanket `assume`/filter без контрактного объяснения.

**Regression test:** каждый новый shrunk counterexample добавляется как именованный example рядом с property test до исправления production code.

**Готово когда:** properties не находят divergence на утверждённой области входов, а invalid domain отвергается validation, а не случайным исключением внутри алгоритма.

### DS-30 — Проверить frontier, budget и limiter через stateful model и управляемое время

**Приоритет:** P1

**Основание:** FRAG-004, FRAG-005, FRAG-007; H-014; wall-clock и mutable queue/counters определяют correctness нескольких алгоритмов.

**Что делаем:** создаём простую эталонную модель состояний и генерируем команды `add/lease/start/retry/complete/fail/expire/cancel`. В production внедряем минимальные callables `now_monotonic`/`now_wall` и RNG там, где без этого нельзя воспроизводимо проверить deadline/backoff; отдельный Clock framework не создаём. Проверяем повторные и конкурентные вызовы, cancellation race и lease expiry при clock jumps.

**Где делаем:** `scraper/control/scheduler.py`, `budget.py`, `rate_limiter.py`, `acquisition/browser_pool.py`; `tests/unit/test_scheduler.py`, `test_budget.py`, `test_rate_limiter.py` и browser fake tests.

**Почему:** корректность stateful алгоритма нельзя доказать тестированием только happy-path методов по отдельности.

**Класс хрупкости:** `FRAG-STATE`, `FRAG-TIME`, `FRAG-CONCURRENCY`, `FRAG-RETRY`, `FRAG-NUMERIC`.

**Как проверить:** model-based test после каждой команды подтверждает: queue IDs уникальны; terminal request не lease-ится; capacity учитывает queued+active по утверждённому контракту; attempts монотонны; stats partition согласован; rejected budget event атомарен; concurrency никогда не превышает limit. Отдельно выполняются `t-ε/t/t+ε`, backward/forward clock jumps и cancellation immediately before/after commit.

**Regression test:** sequence `lease,retry,retry,lease,lease` остаётся обязательным example; каждый новый shrunk command sequence сохраняется рядом с state machine test.

**Готово когда:** реальная система и reference model совпадают на сгенерированных последовательностях, а тесты не используют `sleep` для доказательства времени.

### DS-31 — Ввести fault injection и проверить graceful degradation всего рабочего пути

**Приоритет:** P1

**Основание:** FRAG-010, FRAG-011, H-001, H-011, H-013, H-014; текущие broad exceptions стирают outcome и оставляют неясное состояние output.

**Что делаем:** через уже внедряемые dependencies/transport fakes принудительно создаём DNS failure, redirect to private, timeout до/после response headers, partial/chunked body, malformed payload, browser crash, disk full, permission denied, source file disappearance, cancellation и archive write failure. Для каждой стадии утверждаем `normal → partial → safe failure`; result содержит stage/provider outcome и не выглядит успешным без данных.

**Где делаем:** application service из DS-04, `http_fetcher.py`, `browser_pool.py`, `media_downloader.py`, `search_pipeline.py`, `archive_exporter.py`; существующие unit/integration tests с `httpx.MockTransport` и временной filesystem boundary.

**Почему:** сбой одной зависимости сейчас усиливается до empty success, silent skip либо потенциально неполного persistent artifact.

**Класс хрупкости:** `FRAG-DEPENDENCY`, `FRAG-RECOVERY`, `FRAG-CONTRACT`, `FRAG-CONCURRENCY`, `FRAG-STATE`.

**Как проверить:** fault matrix проверяет outcome и состояние после каждой точки отказа; нет temp/file leaks; manifest появляется только после атомарного завершения; partial result перечисляет пропущенные sources; SSRF test валидирует каждый redirect и browser/media request до соединения.

**Regression test:** `test_single_failure_is_not_empty_success`, `test_redirect_target_revalidated` и по одному fault test на границу каждой pipeline stage.

**Готово когда:** ни один инъецированный сбой не повреждает ранее валидный output, не раскрывает внутренний адрес и не превращается в необъяснимый пустой успех.

### DS-32 — Измерить чувствительность эвристик, порогов и tie-break

**Приоритет:** P1

**Основание:** FRAG-002, FRAG-003, FRAG-009; H-013 и H-015; hard-coded weights/keywords/thresholds определяют browser cost, provider selection и media winner.

**Что делаем:** для classifier, CostPlanner, seed intent и media ranking строим table-driven sensitivity matrix для `threshold-ε/threshold/threshold+ε`, весов `±1/5/10%`, equal/near-equal scores, permutation и добавления neutral candidate. Сначала документируем допустимые discontinuities; конфигурируемым делаем только параметр с доказанной потребностью изменения. Для равных score вводим предметный deterministic tie-break.

**Где делаем:** `scraper/acquisition/page_classifier.py`, `control/planner.py`, `discovery/seed_finder.py`, `media_finder.py`, соответствующие unit tests и capability documentation.

**Почему:** небольшая лексическая или численная вариация сейчас способна переключить дорогую стратегию или полностью поменять выбранный источник.

**Класс хрупкости:** `FRAG-HEURISTIC`, `FRAG-BOUNDARY`, `FRAG-ORDER`, `FRAG-NUMERIC`, `FRAG-COMPLEXITY`.

**Как проверить:** decision/ranking diff на sensitivity corpus объясним; permutation не меняет winner при одинаковом множестве кандидатов; neutral candidate не меняет существующие scores; каждое намеренное пороговое переключение имеет два граничных теста и rationale.

**Regression test:** минимальные `reaction`, equal-score A/B и inverted min/max cases обязательны; новые winner flips сохраняются как parameterized cases.

**Готово когда:** у каждого magic constant есть источник и boundary test, а небольшое изменение входа не вызывает недокументированный скачок поведения.

### DS-33 — Найти complexity cliffs и худшие реалистичные входы

**Приоритет:** P2

**Основание:** линейный scan всех SimHash на каждый документ, повторная сортировка frontier, `list.pop(0)`, последовательные provider/media/PDF запросы и full-body buffering.

**Что делаем:** совместно с DS-25 измеряем `N=0/1/2/10²/10³/10⁴`, all-duplicates, all-equal priority, one huge document, thousands of small objects, long-chain crawl и slow/partial responses. Сначала фиксируем practical break point по latency, memory, event-loop lag и requests; алгоритм меняем только при доказанном cliff. Для fast path создаём простую медленную reference implementation и проверяем equivalence.

**Где делаем:** `tests/performance`, `deduplicator.py`, `scheduler.py`, `search_pipeline.py`, `media_downloader.py`, discovery/provider adapters; benchmark job из DS-25.

**Почему:** Big-O предположительно неблагоприятен в нескольких местах, но оптимизация без практической границы будет преждевременной.

**Класс хрупкости:** `FRAG-COMPLEXITY`, `FRAG-SCALABILITY`, `FRAG-DEPENDENCY`, `FRAG-RECOVERY`.

**Как проверить:** baseline хранит median/p95, peak RSS, request count и event-loop lag; doubling ratio выявляет смену режима; PR gate сравнивает только стабильные deterministic benchmarks, шумные сетевые сценарии запускаются scheduled/manual.

**Regression test:** отдельные adversarial cases для repeated SimHash, equal-priority frontier, oversized chunked body и long-chain queue; correctness всегда сравнивается с reference model.

**Готово когда:** для каждого critical path известна практическая граница, config не позволяет незаметно её превысить, а оптимизация сохраняет результат reference implementation.

### DS-34 — Ввести targeted mutation gate и закрывать FRAG только после повторного индекса

**Приоритет:** P2

**Основание:** 462 lint findings и 61% coverage не показывают, различают ли тесты `>`/`>=`, success/failure, one/two retries и boundary constants.

**Что делаем:** запускаем targeted mutation testing только для top-10 pure/control modules после зелёных regression/property/stateful suites. Приоритетные мутации: `>/<`, `>=/<=`, `and/or`, `0/1`, `N/N+1`, success/error return, удаление validation и retry branch. Surviving mutant получает FRAG/MUT ID; production code не меняется ради metric, если mutant эквивалентен — это доказывается и исключение документируется. После каждого hardening пересчитываем FI и область устойчивости.

**Где делаем:** dev tooling/CI manual или scheduled job, `canonicalizer.py`, `page_classifier.py`, `planner.py`, `scheduler.py`, `budget.py`, `rate_limiter.py`, `deduplicator.py`, archive chunker и их tests; результат — в существующем `AUDIT_REPORT.md`.

**Почему:** line coverage может оставаться высокой при полном отсутствии спецификации критической развилки.

**Класс хрупкости:** все классы, в первую очередь `FRAG-BOUNDARY`, `FRAG-RETRY`, `FRAG-INVARIANT`, `FRAG-RECOVERY`.

**Как проверить:** targeted mutation score не ниже 80%; ни один surviving non-equivalent mutant не меняет security boundary, state transition, limit, retry count или error outcome; job воспроизводим с pinned tool version.

**Regression test:** каждый уничтоженный meaningful mutant связан с существующим test либо порождает минимальный новый test; дублирующие тесты не добавляются только ради процента.

**Готово когда:** FRAG закрывается только при зелёном counterexample, relevant property/state model, fault test при внешней зависимости, отсутствии critical surviving mutants и пересчитанном FI с объяснением остаточного риска.

## 7. Порядок выполнения

| Этап | Пункты | Результат этапа |
| --- | --- | --- |
| A. Правда, доказательства и безопасность | DS-01…DS-08, DS-27, DS-28 | честная поверхность, утверждённые контракты, минимальный corpus и закрытые сетевые/API границы |
| B. Один устойчивый рабочий путь | DS-09…DS-15, DS-29…DS-31 | ограниченный pipeline с properties, state model и безопасной деградацией |
| C. Удаление лишнего и стабилизация решений | DS-16…DS-22, DS-32 | нет demo-функций и недокументированных heuristic flips |
| D. Эксплуатационные границы | DS-23…DS-25, DS-33, DS-34 | известны practical cliffs, mutation strength и измеримая производительность |
| E. Release | DS-26 | документация и capability surface подтверждены полным regression gate |

Пункты выполняются небольшими отдельными коммитами. Каждый коммит обязан добавлять или обновлять проверку из поля «Как проверить». Массовое перемещение файлов не совмещается с изменением поведения: сначала characterization/contract, затем минимальный counterexample, затем локальное исправление и только после этого удаление старого пути. PASS 6–8 запускаются лишь там, где RiskScore/evidence показывают высокую ожидаемую ценность; весь репозиторий не подвергается бесконечному fuzz/mutation запуску.

## 8. Definition of Done для stable release

- Все mandatory CI jobs зелёные на Python 3.11/3.12.
- Unit suite полностью герметична; browser/provider/storage tests отделены и воспроизводимы.
- Нет hard-coded/demo результатов в публичных интерфейсах.
- Один application service обслуживает CLI, REST и MCP.
- Реальные requests проходят SSRF, robots, rate, budget, timeout и cancellation policies.
- Каждый job имеет терминальный статус, причины partial/failure и управляемый workspace.
- Default install не требует PostgreSQL, Redis, Qdrant, MinIO, Chromium или OCR.
- Документация не заявляет возможность без соответствующего contract/integration test.
- Показатели latency, peak memory и request count имеют зафиксированный baseline.
- Clean-room установка, wheel smoke, container health и MCP handshake проходят автоматически.
- Для top-10 утверждены contract, invariants, hidden assumptions, boundary/order/state/time/retry/failure semantics.
- Все подтверждённые P0/P1 FRAG имеют минимальный regression test; неподтверждённые риски явно остаются hypotheses.
- Property tests сохраняют shrunk examples, stateful tests совпадают с reference model, fault tests проверяют состояние после ошибки.
- Нет surviving meaningful mutants на security boundary, state transitions, budgets, retry и error outcomes; targeted mutation score не ниже 80%.
- После hardening пересчитан Fragility Index; остаточный `31+` допускается только с явным risk acceptance и ограничением public capability.
