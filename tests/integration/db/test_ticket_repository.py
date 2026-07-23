import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.dead_letter import DeadLetter
from app.models.ticket import TicketStatus
from app.repositories.tickets import TicketRepository
from app.schemas.ticket import TicketCreate
from app.services.classification_service import ClassificationService
from app.services.openai_service import OpenAIRetriesExhaustedError
from app.services.ticket_service import TicketService
from tests.conftest import make_ticket


@pytest.mark.asyncio
async def test_repository_create_get_and_list(session):
    repository = TicketRepository(session)
    ticket = await repository.create(title="Billing error", description="Charged twice")
    await session.commit()

    loaded = await repository.get(ticket.id)
    items, total = await repository.list(limit=10, offset=0)

    assert loaded is ticket
    assert loaded.status is TicketStatus.PENDING
    assert total == 1
    assert items[0].title == "Billing error"


@pytest.mark.asyncio
async def test_repository_create_many_uses_one_transaction(session):
    repository = TicketRepository(session)
    tickets = await repository.create_many([("A", "one"), ("B", "two")])
    await session.commit()
    assert len(tickets) == 2
    assert (await repository.list(limit=10, offset=0))[1] == 2


@pytest.mark.asyncio
async def test_ticket_service_commits_then_dispatches(session):
    dispatched = []
    service = TicketService(session, task_dispatcher=dispatched.append)

    ticket = await service.create(
        TicketCreate(title="Login issue", description="Cannot access account")
    )

    assert dispatched == [ticket.id]
    assert (await session.get(type(ticket), ticket.id)).status is TicketStatus.PENDING
    assert await service.get(ticket.id) is ticket
    items, total = await service.list(limit=20, offset=0)
    assert total == 1 and items == [ticket]


@pytest.mark.asyncio
async def test_ticket_service_batch_commits_once_and_dispatches_group(session):
    dispatched = []

    def dispatch(ids):
        dispatched.append(ids)
        return SimpleNamespace(id="group-42")

    service = TicketService(
        session,
        task_dispatcher=lambda _id: None,
        batch_task_dispatcher=dispatch,
    )
    tickets, group_id = await service.create_batch(
        [TicketCreate(title="A", description="one"), TicketCreate(title="B", description="two")]
    )

    assert group_id == "group-42"
    assert dispatched == [[ticket.id for ticket in tickets]]
    assert (await service.list(limit=10, offset=0))[1] == 2


@pytest.mark.asyncio
async def test_ticket_service_cache_hit_skips_database(session):
    cached = make_ticket(id=uuid.uuid4(), status=TicketStatus.COMPLETE)
    cache = SimpleNamespace(get=AsyncMock(return_value=cached), set=AsyncMock())
    service = TicketService(session, task_dispatcher=lambda _id: None, cache=cache)

    assert await service.get(cached.id) is cached
    cache.get.assert_awaited_once_with(cached.id)


@pytest.mark.asyncio
async def test_ticket_service_caches_completed_database_result(session):
    ticket = await TicketRepository(session).create(title="Done", description="Complete")
    ticket.status = TicketStatus.COMPLETE
    await session.commit()
    session.expunge(ticket)
    cache = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())

    await TicketService(session, task_dispatcher=lambda _id: None, cache=cache).get(ticket.id)

    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_ticket_service_not_found(session):
    from app.core.exceptions import TicketNotFoundError

    with pytest.raises(TicketNotFoundError):
        await TicketService(session, task_dispatcher=lambda _id: None).get(uuid.uuid4())


@pytest.mark.asyncio
async def test_terminal_failure_creates_durable_dead_letter(session):
    repository = TicketRepository(session)
    ticket = await repository.create(title="Broken", description="Still broken")
    ticket.status = TicketStatus.PROCESSING
    await session.commit()

    underlying = TimeoutError("provider timeout")
    error = OpenAIRetriesExhaustedError(
        model="gpt-4.1", attempts=5, cause=underlying
    )
    await ClassificationService(session).record_failure(
        ticket.id,
        will_retry=False,
        task_id="task-final",
        retry_count=0,
        error=error,
    )

    await session.refresh(ticket)
    dead_letter = await session.scalar(select(DeadLetter))
    assert ticket.status is TicketStatus.FAILED
    assert ticket.retry_count == 4
    assert dead_letter.ticket_id == ticket.id
    assert dead_letter.retry_count == 4
