"""Liveness and dependency-readiness endpoints."""

import logging
from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report whether the API process can serve requests."""

    return HealthResponse(status="ok")


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    """Kubernetes/Docker liveness probe; no dependency calls by design."""

    return HealthResponse(status="ok")


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready():
    """Verify PostgreSQL and the Redis broker before accepting traffic."""

    database_status = "ok"
    redis_status = "ok"
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        database_status = "unavailable"
        logger.warning(
            "Readiness database check failed",
            extra={"event": "readiness.database.failed", "error_type": type(exc).__name__},
        )

    settings = get_settings()
    redis_client: Redis | None = None
    try:
        redis_client = Redis.from_url(
            settings.celery_broker_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await redis_client.ping()
    except Exception as exc:
        redis_status = "unavailable"
        logger.warning(
            "Readiness Redis check failed",
            extra={"event": "readiness.redis.failed", "error_type": type(exc).__name__},
        )
    finally:
        if redis_client is not None:
            await redis_client.aclose()

    payload = {
        "status": "ready"
        if database_status == "ok" and redis_status == "ok"
        else "not_ready",
        "database": database_status,
        "redis": redis_status,
    }
    if payload["status"] == "not_ready":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload
        )
    return ReadinessResponse.model_validate(payload)
