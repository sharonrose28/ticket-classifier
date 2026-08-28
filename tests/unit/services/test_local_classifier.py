import pytest

from app.schemas.classification import ClassificationCategory, ClassificationUrgency
from app.services.local_classifier import LocalClassificationService


@pytest.mark.asyncio
async def test_local_classifier_routes_critical_billing_outage():
    result = await LocalClassificationService().classify_ticket(
        title="Urgent checkout outage",
        description="All customers receive a payment error and checkout is completely unavailable.",
    )

    assert result.classification.urgency is ClassificationUrgency.CRITICAL
    assert result.classification.category is ClassificationCategory.BILLING
    assert result.model == "local-rule-fallback-v1"
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_local_classifier_has_safe_general_defaults():
    result = await LocalClassificationService().classify_ticket(
        title="Product question", description="Please explain this feature."
    )

    assert result.classification.urgency is ClassificationUrgency.LOW
    assert result.classification.category is ClassificationCategory.GENERAL
