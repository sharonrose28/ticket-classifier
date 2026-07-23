"""Distributed fixed-window rate limiting backed by Redis."""

import hashlib
import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.settings import Settings

logger = logging.getLogger(__name__)
_EXEMPT_PATHS = frozenset({"/health", "/ready", "/metrics"})


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply one atomic Redis counter per client and time window."""

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self.settings.rate_limit_enabled or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is None:
            return await self._on_unavailable(request, call_next)

        window = self.settings.rate_limit_window_seconds
        window_id = int(time.time()) // window
        identity = request.client.host if request.client else "unknown"
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        key = f"rate-limit:{digest}:{window_id}"
        try:
            async with redis.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, window + 1)
                count, _ = await pipeline.execute()
        except Exception as exc:
            logger.warning(
                "Rate limiter unavailable",
                extra={"event": "rate_limit.unavailable", "error_type": type(exc).__name__},
            )
            return await self._on_unavailable(request, call_next)

        remaining = max(0, self.settings.rate_limit_requests - int(count))
        headers = {
            "X-RateLimit-Limit": str(self.settings.rate_limit_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str((window_id + 1) * window),
        }
        if count > self.settings.rate_limit_requests:
            headers["Retry-After"] = str(window)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Too many requests. Please retry later.",
                    }
                },
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response

    async def _on_unavailable(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.settings.rate_limit_fail_open:
            return await call_next(request)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "rate_limiter_unavailable",
                    "message": "Request admission is temporarily unavailable.",
                }
            },
        )
