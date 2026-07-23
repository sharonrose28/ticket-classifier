"""Shared pytest fixtures."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - register every mapped table
from app.db.base import Base
from app.models.ticket import Ticket, TicketStatus


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


def make_ticket(**overrides) -> Ticket:
    now = datetime.now(timezone.utc)
    values = {
        "title": "Cannot save profile",
        "description": "The save button returns an error.",
        "status": TicketStatus.PENDING,
        "urgency": None,
        "category": None,
        "assigned_queue": None,
        "confidence": None,
        "llm_model": None,
        "tokens_used": 0,
        "processing_time": None,
        "retry_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return Ticket(**values)
