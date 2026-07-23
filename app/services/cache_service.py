"""Cache-aside access to immutable completed ticket representations."""

import logging
import uuid

from redis.asyncio import Redis

from app.core.telemetry import CACHE_REQUESTS
from app.schemas.ticket import TicketRead

logger = logging.getLogger(__name__)


class TicketCache:
    def __init__(self, redis: Redis | None, *, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    async def get(self, ticket_id: uuid.UUID) -> TicketRead | None:
        if self.redis is None:
            return None
        try:
            value = await self.redis.get(self._key(ticket_id))
            if value is None:
                CACHE_REQUESTS.labels(outcome="miss").inc()
                return None
            CACHE_REQUESTS.labels(outcome="hit").inc()
            return TicketRead.model_validate_json(value)
        except Exception as exc:
            CACHE_REQUESTS.labels(outcome="error").inc()
            logger.warning(
                "Ticket cache read failed",
                extra={"event": "cache.read_failed", "error_type": type(exc).__name__},
            )
            return None

    async def set(self, ticket: TicketRead) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(
                self._key(ticket.id), ticket.model_dump_json(), ex=self.ttl_seconds
            )
        except Exception as exc:
            logger.warning(
                "Ticket cache write failed",
                extra={"event": "cache.write_failed", "error_type": type(exc).__name__},
            )

    @staticmethod
    def _key(ticket_id: uuid.UUID) -> str:
        return f"ticket:v1:{ticket_id}"
