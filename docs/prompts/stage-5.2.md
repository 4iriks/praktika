# ПРОМТ 5.2 — очистка, дедупликация, чанкинг и реальная ingestion pipeline

```text
Продолжай разработку существующего проекта PyAnswer после завершения подэтапа 5.1.

Это подэтап 5.2 Этапа 5.

Не создавай проект заново. Сначала изучи фактический код и последний коммит 5.1:

- worker;
- job queue;
- Stack Exchange client;
- source sync state;
- job events;
- cancellation;
- migrations;
- tests;
- текущие models documents/answers/tags/sources/jobs.

Запусти существующие проверки до изменений.

==================================================
ЦЕЛЬ ПОДЭТАПА 5.2
==================================================

Довести SOURCE_SYNC до реального сохранения документов:

1. Безопасная очистка HTML.
2. Сохранение Python-кода и форматирования.
3. Детерминированный выбор ответов.
4. Canonical document.
5. SHA-256 content/metadata hashes.
6. Identity и exact-content дедупликация.
7. Версионирование документов.
8. Code-aware и section-aware chunking.
9. Сохранение document chunks.
10. Upsert questions, answers и tags.
11. Initial sync.
12. Incremental sync.
13. Checkpoint/resume.
14. Реальный SOURCE_SYNC worker handler.
15. Failure isolation.
16. Полные unit/integration tests.

Не подключай Qdrant, embeddings, BM25, HNSW, reranker или Ollama.

Не устанавливай index statuses в READY.

==================================================
1. MIGRATION 5.2
==================================================

Создай следующую Alembic migration.

Добавь таблицу document_revisions:

- id UUID;
- document_id FK;
- version;
- content_hash;
- metadata_hash;
- source_updated_at nullable;
- snapshot JSONB;
- change_reason;
- created_at.

Constraint: unique document_id + version.

Добавь document_chunks:

- id UUID;
- chunk_key unique;
- document_id FK;
- document_version;
- ordinal;
- section_type;
- answer_id nullable;
- text;
- contextual_text;
- content_hash;
- token_count;
- character_count;
- has_code;
- language nullable;
- created_at;
- updated_at.

Constraints:

- unique document_id + document_version + ordinal;
- ordinal >= 0;
- token_count >= 0;
- text не пустой.

Indexes:

- document_id;
- content_hash;
- section_type;
- document_version.

Расширь documents при отсутствии:

- processing_status;
- deduplication_status;
- duplicate_of_document_id nullable self FK;
- metadata_hash;
- canonical_text;
- last_seen_at;
- source_updated_at;
- processing_error;
- selected_answers_count.

Расширь answers при отсутствии:

- body_text;
- sanitized_html nullable;
- body_hash;
- source_updated_at;
- last_seen_at;
- selected_for_corpus;
- selection_rank nullable;
- source_missing;
- content_license nullable.

Добавь enums/check constraints и indexes.

Не удаляй существующие данные.

==================================================
2. PROCESSING STATES
==================================================

Раздели moderation status и технический processing status.

ProcessingStatus:

- RAW;
- CLEANING;
- CLEANED;
- CHUNKING;
- CHUNKED;
- FAILED.

DeduplicationStatus:

- UNIQUE;
- EXACT_DUPLICATE;
- POSSIBLE_DUPLICATE.

DocumentStatus из предыдущих этапов сохраняется.

Новый успешно обработанный document:

- processing_status=CHUNKED;
- moderation status=ACTIVE либо существующее безопасное значение;
- bm25_status=NOT_INDEXED или OUTDATED;
- vector_status=NOT_INDEXED или OUTDATED.

Не выставляй READY.

==================================================
3. HTML CLEANER
==================================================

Создай отдельный processing module.

Используй BeautifulSoup+lxml либо другую безопасную parser-based реализацию. Не очищай HTML regex-ами.

Допустимо использовать bleach для allowlist sanitization.

Удаляй:

- script;
- style;
- iframe;
- object;
- embed;
- event handler attributes;
- javascript URLs;
- опасные неизвестные элементы.

Сохраняй:

- headings;
- paragraphs;
- списки;
- blockquote;
- inline code;
- pre/code;
- ссылки как текст/безопасный URL при необходимости.

Исходный HTML никогда не рендерится без sanitization и не попадает в audit/logs.

Добавь лимиты входного HTML и результата.

==================================================
4. СОХРАНЕНИЕ КОДА
==================================================

Преобразуй <pre><code>...</code></pre> в fenced code blocks.

Не уничтожай:

- отступы;
- пробелы;
- переносы;
- специальные символы;
- HTML entities внутри кода.

Inline code сохраняй обратными кавычками.

Не выдумывай язык блока, если его нельзя определить надёжно.

Если class явно содержит language-python/lang-python, можно использовать python.

Никогда не выполняй и не компилируй код из публикаций.

==================================================
5. НОРМАЛИЗАЦИЯ
==================================================

Детерминированный pipeline:

1. Ограничить входной размер.
2. Decode HTML entities.
3. Unicode NFC.
4. Нормализовать line endings.
5. Удалить опасные элементы.
6. Извлечь структурные blocks.
7. Сохранить code blocks.
8. Нормализовать пробелы вне code.
9. Ограничить повторные пустые строки.
10. Trim.

Не применять агрессивный NFKC к программному коду.

==================================================
6. ANSWER SELECTION
==================================================

Алгоритм детерминированный.

Если accepted answer существует и получен:

1. Выбрать accepted первым.
2. Исключить его из дополнительных.
3. Остальные сортировать:
   - score DESC;
   - creation_date ASC;
   - external answer ID ASC.
4. Выбрать до max_additional_answers.

Если accepted answer отсутствует:

- выбрать до max_additional_answers + 1 лучших ответов.

При max_additional_answers=3 максимум четыре выбранных ответа.

Пустой очищенный answer и source_missing answer не включаются.

Если accepted_answer_id заявлен, но answer не получен:

- warning event/failure metric;
- не помечать другой answer принятым;
- использовать лучшие доступные ответы.

Сохраняй все полученные answers, но выставляй selected_for_corpus и selection_rank только выбранным.

==================================================
7. CANONICAL DOCUMENT
==================================================

Сформируй стабильный canonical document:

# Нормализованный заголовок

Теги: ...

## Вопрос

...

## Принятый ответ

...

## Дополнительный ответ 1

...

Canonical representation включает:

- title;
- sorted tags;
- question text;
- selected answer texts;
- явный section type.

Не включай в content hash:

- views;
- scores;
- случайные timestamps;
- job ID;
- processing metadata.

Сохраняй source URL и attribution отдельно.

==================================================
8. HASHES
==================================================

Используй SHA-256.

content_hash:

- canonical title;
- sorted tags;
- normalized question text;
- selected answers и их порядок.

metadata_hash:

- score;
- views;
- answer count;
- author;
- source dates;
- прочие несмысловые metadata.

Serialization:

- стабильный JSON;
- sort_keys;
- фиксированные separators;
- UTC timestamps;
- без Python hash().

Если content_hash не изменился:

- не пересоздавать chunks;
- не создавать revision;
- обновить metadata, last_seen_at и answers;
- result=UNCHANGED.

Если content_hash изменился:

- увеличить version;
- создать revision;
- заменить chunks атомарно;
- index statuses OUTDATED/NOT_INDEXED;
- result=UPDATED.

==================================================
9. ДЕДУПЛИКАЦИЯ
==================================================

Уровень 1:

- source_id + external_id unique;
- повторная загрузка обновляет существующую запись.

Уровень 2 URL normalization:

- lowercase host;
- удалить fragment;
- удалить trailing slash;
- удалить известные tracking params;
- привести Stack Overflow question URL к canonical form;
- не менять значимые части URL.

Уровень 3 exact content:

- искать другой non-duplicate document с тем же content_hash;
- пометить EXACT_DUPLICATE;
- сохранить duplicate_of_document_id;
- не удалять физически;
- не включать duplicate в будущую индексируемую выборку;
- оставить доступ EDITOR/ADMIN.

Не реализуй O(N²) fuzzy comparison.

POSSIBLE_DUPLICATE может оставаться подготовленным статусом без автоматического merge.

==================================================
10. DOCUMENT REVISIONS
==================================================

Revision создаётся при смысловом изменении content.

Snapshot содержит безопасные поля:

- title;
- tags;
- question text;
- selected answer IDs/text hashes;
- previous metadata summary.

Не сохраняй secrets и raw API wrapper.

Добавь DOCUMENT_REVISION_LIMIT, например 10.

Retention старых revisions выполняется безопасно после создания новой revision и документируется.

==================================================
11. CHUNKER
==================================================

Создай code-aware, section-aware, deterministic chunker.

Settings:

- CHUNK_TARGET_TOKENS=650;
- CHUNK_MAX_TOKENS=900;
- CHUNK_OVERLAP_TOKENS=80;
- CHUNK_MIN_TOKENS=40.

Создай token counter abstraction. Допустимо использовать tiktoken как приблизительный tokenizer, но chunker не должен быть жёстко связан с будущей embedding model.

Atomic blocks:

- heading;
- paragraph;
- list;
- quote;
- code block.

Packing:

- не смешивать question и answer без необходимости;
- не разделять code block, если он помещается;
- очень большой code block делить по строкам;
- сохранять отступы и порядок;
- overlap применять к текстовым chunks;
- не копировать огромный code block полностью в overlap.

SectionType:

- QUESTION;
- ACCEPTED_ANSWER;
- ANSWER;
- MIXED.

contextual_text включает:

- title;
- tags;
- section label;
- chunk text.

==================================================
12. STABLE CHUNK KEY
==================================================

Создай стабильный chunk_key, например UUIDv5/hex SHA-256 от:

- document_id;
- document_version;
- ordinal;
- chunk content_hash.

Неизменившийся document не создаёт новые chunks.

Изменившийся version может создавать новые chunk IDs.

Замена chunks для одной document version должна быть атомарной.

==================================================
13. INGEST QUESTION THREAD SERVICE
==================================================

Создай бизнес-сервис ingest_question_thread(question, answers, context).

Порядок:

1. Валидировать DTO.
2. Очистить question.
3. Очистить answers.
4. Выбрать corpus answers.
5. Сформировать canonical document.
6. Вычислить hashes.
7. Нормализовать source URL.
8. Найти существующий document.
9. Upsert document.
10. Upsert answers.
11. Upsert tags/document_tags.
12. Выполнить exact dedup.
13. Создать revision при необходимости.
14. Создать/заменить chunks при необходимости.
15. Обновить processing/index statuses.
16. Вернуть типизированный result:
   - INSERTED;
   - UPDATED;
   - UNCHANGED;
   - DUPLICATE;
   - SKIPPED;
   - FAILED.

Один thread обрабатывается в короткой transaction.

Не держи transaction во время network call.

==================================================
14. INITIAL SYNC
==================================================

AUTO выбирает INITIAL, если initial_sync_completed_at отсутствует.

INITIAL:

- sort=creation;
- order=desc;
- fixed todate в начале job;
- tagged=python;
- pagesize=100;
- продолжает с checkpoint page;
- получает answers batch на каждую questions page;
- обрабатывает каждый thread;
- commit page/batch;
- только после commit обновляет checkpoint;
- прекращается при targetDocuments, has_more=false, empty items, cancellation, quota reserve или fatal error.

Initial sync считается завершённым только после успешного окончания, не после dry-run/cancel/failure.

==================================================
15. INCREMENTAL SYNC
==================================================

AUTO выбирает INCREMENTAL после initial completion.

INCREMENTAL:

- sort=activity;
- order=desc;
- fromdate = watermark - overlap;
- fixed todate на начало job;
- overlap setting по умолчанию 86400 секунд;
- повторная загрузка безопасна из-за identity/content hash;
- watermark обновляется только после COMPLETED job;
- FAILED/CANCELLED job не продвигает watermark.

==================================================
16. BATCH TRANSACTIONS И CHECKPOINT
==================================================

На каждую page:

1. Fetch questions вне transaction.
2. Fetch all answer pages вне transaction.
3. Начать DB work короткими transactions.
4. Обработать threads.
5. Commit сохранённые данные.
6. Commit counters/checkpoint.

Checkpoint не продвигается до успешного сохранения batch.

Локальная ошибка одного document:

- сохранить ingestion_failure;
- увеличить counter;
- продолжить остальные документы.

Fatal schema/client/DB error:

- остановить job;
- сохранить checkpoint;
- retry по правилам worker.

==================================================
17. ANSWER RECONCILIATION
==================================================

При каждой полной загрузке answers для question batch:

- upsert полученные answers;
- обновить last_seen_at;
- сбросить и пересчитать selected_for_corpus/selection_rank;
- ранее известный, но отсутствующий в полученном полном наборе answer пометить source_missing=true;
- source_missing исключить из canonical document;
- не удалять answer физически.

Если accepted answer изменился, content должен пересобраться.

==================================================
18. QUALITY LIMITS
==================================================

Settings:

- MIN_QUESTION_TEXT_LENGTH;
- MIN_ANSWER_TEXT_LENGTH;
- MAX_DOCUMENT_TEXT_LENGTH;
- MAX_ANSWER_COUNT_PER_QUESTION;
- MAX_HTML_BODY_BYTES.

Не отбрасывай вопрос только из-за отсутствия accepted answer.

Пустой/невалидный question → SKIPPED с безопасной причиной.

==================================================
19. ATTRIBUTION
==================================================

Сохраняй:

- source URL;
- external question ID;
- external answer ID;
- author display name;
- author profile URL при наличии;
- content license при наличии;
- source name.

Не заявляй право собственности PyAnswer на исходный контент.

==================================================
20. REAL SOURCE_SYNC HANDLER
==================================================

Заверши worker handler SOURCE_SYNC.

Он должен:

- выбирать mode;
- читать checkpoint;
- получать pages;
- batch-fetch answers;
- вызывать ingest service;
- обновлять job progress/events/counters;
- поддерживать cancellation;
- поддерживать retry/resume;
- обновлять source_sync_state;
- устанавливать source status;
- завершать job COMPLETED только при корректном завершении.

Job result содержит минимум:

- questions_fetched;
- answers_fetched;
- inserted;
- updated;
- unchanged;
- duplicates;
- skipped;
- failed;
- chunks_created;
- requests;
- bytes_received;
- final_page;
- mode.

==================================================
21. API ДЛЯ INGESTION
==================================================

Добавь/заверши:

GET /api/admin/sources/{sourceId}/sync-state
GET /api/admin/ingestion/stats
GET /api/admin/ingestion/failures
GET /api/admin/ingestion/failures/{failureId}

Все endpoints защищены существующими permissions.

Не раскрывай raw HTML, API key и secrets.

==================================================
22. TESTS 5.2
==================================================

Не удаляй существующие tests.

HTML/code:

1. entities декодируются;
2. script/iframe удаляются;
3. handlers/javascript URLs удаляются;
4. paragraphs/lists сохраняются;
5. inline code сохраняется;
6. code indentation сохраняется;
7. Python special chars сохраняются;
8. Unicode/line endings нормализуются;
9. canonical output детерминирован.

Answer selection:

10. accepted всегда выбран;
11. accepted не дублируется;
12. три лучших дополнительных;
13. без accepted до четырёх;
14. tie-breaker стабилен;
15. empty/source_missing исключены;
16. missing accepted создаёт warning.

Hashes/dedup:

17. одинаковый canonical даёт одинаковый SHA-256;
18. score/views не меняют content_hash;
19. question/selected answer меняют content_hash;
20. порядок tags не меняет hash;
21. external identity выполняет update;
22. exact duplicate получает duplicate_of;
23. duplicate физически сохраняется.

Chunking:

24. deterministic;
25. max token limit;
26. code block не режется без необходимости;
27. большой code block режется по строкам;
28. indentation сохраняется;
29. overlap работает;
30. пустые chunks отсутствуют;
31. section types корректны;
32. contextual_text содержит title/tags;
33. stable chunk keys.

PostgreSQL ingestion:

34. question/answers/tags/chunks сохраняются;
35. повторный batch не создаёт duplicates;
36. unchanged не создаёт revision/chunks;
37. changed создаёт revision и новую version;
38. metadata-only не пересоздаёт chunks;
39. initial checkpoint после commit;
40. failure до commit не продвигает checkpoint;
41. cancellation сохраняет checkpoint;
42. retry продолжает;
43. incremental использует watermark и overlap;
44. watermark не обновляется при failure;
45. один document failure не останавливает batch;
46. fatal schema error останавливает job;
47. index statuses не становятся READY.

Используй реальный PostgreSQL test DB и mocked HTTP.

==================================================
23. DOCUMENTATION 5.2
==================================================

Создай/обнови:

- docs/content-cleaning.md;
- docs/chunking.md;
- docs/stage5-ingestion.md;
- docs/erd.md;
- docs/sql_examples.sql;
- backend/README.md.

ERD должен соответствовать migration.

SQL examples добавить:

- documents без chunks;
- avg chunks per document;
- processing statuses;
- exact duplicates;
- revisions;
- changed after last indexing;
- ingestion failure rate;
- source sync counters.

==================================================
24. ПРОВЕРКИ И GIT
==================================================

Выполни backend/frontend regression, Alembic upgrade/downgrade на disposable DB и Docker worker build.

Coverage не ниже 80%.

Не выполнять live full import.

После успешных проверок создай промежуточный коммит:

Реализована обработка и чанкинг документов Stack Exchange

Не выполнять push.

В финальном отчёте этого подэтапа отдельно подтвердить:

- index statuses не READY;
- search/ask всё ещё 501 в HTTP mode;
- полный Этап 5 ещё не объявлен завершённым;
- рабочее дерево чистое.
```
