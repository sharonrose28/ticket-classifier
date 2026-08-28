from types import SimpleNamespace

import pytest

from app.models.ticket import TicketStatus
from app.repositories.tickets import TicketRepository
from app.schemas.classification import ClassificationResult, TicketClassification
from app.services.classification_service import ClassificationService


class FakeOpenAIService:
    async def classify_ticket(self, **_kwargs):
        return ClassificationResult(
            classification=TicketClassification(
                urgency="critical",
                category="technical",
                confidence=0.97,
                reasoning="A production system is unavailable.",
            ),
            model="gpt-4.1",
            response_id="resp_1",
            input_tokens=80,
            cached_input_tokens=0,
            output_tokens=20,
            total_tokens=100,
            estimated_cost_usd=0.00032,
            latency_ms=25,
            attempt_count=2,
        )


@pytest.mark.asyncio
async def test_complete_classification_flow_updates_database(session):
    repository = TicketRepository(session)
    ticket = await repository.create(title="Outage", description="Production is down")
    await session.commit()

    result = await ClassificationService(session, openai_service=FakeOpenAIService()).process(
        ticket.id
    )

    assert result.status is TicketStatus.COMPLETE
    assert result.urgency.value == "critical"
    assert result.category == "technical"
    assert result.assigned_queue == "support"
    assert float(result.confidence) == 0.97
    assert result.llm_model == "gpt-4.1"
    assert result.tokens_used == 100
    assert result.processing_time >= 0
    assert result.retry_count == 1
    assert float(result.estimated_cost_usd) == pytest.approx(0.00032)


@pytest.mark.asyncio
async def test_completed_ticket_is_idempotent(session):
    repository = TicketRepository(session)
    ticket = await repository.create(title="Done", description="Already classified")
    ticket.status = TicketStatus.COMPLETE
    await session.commit()

    result = await ClassificationService(session, openai_service=SimpleNamespace()).process(
        ticket.id
    )
    assert result.status is TicketStatus.COMPLETE


@pytest.mark.asyncio
async def test_no_key_fallback_completes_database_workflow(session, monkeypatch):
    repository = TicketRepository(session)
    ticket = await repository.create(
        title="Payment outage",
        description="All customers cannot complete payment in production.",
    )
    await session.commit()
    monkeypatch.setattr(
        "app.services.classification_service.get_settings",
        lambda: SimpleNamespace(openai_api_key=None),
    )

    result = await ClassificationService(session).process(ticket.id)

    assert result.status is TicketStatus.COMPLETE
    assert result.llm_model == "local-rule-fallback-v1"
    assert result.assigned_queue == "support"
