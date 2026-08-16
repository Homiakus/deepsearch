# DeepSearch — подробный план улучшения алгоритма поиска и работы с источниками

**Статус:** implementation roadmap  
**Ветка:** `main`  
**Связан с:**
- `docs/architecture/IMPROVEMENT_PLAN_AXIOM.md`
- `docs/architecture/RUST_BROWSER_EXECUTION_PLAN.md`
- `docs/architecture/REFACTOR_PLAN.md`

**Область:** query understanding / source discovery / ranking / crawl frontier / source quality / deduplication / hybrid retrieval / reranking / evidence selection / iterative research / stopping criteria

---

# 0. Цель

Цель — превратить DeepSearch из breadth-first crawler с набором discovery providers в evidence-driven research search engine, который:

1. понимает, **что именно нужно доказать или выяснить**;
2. разбивает сложный запрос на исследовательские подзадачи;
3. генерирует несколько поисковых формулировок и стратегий;
4. получает большой пул кандидатов из разных источников;
5. ранжирует URL до загрузки;
6. загружает только наиболее перспективные страницы;
7. отбрасывает мусор, дубли, thin content и нерелевантные документы;
8. выполняет dense + sparse retrieval по извлечённым данным;
9. применяет reranking и diversity selection;
10. строит evidence graph;
11. измеряет, какие части исследовательской задачи уже покрыты;
12. ищет именно недостающую информацию;
13. прекращает поиск не по фиксированному `max_pages`, а по достаточности evidence, diminishing information gain и hard budget limits.

Главный переход:

```text
СЕЙЧАС

query
  ↓
hard-coded category
  ↓
несколько provider API
  ↓
список URL
  ↓
FIFO crawl
  ↓
первые 10 ссылок со страницы
  ↓
max_pages


ЦЕЛЬ

query
  ↓
ResearchIntent
  ↓
ResearchGoalGraph
  ↓
QueryStrategySet
  ↓
parallel discovery
  ↓
CandidatePool
  ↓
pre-ranking
  ↓
RankedFrontier
  ↓
acquisition
  ↓
quality / relevance / dedup gates
  ↓
chunk retrieval
  ↓
hybrid fusion
  ↓
reranking
  ↓
diversity + information gain
  ↓
EvidenceGraph
  ↓
CoverageAnalyzer
  ├── gaps → follow-up search
  └── sufficient → synthesis
```

---

# 1. Подтверждённые проблемы текущего search path

## 1.1 Query intent определяется keyword-списками

Текущий `scraper/discovery/seed_finder.py` классифицирует запрос через набор `any(k in q_lower ...)` для medical/science/news/engineering.

Это создаёт:

- слабую переносимость на новые домены;
- ложные классификации;
- отсутствие entity extraction;
- отсутствие временных ограничений;
- отсутствие language strategy;
- отсутствие evidence requirements;
- отсутствие decomposition сложных вопросов.

## 1.2 Provider order фактически является ranking

`discover_diverse_seeds()` просто добавляет URL в общий список, а затем делает exact dedup preserving insertion order.

Нет явного scoring по:

- query relevance;
- subgoal relevance;
- source type;
- authority;
- freshness;
- diversity;
- estimated acquisition cost;
- probability of successful extraction.

## 1.3 Link expansion недетерминирован и не ранжируется

`scraper/discovery/links.py` складывает ссылки в `set`, затем возвращает `list(set)`.

`scraper/pipeline/search_pipeline.py` затем берёт:

```python
for link in discovered_links[:10]:
    ...
```

То есть следующие URL выбираются без relevance scoring и без сохранения DOM order.

Это P0-дефект.

## 1.4 Основной pipeline не использует `RequestFrontier`

Хотя `scraper/control/scheduler.py` уже содержит priority queue semantics и retry lifecycle, `DeepSearchPipeline.execute()` использует обычный список и `pop(0)`.

Следствие:

- фактический обход — FIFO/BFS;
- priority formula не применяется;
- retry frontier не применяется;
- стоимость и релевантность не влияют на очередность.

## 1.5 URL отмечается visited до успешной обработки

В текущем pipeline canonical URL попадает в `visited_canonical` до acquisition.

При transient failure URL фактически теряется для данного research run.

## 1.6 `content_quality` сейчас означает почти только отсутствие block-page

`scraper/acquisition/page_classifier.py` вычисляет `content_quality ≈ 1 - block_score`.

Это не определяет:

- topical relevance;
- useful information density;
- duplication;
- source authority;
- evidence value;
- extraction completeness.

## 1.7 Нет полноценного relevance filter после acquisition

Успешно загруженный документ практически сразу добавляется в `acquired_results`.

Нет обязательного decision layer:

```text
RELEVANT
PARTIALLY_RELEVANT
OFF_TOPIC
DUPLICATE
LOW_VALUE
SPAM
NAVIGATION
BLOCK_PAGE
```

## 1.8 Dedup фактически URL-level

`canonicalize_url()` полезен, но не решает:

- одинаковый контент под разными URL;
- print/mobile/AMP mirrors;
- syndicated copies;
- minor revisions;
- semantic duplicates;
- repeated claims from one primary source.

## 1.9 Retrieval layer не реализован

`scraper/storage/vector_store.py` содержит placeholders, а `scraper/search/search_engine.py` возвращает fixture-like результаты.

Поэтому фактически отсутствуют:

- dense retrieval;
- sparse retrieval;
- fusion;
- reranking;
- metadata filtering;
- source-aware ranking.

## 1.10 RAG chunks не имеют реального relevance score

`scraper/storage/archive_exporter.py` присваивает одинаковый `relevance_score` всем chunks.

Это необходимо удалить при переходе на реальный retrieval pipeline.

---

# 2. Архитектурные принципы нового поиска

## 2.1 Не смешивать discovery, crawling и retrieval

Разделить систему на три уровня:

