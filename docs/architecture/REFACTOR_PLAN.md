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

## 4. Целевая архитектура без нового оверинжиниринга

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

## 5. План работ

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

## 6. Порядок выполнения

| Этап | Пункты | Результат этапа |
| --- | --- | --- |
| A. Правда и безопасность | DS-01…DS-08 | честная поверхность, зелёный герметичный baseline, закрытые сетевые/API границы |
| B. Один рабочий путь | DS-09…DS-15 | ограниченный и объяснимый research/crawl pipeline без утечек |
| C. Удаление лишнего | DS-16…DS-22 | нет demo-функций, параллельных приложений и неработающих интерфейсов |
| D. Эксплуатация | DS-23…DS-26 | измеримая производительность, безопасный контейнер и проверяемый release |

Пункты выполняются небольшими отдельными коммитами. Каждый коммит обязан добавлять или обновлять проверку из поля «Как проверить». Массовое перемещение файлов не совмещается с изменением поведения: сначала characterization tests, затем изменение контракта, затем удаление старого пути.

## 7. Definition of Done для stable release

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
