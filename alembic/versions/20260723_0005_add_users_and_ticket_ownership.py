"""Add users, roles, ticket ownership, and agent assignment.

Revision ID: 20260723_0005
Revises: 20260723_0004
Create Date: 2026-07-23
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0005"
down_revision: str | None = "20260723_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="customer", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('customer', 'support_agent', 'admin')", name="user_role"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role_active", "users", ["role", "is_active"])
    op.add_column("tickets", sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tickets", sa.Column("assigned_agent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(op.f("fk_tickets_customer_id_users"), "tickets", "users", ["customer_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key(op.f("fk_tickets_assigned_agent_id_users"), "tickets", "users", ["assigned_agent_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"])
    op.create_index("ix_tickets_assigned_agent_id", "tickets", ["assigned_agent_id"])


def downgrade() -> None:
    op.drop_index("ix_tickets_assigned_agent_id", table_name="tickets")
    op.drop_index("ix_tickets_customer_id", table_name="tickets")
    op.drop_constraint(op.f("fk_tickets_assigned_agent_id_users"), "tickets", type_="foreignkey")
    op.drop_constraint(op.f("fk_tickets_customer_id_users"), "tickets", type_="foreignkey")
    op.drop_column("tickets", "assigned_agent_id")
    op.drop_column("tickets", "customer_id")
    op.drop_index("ix_users_role_active", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
