"""Database-backed ticket classification workflow."""

import logging
import time
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import TicketNotFoundError
from app.core.telemetry import CLASSIFICATION_LATENCY, TICKETS_PROCESSED
from app.models.dead_letter import DeadLetter
from app.models.ticket import Ticket, TicketStatus, TicketUrgency
from app.repositories.tickets import TicketRepository
from app.services.local_classifier import LocalClassificationService
from app.services.openai_service import OpenAIRetriesExhaustedError, OpenAIService
from app.services.routing_service import RoutingService

logger = logging.getLogger(__name__)


class ClassificationService:
    """Coordinate state transitions, classification, and queue routing."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        openai_service: OpenAIService | None = None,
        routing_service: RoutingService | None = None,
    ) -> None:
        self.session = session
        self.repository = TicketRepository(session)
        self.openai_service = openai_service
        self.routing_service = routing_service or RoutingService()

    async def process(self, ticket_id: uuid.UUID) -> Ticket:
        started_at = time.perf_counter()
        ticket_input = await self._claim(ticket_id)
        if ticket_input is None:
            ticket = await self.repository.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError()
            return ticket

        title, description = ticket_input
        openai_service = self.openai_service or self._default_classifier()
        result = await openai_service.classify_ticket(title=title, description=description)
        assigned_queue = self.routing_service.assign_queue(result.classification)

        ticket = await self.repository.get_for_update(ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        if ticket.status is TicketStatus.COMPLETE:
            await self.session.rollback()
            return ticket

        ticket.urgency = TicketUrgency(result.classification.urgency.value)
        ticket.category = result.classification.category.value
        ticket.assigned_queue = assigned_queue
        ticket.confidence = Decimal(str(result.classification.confidence))
        ticket.llm_model = result.model
        ticket.tokens_used = result.total_tokens
        ticket.processing_time = max(0, round((time.perf_counter() - started_at) * 1000))
        ticket.estimated_cost_usd = Decimal(str(result.estimated_cost_usd))
        ticket.retry_count += result.attempt_count - 1
        ticket.status = TicketStatus.COMPLETE
        await self.session.commit()
        CLASSIFICATION_LATENCY.observe(ticket.processing_time / 1000)
        TICKETS_PROCESSED.labels(status="complete").inc()
        logger.info(
            "Ticket classification persisted and routed",
            extra={
                "event": "ticket.classification.completed",
                "ticket_id": str(ticket.id),
                "openai_model": ticket.llm_model,
                "confidence": float(ticket.confidence),
                "tokens": ticket.tokens_used,
                "queue": ticket.assigned_queue,
                "processing_time_ms": ticket.processing_time,
                "estimated_cost_usd": float(ticket.estimated_cost_usd),
                "retry_count": ticket.retry_count,
                "status": ticket.status.value,
            },
        )
        return ticket

    @staticmethod
    def _default_classifier() -> OpenAIService | LocalClassificationService:
        settings = get_settings()
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            logger.warning(
                "OpenAI credential unavailable; using deterministic fallback",
                extra={"event": "ticket.classification.local_fallback"},
            )
            return LocalClassificationService()
        return OpenAIService(settings=settings)

    async def record_failure(
        self,
        ticket_id: uuid.UUID,
        *,
        will_retry: bool,
        task_id: str,
        retry_count: int,
        error: Exception,
    ) -> None:
        ticket = await self.repository.get_for_update(ticket_id)
        if ticket is None or ticket.status is TicketStatus.COMPLETE:
            await self.session.rollback()
            return
        retry_increment = (
            max(0, error.attempts - 1) if isinstance(error, OpenAIRetriesExhaustedError) else 1
        )
        ticket.retry_count += retry_increment
        ticket.status = TicketStatus.PENDING if will_retry else TicketStatus.FAILED
        if not will_retry:
            existing = await self.session.scalar(
                select(DeadLetter.id).where(DeadLetter.task_id == task_id)
            )
            if existing is None:
                self.session.add(
                    DeadLetter(
                        ticket_id=ticket_id,
                        task_id=task_id,
                        task_name="tickets.classify",
                        error_type=type(error).__name__[:255],
                        error_message=_safe_error_message(error),
                        retry_count=max(retry_count, ticket.retry_count),
                    )
                )
        await self.session.commit()
        if not will_retry:
            TICKETS_PROCESSED.labels(status="failed").inc()
        logger.log(
            logging.WARNING if will_retry else logging.ERROR,
            "Ticket classification failed",
            extra={
                "event": "ticket.classification.failed",
                "ticket_id": str(ticket_id),
                "status": ticket.status.value,
                "will_retry": will_retry,
                "retry_count": ticket.retry_count,
                "error_type": type(error).__name__,
                "error_message": _safe_error_message(error),
            },
        )

    async def _claim(self, ticket_id: uuid.UUID) -> tuple[str, str] | None:
        ticket = await self.repository.get_for_update(ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        if ticket.status is TicketStatus.COMPLETE:
            await self.session.rollback()
            return None
        ticket.status = TicketStatus.PROCESSING
        title, description = ticket.title, ticket.description
        await self.session.commit()
        logger.info(
            "Ticket classification started",
            extra={
                "event": "ticket.classification.started",
                "ticket_id": str(ticket_id),
                "status": TicketStatus.PROCESSING.value,
            },
        )
        return title, description


def _safe_error_message(error: Exception) -> str:
    message = str(error).replace("\n", " ").replace("\r", " ").strip()
    return (message or type(error).__name__)[:1000]
