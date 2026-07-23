"""Ticket persistence operations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, title: str, description: str, customer_id: uuid.UUID | None = None) -> Ticket:
        ticket = Ticket(title=title, description=description, customer_id=customer_id)
        self.session.add(ticket)
        await self.session.flush()
        await self.session.refresh(ticket)
        return ticket

    async def create_many(self, items: list[tuple[str, str]], *, customer_id: uuid.UUID | None = None) -> list[Ticket]:
        """Insert a batch with one flush instead of one round trip per ticket."""

        result = await self.session.scalars(
            insert(Ticket).returning(Ticket),
            [{"title": title, "description": description, "customer_id": customer_id} for title, description in items],
        )
        return list(result.all())

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        return await self.session.get(Ticket, ticket_id)

    async def get_for_update(self, ticket_id: uuid.UUID) -> Ticket | None:
        result = await self.session.execute(
            select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list(self, *, limit: int, offset: int) -> tuple[list[Ticket], int]:
        items_result = await self.session.execute(
            select(Ticket)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total_result = await self.session.execute(select(func.count()).select_from(Ticket))
        return list(items_result.scalars().all()), total_result.scalar_one()

    async def list_for_customer(self, customer_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[Ticket], int]:
        where = Ticket.customer_id == customer_id
        return await self._list_where(where, limit=limit, offset=offset)

    async def list_for_agent(self, agent_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[Ticket], int]:
        where = Ticket.assigned_agent_id == agent_id
        return await self._list_where(where, limit=limit, offset=offset)

    async def _list_where(self, where, *, limit: int, offset: int) -> tuple[list[Ticket], int]:
        items = await self.session.scalars(select(Ticket).where(where).order_by(Ticket.created_at.desc()).limit(limit).offset(offset))
        total = await self.session.scalar(select(func.count()).select_from(Ticket).where(where))
        return list(items.all()), int(total or 0)