```text
Discovery
= где потенциально искать

Acquisition
= как получить документ

Retrieval
= какие уже полученные документы/chunks полезнее всего
```

## 2.2 Не использовать один score для всех стадий

Разные стадии оптимизируют разные цели:

```text
Discovery ranking       → recall + cheap precision
Acquisition priority    → expected utility / cost
Document acceptance     → useful evidence probability
Passage retrieval       → recall
Reranking               → precision
Evidence selection      → novelty + coverage + authority
```

## 2.3 Hard filters и soft penalties должны быть раздельными

Hard reject:

- disallowed scheme;
- SSRF/security violation;
- known malware domain;
- exact duplicate;
- unsupported content type;
- explicit scope violation.

Soft demotion:

- low authority;
- old content;
- high expected cost;
- duplicate-like content;
- low novelty;
- low domain diversity.

## 2.4 Search engine должен быть evidence-centric

URL и document — промежуточные сущности.

Верхнеуровневая единица качества:

```text
Claim
  ↓
Evidence
  ↓
Source
```

---

# 3. Целевые сущности и контракты

## 3.1 `ResearchIntent`

Добавить:

```text
scraper/research/intent.py
```

Модель:

```python
class ResearchIntent(BaseModel):
    original_query: str
    normalized_query: str
    task_type: str
    domain: str | None
    entities: list[Entity]
    constraints: list[Constraint]
    languages: list[str]
    freshness_requirement: FreshnessRequirement
    source_preferences: list[SourcePreference]
    evidence_requirements: EvidenceRequirements
    ambiguity: float
```

`FreshnessRequirement`:

```text
NONE
LOW
MEDIUM
HIGH
REALTIME
```

## 3.2 `ResearchGoalGraph`

Добавить:

```text
scraper/research/goals.py
```

Структура:

```text
ResearchGoal
├── id
├── question
├── importance
├── dependencies
├── required_evidence_types
├── status
├── coverage
└── unresolved_conflicts
```

## 3.3 `SearchQueryVariant`

Добавить:

```text
scraper/search/query_models.py
```

Поля:

```text
query
language
provider_hint
goal_id
query_type
freshness
required_source_type
priority
```

`query_type`:

```text
LEXICAL
SEMANTIC
ENTITY
EXACT
DOMAIN_SPECIFIC
PRIMARY_SOURCE
CONTRADICTION
FOLLOW_UP
```

## 3.4 `SourceCandidate`

Добавить:

```text
scraper/search/candidates.py
```

Поля:

```text
url
canonical_url
title
snippet
provider
provider_rank
source_type
published_at
domain
goal_ids
query_variants
lexical_score
semantic_score
authority_prior
freshness_score
novelty_prior
expected_cost
expected_extractability
risk_score
```

## 3.5 `DocumentAssessment`

Добавить:

```text
scraper/search/document_assessment.py
```

Поля:

```text
relevance
quality
authority
freshness
novelty
extractability
spam_probability
navigation_probability
duplicate_probability
evidence_density
accepted
reject_reason
```

## 3.6 `EvidenceCandidate`

Добавить:

```text
scraper/evidence/models.py
```

Поля:

```text
claim_id
goal_id
source_id
chunk_id
stance
relevance
authority
freshness
novelty
information_gain
confidence
citation_span
```

---

# PHASE SI0 — benchmark и наблюдаемость поиска

## DS-SI00. Создать search benchmark corpus

### Что делаем

До изменения ranking создать воспроизводимый benchmark текущего поведения.

### Где

Добавить:

```text
benchmarks/search/
├── queries.jsonl
├── query_groups.yaml
├── relevant_urls.jsonl
├── expected_evidence.jsonl
├── source_quality.jsonl
├── run.py
├── metrics.py
└── reports/
```

### Набор запросов

Минимум 200, целевой размер 500+.

Группы:

- factual;
- technical;
- medical;
- engineering;
- current information;
- multi-hop;
- comparative;
- contradiction-seeking;
- multilingual RU/EN;
- ambiguous;
- niche terminology;
- primary-source-required;
- user-forum-required;
- long-tail.

### Метрики

```text
SeedRecall@K
URLRecall@K
URLnDCG@K
UsefulDocumentPrecision
UsefulDocumentRecall
EvidenceRecall
EvidencePrecision
SourceDiversity
PrimarySourceRate
NearDuplicateRatio
PagesPerSolvedQuery
UsefulTokensPerFetchedMB
TimeToFirstUsefulEvidence
CostPerSolvedQuery
```

### Проверка

Текущий pipeline должен иметь baseline report, даже если показатели низкие.

---

## DS-SI01. Добавить search trace

### Где

Добавить:

```text
scraper/search/trace.py
```

Изменить:

- `scraper/discovery/seed_finder.py`
- `scraper/pipeline/search_pipeline.py`
- будущий ranked frontier
- retrieval/reranker

### Trace events

```text
QUERY_ANALYZED
GOAL_CREATED
QUERY_VARIANT_CREATED
PROVIDER_CALLED
CANDIDATE_DISCOVERED
CANDIDATE_DEDUPED
CANDIDATE_SCORED
CANDIDATE_QUEUED
CANDIDATE_REJECTED
DOCUMENT_ACCEPTED
DOCUMENT_REJECTED
PASSAGE_RETRIEVED
PASSAGE_RERANKED
EVIDENCE_ACCEPTED
GOAL_COVERAGE_CHANGED
STOP_DECISION
```

### DoD

Для любого research run можно объяснить, почему URL был:

- найден;
- повышен;
- понижен;
- загружен;
- пропущен;
- отброшен.

---

# PHASE SI1 — Query Intelligence

## DS-SI02. Убрать hard-coded intent classification из основного path

### Где

- `scraper/discovery/seed_finder.py`
- новый `scraper/research/intent.py`

### Что делаем

Keyword rules оставить только как fallback heuristic.

Основной path должен получать структурированный `ResearchIntent`.

