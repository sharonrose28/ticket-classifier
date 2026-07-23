import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.ticket import TicketStatus
from app.schemas.ticket import TicketRead
from app.services.cache_service import TicketCache
from tests.conftest import make_ticket


@pytest.mark.asyncio
async def test_cache_round_trip_uses_ttl():
    ticket = TicketRead.model_validate(
        make_ticket(id=uuid.uuid4(), status=TicketStatus.COMPLETE)
    )
    redis = AsyncMock()
    redis.get.return_value = ticket.model_dump_json()
    cache = TicketCache(redis, ttl_seconds=120)

    assert await cache.get(ticket.id) == ticket
    await cache.set(ticket)

    redis.set.assert_awaited_once()
    assert redis.set.await_args.kwargs["ex"] == 120


@pytest.mark.asyncio
async def test_cache_miss_and_failure_fail_open():
    redis = AsyncMock()
    redis.get.return_value = None
    cache = TicketCache(redis, ttl_seconds=10)
    assert await cache.get(uuid.uuid4()) is None

    redis.get.side_effect = TimeoutError()
    assert await cache.get(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_cache_write_failure_is_non_fatal():
    ticket = TicketRead.model_validate(
        make_ticket(id=uuid.uuid4(), status=TicketStatus.COMPLETE)
    )
    redis = AsyncMock()
    redis.set.side_effect = ConnectionError()
    await TicketCache(redis, ttl_seconds=10).set(ticket)
