"""Deterministic and auditable ticket routing rules."""

from app.schemas.classification import TicketClassification

SUPPORT_QUEUE = "support"


class RoutingService:
    """Route every classified ticket to the central support team."""

    def assign_queue(self, classification: TicketClassification) -> str:
        return SUPPORT_QUEUE