### Проверка

Тесты на запросы, которые не содержат известных keyword-маркеров, но корректно классифицируются по смыслу/структуре.

---

## DS-SI03. Реализовать deterministic query normalization

### Где

```text
scraper/research/query_normalizer.py
```

### Делать

- Unicode normalization;
- whitespace normalization;
- сохранение исходного текста;
- извлечение quoted phrases;
- распознавание identifiers;
- распознавание version-like tokens;
- units;
- dates;
- product/model numbers;
- acronyms.

### Важно

Нельзя stem/lemmatize оригинальный query destructively.

### Проверка

`NXOpen UF_DRAW 2512`, DOI, ГОСТ, артикулы, PMID и химические обозначения сохраняются без потери формы.

---

## DS-SI04. Реализовать entity extraction

### Где

```text
scraper/research/entities.py
```

### Entity classes

```text
PERSON
ORGANIZATION
PRODUCT
MODEL
VERSION
STANDARD
PAPER
DOI
PMID
CHEMICAL
DISEASE
LOCATION
DATE
SOFTWARE_API
OTHER_IDENTIFIER
```

### Проверка

Entities становятся search features и не смешиваются с обычными tokens.

---

## DS-SI05. Реализовать Research Goal decomposition

### Где

```text
scraper/research/decomposer.py
scraper/research/goals.py
```

### Принцип

Не дробить простой вопрос искусственно.

Создавать decomposition только если:

- несколько независимых аспектов;
- требуется сравнение;
- требуется причина + доказательство;
- multi-hop dependency;
- разные source types;
- explicit multiple questions.

### Проверка

Для простого factual query создаётся 1 goal.
Для сложного research query — несколько связанных goals.

---

## DS-SI06. Ввести evidence requirements per goal

### Примеры

Medical:

```text
prefer:
  guideline
  regulator
  systematic_review
  meta_analysis
  RCT
```

Software API:

```text
prefer:
  official_docs
  source_code
  release_notes
```

User experience:

```text
prefer:
  user_forum
  issue_tracker
  discussion
```

### Проверка

Одинаковый domain не приводит к одинаковому authority prior для разных типов вопросов.

---

## DS-SI07. Генерация query variants

### Где

```text
scraper/search/query_generator.py
```

### Для каждого goal генерировать ограниченный набор

- canonical query;
- exact entity query;
- synonyms/terminology variant;
- English variant при RU query;
- Russian variant при необходимости;
- source-specific query;
- primary-source query;
- contradiction query;
- recency query.

### Ограничение

Не создавать query explosion.

Ввести budget:

```text
max_queries_per_goal
max_total_query_variants
```

### Проверка

Каждый variant имеет причину и `goal_id`.

---

# PHASE SI2 — Provider architecture

## DS-SI08. Превратить `seed_finder.py` в provider registry

### Добавить

```text
scraper/discovery/providers/
├── base.py
├── registry.py
├── wikipedia.py
├── arxiv.py
├── pubmed.py
├── europe_pmc.py
├── web_search.py
├── github.py
└── ...
```

### Contract

```python
class DiscoveryProvider(Protocol):
    descriptor: ProviderDescriptor
    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]: ...
```

### `ProviderDescriptor`

```text
name
supported_domains
supported_source_types
languages
freshness_capability
cost_class
rate_limit_class
```

### DoD

`discover_diverse_seeds()` перестаёт содержать provider-specific network logic.

---

## DS-SI09. Запускать providers параллельно

### Что делаем

Независимые providers должны выполняться через bounded concurrency.

### Требования

- timeout per provider;
- partial success;
- cancellation;
- rate limits;
- trace.

### Проверка

Падение одного provider не блокирует весь discovery stage.

---

## DS-SI10. Добавить provider selection policy

### Где

```text
scraper/discovery/provider_policy.py
```

### Вход

- `ResearchIntent`;
- goal;
- evidence requirements;
- freshness;
- language;
- historical provider quality/cost.

### Выход

Ранжированный список provider requests.

### Не делать

`if medical -> PubMed` как единственное правило.

---

## DS-SI11. Добавить provider result normalization

Все providers должны возвращать одинаковый `SourceCandidate`.

Нормализовать:

- URL;
- title;
- snippet;
- publication date;
- author;
- source type;
- provider rank;
- provider metadata.

---

# PHASE SI3 — Candidate normalization и pre-ranking

## DS-SI12. Исправить link extraction: убрать `set -> list`

### Где

`scraper/discovery/links.py`

### Что делаем

Возвращать `DiscoveredLink`:

```text
url
anchor_text
surrounding_text
dom_position
section_heading
rel
is_navigation
is_footer
is_sidebar
```

Сохранять DOM order.

### Проверка

Порядок одинаков для одинакового HTML во всех запусках.

---

## DS-SI13. Добавить LinkContextExtractor

### Где

```text
scraper/discovery/link_context.py
```

### Извлекать

- anchor text;
- ближайший paragraph;
- heading ancestry;
- semantic section;
- nav/footer/sidebar markers;
- link type.

### Цель

Ссылку ранжировать не только по URL string.

---

## DS-SI14. Создать `CandidateNormalizer`

### Где

```text
scraper/search/candidate_normalizer.py
```

### Делать

- canonical URL;
- normalized domain;
- normalized title;
- normalized date;
- provider provenance merge;
- goal merge;
- query-variant merge.

Один URL, найденный 5 providers, должен стать одним candidate с несколькими provenance signals.

---

## DS-SI15. Добавить exact candidate dedup до crawl

Ключ:

```text
canonical_url
```

Но сохранять:

```text
found_by_providers[]
matched_queries[]
goal_ids[]
```

Provider agreement должен быть positive signal, а не потерянной информацией.

---

## DS-SI16. Реализовать cheap lexical pre-ranker

### Где

```text
scraper/search/prerank/lexical.py
```

### Features

