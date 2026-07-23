"""Application user and role persistence model."""

from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Enum, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    SUPPORT_AGENT = "support_agent"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, values_callable=lambda values: [v.value for v in values]),
        nullable=False, default=UserRole.CUSTOMER, server_default=UserRole.CUSTOMER.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="customer", foreign_keys="Ticket.customer_id")
    assigned_tickets: Mapped[list["Ticket"]] = relationship(back_populates="assigned_agent", foreign_keys="Ticket.assigned_agent_id")
