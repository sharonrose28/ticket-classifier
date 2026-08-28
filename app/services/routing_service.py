"""Deterministic and auditable ticket routing rules."""

from app.schemas.classification import (
    ClassificationCategory,
    ClassificationUrgency,
    TicketClassification,
)

CATEGORY_QUEUES: dict[ClassificationCategory, str] = {
    ClassificationCategory.TECHNICAL: "engineering",
    ClassificationCategory.BUG: "engineering",
    ClassificationCategory.BILLING: "finance",
    ClassificationCategory.ACCOUNT: "customer-success",
    ClassificationCategory.GENERAL: "support",
}


class RoutingService:
    """Route classifications to the responsible operational department."""

    def assign_queue(self, classification: TicketClassification) -> str:
        if classification.urgency is ClassificationUrgency.CRITICAL:
            return "emergency"
        return CATEGORY_QUEUES[classification.category]
