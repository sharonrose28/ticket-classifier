"""OpenAI Structured Outputs ticket classifier."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.ai.prompts import CLASSIFICATION_SYSTEM_PROMPT, format_ticket_input
from app.core.config import Settings, get_settings
from app.schemas.classification import TicketClassification


class ClassificationOutputError(RuntimeError):
    """The provider did not return an acceptable structured classification."""


class ClassificationRefusedError(ClassificationOutputError):
    """The model explicitly refused to classify the ticket."""


class OpenAIClassifier:
    """Classify tickets through the Responses API and a Pydantic output schema."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI | Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if client is not None:
            self.client = client
            return

        if self.settings.openai_api_key is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        api_key = self.settings.openai_api_key.get_secret_value()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=self.settings.openai_timeout_seconds,
            max_retries=0,
        )

    async def classify(
        self, *, title: str, description: str, model: str | None = None
    ) -> TicketClassification:
        """Return a validated model or raise when output cannot be trusted."""

        classification, _response = await self.classify_with_response(
            title=title, description=description, model=model
        )
        return classification

    async def classify_with_response(
        self, *, title: str, description: str, model: str | None = None
    ) -> tuple[TicketClassification, Any]:
        """Perform one provider attempt and retain metadata for the service layer."""

        response = await self.client.responses.parse(
            model=model or self.settings.openai_primary_model,
            # Responses API `instructions` is the high-priority system/developer prompt.
            instructions=CLASSIFICATION_SYSTEM_PROMPT,
            input=format_ticket_input(title=title, description=description),
            text_format=TicketClassification,
            temperature=0,
        )

        parsed = response.output_parsed
        if parsed is None:
            refusal = _find_refusal(response)
            if refusal is not None:
                raise ClassificationRefusedError(refusal)
            raise ClassificationOutputError(
                f"OpenAI response had no parsed output (status={response.status!r})"
            )

        try:
            # Revalidate even if a custom or mocked client supplies output_parsed.
            classification = TicketClassification.model_validate(parsed)
        except ValidationError as exc:
            raise ClassificationOutputError(
                "OpenAI returned an invalid classification"
            ) from exc
        return classification, response


def _find_refusal(response: Any) -> str | None:
    for item in getattr(response, "output", ()):
        for content in getattr(item, "content", ()):
            if getattr(content, "type", None) == "refusal":
                return getattr(content, "refusal", None) or "Classification was refused"
    return None
