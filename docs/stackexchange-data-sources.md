# Источники корпуса Stack Exchange

PyAnswer использует несколько независимых способов пополнения корпуса. Основной
online-канал остаётся Stack Exchange API, но его суточная quota не должна блокировать
первичную загрузку.

## 1. Официальный Stack Exchange Data Dump

Для массовой загрузки используется официальный Creative Commons dump с Internet
Archive. Он публикуется примерно ежеквартально и содержит `Posts.xml`, `Users.xml` и
другие сущности каждого сайта. Это предпочтительный способ первичного наполнения:

- отсутствует суточная API quota;
- вопросы и ответы получаются из одного согласованного snapshot;
- сохраняются ID, даты, HTML, теги, авторы, лицензия и attribution;
- повторный импорт идемпотентен благодаря `(source_id, external_id)` и content hash.

Текущий snapshot для русского Stack Overflow:

```text
https://archive.org/download/stackexchange_20260331/stackexchange_20260331/ru.stackoverflow.com.7z
```

Пример загрузки с возобновлением:

```bash
mkdir -p artifacts/raw/stackexchange
curl -L --fail --retry 5 --continue-at - \
  --output artifacts/raw/stackexchange/ru.stackoverflow.com.7z \
  https://archive.org/download/stackexchange_20260331/stackexchange_20260331/ru.stackoverflow.com.7z
```

Импорт в существующий pipeline:

```bash
RUN_DATA_DUMP_IMPORT=1 \
DUMP_ARCHIVE=artifacts/raw/stackexchange/ru.stackoverflow.com.7z \
DUMP_TARGET_TOTAL=25000 \
make import-dump
```

Импортёр потоково читает XML через 7z, выбирает только вопросы с меткой `python`,
выполняет отдельный bounded проход за ответами (порядок строк `Posts.xml` не считается
сортированным), присоединяет имена авторов, после чего вызывает обычный
`ingest_question_thread`. Поэтому очистка HTML, сохранение кода, выбор ответов,
хеширование, дедупликация, revisions, чанкинг и постановка переиндексации не
дублируются.

Если импорт старой версией был прерван либо обнаружены неполные ветки, ответы можно
безопасно восстановить идемпотентно:

```bash
RUN_DATA_DUMP_IMPORT=1 \
DUMP_REPAIR_ANSWER_GAPS=1 \
DUMP_ARCHIVE=artifacts/raw/stackexchange/ru.stackoverflow.com.7z \
make import-dump
```

## 2. BitTorrent официального dump

Internet Archive публикует `.torrent` для каждого release. Это тот же официальный
набор данных и полезный резерв при медленной HTTP-загрузке. В torrent необходимо
выбрать только файл `stackexchange_20260331/ru.stackoverflow.com.7z`, иначе клиент
может попытаться скачать весь многогигабайтный release сети Stack Exchange.

## 3. Stack Exchange Data Explorer

SEDE подходит для выборочных SQL-выгрузок и сверки свежих данных. Он содержит таблицы
`Posts`, `PostTags`, `Tags` и позволяет скачать результат как CSV/XML. Ограничения
выдачи и периодичность обновления делают его резервом, а не заменой bulk dump.

## 4. Common Crawl

Common Crawl хранит публичные HTML snapshots и позволяет находить записи через CDX
index, затем скачивать только нужные byte ranges из WARC. Канал полезен для точечного
восстановления страниц, но менее полный и менее структурированный, чем официальный
dump. Полученный HTML всё равно обязан пройти текущий sanitizer и attribution checks.

## 5. API с зарегистрированным key

Для последующей incremental-синхронизации рекомендуется зарегистрировать приложение
на Stack Apps и задать `STACKEXCHANGE_KEY`. Это увеличивает стандартную суточную quota,
но не отменяет обязательную обработку `backoff`, `Retry-After` и ограничение частоты.

PyAnswer не использует ротацию IP/ключей, обход CAPTCHA или агрессивный HTML scraping.
Такие способы ненадёжны, ухудшают качество корпуса и могут нарушить правила источника.
