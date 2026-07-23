from fastapi.testclient import TestClient

from app.main import app


def test_health_and_metrics_endpoints():
    with TestClient(app) as client:
        health = client.get("/health")
        live = client.get("/live")
        metrics = client.get("/metrics")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert metrics.status_code == 200
    assert "ticket_classification_latency_seconds" in metrics.text
    assert "openai_requests_failed_total" in metrics.text


def test_ready_when_dependencies_are_available(monkeypatch):
    from app.api.v1.endpoints import health

    class Connection:
        async def execute(self, _statement):
            return None

    class ConnectionContext:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return None

    class Engine:
        def connect(self):
            return ConnectionContext()

    class RedisClient:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    monkeypatch.setattr(health, "get_engine", lambda: Engine())
    monkeypatch.setattr(health.Redis, "from_url", lambda *_args, **_kwargs: RedisClient())

    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "redis": "ok"}


def test_ready_returns_503_when_dependencies_fail(monkeypatch):
    from app.api.v1.endpoints import health

    class BrokenEngine:
        def connect(self):
            raise OSError("database down")

    class BrokenRedis:
        async def ping(self):
            raise TimeoutError("redis down")

        async def aclose(self):
            return None

    monkeypatch.setattr(health, "get_engine", lambda: BrokenEngine())
    monkeypatch.setattr(health.Redis, "from_url", lambda *_args, **_kwargs: BrokenRedis())

    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
