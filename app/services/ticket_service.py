"""Ticket intake and retrieval use cases."""

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TaskDispatchError, TicketNotFoundError
from app.models.ticket import Ticket
from app.repositories.tickets import TicketRepository
from app.core.telemetry import BATCH_SIZE
from app.schemas.ticket import TicketCreate, TicketRead
from app.services.cache_service import TicketCache
from app.core.exceptions import AuthorizationError
from app.models.user import User, UserRole
from app.models.ticket import TicketStatus, TicketUrgency
from app.schemas.ticket import ClassificationCorrection
from app.services.routing_service import RoutingService


logger = logging.getLogger(__name__)

TaskDispatcher = Callable[[uuid.UUID], Any]
BatchTaskDispatcher = Callable[[list[uuid.UUID]], Any]


def _dispatch_classification(ticket_id: uuid.UUID) -> Any:
    from app.tasks.classification import enqueue_ticket_classification

    return enqueue_ticket_classification(ticket_id)


def _dispatch_classification_batch(ticket_ids: list[uuid.UUID]) -> Any:
    from app.tasks.classification import enqueue_ticket_classification_batch

    return enqueue_ticket_classification_batch(ticket_ids)


class TicketService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        task_dispatcher: TaskDispatcher = _dispatch_classification,
        batch_task_dispatcher: BatchTaskDispatcher = _dispatch_classification_batch,
        cache: TicketCache | None = None,
        current_user: User | None = None,
    ) -> None:
        self.session = session
        self.repository = TicketRepository(session)
        self.task_dispatcher = task_dispatcher
        self.batch_task_dispatcher = batch_task_dispatcher
        self.cache = cache
        self.current_user = current_user

    async def create(self, payload: TicketCreate) -> Ticket:
        if self.current_user is not None and self.current_user.role not in {UserRole.CUSTOMER, UserRole.ADMIN}:
            raise AuthorizationError()
        ticket = await self.repository.create(
            title=payload.title, description=payload.description,
            customer_id=self.current_user.id if self.current_user else None,
        )
        await self.session.commit()
        try:
            task_id = self.task_dispatcher(ticket.id)
        except Exception as exc:
            logger.exception(
                "Ticket classification dispatch failed",
                extra={"event": "ticket.classification.dispatch_failed", "ticket_id": str(ticket.id)},
            )
            raise TaskDispatchError() from exc
        logger.info(
            "Ticket accepted for classification",
            extra={
                "event": "ticket.created",
                "ticket_id": str(ticket.id),
                "status": ticket.status.value,
                "task_id": str(task_id),
            },
        )
        return ticket

    async def create_batch(
        self, payloads: list[TicketCreate]
    ) -> tuple[list[Ticket], str | None]:
        tickets = await self.repository.create_many(
            [(payload.title, payload.description) for payload in payloads],
            customer_id=self.current_user.id if self.current_user else None,
        )
        await self.session.commit()
        try:
            result = self.batch_task_dispatcher([ticket.id for ticket in tickets])
        except Exception as exc:
            logger.exception(
                "Ticket batch dispatch failed",
                extra={"event": "ticket.batch.dispatch_failed", "batch_size": len(tickets)},
            )
            raise TaskDispatchError() from exc
        BATCH_SIZE.observe(len(tickets))
        return tickets, getattr(result, "id", result if isinstance(result, str) else None)

    async def get(self, ticket_id: uuid.UUID) -> Ticket | TicketRead:
        cache_allowed = self.current_user is None or self.current_user.role is UserRole.ADMIN
        if self.cache is not None and cache_allowed:
            cached = await self.cache.get(ticket_id)
            if cached is not None:
                return cached
        ticket = await self.repository.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        self._authorize_ticket(ticket)
        if self.cache is not None and cache_allowed and ticket.status.value == "complete":
            await self.cache.set(TicketRead.model_validate(ticket))
        return ticket

    async def list(self, *, limit: int, offset: int) -> tuple[list[Ticket], int]:
        if self.current_user is not None:
            if self.current_user.role is UserRole.CUSTOMER:
                return await self.repository.list_for_customer(self.current_user.id, limit=limit, offset=offset)
            if self.current_user.role is UserRole.SUPPORT_AGENT:
                return await self.repository.list_for_agent(self.current_user.id, limit=limit, offset=offset)
        return await self.repository.list(limit=limit, offset=offset)

    async def update_status(self, ticket_id: uuid.UUID, status: TicketStatus) -> Ticket:
        ticket = await self.repository.get_for_update(ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        self._authorize_agent(ticket)
        ticket.status = status
        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    async def correct_classification(self, ticket_id: uuid.UUID, correction: ClassificationCorrection) -> Ticket:
        from decimal import Decimal
        from app.schemas.classification import TicketClassification
        ticket = await self.repository.get_for_update(ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        self._authorize_agent(ticket)
        classification = TicketClassification(**correction.model_dump())
        ticket.urgency = TicketUrgency(classification.urgency.value)
        ticket.category = classification.category.value
        ticket.confidence = Decimal(str(classification.confidence))
        ticket.assigned_queue = RoutingService().assign_queue(classification)
        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    async def assign(self, ticket_id: uuid.UUID, agent_id: uuid.UUID) -> Ticket:
        if self.current_user is None or self.current_user.role is not UserRole.ADMIN:
            raise AuthorizationError()
        from app.repositories.users import UserRepository
        agent = await UserRepository(self.session).get(agent_id)
        if agent is None or agent.role is not UserRole.SUPPORT_AGENT or not agent.is_active:
            raise AuthorizationError("The selected user is not an active support agent.")
        ticket = await self.repository.get_for_update(ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        ticket.assigned_agent_id = agent_id
        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    def _authorize_ticket(self, ticket: Ticket) -> None:
        if self.current_user is None or self.current_user.role is UserRole.ADMIN:
            return
        if self.current_user.role is UserRole.CUSTOMER and ticket.customer_id == self.current_user.id:
            return
        if self.current_user.role is UserRole.SUPPORT_AGENT and ticket.assigned_agent_id == self.current_user.id:
            return
        raise AuthorizationError()

    def _authorize_agent(self, ticket: Ticket) -> None:
        if self.current_user is not None and self.current_user.role is UserRole.ADMIN:
            return
        if self.current_user is not None and self.current_user.role is UserRole.SUPPORT_AGENT and ticket.assigned_agent_id == self.current_user.id:
            return
        raise AuthorizationError()
