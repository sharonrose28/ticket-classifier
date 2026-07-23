import logging
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

from app.core.config import Settings
from app.schemas.classification import TicketClassification
from app.services.openai_service import (
    AllModelsFailedError,
    OpenAIService,
    is_retryable_openai_error,
)

CLASSIFICATION = TicketClassification(
    urgency="high",
    category="technical",
    confidence=0.91,
    reasoning="The customer cannot use a core workflow.",
)


def api_error(status_code: int, **headers) -> APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request, headers=headers)
    return APIStatusError("provider error", response=response, body=None)


class ScriptedClassifier:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.models = []

    async def classify_with_response(self, *, model, **_kwargs):
        self.models.append(model)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return CLASSIFICATION, SimpleNamespace(
            model=model,
            id="resp_123",
            usage=SimpleNamespace(
                input_tokens=20,
                input_tokens_details=SimpleNamespace(cached_tokens=5),
                output_tokens=10,
                total_tokens=30,
            ),
        )


@pytest.fixture
def settings():
    return Settings(
        openai_primary_model="gpt-4.1",
        openai_fallback_model="gpt-4.1-mini",
        openai_max_attempts=5,
        openai_backoff_base_seconds=0.001,
        openai_backoff_max_seconds=0.01,
    )


@pytest.mark.asyncio
async def test_retries_transient_failure_then_succeeds(settings, caplog):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    classifier = ScriptedClassifier([api_error(503), TimeoutError(), object()])
    with caplog.at_level(logging.INFO, logger="app.services.openai_service"):
        result = await OpenAIService(
            classifier=classifier, settings=settings, sleep=sleep
        ).classify_ticket(title="x", description="y")

    assert result.model == "gpt-4.1"
    assert result.attempt_count == 3
    assert result.cached_input_tokens == 5
    assert result.estimated_cost_usd == pytest.approx(0.0001125)
    assert len(delays) == 2
    retry_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "openai.classification.retry_scheduled"
    ]
    assert len(retry_records) == 2


@pytest.mark.asyncio
async def test_primary_exhaustion_activates_fallback(settings, caplog):
    classifier = ScriptedClassifier([TimeoutError()] * 5 + [object()])

    async def no_sleep(_delay):
        return None

    with caplog.at_level(logging.INFO, logger="app.services.openai_service"):
        result = await OpenAIService(
            classifier=classifier, settings=settings, sleep=no_sleep
        ).classify_ticket(title="x", description="y")

    assert result.model == "gpt-4.1-mini"
    assert result.attempt_count == 6
    assert classifier.models == ["gpt-4.1"] * 5 + ["gpt-4.1-mini"]
    fallback = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "openai.classification.fallback_activated"
    ]
    assert fallback[0].reason == "TimeoutError"


@pytest.mark.asyncio
async def test_both_models_exhaust_attempt_budget(settings):
    classifier = ScriptedClassifier([TimeoutError()] * 10)

    async def no_sleep(_delay):
        return None

    with pytest.raises(AllModelsFailedError) as raised:
        await OpenAIService(
            classifier=classifier, settings=settings, sleep=no_sleep
        ).classify_ticket(title="x", description="y")
    assert raised.value.attempts == 10


@pytest.mark.asyncio
async def test_permanent_error_is_not_retried_or_fallbacked(settings):
    classifier = ScriptedClassifier([api_error(400)])
    with pytest.raises(APIStatusError):
        await OpenAIService(classifier=classifier, settings=settings).classify_ticket(
            title="x", description="y"
        )
    assert classifier.models == ["gpt-4.1"]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_status_codes(status):
    assert is_retryable_openai_error(api_error(status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 501])
def test_non_retryable_status_codes(status):
    assert not is_retryable_openai_error(api_error(status))


def test_retry_after_header_is_respected(settings):
    service = OpenAIService(classifier=object(), settings=settings)
    assert service._retry_delay(1, api_error(429, **{"retry-after": "2"})) >= 2
