from __future__ import annotations

from collections.abc import Mapping

import httpx
import pytest

from app.core.config import Settings
from app.integrations.stackexchange.client import StackExchangeClient
from app.integrations.stackexchange.errors import (
    StackExchangeCancelled,
    StackExchangePermanentError,
    StackExchangeQuotaLow,
    StackExchangeResponseTooLarge,
    StackExchangeRetryExhausted,
)
from app.integrations.stackexchange.schemas import StackExchangeResponseMetrics


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.value

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.value += delay


def stack_settings(**values: object) -> Settings:
    defaults: dict[str, object] = {
        "APP_ENV": "test",
        "STACKEXCHANGE_REQUESTS_PER_SECOND": 10,
        "STACKEXCHANGE_MAX_RETRIES": 2,
        "STACKEXCHANGE_QUOTA_RESERVE": 5,
    }
    defaults.update(values)
    return Settings(**defaults)


def question_payload(
    question_id: int,
    *,
    has_more: bool = False,
    backoff: int | None = None,
    quota_remaining: int = 100,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "items": [
            {
                "question_id": question_id,
                "title": "Python",
                "body": "<p>Текст</p>",
                "tags": ["python"],
                "link": f"https://ru.stackoverflow.com/questions/{question_id}",
                "creation_date": 1_700_000_000,
                "last_activity_date": 1_700_000_100,
                "score": 1,
                "view_count": 2,
                "answer_count": 1,
                "is_answered": True,
            }
        ],
        "has_more": has_more,
        "quota_max": 300,
        "quota_remaining": quota_remaining,
    }
    if backoff is not None:
        payload["backoff"] = backoff
    return payload


def answer_payload(answer_id: int, question_id: int, *, has_more: bool) -> dict[str, object]:
    return {
        "items": [
            {
                "answer_id": answer_id,
                "question_id": question_id,
                "body": "<p>Ответ</p>",
                "creation_date": 1_700_000_200,
                "last_activity_date": 1_700_000_300,
                "score": 4,
                "is_accepted": True,
            }
        ],
        "has_more": has_more,
        "quota_max": 300,
        "quota_remaining": 200,
    }


@pytest.mark.asyncio
async def test_question_request_and_pagination_use_ru_python() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(200, json=question_payload(page, has_more=page == 1))

    fake = FakeTime()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(), client=http, sleep=fake.sleep, clock=fake.clock
        )
        pages = [page async for page in client.iterate_questions(sort="creation")]

    assert [page.page for page in pages] == [1, 2]
    assert requests[0].url.path == "/2.3/questions"
    assert requests[0].url.params["site"] == "ru.stackoverflow"
    assert requests[0].url.params["tagged"] == "python"
    assert int(requests[0].url.params["pagesize"]) <= 100


@pytest.mark.asyncio
async def test_missing_has_more_and_empty_page_stop_iteration() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(200, json={"items": [], "quota_remaining": 100})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        pages = [
            page
            async for page in StackExchangeClient(stack_settings(), client=http).iterate_questions(
                sort="activity"
            )
        ]

    assert pages == []
    assert calls == 1


@pytest.mark.asyncio
async def test_answers_are_batched_and_paginated() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(200, json=answer_payload(page, 10, has_more=page == 1))

    fake = FakeTime()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(), client=http, sleep=fake.sleep, clock=fake.clock
        )
        pages = [page async for page in client.fetch_answers_for_question_ids([10, 11, 10])]

    assert len(pages) == 2
    assert requests[0].url.path == "/2.3/questions/10;11/answers"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_answer_batch_rejects_more_than_one_hundred_ids() -> None:
    client = StackExchangeClient(stack_settings())
    with pytest.raises(StackExchangePermanentError) as raised:
        _ = [page async for page in client.fetch_answers_for_question_ids(range(1, 102))]
    await client.aclose()
    assert raised.value.code == "STACKEXCHANGE_INVALID_ANSWER_BATCH"


