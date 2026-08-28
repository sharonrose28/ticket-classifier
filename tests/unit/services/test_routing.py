import pytest

from app.schemas.classification import TicketClassification
from app.services.routing_service import RoutingService


@pytest.mark.parametrize(
    ("urgency", "category", "expected"),
    [
        ("critical", "billing", "emergency"),
        ("high", "technical", "engineering"),
        ("medium", "bug", "engineering"),
        ("medium", "billing", "finance"),
        ("low", "account", "customer-success"),
        ("low", "general", "support"),
    ],
)
def test_assign_queue(urgency, category, expected):
    classification = TicketClassification(
        urgency=urgency,
        category=category,
        confidence=0.9,
        reasoning="Classification reason.",
    )
    assert RoutingService().assign_queue(classification) == expected