- title match;
- exact identifier match;
- phrase match;
- anchor match;
- snippet match;
- entity overlap;
- query term coverage.

### Важно

Identifier match должен иметь больший вес, чем generic token match.

---

## DS-SI17. Реализовать semantic candidate pre-ranker

### Где

```text
scraper/search/prerank/semantic.py
```

### Векторизовать

```text
query/goal
vs
candidate title + snippet + anchor context
```

### Ограничение

Не выполнять дорогой cross-encoder на тысячах URL.

---

## DS-SI18. Добавить source-type prior

### Где

```text
scraper/search/source_policy.py
```

Не общий `domain_score`, а:

```text
AuthorityPrior(query_type, source_type, domain)
```

### Пример

Software API:

```text
official docs > source repository > issue tracker > blog
```

User complaints:

```text
issue tracker / forum > marketing docs
```

---

## DS-SI19. Реализовать freshness score

### Где

```text
scraper/search/freshness.py
```

### Вход

- query freshness requirement;
- publication/update date;
- source type;
- current time.

### Не делать

Автоматически считать новое лучше старого.

---

## DS-SI20. Добавить expected acquisition cost

### Сигналы

- historical domain latency;
- HTTP success probability;
- JS requirement probability;
- browser escalation probability;
- document size;
- provider metadata.

### Связь

Использовать данные Rust acquisition worker/backend planner после его внедрения.

---

## DS-SI21. Создать `CandidateFeatureVector`

### Где

```text
scraper/search/features.py
```

Поля:

```text
lexical_relevance
semantic_relevance
identifier_match
provider_rank
provider_agreement
authority_prior
freshness
expected_novelty
expected_extractability
expected_cost
risk
source_diversity_bonus
depth_penalty
```

Не прятать всё сразу в один float.

---

## DS-SI22. Создать `CandidateRanker`

### Где

```text
scraper/search/ranking/candidate_ranker.py
```

### Первый этап

Deterministic weighted model.

### Позже

Learning-to-rank допускается только после накопления benchmark/traces.

### Проверка

Ranker должен быть объяснимым:

```text
score breakdown
```

для каждого candidate.

---

# PHASE SI4 — Ranked Frontier

## DS-SI23. Заменить FIFO queue на `RankedFrontier`

### Где

Добавить:

```text
scraper/control/ranked_frontier.py
```

Мигрировать логику из:

- `scraper/control/scheduler.py`
- `scraper/pipeline/search_pipeline.py`

### Priority objective

Не фиксировать только:

```text
relevance + depth - cost
```

Использовать `CandidateFeatureVector` + policy.

### DoD

`DeepSearchPipeline` больше не использует `queued_urls.pop(0)`.

---

## DS-SI24. Разделить states `discovered`, `attempted`, `accepted`

URL не должен считаться окончательно обработанным после простого dequeue.

Состояния:

```text
DISCOVERED
QUEUED
LEASED
ACQUIRING
ACQUIRED
ASSESSING
ACCEPTED
REJECTED
RETRY
DEAD
```

---

## DS-SI25. Исправить retry semantics

### Требование

Transient failure не переводит URL в permanently visited.

### Failure classes

```text
TIMEOUT
DNS
RATE_LIMIT
BLOCKED
TEMPORARY_NETWORK
INVALID_URL
PERMANENT_HTTP
SECURITY_REJECT
```

### Проверка

429/timeout → retry policy.
404/security reject → no retry.

---

## DS-SI26. Добавить host/domain fairness

Нельзя позволять одному domain занять весь top frontier.

Добавить:

```text
max_active_per_domain
domain_diversity_window
same_domain_penalty
```

### Цель

Повысить независимость источников.

---

## DS-SI27. Добавить goal-aware scheduling

Frontier должен видеть `goal_id`.

Не допускать ситуацию, когда 90% budget ушло на один subgoal, а остальные не исследованы.

Ввести:

```text
coverage deficit bonus
```

---

# PHASE SI5 — post-acquisition document assessment

## DS-SI28. Разделить AcquisitionQuality и DocumentQuality

### Где

- `scraper/acquisition/page_classifier.py`
- новый `scraper/search/document_quality.py`

### `AcquisitionQuality`

- page loaded;
- expected DOM rendered;
- no block page;
- non-empty content;
- network/render completeness.

### `DocumentQuality`

- topical relevance;
- evidence density;
- spam likelihood;
- navigation ratio;
- boilerplate ratio;
- authority;
- freshness;
- extractability.

---

## DS-SI29. Реализовать `DocumentRelevanceEvaluator`

### Где

```text
scraper/search/document_relevance.py
```

### Stage 1 cheap

- title;
- headings;
- extracted main text preview;
- entities;
- goal terms.

### Stage 2 optional expensive

Cross-encoder/reranker для borderline cases.

### Output

```text
HIGH
MEDIUM
LOW
OFF_TOPIC
```

---

## DS-SI30. Реализовать boilerplate/navigation filter

### Где

```text
scraper/extraction/content_filter.py
```

### Метрики

- main text ratio;
- link density;
- repeated nav text;
- footer/header ratio;
- sentence density;
- unique token ratio.

### Reject/demote

Directory pages и tag pages могут быть полезны для discovery, но не должны автоматически идти в evidence corpus.

---

## DS-SI31. Реализовать spam/thin-content classifier

### Сигналы

- extreme ad/link density;
- templated repetition;
- keyword stuffing;
- low unique content;
- copied snippets;
- suspicious redirect chain.

### Результат

Soft penalty + optional hard reject threshold.

---

# PHASE SI6 — многослойный dedup

## DS-SI32. D0 — URL canonical dedup

Оставить `canonicalize_url()`, но расширить tests.

Добавить cases:

- AMP;
- print versions;
- trailing slash;
- tracking params;
- duplicated query order;
- mobile subdomains where safe.

---

## DS-SI33. D1 — exact content hash

### Где

```text
scraper/normalization/content_hash.py
```

