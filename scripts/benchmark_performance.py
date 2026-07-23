"""Reproducible local benchmark for persistence round trips and batching."""

import asyncio
import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - register metadata
from app.db.base import Base
from app.repositories.tickets import TicketRepository


async def run(size: int = 100) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    statements = 0

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def count_statements(*_args):
        nonlocal statements
        statements += 1

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    statements = 0
    started = time.perf_counter()
    async with factory() as session:
        repository = TicketRepository(session)
        for index in range(size):
            await repository.create(title=f"Ticket {index}", description="benchmark")
        await session.rollback()
    sequential_ms = (time.perf_counter() - started) * 1000
    sequential_statements = statements

    statements = 0
    started = time.perf_counter()
    async with factory() as session:
        repository = TicketRepository(session)
        await repository.create_many(
            [(f"Ticket {index}", "benchmark") for index in range(size)]
        )
        await session.rollback()
    batch_ms = (time.perf_counter() - started) * 1000

    print(f"tickets={size}")
    print(f"sequential: {sequential_ms:.2f} ms, SQL statements={sequential_statements}")
    print(f"batch:      {batch_ms:.2f} ms, SQL statements={statements}")
    print(f"latency speedup: {sequential_ms / batch_ms:.2f}x")
    print(f"statement reduction: {(1 - statements / sequential_statements) * 100:.1f}%")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
