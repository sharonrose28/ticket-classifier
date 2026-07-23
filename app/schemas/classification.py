"""Strict schema for AI classification output."""

import enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClassificationUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClassificationCategory(str, enum.Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    BUG = "bug"
    ACCOUNT = "account"
    GENERAL = "general"


class TicketClassification(BaseModel):
    """Only output accepted from the ticket classifier."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    urgency: ClassificationUrgency
    category: ClassificationCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=300)

    @field_validator("reasoning")
    @classmethod
    def reasoning_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reasoning must not be blank")
        return value


class ClassificationResult(BaseModel):
    """Validated classification plus operational metadata."""

    model_config = ConfigDict(extra="forbid")

    classification: TicketClassification
    model: str
    response_id: str | None = None
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    attempt_count: int = Field(ge=1)