Хешировать normalized extracted main content.

Хранить SHA-256.

---

## DS-SI34. D2 — near-duplicate fingerprint

### Где

```text
scraper/normalization/near_duplicate.py
```

Рассмотреть:

- SimHash;
- MinHash;
- shingles.

### Цель

Обнаруживать syndicated/print/minor-edit copies дешево.

---

## DS-SI35. D3 — semantic duplicate detection

После embeddings:

```text
cosine / dense similarity
```

использовать только как более дорогой слой.

### Не делать

Не удалять похожие документы автоматически, если они представляют независимые источники.

---

## DS-SI36. Ввести `SourceLineage`

### Где

```text
scraper/search/source_lineage.py
```

Отличать:

```text
same content
same publisher
syndicated copy
summary of source
independent corroboration
primary source
```

Это критично для evidence confidence.

---

# PHASE SI7 — реальный retrieval index

## DS-SI37. Реализовать Qdrant collection schema

### Где

- `scraper/storage/vector_store.py`
- `scraper/search/index_schema.py`

### Payload

```text
chunk_id
document_id
source_id
url
canonical_url
domain
title
heading_path
text
language
published_at
source_type
authority_score
goal_ids
content_hash
near_dup_cluster
```

### Vectors

Минимум:

```text
dense
sparse
```

Опционально позже:

```text
late_interaction
```

---

## DS-SI38. Реализовать dense embeddings

### Где

```text
scraper/search/embeddings/dense.py
```

### Требования

- batch embedding;
- model version in metadata;
- deterministic preprocessing;
- multilingual support;
- cache by content hash.

### Benchmark candidates

Сравнить по собственному корпусу, не выбирать по leaderboard вслепую.

---

## DS-SI39. Реализовать sparse retrieval

### Где

```text
scraper/search/embeddings/sparse.py
```

Поддержать lexical/sparse representation.

Цель — exact identifiers, API names, standards, codes, rare terms.

---

## DS-SI40. Реализовать hybrid retrieval

### Где

```text
scraper/search/retrieval/hybrid.py
```

Pipeline:

```text
dense top-N
+
sparse top-N
↓
fusion
↓
merged candidates
```

Начать с RRF/weighted RRF.

### Проверка

Identifier-heavy и semantic queries должны выигрывать от разных branches.

---

## DS-SI41. Реализовать metadata filters

Фильтры:

- date range;
- language;
- source type;
- domain;
- goal;
- primary/secondary source;
- duplicate cluster.

---

# PHASE SI8 — reranking

## DS-SI42. Добавить reranker abstraction

### Где

```text
scraper/search/rerank/base.py
scraper/search/rerank/cross_encoder.py
scraper/search/rerank/late_interaction.py
```

### Contract

```text
query/goal + candidate passages → ordered passages + calibrated scores
```

---

## DS-SI43. Benchmark reranker models

Сравнить минимум:

- lightweight cross-encoder;
- Qwen-family reranker;
- ColBERT-like late interaction;
- no-rerank baseline.

Метрики:

```text
nDCG@10
MRR
EvidenceRecall@10
latency
RAM/VRAM
cost/query
```

### Gate

Reranker не включается production-wide без измеримого выигрыша.

---

## DS-SI44. Добавить score calibration

Нельзя сравнивать raw dense score и reranker score напрямую.

Хранить отдельно:

```text
retrieval_score
fusion_score
rerank_score
```

---

# PHASE SI9 — diversity и novelty

## DS-SI45. Реализовать MMR/diversity selector

### Где

```text
scraper/search/selection/diversity.py
```

### Цель

Не отдавать top-N из одного near-duplicate cluster/domain.

### Features

- semantic redundancy;
- same-domain redundancy;
- source-lineage redundancy;
- goal coverage.

---

## DS-SI46. Ввести source diversity constraints

Пример policy:

```text
для high-confidence factual claim:
  минимум 2 независимых source lineages
```

Не применять механически к задачам, где первичный источник достаточен.

---

# PHASE SI10 — Source Authority

## DS-SI47. Создать SourceType taxonomy

### Где

```text
scraper/search/source_types.py
```

Пример:

```text
OFFICIAL_DOC
PRIMARY_RESEARCH
SYSTEMATIC_REVIEW
META_ANALYSIS
GUIDELINE
REGULATOR
NEWS_WIRE
NEWS_MEDIA
GOVERNMENT
STANDARD
SOURCE_CODE
ISSUE_TRACKER
FORUM
BLOG
WIKI
AGGREGATOR
MARKETING
UNKNOWN
```

---

## DS-SI48. Создать `AuthorityEvaluator`

### Где

```text
scraper/search/authority.py
```

### Не делать

Глобальный список `good domains`.

### Делать

```text
Authority(query intent, goal, source type, domain, provenance)
```

### Signals

- source type;
- primary-source status;
- publisher identity;
- citation/reference presence;
- author metadata;
- domain history;
- reproducibility signals;
- provider metadata.

---

## DS-SI49. Разделить authority и relevance

Высокоавторитетный нерелевантный документ не должен побеждать.

Низкоавторитетный, но уникальный user report не должен автоматически исчезать.

---

## DS-SI50. Ввести source trust history

### Где

```text
scraper/search/source_stats.py
```

Хранить наблюдаемые operational metrics:

```text
acquisition_success
extractability
block_rate
latency
content_dup_rate
```

Не смешивать operational reliability с epistemic authority.

---

# PHASE SI11 — Evidence layer

## DS-SI51. Создать Evidence Store

### Где

```text
scraper/evidence/
├── models.py
├── store.py
├── extractor.py
├── matcher.py
└── graph.py
```

### Сущности

```text
Claim
Evidence
Source
Relation
```

Relation:

```text
SUPPORTS
CONTRADICTS
QUALIFIES
DUPLICATES
DERIVED_FROM
```

---

## DS-SI52. Извлекать evidence spans с provenance

