from types import SimpleNamespace

import pytest

from app.ai.client import (
    ClassificationOutputError,
    ClassificationRefusedError,
    OpenAIClassifier,
)
from app.core.config import Settings
from app.schemas.classification import TicketClassification
from app.ai.prompts import CLASSIFICATION_SYSTEM_PROMPT


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


@pytest.mark.asyncio
async def test_structured_output_is_parsed_and_model_is_forwarded():
    response = SimpleNamespace(
        output_parsed={
            "urgency": "high",
            "category": "bug",
            "confidence": 0.93,
            "reasoning": "A core workflow is blocked.",
        },
        output=[],
        status="completed",
    )
    client = FakeClient(response)
    classifier = OpenAIClassifier(client=client, settings=Settings())

    result = await classifier.classify(
        title="Broken", description="Cannot save", model="gpt-4.1-mini"
    )

    assert isinstance(result, TicketClassification)
    assert result.category.value == "bug"
    assert client.responses.kwargs["model"] == "gpt-4.1-mini"
    assert client.responses.kwargs["text_format"] is TicketClassification
    assert client.responses.kwargs["temperature"] == 0
    assert client.responses.kwargs["instructions"] == CLASSIFICATION_SYSTEM_PROMPT

    schema = TicketClassification.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["confidence"]["minimum"] == 0.0
    assert schema["properties"]["confidence"]["maximum"] == 1.0
    assert schema["properties"]["reasoning"]["maxLength"] == 300


@pytest.mark.asyncio
async def test_invalid_structured_output_is_rejected():
    response = SimpleNamespace(
        output_parsed={
            "urgency": "urgent",
            "category": "bug",
            "confidence": 2,
            "reasoning": "Invalid.",
        },
        output=[],
        status="completed",
    )
    classifier = OpenAIClassifier(client=FakeClient(response), settings=Settings())
    with pytest.raises(ClassificationOutputError):
        await classifier.classify(title="x", description="y")


@pytest.mark.asyncio
async def test_refusal_is_a_typed_failure():
    refusal = SimpleNamespace(type="refusal", refusal="Cannot process this ticket")
    response = SimpleNamespace(
        output_parsed=None,
        output=[SimpleNamespace(content=[refusal])],
        status="completed",
    )
    classifier = OpenAIClassifier(client=FakeClient(response), settings=Settings())
    with pytest.raises(ClassificationRefusedError, match="Cannot process"):
        await classifier.classify(title="x", description="y")


@pytest.mark.asyncio
async def test_missing_output_is_rejected():
    response = SimpleNamespace(output_parsed=None, output=[], status="incomplete")
    classifier = OpenAIClassifier(client=FakeClient(response), settings=Settings())
    with pytest.raises(ClassificationOutputError, match="no parsed output"):
        await classifier.classify(title="x", description="y")
