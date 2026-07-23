import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_ticket_service
from app.main import app
from app.models.ticket import TicketStatus
from app.schemas.ticket import TicketList
from tests.conftest import make_ticket


class FakeTicketService:
    ticket = make_ticket(id=uuid.uuid4())
    error = None

    def __init__(self, _session):
        pass

    async def create(self, _payload):
        if self.error:
            raise self.error
        return self.ticket

    async def get(self, _ticket_id):
        if self.error:
            raise self.error
        return self.ticket

    async def list(self, *, limit, offset):
        if self.error:
            raise self.error
        return [self.ticket], 1

    async def create_batch(self, payloads):
        if self.error:
            raise self.error
        return [self.ticket for _ in payloads], "group-1"


@pytest.fixture
def client():
    FakeTicketService.error = None
    app.dependency_overrides[get_ticket_service] = lambda: FakeTicketService(None)
    with TestClient(app) as test_client:
        app.state.redis = None
        yield test_client
    app.dependency_overrides.clear()


def test_create_ticket(client):
    response = client.post(
        "/tickets",
        json={"title": "Cannot save", "description": "Save returns an error"},
        headers={"X-Request-ID": "api-test-1"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == TicketStatus.PENDING.value
    assert response.headers["X-Request-ID"] == "api-test-1"


def test_get_ticket(client):
    response = client.get(f"/tickets/{FakeTicketService.ticket.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(FakeTicketService.ticket.id)


def test_create_ticket_batch(client):
    response = client.post(
        "/tickets/batch",
        json={"tickets": [{"title": "A", "description": "B"}]},
    )
    assert response.status_code == 201
    assert response.json()["count"] == 1
    assert response.json()["task_group_id"] == "group-1"


def test_list_tickets_and_pagination(client):
    response = client.get("/tickets?limit=10&offset=0")
    assert response.status_code == 200
    payload = TicketList.model_validate(response.json())
    assert payload.total == 1
    assert payload.limit == 10


@pytest.mark.parametrize(
    "path",
    ["/tickets?limit=0", "/tickets?limit=101", "/tickets?offset=-1", "/tickets/not-a-uuid"],
)
def test_request_validation(client, path):
    response = client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_body_validation_rejects_unknown_fields(client):
    response = client.post(
        "/tickets",
        json={"title": "x", "description": "y", "admin": True},
    )
    assert response.status_code == 422


def test_database_errors_are_sanitized(client):
    FakeTicketService.error = SQLAlchemyError("secret database detail")
    response = client.get(f"/tickets/{FakeTicketService.ticket.id}")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "secret" not in response.text
