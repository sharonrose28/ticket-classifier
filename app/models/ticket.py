"""Ticket persistence model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.dead_letter import DeadLetter
    from app.models.user import User


class TicketStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class TicketUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Ticket(Base):
    """A support ticket and its latest classification result."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("tokens_used >= 0", name="tokens_used_nonnegative"),
        CheckConstraint("processing_time >= 0", name="processing_time_nonnegative"),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        Index("ix_tickets_status_created_at", "status", "created_at"),
        Index(
            "ix_tickets_queue_status_created_at",
            "assigned_queue",
            "status",
            "created_at",
        ),
        Index("ix_tickets_category_urgency", "category", "urgency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            name="ticket_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
        default=TicketStatus.PENDING,
        server_default=TicketStatus.PENDING.value,
    )
    urgency: Mapped[TicketUrgency | None] = mapped_column(
        Enum(
            TicketUrgency,
            name="ticket_urgency",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=True,
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_queue: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    processing_time: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="End-to-end classification processing time in milliseconds",
    )
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8),
        nullable=True,
        comment="Estimated OpenAI token cost in USD at processing time",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    dead_letters: Mapped[list["DeadLetter"]] = relationship(back_populates="ticket")
    customer: Mapped["User | None"] = relationship(back_populates="tickets", foreign_keys=[customer_id])
    assigned_agent: Mapped["User | None"] = relationship(back_populates="assigned_tickets", foreign_keys=[assigned_agent_id])