Каждый evidence object должен хранить:

- exact source URL;
- document id;
- chunk id;
- span offsets / quoted span reference;
- extraction timestamp;
- source metadata;
- retrieval path.

---

## DS-SI53. Реализовать claim/evidence matching

### Где

```text
scraper/evidence/matcher.py
```

Определять:

```text
support
contradiction
unrelated
uncertain
```

### Проверка

Противоречащий источник не должен быть отброшен как просто "low relevance".

---

## DS-SI54. Реализовать contradiction search

Для важных claims автоматически генерировать follow-up queries типа:

```text
<claim> criticism
<claim> not associated
<claim> failed to reproduce
<claim> controversy
```

Только когда это уместно для типа задачи.

---

# PHASE SI12 — Coverage и Information Gain

## DS-SI55. Реализовать Goal Coverage Analyzer

### Где

```text
scraper/research/coverage.py
```

Для каждого goal считать:

```text
coverage
number_of_independent_sources
source_type_coverage
contradiction_status
confidence
missing_evidence_types
```

---

## DS-SI56. Реализовать Evidence Sufficiency Policy

### Пример

```text
simple factual:
  one strong primary source may be sufficient

high-stakes medical:
  multiple high-quality independent sources

current event:
  primary statement + reputable reporting + freshness
```

Policy должна зависеть от task type.

---

## DS-SI57. Реализовать Information Gain scoring

### Где

```text
scraper/search/information_gain.py
```

Оценивать candidate не только по similarity, но и по ожидаемому улучшению ResearchGoalGraph.

Signals:

```text
new goal coverage
new source lineage
new source type
new entity/relation
new contradiction
new date/version
new quantitative evidence
```

---

## DS-SI58. Ввести redundancy penalty

Документ, повторяющий уже подтверждённые claims без новой provenance, должен терять priority.

---

# PHASE SI13 — Iterative search

## DS-SI59. Добавить Gap Analyzer

### Где

```text
scraper/research/gaps.py
```

### Output

```text
missing_goal
weakly_supported_claim
unresolved_contradiction
missing_primary_source
missing_recent_source
missing_alternative_explanation
```

---

## DS-SI60. Реализовать follow-up query generation

### Где

```text
scraper/search/followup.py
```

Query должен быть привязан к конкретному gap, а не повторять исходный query.

---

## DS-SI61. Ограничить research loops

Hard bounds:

```text
max_iterations
max_queries
max_pages
max_time
max_cost
```

Soft bounds:

```text
min_information_gain
coverage_target
```

---

## DS-SI62. Связать iterative search с Axiom ADGO

### Где

- `orchestrator/internal/plan/research.go`
- `orchestrator/internal/activities/search.go`

### Узлы

```text
AnalyzeQuery
PlanGoals
DiscoverCandidates
RankCandidates
AcquireBatch
AssessDocuments
IndexDocuments
RetrieveEvidence
EvaluateCoverage
PlanFollowup
```

`EvaluateCoverage` должен быть deterministic gate на основании persisted facts.

---

# PHASE SI14 — Stopping criteria

## DS-SI63. Убрать `max_pages` как основной критерий успеха

`max_pages` оставить hard budget guard.

Основной stop decision:

```text
coverage sufficient
AND critical contradictions resolved/recorded
AND evidence requirements satisfied
AND marginal information gain below threshold
```

---

## DS-SI64. Добавить explicit stop reasons

```text
SUFFICIENT_EVIDENCE
DIMINISHING_RETURNS
BUDGET_EXHAUSTED
TIME_EXHAUSTED
NO_MORE_CANDIDATES
USER_CANCELLED
BLOCKED_BY_POLICY
```

Это должно попадать в result/report.

---

# PHASE SI15 — Chunking и retrieval quality

## DS-SI65. Заменить fixed paragraph chunking на structure-aware chunking

### Где

- `scraper/storage/archive_exporter.py`
- новый `scraper/search/chunking.py`

### Использовать

- heading boundaries;
- paragraph boundaries;
- table boundaries;
- list boundaries;
- section metadata;
- parent-child context.

---

## DS-SI66. Добавить parent-child retrieval

Index smaller passages, но возвращать достаточный parent context.

Хранить:

```text
chunk_id
parent_section_id
document_id
heading_path
```

---

## DS-SI67. Не хранить fake relevance score

Удалить hard-coded `relevance_score=0.95`.

До retrieval score должен быть `None`/отсутствовать.

---

# PHASE SI16 — Search API

## DS-SI68. Переписать `SearchEngine`

### Где

`scraper/search/search_engine.py`

### API

```python
search_documents(...)
search_passages(...)
search_evidence(...)
```

### Pipeline

```text
query normalization
→ dense retrieval
→ sparse retrieval
→ fusion
→ rerank
→ diversity
→ source-aware filtering
```

Удалить synthetic `example.com` results.

---

## DS-SI69. Добавить explain mode

По каждому result возвращать опционально:

```text
why_retrieved
matched_terms
matched_entities
dense_rank
sparse_rank
fusion_rank
rerank_score
authority
freshness
novelty
dedup_cluster
```

---

# PHASE SI17 — Evaluation

## DS-SI70. Ввести offline ranking evaluation

Метрики:

```text
Recall@10/50/100
Precision@10
MRR
nDCG@10
MAP
EvidenceRecall
EvidencePrecision
```

---

## DS-SI71. Ввести source-quality evaluation

Метрики:

```text
PrimarySourceRate
IndependentSourceCount
SourceTypeDiversity
FreshnessErrorRate
DuplicateEvidenceRate
AuthorityCalibration
```

---

## DS-SI72. Ввести end-to-end research metrics

```text
ClaimCoverage
CriticalClaimCoverage
CitationPrecision
CitationCompleteness
ContradictionDiscoveryRate
TimeToFirstUsefulEvidence
UsefulEvidencePerPage
UsefulEvidencePerDollar
UsefulEvidencePerSecond
```

