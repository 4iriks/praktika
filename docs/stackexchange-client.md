# Клиент Stack Exchange API — подэтап 5.1

Интеграция находится в отдельном backend layer и использует типизированные Pydantic DTO и один
`httpx.AsyncClient` на lifecycle worker. HTTP-клиент не зависит от SQLAlchemy repositories и не
передаёт raw DTO во frontend.

## Разрешённый источник

- API base URL: `https://api.stackexchange.com/2.3`;
- site: `ru.stackoverflow`;
- tag: `python`;
- явный User-Agent PyAnswer.

Base URL проверяется allowlist. Admin source settings не могут направить worker на произвольный
host, поэтому URL конфигурации не превращается в SSRF-вектор.

`STACKEXCHANGE_KEY` необязателен и читается только из environment. Пустое значение означает
работу без key. Key не сохраняется в source, job payload/checkpoint, audit, events, failure,
response frontend или Git. В API доступен только безопасный признак `apiKeyConfigured`.

## Questions

Клиент использует `GET /questions` с параметрами:

- `site=ru.stackoverflow`;
- `tagged=python`;
- `page`, `pagesize` не более 100;
- `sort`, `order`;
- опциональные `fromdate` и фиксированный `todate`;
- configured filter;
- `key` только когда он непустой.

Iterator отдаёт страницы по мере получения, следует `has_more`, прекращает работу при пустом
`items` и имеет аварийный `max pages`. Все страницы целиком в память не загружаются.

## Answers

Ответы загружаются через `GET /questions/{ids}/answers`. В одном path не более 100 question ID,
разделённых точкой с запятой. Answers endpoint также проходит все страницы по `has_more`; один
request на каждый вопрос не выполняется.

На подэтапе 5.1 клиент проверяет wrapper и поддерживает fetch/checkpoint. Выбор corpus answers,
очистка, canonical document и сохранение появятся в 5.2.

## Wrapper и ограничения

Общий DTO учитывает `items`, `has_more`, `quota_max`, `quota_remaining`, `backoff` и optional API
error fields. Отсутствующий `has_more` трактуется как `false`.

После response учитываются request count и полученные bytes. Ответ больше
`STACKEXCHANGE_MAX_RESPONSE_BYTES` отклоняется до бесконтрольного разбора. Количество страниц и
page size ограничены конфигурацией.

## Rate limit, retry и backoff

Локальный async limiter по умолчанию допускает три запроса в секунду. Клиент соблюдает:

- Stack Exchange wrapper `backoff`;
- HTTP `Retry-After`;
- exponential backoff с jitter;
- ограниченный `STACKEXCHANGE_MAX_RETRIES`;
- cancellation во время ожидания.

Временно повторяются timeout/connection error, HTTP 429, 502, 503 и 504. Ошибки 400, 401, 403 и
валидационные ошибки API не попадают в бесконечный retry. Во время долгого ожидания heartbeat
worker продолжает обновляться.

После каждого wrapper source получает quota remaining/max и время обновления quota. При
достижении reserve checkpoint сохраняется, job планируется на более позднюю попытку без tight
loop. `quotaResetAt` не выдумывается, если API его не сообщил.

## Test connection

Проверка source делает один малый questions request с `pagesize` 1–5, timeout и DTO validation.
Она не создаёт `SOURCE_SYNC` и не сохраняет документы. Результат содержит success, latency,
quota, `hasMore` и время проверки; audit не содержит response body или key.

## Environment

Основные переменные перечислены в `.env.example`:

- `STACK_EXCHANGE_SITE`, `STACK_EXCHANGE_TAG`, `STACK_EXCHANGE_TARGET_DOCUMENTS`;
- `STACKEXCHANGE_API_BASE_URL`, optional `STACKEXCHANGE_KEY`;
- question/answer filters и page size;
- requests per second и HTTP timeouts;
- retries, quota reserve, maximum response bytes/pages;
- incremental overlap и User-Agent.

Автоматические тесты используют `httpx.MockTransport` и не зависят от интернета.
