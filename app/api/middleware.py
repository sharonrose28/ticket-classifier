"""HTTP request correlation and access logging."""

import logging
import re
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.logging import bind_request_id, reset_request_id

logger = logging.getLogger(__name__)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


async def request_context_middleware(request: Request, call_next) -> Response:
    request_id = _request_id_from(request)
    token = bind_request_id(request_id)
    started_at = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "HTTP request failed",
                extra={
                    "event": "http.request.failed",
                    "method": request.method,
                    "path": request.url.path,
                    "latency_ms": _elapsed_ms(started_at),
                },
            )
            raise

        response.headers["X-Request-ID"] = request_id
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "HTTP request completed",
            extra={
                "event": "http.request.completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": _elapsed_ms(started_at),
            },
        )
        return response
    finally:
        reset_request_id(token)


def _request_id_from(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "")
    return supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


async def exception_middleware(request: Request, call_next) -> Response:
    """Log unexpected failures and prevent internal details leaking to clients."""

    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled HTTP error",
            extra={"event": "http.unhandled_error", "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                }
            },
        )


async def security_headers_middleware(request: Request, call_next) -> Response:
    """Attach browser hardening headers to every API response."""

    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": _content_security_policy(request.url.path),
            "Cache-Control": "no-store",
        }
    )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _content_security_policy(path: str) -> str:
    """Allow only the assets required by the requested browser surface."""

    if path in {"/docs", "/redoc"}:
        return (
            "default-src 'none'; "
            "script-src 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src data: https://fastapi.tiangolo.com; "
            "font-src data:; connect-src 'self'; frame-ancestors 'none'"
        )
    if path == "/" or path.endswith((".html", ".css", ".js")):
        return (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'"
        )
    return "default-src 'none'; frame-ancestors 'none'"