---

## DS-SI73. Добавить ablation benchmark

Сравнить:

```text
FIFO
vs ranked frontier

Dense only
vs Sparse only
vs Hybrid

Hybrid
vs Hybrid + reranker

Reranker
vs Reranker + diversity

Relevance
vs Relevance + information gain
```

Нельзя принимать архитектурные усложнения без измеримого выигрыша.

---

# PHASE SI18 — Learning-to-rank после накопления данных

## DS-SI74. Начать сохранять training traces

Сохранять feature vectors и outcomes:

```text
candidate features
selected/not selected
acquisition result
accepted/rejected
retrieval rank
became evidence?
closed goal?
```

Без raw secrets/private payloads.

---

## DS-SI75. Ввести offline LTR experiment

Только после достаточного количества labels/traces.

Возможные модели:

- logistic regression baseline;
- gradient boosted trees;
- LambdaMART-like ranking;
- learned utility model.

Не начинать с neural LTR.

---

## DS-SI76. Production LTR только через shadow rollout

Сначала:

```text
current deterministic ranker
+
shadow learned ranker
```

Сравнивать decisions и benchmark outcomes.

---

# PHASE SI19 — интеграция с Rust acquisition layer

## DS-SI77. Передавать Rust worker уже ranked AcquireBatch

ADGO/Rust worker не должен повторно решать research relevance.

Разделение:

```text
Search Intelligence
= какой URL полезнее исследованию

Rust Browser Planner
= каким backend дешевле/надёжнее получить этот URL
```

---

## DS-SI78. Использовать acquisition feedback как rank feature

Возвращать в search layer:

```text
domain_http_success
servo_success
chromium_needed
latency
bytes
block_probability
```

Но не смешивать с authority.

---

# PHASE SI20 — миграция legacy pipeline

## DS-SI79. Shadow-mode нового Search Intelligence

Старый pipeline продолжает исполнять crawl.

Новый ranker параллельно рассчитывает:

- какие URL выбрал бы;
- в каком порядке;
- что отбросил бы.

Сохранять comparison report.

---

## DS-SI80. Canary ranked frontier

Включить новый frontier для части test runs.

Rollback flag:

```text
SEARCH_FRONTIER_MODE=fifo|ranked
```

---

## DS-SI81. Перевести default path на ranked frontier

Только после benchmark gates.

Удалить `list.pop(0)` path из production execution.

---

## DS-SI82. Удалить legacy hard-coded discovery branching

После provider registry/query intent rollout удалить business logic из `seed_finder.py`.

Оставить thin compatibility wrapper или удалить модуль полностью после migration window.

---

# 4. Целевая структура файлов

```text
scraper/
├── research/
│   ├── intent.py
│   ├── entities.py
│   ├── query_normalizer.py
│   ├── decomposer.py
│   ├── goals.py
│   ├── coverage.py
│   └── gaps.py
│
├── discovery/
│   ├── link_context.py
│   └── providers/
│       ├── base.py
│       ├── registry.py
│       ├── wikipedia.py
│       ├── arxiv.py
│       ├── pubmed.py
│       ├── europe_pmc.py
│       ├── github.py
│       └── web_search.py
│
├── search/
│   ├── query_models.py
│   ├── query_generator.py
│   ├── candidates.py
│   ├── candidate_normalizer.py
│   ├── features.py
│   ├── source_types.py
│   ├── source_policy.py
│   ├── authority.py
│   ├── freshness.py
│   ├── source_lineage.py
│   ├── source_stats.py
│   ├── document_quality.py
│   ├── document_relevance.py
│   ├── information_gain.py
│   ├── followup.py
│   ├── trace.py
│   ├── chunking.py
│   ├── index_schema.py
│   │
│   ├── prerank/
│   │   ├── lexical.py
│   │   └── semantic.py
│   │
│   ├── ranking/
│   │   └── candidate_ranker.py
│   │
│   ├── embeddings/
│   │   ├── dense.py
│   │   └── sparse.py
│   │
│   ├── retrieval/
│   │   └── hybrid.py
│   │
│   ├── rerank/
│   │   ├── base.py
│   │   ├── cross_encoder.py
│   │   └── late_interaction.py
│   │
│   └── selection/
│       └── diversity.py
│
├── evidence/
│   ├── models.py
│   ├── store.py
│   ├── extractor.py
│   ├── matcher.py
│   └── graph.py
│
├── control/
│   └── ranked_frontier.py
│
└── normalization/
    ├── content_hash.py
    └── near_duplicate.py
```

---

# 5. Порядок реализации — рекомендуемая серия коммитов

Не реализовывать всё одной веткой/одним большим изменением.

Рекомендуемая последовательность:

```text
01  search benchmark + trace
02  ResearchIntent + query normalization
03  ResearchGoalGraph + decomposition
04  provider registry
05  SourceCandidate + normalization
06  deterministic link extraction + context
07  lexical pre-ranker
08  semantic pre-ranker
09  CandidateFeatureVector + explainable ranker
10  RankedFrontier
11  retry/visited state fix
12  DocumentQuality/Relevance gate
13  exact content hash
14  near-duplicate detection
15  SourceLineage
16  Qdrant schema
17  dense embeddings
18  sparse retrieval
19  hybrid fusion
20  reranker benchmark
21  diversity selector
22  SourceType + AuthorityEvaluator
23  Evidence Store
24  claim/evidence matcher
25  coverage analyzer
26  information gain
27  gap analysis + follow-up search
28  ADGO iterative research gate
29  stopping criteria
30  shadow migration
31  canary ranked frontier
32  remove legacy FIFO/hard-coded discovery path
```

После каждого шага `main` должен оставаться runnable.

---

# 6. Priority map

## P0 — исправить качество поиска до дальнейшего усложнения