@pytest.mark.asyncio
async def test_wrapper_backoff_delays_next_same_method() -> None:
    calls = 0
    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(
            200,
            json=question_payload(calls, has_more=calls == 1, backoff=2 if calls == 1 else None),
        )

    async def on_event(code: str, message: str, metrics: Mapping[str, object]) -> None:
        del message, metrics
        events.append(code)

    fake = FakeTime()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(),
            client=http,
            sleep=fake.sleep,
            clock=fake.clock,
            on_event=on_event,
        )
        _ = [page async for page in client.iterate_questions(sort="creation")]

    assert sum(fake.sleeps) >= 2
    assert events == ["STACKEXCHANGE_BACKOFF"]


@pytest.mark.asyncio
async def test_retry_after_and_retryable_status_are_bounded() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=question_payload(1))

    fake = FakeTime()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(), client=http, sleep=fake.sleep, clock=fake.clock
        )
        pages = [page async for page in client.iterate_questions(sort="creation")]

    assert len(pages) == 1
    assert calls == 2
    assert sum(fake.sleeps) >= 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [502, 503, 504])
async def test_transient_server_errors_exhaust_retries(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(status)

    fake = FakeTime()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(STACKEXCHANGE_MAX_RETRIES=1),
            client=http,
            sleep=fake.sleep,
            clock=fake.clock,
            random_value=lambda: 0,
        )
        with pytest.raises(StackExchangeRetryExhausted):
            _ = [page async for page in client.iterate_questions(sort="creation")]

    assert calls == 2


@pytest.mark.asyncio
async def test_permanent_http_error_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(400)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        with pytest.raises(StackExchangePermanentError):
            _ = [
                page
                async for page in StackExchangeClient(
                    stack_settings(), client=http
                ).iterate_questions(sort="creation")
            ]

    assert calls == 1


@pytest.mark.asyncio
async def test_quota_metrics_are_reported_and_reserve_stops_fetch() -> None:
    observed: list[StackExchangeResponseMetrics] = []

    async def metrics(value: StackExchangeResponseMetrics) -> None:
        observed.append(value)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=question_payload(1, quota_remaining=5),
            request=request,
        )
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        with pytest.raises(StackExchangeQuotaLow):
            _ = [
                page
                async for page in StackExchangeClient(
                    stack_settings(), client=http, on_metrics=metrics
                ).iterate_questions(sort="creation")
            ]

    assert observed[0].quota_remaining == 5
    assert observed[0].quota_max == 300


@pytest.mark.asyncio
async def test_cancellation_interrupts_method_backoff() -> None:
    calls = 0
    fake = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(200, json=question_payload(1, has_more=True, backoff=3))

    async def cancelled() -> bool:
        return fake.value >= 0.25

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(),
            client=http,
            sleep=fake.sleep,
            clock=fake.clock,
            cancellation_check=cancelled,
        )
        with pytest.raises(StackExchangeCancelled):
            _ = [page async for page in client.iterate_questions(sort="creation")]

    assert calls == 1


@pytest.mark.asyncio
async def test_response_size_limit_is_enforced() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 2048, request=request)
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        client = StackExchangeClient(
            stack_settings(STACKEXCHANGE_MAX_RESPONSE_BYTES=1024), client=http
        )
        with pytest.raises(StackExchangeResponseTooLarge):
            _ = [page async for page in client.iterate_questions(sort="creation")]


@pytest.mark.asyncio
async def test_api_key_is_not_exposed_by_repr_or_safe_error() -> None:
    secret = "super-secret-stack-key"
    settings = stack_settings(STACKEXCHANGE_KEY=secret)
    assert secret not in repr(settings)
    transport = httpx.MockTransport(lambda request: httpx.Response(403, request=request))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.stackexchange.com/2.3/",
    ) as http:
        with pytest.raises(StackExchangePermanentError) as raised:
            _ = [
                page
                async for page in StackExchangeClient(settings, client=http).iterate_questions(
                    sort="creation"
                )
            ]
    assert secret not in str(raised.value)
