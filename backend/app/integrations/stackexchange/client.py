from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import TypeVar

import httpx
from pydantic import TypeAdapter, ValidationError

from app.core.config import Settings
from app.integrations.stackexchange.errors import (
    StackExchangeCancelled,
    StackExchangePermanentError,
    StackExchangeQuotaLow,
    StackExchangeResponseTooLarge,
    StackExchangeRetryExhausted,
)
from app.integrations.stackexchange.rate_limiter import (
    AsyncRateLimiter,
    AsyncSleep,
    CancellationCheck,
    cancellable_sleep,
)
from app.integrations.stackexchange.schemas import (
    StackExchangeAnswer,
    StackExchangeEnvelope,
    StackExchangePage,
    StackExchangeQuestion,
    StackExchangeResponseMetrics,
)

ItemT = TypeVar("ItemT")
MetricsCallback = Callable[[StackExchangeResponseMetrics], Awaitable[None]]
EventCallback = Callable[[str, str, Mapping[str, object]], Awaitable[None]]


async def _noop_metrics(metrics: StackExchangeResponseMetrics) -> None:
    del metrics


async def _noop_event(code: str, message: str, metrics: Mapping[str, object]) -> None:
    del code, message, metrics


class StackExchangeClient:
    RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        cancellation_check: CancellationCheck | None = None,
        on_metrics: MetricsCallback = _noop_metrics,
        on_event: EventCallback = _noop_event,
        sleep: AsyncSleep = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._cancellation_check = cancellation_check
        self._on_metrics = on_metrics
        self._on_event = on_event
        self._sleep = sleep
        self._clock = clock
        self._random_value = random_value
        self._rate_limiter = AsyncRateLimiter(
            settings.stackexchange_requests_per_second,
            clock=clock,
            sleep=sleep,
        )
        self._blocked_until: dict[str, float] = {}
        self._owns_client = client is None
        timeout = httpx.Timeout(
            connect=settings.stackexchange_connect_timeout_seconds,
            read=settings.stackexchange_read_timeout_seconds,
            write=settings.stackexchange_write_timeout_seconds,
            pool=settings.stackexchange_pool_timeout_seconds,
        )
        self._client = client or httpx.AsyncClient(
            base_url=settings.stackexchange_api_base_url.rstrip("/") + "/",
            timeout=timeout,
            headers={"User-Agent": settings.stackexchange_user_agent},
            follow_redirects=False,
        )

    async def __aenter__(self) -> StackExchangeClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _check_cancellation(self) -> None:
        if self._cancellation_check is not None and await self._cancellation_check():
            raise StackExchangeCancelled

    def _base_params(self) -> dict[str, str | int]:
        params: dict[str, str | int] = {"site": self._settings.stack_exchange_site}
        secret = self._settings.stackexchange_key
        if secret is not None and secret.get_secret_value():
            params["key"] = secret.get_secret_value()
        return params

    async def _wait_for_method_backoff(self, method: str) -> None:
        delay = max(0.0, self._blocked_until.get(method, 0.0) - self._clock())
        if delay > 0:
            await cancellable_sleep(
                delay,
                cancellation_check=self._cancellation_check,
                sleep=self._sleep,
            )

    @staticmethod
    def _retry_after_seconds(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0.0, (parsed - datetime.now(UTC)).total_seconds())

    async def _read_limited(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > self._settings.stackexchange_max_response_bytes:
                    raise StackExchangeResponseTooLarge(
                        self._settings.stackexchange_max_response_bytes
                    )
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._settings.stackexchange_max_response_bytes:
                raise StackExchangeResponseTooLarge(self._settings.stackexchange_max_response_bytes)
            chunks.append(chunk)
        return b"".join(chunks)

    async def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str | int],
        page: int,
        adapter: TypeAdapter[StackExchangeEnvelope[ItemT]],
    ) -> StackExchangePage[ItemT]:
        await self._wait_for_method_backoff(method)
        for attempt in range(self._settings.stackexchange_max_retries + 1):
            await self._check_cancellation()
            await self._rate_limiter.acquire(self._cancellation_check)
            response: httpx.Response | None = None
            try:
                url = self._settings.stackexchange_api_base_url.rstrip("/") + "/" + path
                request = self._client.build_request("GET", url, params=params)
                response = await self._client.send(request, stream=True)
                payload = await self._read_limited(response)
            except StackExchangeResponseTooLarge:
                if response is not None:
                    await response.aclose()
                raise
            except (httpx.TimeoutException, httpx.NetworkError):
                if response is not None:
                    await response.aclose()
                if attempt >= self._settings.stackexchange_max_retries:
                    raise StackExchangeRetryExhausted from None
                await self._wait_before_retry(method, attempt, None)
                continue
            finally:
                if response is not None:
                    await response.aclose()

            await self._check_cancellation()
            if response.status_code in self.RETRYABLE_STATUSES:
                await self._on_metrics(
                    StackExchangeResponseMetrics(
                        method=method,
                        page=page,
                        response_bytes=len(payload),
                        quota_remaining=None,
                        quota_max=None,
                    )
                )
                if attempt >= self._settings.stackexchange_max_retries:
                    raise StackExchangeRetryExhausted
                await self._wait_before_retry(
                    method,
                    attempt,
                    self._retry_after_seconds(response.headers.get("Retry-After")),
                )
                continue
            if response.status_code >= 400:
                await self._on_metrics(
                    StackExchangeResponseMetrics(
                        method=method,
                        page=page,
                        response_bytes=len(payload),
                        quota_remaining=None,
                        quota_max=None,
                    )
                )
                raise StackExchangePermanentError(
                    "STACKEXCHANGE_AUTH_REJECTED"
                    if response.status_code in {401, 403}
                    else "STACKEXCHANGE_REQUEST_REJECTED"
                )
            try:
                envelope = adapter.validate_json(payload)
            except ValidationError as exc:
                raise StackExchangePermanentError("STACKEXCHANGE_INVALID_RESPONSE") from exc
            if envelope.error_id is not None or envelope.error_name is not None:
                raise StackExchangePermanentError("STACKEXCHANGE_API_ERROR")
            metrics = StackExchangeResponseMetrics(
                method=method,
                page=page,
                response_bytes=len(payload),
                quota_remaining=envelope.quota_remaining,
                quota_max=envelope.quota_max,
            )
            await self._on_metrics(metrics)
            if envelope.backoff:
                self._blocked_until[method] = max(
                    self._blocked_until.get(method, 0.0),
                    self._clock() + envelope.backoff,
                )
                await self._on_event(
                    "STACKEXCHANGE_BACKOFF",
                    "Stack Exchange запросил паузу для метода",
                    {"method": method, "seconds": envelope.backoff},
                )
            if (
                envelope.quota_remaining is not None
                and envelope.quota_remaining <= self._settings.stackexchange_quota_reserve
            ):
                await self._on_event(
                    "STACKEXCHANGE_QUOTA_LOW",
                    "Остаток квоты достиг безопасного резерва",
                    {
                        "quotaRemaining": envelope.quota_remaining,
                        "quotaReserve": self._settings.stackexchange_quota_reserve,
                    },
                )
                raise StackExchangeQuotaLow(
                    envelope.quota_remaining,
                    self._settings.stackexchange_quota_reserve,
                )
            return StackExchangePage(
                page=page,
                envelope=envelope,
                response_bytes=len(payload),
            )
        raise StackExchangeRetryExhausted

    async def _wait_before_retry(
        self,
        method: str,
        attempt: int,
        retry_after: float | None,
    ) -> None:
        exponential = min(30.0, float(2**attempt))
        delay = retry_after if retry_after is not None else exponential + self._random_value()
        await self._on_event(
            "STACKEXCHANGE_RETRY",
            "Запланирован ограниченный повтор Stack Exchange",
            {"method": method, "attempt": attempt + 1, "delaySeconds": round(delay, 3)},
        )
        await cancellable_sleep(
            delay,
            cancellation_check=self._cancellation_check,
            sleep=self._sleep,
        )

    async def iterate_questions(
        self,
        *,
        sort: str,
        order: str = "desc",
        start_page: int = 1,
        fromdate: int | None = None,
        todate: int | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[StackExchangePage[StackExchangeQuestion]]:
        if sort not in {"creation", "activity"} or order not in {"asc", "desc"}:
            raise StackExchangePermanentError("STACKEXCHANGE_INVALID_PAGINATION")
        size = page_size or self._settings.stackexchange_page_size
        if not 1 <= size <= 100 or start_page < 1:
            raise StackExchangePermanentError("STACKEXCHANGE_INVALID_PAGINATION")
        page_limit = min(
            max_pages or self._settings.stackexchange_max_pages,
            self._settings.stackexchange_max_pages,
        )
        page = start_page
        emitted = 0
        while emitted < page_limit:
            result = await self.fetch_questions_page(
                page=page,
                page_size=size,
                sort=sort,
                order=order,
                fromdate=fromdate,
                todate=todate,
            )
            if not result.envelope.items:
                return
            yield result
            emitted += 1
            if not result.envelope.has_more:
                return
            page += 1

    async def fetch_questions_page(
        self,
        *,
        page: int,
        page_size: int,
        sort: str,
        order: str = "desc",
        fromdate: int | None = None,
        todate: int | None = None,
    ) -> StackExchangePage[StackExchangeQuestion]:
        if (
            sort not in {"creation", "activity"}
            or order not in {"asc", "desc"}
            or page < 1
            or not 1 <= page_size <= 100
        ):
            raise StackExchangePermanentError("STACKEXCHANGE_INVALID_PAGINATION")
        params = self._base_params()
        params.update(
            {
                "tagged": self._settings.stack_exchange_tag,
                "page": page,
                "pagesize": page_size,
                "sort": sort,
                "order": order,
                "filter": self._settings.stackexchange_question_filter,
            }
        )
        if fromdate is not None:
            params["fromdate"] = fromdate
        if todate is not None:
            params["todate"] = todate
        adapter = TypeAdapter(StackExchangeEnvelope[StackExchangeQuestion])
        return await self._request("questions", "questions", params, page, adapter)

    async def fetch_answers_for_question_ids(
        self,
        question_ids: Sequence[int],
        *,
        start_page: int = 1,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[StackExchangePage[StackExchangeAnswer]]:
        unique_ids = list(dict.fromkeys(question_ids))
        if not unique_ids or len(unique_ids) > 100 or any(item <= 0 for item in unique_ids):
            raise StackExchangePermanentError("STACKEXCHANGE_INVALID_ANSWER_BATCH")
        size = page_size or self._settings.stackexchange_page_size
        if not 1 <= size <= 100 or start_page < 1:
            raise StackExchangePermanentError("STACKEXCHANGE_INVALID_PAGINATION")
        page_limit = min(
            max_pages or self._settings.stackexchange_max_pages,
            self._settings.stackexchange_max_pages,
        )
        adapter = TypeAdapter(StackExchangeEnvelope[StackExchangeAnswer])
        path = "questions/" + ";".join(str(item) for item in unique_ids) + "/answers"
        page = start_page
        emitted = 0
        while emitted < page_limit:
            params = self._base_params()
            params.update(
                {
                    "page": page,
                    "pagesize": size,
                    "sort": "creation",
                    "order": "asc",
                    "filter": self._settings.stackexchange_answer_filter,
                }
            )
            result = await self._request("answers", path, params, page, adapter)
            if not result.envelope.items:
                return
            yield result
            emitted += 1
            if not result.envelope.has_more:
                return
            page += 1
