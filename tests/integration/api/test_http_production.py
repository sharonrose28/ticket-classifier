from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import exception_middleware, security_headers_middleware
from app.api.rate_limit import RedisRateLimitMiddleware
from app.core.settings import Settings


class Pipeline:
    def __init__(self, count):
        self.count = count

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def incr(self, _key):
        return self

    def expire(self, _key, _ttl):
        return self

    async def execute(self):
        return [self.count, True]


class RedisStub:
    def __init__(self, count):
        self.count = count

    def pipeline(self, **_kwargs):
        return Pipeline(self.count)


def make_rate_limited_app(count, *, fail_open=True):
    application = FastAPI()
    settings = Settings(
        rate_limit_requests=1,
        rate_limit_fail_open=fail_open,
        cors_allowed_origins=[],
    )
    application.add_middleware(RedisRateLimitMiddleware, settings=settings)

    @application.get("/resource")
    async def resource():
        return {"ok": True}

    application.state.redis = RedisStub(count) if count is not None else None
    return application


def test_rate_limit_allows_and_reports_budget():
    with TestClient(make_rate_limited_app(1)) as client:
        response = client.get("/resource")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limit_rejects_excess_requests():
    with TestClient(make_rate_limited_app(2)) as client:
        response = client.get("/resource")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert "Retry-After" in response.headers


def test_rate_limit_can_fail_closed():
    with TestClient(make_rate_limited_app(None, fail_open=False)) as client:
        response = client.get("/resource")
    assert response.status_code == 503


def test_security_headers_and_exception_sanitization():
    application = FastAPI()
    application.middleware("http")(exception_middleware)
    application.middleware("http")(security_headers_middleware)

    @application.get("/boom")
    async def boom():
        raise RuntimeError("secret")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    with TestClient(application) as client:
        docs = client.get("/docs")
    assert docs.status_code == 200
    assert "https://cdn.jsdelivr.net" in docs.headers["Content-Security-Policy"]
    assert "connect-src 'self'" in docs.headers["Content-Security-Policy"]
