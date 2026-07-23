"""Celery entry point for the ticket classification workflow."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from celery import Task
from celery import group
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.logging import (
    bind_request_id,
    bind_ticket_id,
    get_request_id,
    reset_request_id,
    reset_ticket_id,
)
from app.core.telemetry import CLASSIFICATION_RETRIES, metric_error_reason
from app.db.session import dispose_engine, get_session_factory
from app.services.classification_service import ClassificationService
from app.services.openai_service import is_retryable_openai_error
from app.tasks.dead_letter import dead_letter_ticket_task
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(slots=True)
class WorkflowFailure:
    error: Exception
    retryable: bool


@celery_app.task(
    bind=True,
    name="tickets.classify",
    max_retries=settings.celery_task_max_retries,
    acks_late=True,
    reject_on_worker_lost=True,
)
def classify_ticket_task(
    self: Task, ticket_id: str, request_id: str | None = None
) -> dict[str, str]:
    """Run an async classification workflow inside a Celery worker process."""

    request_token = bind_request_id(request_id or self.request.id)
    ticket_token = bind_ticket_id(ticket_id)
    try:
        parsed_ticket_id = uuid.UUID(ticket_id)
        retry_available = self.request.retries < self.max_retries
        failure = asyncio.run(
            _run_and_record_failure(
                parsed_ticket_id,
                retry_available=retry_available,
                task_id=self.request.id,
                retry_count=self.request.retries,
            )
        )

        if failure is None:
            return {"ticket_id": ticket_id, "status": "complete"}

        if failure.retryable and retry_available:
            countdown = min(300, 10 * (2 ** self.request.retries))
            CLASSIFICATION_RETRIES.labels(
                layer="celery", reason=metric_error_reason(failure.error)
            ).inc()
            raise self.retry(exc=failure.error, countdown=countdown)

        try:
            dead_letter_ticket_task.apply_async(
                kwargs={
                    "ticket_id": ticket_id,
                    "task_id": self.request.id,
                    "request_id": request_id,
                    "error_type": type(failure.error).__name__,
                    "retry_count": self.request.retries,
                },
                queue="classification.dead_letter",
            )
        except Exception:
            # The durable dead_letters row was already committed; Redis notification
            # failure must not erase the audit trail.
            logger.exception(
                "Could not publish dead-letter notification",
                extra={"source_task_id": self.request.id},
            )
        raise failure.error
    finally:
        reset_ticket_id(ticket_token)
        reset_request_id(request_token)


def enqueue_ticket_classification(ticket_id: uuid.UUID) -> str:
    """Publish a JSON-safe classification message after ticket commit."""

    result = classify_ticket_task.apply_async(
        args=[str(ticket_id), get_request_id()], queue="classification.default"
    )
    return result.id


def enqueue_ticket_classification_batch(ticket_ids: list[uuid.UUID]):
    """Publish one Celery group so available workers classify tickets in parallel."""

    request_id = get_request_id()
    job = group(
        classify_ticket_task.s(str(ticket_id), request_id).set(
            queue="classification.default"
        )
        for ticket_id in ticket_ids
    )
    return job.apply_async()


async def _run_and_record_failure(
    ticket_id: uuid.UUID,
    *,
    retry_available: bool,
    task_id: str,
    retry_count: int,
) -> WorkflowFailure | None:
    try:
        try:
            async with get_session_factory()() as session:
                await ClassificationService(session).process(ticket_id)
            return None
        except Exception as exc:
            retryable = is_retryable_openai_error(exc) or isinstance(
                exc, (SQLAlchemyError, ConnectionError, TimeoutError)
            )
            will_retry = retryable and retry_available
            try:
                async with get_session_factory()() as failure_session:
                    await ClassificationService(failure_session).record_failure(
                        ticket_id,
                        will_retry=will_retry,
                        task_id=task_id,
                        retry_count=retry_count,
                        error=exc,
                    )
            except Exception:
                logger.exception(
                    "Could not persist ticket failure state",
                    extra={"ticket_id": str(ticket_id)},
                )
            return WorkflowFailure(error=exc, retryable=retryable)
    finally:
        # asyncio.run creates a loop per task; dispose pooled connections on that loop.
        await dispose_engine()
