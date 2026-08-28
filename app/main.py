"""FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.api.middleware import (
    exception_middleware,
    request_context_middleware,
    security_headers_middleware,
)
from app.api.rate_limit import RedisRateLimitMiddleware
from app.api.router import router
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings
from app.db.session import dispose_engine

logger = logging.getLogger(__name__)
FRONTEND_DIR = Path("/app/frontend")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings: Settings = application.state.settings
    application.state.redis = (
        Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        if settings.redis_enabled
        else None
    )
    logger.info("Application started", extra={"event": "application.started"})
    try:
        yield
    finally:
        logger.info("Application shutdown started", extra={"event": "application.stopping"})
        try:
            if application.state.redis is not None:
                await asyncio.wait_for(
                    application.state.redis.aclose(),
                    timeout=settings.shutdown_timeout_seconds,
                )
        except Exception:
            logger.exception("Redis shutdown failed", extra={"event": "redis.shutdown_failed"})
        try:
            await asyncio.wait_for(
                dispose_engine(), timeout=settings.shutdown_timeout_seconds
            )
        except Exception:
            logger.exception(
                "Database shutdown failed", extra={"event": "database.shutdown_failed"}
            )
        logger.info("Application shutdown complete", extra={"event": "application.stopped"})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = settings
    register_exception_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )
    application.add_middleware(RedisRateLimitMiddleware, settings=settings)
    application.middleware("http")(exception_middleware)
    application.middleware("http")(request_context_middleware)
    application.middleware("http")(security_headers_middleware)
    application.include_router(router)
    # Keep the original API paths for backwards compatibility while exposing
    # the same endpoints under /api for the bundled browser client.
    application.include_router(router, prefix="/api", include_in_schema=False)
    if FRONTEND_DIR.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=FRONTEND_DIR, html=True),
            name="frontend",
        )
    return application


app = create_app()