```text
DS-SI00 benchmark
DS-SI01 trace
DS-SI02 intent boundary
DS-SI08 provider registry
DS-SI12 deterministic links
DS-SI16 lexical pre-rank
DS-SI21 feature vector
DS-SI22 candidate ranker
DS-SI23 ranked frontier
DS-SI24 state model
DS-SI25 retry semantics
DS-SI28 quality separation
DS-SI29 document relevance
DS-SI32 URL dedup
DS-SI33 exact content hash
DS-SI37 Qdrant schema
DS-SI38 dense
DS-SI39 sparse
DS-SI40 hybrid
DS-SI42 reranker abstraction
DS-SI67 remove fake relevance
DS-SI68 real SearchEngine
```

## P1 — превратить поиск в research engine

```text
DS-SI05 goal decomposition
DS-SI06 evidence requirements
DS-SI07 query variants
DS-SI18 source prior
DS-SI19 freshness
DS-SI26 domain fairness
DS-SI27 goal-aware scheduling
DS-SI34 near duplicate
DS-SI36 source lineage
DS-SI45 diversity
DS-SI47 source taxonomy
DS-SI48 authority
DS-SI51 Evidence Store
DS-SI53 claim matching
DS-SI55 coverage
DS-SI57 information gain
DS-SI59 gap analyzer
DS-SI60 follow-up search
DS-SI63 stop criteria
```

## P2 — adaptive/learned optimization

```text
DS-SI20 expected acquisition cost
DS-SI35 semantic duplicate
DS-SI43 reranker model optimization
DS-SI50 source history
DS-SI54 contradiction search
DS-SI74 training traces
DS-SI75 LTR experiment
DS-SI76 shadow LTR
```

---

# 7. Benchmark gates перед production rollout

Новый search stack считается успешным только если на зафиксированном benchmark corpus:

1. `URLRecall@50` не хуже baseline;
2. `nDCG@10` статистически лучше baseline;
3. `EvidenceRecall` выше baseline;
4. `NearDuplicateRatio` ниже baseline;
5. `SourceDiversity` не деградирует;
6. `TimeToFirstUsefulEvidence` не ухудшается существенно;
7. `PagesPerSolvedQuery` снижается или качество растёт сильнее стоимости;
8. `UsefulEvidencePerPage` растёт;
9. high-authority primary sources не вытесняются generic semantic similarity;
10. identifier-heavy queries не деградируют относительно lexical baseline;
11. multilingual RU/EN queries не деградируют;
12. transient network failures не приводят к потере кандидата;
13. ranking deterministic при одинаковом input/config;
14. explain trace позволяет восстановить ranking decision.

---

# 8. Definition of Done всей программы улучшения

Система считается перешедшей на новый Search Intelligence layer, когда одновременно выполняется следующее:

1. `seed_finder.py` больше не является центром business logic discovery;
2. query представлен как `ResearchIntent`;
3. сложные задачи могут иметь `ResearchGoalGraph`;
4. providers работают через единый registry/contract;
5. provider results нормализуются в `SourceCandidate`;
6. ссылки со страницы сохраняют context и deterministic order;
7. `[:10]` без ranking отсутствует;
8. FIFO `pop(0)` отсутствует в production path;
9. frontier ранжирует candidates по явным features;
10. retry не конфликтует с visited/dedup semantics;
11. acquisition quality отделён от evidence/document quality;
12. off-topic/thin/spam/navigation content не попадает автоматически в evidence corpus;
13. exact и near duplicate detection работают;
14. source lineage отличает копии от независимого подтверждения;
15. Qdrant реально индексирует chunks;
16. dense retrieval работает;
17. sparse retrieval работает;
18. hybrid fusion работает;
19. reranking измерен benchmark-ом и включён только при выигрыше;
20. diversity selection уменьшает redundant evidence;
21. source authority query-dependent;
22. freshness query-dependent;
23. Evidence Store содержит claims/evidence/provenance;
24. contradictions сохраняются как отдельный signal;
25. coverage считается per research goal;
26. follow-up search создаётся из конкретных gaps;
27. information gain влияет на приоритет дальнейшего поиска;
28. `max_pages` является hard guard, а не главным stop condition;
29. stop reason сохраняется в execution result;
30. Axiom ADGO управляет iterative research lifecycle;
31. Rust acquisition worker получает уже ranked acquisition tasks;
32. search benchmark запускается автоматически;
33. можно объяснить, почему каждый итоговый источник был выбран;
34. synthetic search results и fake relevance scores удалены;
35. один production search path используется CLI/REST/MCP.

---

# 9. Финальная целевая схема

```text
User Query
    ↓
ResearchIntent
    ↓
ResearchGoalGraph
    ↓
QueryGenerator
    ↓
ProviderPolicy
    ↓
Parallel Discovery Providers
    ↓
SourceCandidate Pool
    ↓
Normalize + URL Dedup
    ↓
Cheap Lexical/Semantic Pre-Rank
    ↓
SourceType / Authority / Freshness / Cost Features
    ↓
CandidateRanker
    ↓
RankedFrontier
    ↓
Axiom ADGO AcquireBatch
    ↓
Rust Acquisition Worker
    ↓
Document Quality / Relevance Gate
    ↓
Exact + Near Duplicate Detection
    ↓
Structure-aware Chunking
    ↓
Qdrant
    ├── Dense
    └── Sparse
          ↓
        Fusion
          ↓
       Reranker
          ↓
   Diversity / MMR
          ↓
    Evidence Extractor
          ↓
      EvidenceGraph
          ↓
   Coverage + Contradictions
          ↓
  Information Gain / Gap Analyzer
     ├── gaps → Follow-up Queries
     └── sufficient → Stop + Synthesis
```

Главная архитектурная формула проекта после реализации этого плана:

> **DeepSearch должен оптимизировать не количество найденных страниц и не similarity само по себе, а стоимость получения нового, проверяемого и независимого evidence, которое закрывает конкретные исследовательские цели.**
