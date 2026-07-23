"""Resilient service layer for OpenAI ticket classification."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from openai import APIStatusError, APITimeoutError

from app.ai.client import OpenAIClassifier
from app.ai.pricing import estimate_cost_usd
from app.core.config import Settings, get_settings
from app.core.telemetry import (
    CLASSIFICATION_RETRIES,
    OPENAI_FAILURES,
    OPENAI_FALLBACKS,
    metric_error_reason,
)
from app.schemas.classification import ClassificationResult

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


class OpenAIService:
    """Apply resilience and observability around the provider adapter."""

    def __init__(
        self,
        *,
        classifier: OpenAIClassifier | Any | None = None,
        settings: Settings | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.classifier = classifier or OpenAIClassifier(settings=self.settings)
        self.sleep = sleep

    async def classify_ticket(
        self, *, title: str, description: str
    ) -> ClassificationResult:
        """Classify with the primary model, then fall back after retry exhaustion."""

        started_at = time.perf_counter()
        primary_model = self.settings.openai_primary_model
        fallback_model = self.settings.openai_fallback_model
        fallback_reason: str | None = None

        try:
            classification, response, attempt_count = await self._attempt_model(
                title=title, description=description, model=primary_model
            )
        except OpenAIRetriesExhaustedError as primary_error:
            fallback_reason = _fallback_reason(primary_error.cause)
            OPENAI_FALLBACKS.labels(
                primary_model=primary_model,
                fallback_model=fallback_model,
                reason=metric_error_reason(primary_error.cause),
            ).inc()
            logger.warning(
                "Primary OpenAI model exhausted retries; activating fallback",
                extra={
                    "event": "openai.classification.fallback_activated",
                    "primary_model": primary_model,
                    "fallback_model": fallback_model,
                    "reason": fallback_reason,
                    "primary_attempts": primary_error.attempts,
                },
            )
            try:
                classification, response, fallback_attempts = await self._attempt_model(
                    title=title, description=description, model=fallback_model
                )
            except OpenAIRetriesExhaustedError as fallback_error:
                logger.error(
                    "Primary and fallback OpenAI models exhausted retries",
                    extra={
                        "event": "openai.classification.all_models_failed",
                        "primary_model": primary_model,
                        "fallback_model": fallback_model,
                        "primary_reason": fallback_reason,
                        "fallback_reason": _fallback_reason(fallback_error.cause),
                        "primary_attempts": primary_error.attempts,
                        "fallback_attempts": fallback_error.attempts,
                    },
                )
                raise AllModelsFailedError(
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                ) from fallback_error
            attempt_count = primary_error.attempts + fallback_attempts

        usage = getattr(response, "usage", None)
        input_tokens = _usage_value(usage, "input_tokens")
        input_details = getattr(usage, "input_tokens_details", None)
        cached_input_tokens = _usage_value(input_details, "cached_tokens")
        output_tokens = _usage_value(usage, "output_tokens")
        total_tokens = _usage_value(
            usage, "total_tokens", default=input_tokens + output_tokens
        )
        latency_ms = _milliseconds_since(started_at)
        model = getattr(response, "model", None) or (
            fallback_model if fallback_reason else primary_model
        )
        response_id = getattr(response, "id", None)
        estimated_cost = estimate_cost_usd(
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            settings=self.settings,
        )

        result = ClassificationResult(
            classification=classification,
            model=model,
            response_id=response_id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=float(estimated_cost),
            latency_ms=latency_ms,
            attempt_count=attempt_count,
        )
        logger.info(
            "OpenAI ticket classification completed",
            extra={
                "event": "openai.classification.completed",
                "model": result.model,
                "primary_model": primary_model,
                "fallback_model": fallback_model,
                "fallback_used": fallback_reason is not None,
                "fallback_reason": fallback_reason,
                "confidence": result.classification.confidence,
                "response_id": result.response_id,
                "attempt_count": result.attempt_count,
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "cached_input_tokens": result.cached_input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "estimated_cost_usd": result.estimated_cost_usd,
            },
        )
        return result

    async def _attempt_model(
        self, *, title: str, description: str, model: str
    ) -> tuple[Any, Any, int]:
        """Run one model's bounded retry budget."""

        for attempt in range(1, self.settings.openai_max_attempts + 1):
            attempt_started_at = time.perf_counter()
            try:
                async with asyncio.timeout(self.settings.openai_timeout_seconds):
                    classification, response = (
                        await self.classifier.classify_with_response(
                            title=title, description=description, model=model
                        )
                    )
            except Exception as exc:
                attempt_latency_ms = _milliseconds_since(attempt_started_at)
                retryable = is_retryable_openai_error(exc)
                is_final = attempt >= self.settings.openai_max_attempts
                reason = metric_error_reason(exc)
                OPENAI_FAILURES.labels(model=model, reason=reason).inc()

                logger.warning(
                    "OpenAI classification attempt failed",
                    extra={
                        "event": "openai.classification.attempt_failed",
                        "model": model,
                        "attempt": attempt,
                        "max_attempts": self.settings.openai_max_attempts,
                        "latency_ms": attempt_latency_ms,
                        "retryable": retryable,
                        "error_type": type(exc).__name__,
                    },
                    exc_info=is_final or not retryable,
                )

                if is_final or not retryable:
                    if retryable:
                        raise OpenAIRetriesExhaustedError(
                            model=model, attempts=attempt, cause=exc
                        ) from exc
                    raise

                delay = self._retry_delay(attempt, exc)
                CLASSIFICATION_RETRIES.labels(layer="openai", reason=reason).inc()
                logger.info(
                    "Scheduling OpenAI classification retry",
                    extra={
                        "event": "openai.classification.retry_scheduled",
                        "model": model,
                        "attempt": attempt,
                        "next_attempt": attempt + 1,
                        "max_attempts": self.settings.openai_max_attempts,
                        "status_code": _status_code(exc),
                        "error_type": type(exc).__name__,
                        "delay_seconds": delay,
                    },
                )
                await self.sleep(delay)
                continue

            return classification, response, attempt

        raise RuntimeError("OpenAI retry loop exited unexpectedly")

    def _retry_delay(self, failed_attempt: int, exc: Exception) -> float:
        cap = min(
            self.settings.openai_backoff_max_seconds,
            self.settings.openai_backoff_base_seconds * (2 ** (failed_attempt - 1)),
        )
        exponential_delay = random.uniform(0, cap)
        retry_after = _retry_after_seconds(exc)
        if retry_after is None:
            return exponential_delay
        return max(
            exponential_delay,
            min(retry_after, self.settings.openai_retry_after_max_seconds),
        )


