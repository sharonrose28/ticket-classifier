"""Ticket request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.ticket import TicketStatus, TicketUrgency
from app.schemas.classification import ClassificationCategory, ClassificationUrgency


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50_000)

    @field_validator("title", "description")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID | None
    assigned_agent_id: uuid.UUID | None
    title: str
    description: str
    status: TicketStatus
    urgency: TicketUrgency | None
    category: str | None
    assigned_queue: str | None
    confidence: float | None
    llm_model: str | None
    tokens_used: int
    processing_time: int | None
    estimated_cost_usd: float | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class TicketList(BaseModel):
    items: list[TicketRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class TicketBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickets: list[TicketCreate] = Field(min_length=1, max_length=100)


class TicketBatchRead(BaseModel):
    items: list[TicketRead]
    count: int = Field(ge=1)
    task_group_id: str | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketAssignmentUpdate(BaseModel):
    assigned_agent_id: uuid.UUID


class ClassificationCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urgency: ClassificationUrgency
    category: ClassificationCategory
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1, max_length=300)
