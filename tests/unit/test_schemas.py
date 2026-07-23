import pytest
from pydantic import ValidationError

from app.schemas.classification import TicketClassification
from app.schemas.ticket import TicketCreate


def test_ticket_input_strips_whitespace():
    ticket = TicketCreate(title="  Help  ", description="  Broken  ")
    assert ticket.title == "Help"
    assert ticket.description == "Broken"


@pytest.mark.parametrize("field", ["title", "description"])
def test_blank_ticket_input_is_rejected(field):
    values = {"title": "Title", "description": "Description", field: "   "}
    with pytest.raises(ValidationError):
        TicketCreate.model_validate(values)


def test_classification_rejects_extra_keys_and_long_reasoning():
    base = {
        "urgency": "low",
        "category": "general",
        "confidence": 0.5,
        "reasoning": "ok",
    }
    with pytest.raises(ValidationError):
        TicketClassification.model_validate({**base, "unexpected": True})
    with pytest.raises(ValidationError):
        TicketClassification.model_validate({**base, "reasoning": "x" * 301})