class OpenAIRetriesExhaustedError(RuntimeError):
    """All permitted attempts failed with a transient provider error."""

    def __init__(self, *, model: str, attempts: int, cause: Exception) -> None:
        self.model = model
        self.attempts = attempts
        self.cause = cause
        super().__init__(
            f"OpenAI model {model} failed after {attempts} attempts: "
            f"{type(cause).__name__}"
        )


class AllModelsFailedError(OpenAIRetriesExhaustedError):
    """Both the primary and fallback model exhausted their retry budgets."""

    def __init__(
        self,
        *,
        primary_error: OpenAIRetriesExhaustedError,
        fallback_error: OpenAIRetriesExhaustedError,
    ) -> None:
        self.primary_error = primary_error
        self.fallback_error = fallback_error
        super().__init__(
            model=fallback_error.model,
            attempts=primary_error.attempts + fallback_error.attempts,
            cause=fallback_error.cause,
        )


def is_retryable_openai_error(exc: Exception) -> bool:
    if isinstance(exc, OpenAIRetriesExhaustedError):
        return False
    if isinstance(exc, (TimeoutError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {429, 500, 502, 503, 504}
    return False


def _status_code(exc: Exception) -> int | None:
    return exc.status_code if isinstance(exc, APIStatusError) else None


def _fallback_reason(exc: Exception) -> str:
    status_code = _status_code(exc)
    return (
        f"{type(exc).__name__} (HTTP {status_code})"
        if status_code is not None
        else type(exc).__name__
    )


def _retry_after_seconds(exc: Exception) -> float | None:
    if not isinstance(exc, APIStatusError):
        return None

    headers = exc.response.headers
    retry_after_ms = headers.get("retry-after-ms")
    if retry_after_ms:
        try:
            return max(0.0, float(retry_after_ms) / 1000)
        except ValueError:
            pass

    retry_after = headers.get("retry-after")
    if not retry_after:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _usage_value(usage: Any, name: str, *, default: int = 0) -> int:
    value = getattr(usage, name, None)
    return default if value is None else max(0, int(value))


def _milliseconds_since(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))
