# DeepSearch: анализ качества источников и план улучшений

## 1. Воспроизводимый прогон

Команда:

```powershell
.\.venv\Scripts\scraper.exe research `
  --query "retrieval-augmented generation evaluation faithfulness factuality citation correctness" `
  --depth 1 --max-pages 12 --mode balanced `
  --min-media 5 --max-media 5 `
  --output deepsearch_source_quality_run.zip
```

Артефакт: `deepsearch_source_quality_run.zip`.

Результат запуска:

| Метрика | Значение |
|---|---:|
| Принятые страницы | 12 |
| RAG-чанки | 114 |
| Записи PDF в inventory | 62 |
| Уникальные PDF по SHA-256 | 56 |
| Медиафайлы | 2 из целевых 5 |
| Размер ZIP | 263 886 862 байта |
| Источники-домены | 5 hostname |
| Чанки с `relevance_score` | 0 |

## 2. Набор источников

### Полезные прямые научные источники

Эти четыре записи содержат полноценные страницы arXiv с названием и abstract,
релевантными теме прогона:

1. [FAIR-RAG](https://arxiv.org/abs/2510.22344v1) — итеративное восполнение пробелов в доказательствах.
2. [Ragas: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217v2) — метрики оценки RAG.
3. [Evaluation of Retrieval-Augmented Generation: A Survey](https://arxiv.org/abs/2405.07437) — обзор метрик и benchmark-подходов.
4. [A Comparative Analysis of Faithfulness Metrics and Humans in Citation Evaluation](https://arxiv.org/abs/2408.12398v1) — сравнение автоматических метрик поддержки цитат с людьми.

### Слабые или нерелевантные результаты

- `arxiv.org/abs/2506.06962v3` — AR-RAG для генерации изображений, а не оценки текстового RAG.
- `arxiv.org/search/cs?searchtype=author&query=Zhang,+W` — страница поиска авторов; 87 из 114 чанков, то есть 76,3% всего RAG-корпуса.
- `arxiv.org/search/cs?searchtype=author&query=Asl,+M+A` — ещё одна страница списка результатов вместо отдельной статьи.
- `blog.europepmc.org` — справочный блог о Europe PMC, не доказательство по теме RAG.
- `link.springer.com/...` — JS-заглушка, 46 слов полезного текста.
- `www.mdpi.com/...` — Access Denied, 16 слов.
- `europepmc.org/` и `/accounts/login` — home/login shell, а не источники исследования.

Итого ручная классификация 12 принятых страниц:

| Класс | Количество | Доля |
|---|---:|---:|
| Прямое релевантное evidence | 4 | 33,3% |
| Связано с темой, но не отвечает запросу | 1 | 8,3% |
| Search/listing/справочная навигация | 3 | 25,0% |
| Ошибка, login или JS-shell | 4 | 33,3% |

## 3. Что говорит качество артефакта

1. **Discovery даёт recall без достаточной precision.** В corpus попали страницы
   авторского поиска, главная страница, login и блог. Это должен был быть hard reject
   или как минимум сильный penalty ещё до acquisition.
2. **Quality gate пропускает не-документы.** Страницы Springer, MDPI и Europe PMC
   попали в `files/` и `rag/`, хотя их текст прямо сообщает о JS, Access Denied или
   необходимости входа.
3. **RAG индексирует навигационный шум.** Один listing-документ дал 87 чанков; при
   этом у всех 114 чанков `relevance_score=null`. Система не может отличить evidence
   от навигации после экспорта.
4. **PDF acquisition не равен PDF evidence.** В архиве есть 62 PDF-записи, но
   RAG-чанки построены вокруг 12 HTML-страниц. Для arXiv это в основном abstract и
   служебная разметка, а не полный текст статьи.
5. **Дедупликация неполная.** 62 PDF-записи соответствуют 56 уникальным SHA-256;
   варианты одного и того же arXiv PDF с `.pdf`, без расширения и с разными URL
   сохраняются повторно.
6. **Медиа-пайплайн формально сработал, но по смыслу нет.** Получены только
   `qmark.png` 10×10 и значок лицензии Creative Commons 88×31, оба с relevance 0,3.
   Это не topic evidence и не выполнение цели 5 изображений.
7. **Состав источников зависим от одного host.** 7 из 12 страниц — arXiv, а
   прямых usable sources из рецензируемых журналов в прогоне нет. Для научного
   ответа нужны явные правила preprint/journal/official и измерение независимости.

## 4. План улучшений

### P0 — сделать источник недопустимым, если это не документ

**Изменения**

- Ввести типы результата acquisition: `DOCUMENT`, `SEARCH_LISTING`, `NAVIGATION`,
  `LOGIN`, `BLOCK_PAGE`, `JS_SHELL`, `ERROR_PAGE`.
- Добавить hard reject по признакам `Access Denied`, Cloudflare/challenge, login,
  `enable JavaScript`, пустого SPA-shell, titleless listing и доминирующей навигации.
- Не добавлять rejected result в `files/`, `rag/`, PDF/media inventory; сохранять его
  только в диагностический `rejections.jsonl` с причиной и URL.
- При L3 timeout не ждать `networkidle` для всех страниц: использовать ограниченный
  `domcontentloaded`/selector readiness и короткий budget, затем явно маркировать
  acquisition failure.

**Критерии приёмки**

- В golden-прогоне 0 block/login/JS-shell страниц в accepted corpus.
- `accepted_document_precision >= 0.80` на размеченном наборе.
- Каждый rejected URL имеет одну машинно-читаемую причину.

### P0 — исправить discovery и ranking

**Изменения**

- Ранжировать кандидатов по query/subgoal relevance до acquisition.
- Запрещать как конечные источники URL-маски `/search`, `/accounts/login`, главные
  страницы и списки авторов; разрешать их только как transient discovery pages.
- Сохранять provenance кандидата: provider, rank, query variant, source type,
  authority prior, freshness и extraction probability.
- Не расширять frontier первыми десятью ссылками без relevance/diversity filter.

**Критерии приёмки**

- Ни один listing/login/home URL не попадает в accepted documents.
- Listing-страница не может дать более 5% RAG-чанков одного запуска.
- `top-10 precision` по golden queries — не ниже 0,80.

### P0 — сделать полный текст источником evidence

**Изменения**

- После скачивания PDF извлекать текст и связывать его с исходной scholarly record.
- Строить RAG chunks из полного текста, а abstract хранить как отдельный summary.
- В каждый chunk добавить `source_id`, `document_type`, `section`, `page`, `published_at`,
  `authority_score`, `relevance_score` и прямую ссылку на источник.
- Не архивировать один PDF более одного раза после content-hash dedup.

**Критерии приёмки**

- `unique_pdf_files == unique_sha256_count`.
- Для принятой scholarly записи есть хотя бы один chunk из полного текста или явный
  `full_text_unavailable`.
- `relevance_score` заполнен для 100% RAG-чанков.

### P1 — ввести source policy и coverage

**Изменения**

- Классифицировать источники как `peer_reviewed`, `preprint`, `official`, `dataset`,
  `secondary`, `navigation`.
- Ввести минимумы по задаче: для научного обзора минимум 2 независимых домена,
  минимум 1 обзор/benchmark и минимум 3 прямых исследования; preprint не считать
  эквивалентом peer-reviewed публикации.
- Добавить diversity selection по домену, типу источника, году и подцели.
- Экспортировать `source_quality_report.json` с authority, topical relevance,
  extraction completeness, freshness, duplicate cluster и decision reason.

**Критерии приёмки**

- Отчёт показывает source count, independent domain count, source-type coverage и
  unresolved gaps.
- При невыполнении минимума run получает статус `insufficient_evidence`, а не выглядит
  успешным только потому, что ZIP создан.

### P1 — media quality gate

**Изменения**

- Отбрасывать изображения меньше минимального размера, placeholder/logo/licence assets
  и изображения без topic/entity match.
- Разделить `requested_media_count` и `accepted_media_count`; не считать техническую
  картинку выполнением цели.
- Для каждого media item сохранять rejection/selection reason.

**Критерии приёмки**

- В accepted media нет favicon, qmark, badge и licence logo.
- Если 5 качественных изображений не найдено, manifest явно содержит shortfall.

### P1 — benchmark и регрессии

Добавить размеченные golden queries для science, medicine, engineering и news с
ожидаемыми source URLs и негативными URL. Считать:

- accepted-document precision/recall;
- block-page rejection rate;
- direct-evidence rate;
- independent-domain coverage;
- duplicate rate;
- chunk relevance coverage;
- source-to-chunk concentration;
- acquisition latency и L3 fallback rate.

## 5. Порядок реализации

1. P0 document-type classifier и rejection manifest.
2. P0 candidate ranking/URL policy.
3. P0 PDF full-text path и content-hash dedup.
4. P1 source policy, authority/diversity scoring и coverage report.
5. P1 media quality gate.
6. P1 golden benchmark и CI thresholds.

После каждого шага повторять тот же прогон и сравнивать метрики с baseline выше.
Главная целевая метрика первой итерации — поднять direct-evidence rate с 33,3% до
не менее 80%, одновременно доведя block-page rate до 0% и устранив null relevance
scores.

## 6. Статус реализации

Реализованы все запланированные этапы первой итерации:

- `document_type.py`: классификация `DOCUMENT`, `SEARCH_LISTING`, `NAVIGATION`,
  `LOGIN`, `BLOCK_PAGE`, `JS_SHELL`, `ERROR_PAGE`.
- `rejections.jsonl`: диагностический реестр rejected URL и acquisition failures.
- `url_policy.py`: terminal URL policy для listing/login/home и binary-document URL.
- canonical HTTPS upgrade для известных secure discovery domains.
- PDF full-text evidence, abstract/full-text разделение, provenance и SHA-256 dedup.
- `source_quality_report.json`, source classes, independent-domain и evidence gates.
- lifecycle `INSUFFICIENT_EVIDENCE` для CLI, application service и MCP.
- media quality gate с dimension/technical-asset/relevance фильтрами и shortfall.
- offline benchmark metrics, quality-gate runner и CI fixture validation.
- bounded browser navigation: `domcontentloaded` вместо безграничного `networkidle`.

Проверка: `125 passed`; targeted ruff для изменённых модулей проходит. Контрольные
v2/v3 запуски корректно сформировали `INSUFFICIENT_EVIDENCE` и diagnostic rejection
отчёты; upstream arXiv в момент v3 был недоступен для acquisition, поэтому этот
прогон нельзя считать новой оценкой scholarly recall.
