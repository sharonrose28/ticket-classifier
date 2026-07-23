"""Create tickets table.

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=10),
            server_default="received",
            nullable=False,
        ),
        sa.Column("urgency", sa.String(length=8), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("assigned_queue", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "processing_time",
            sa.Integer(),
            nullable=True,
            comment="End-to-end classification processing time in milliseconds",
        ),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'classified', 'routed', 'failed')",
            name="ticket_status",
        ),
        sa.CheckConstraint(
            "urgency IS NULL OR urgency IN ('low', 'medium', 'high', 'critical')",
            name="ticket_urgency",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_range",
        ),
        sa.CheckConstraint("tokens_used >= 0", name="tokens_used_nonnegative"),
        sa.CheckConstraint(
            "processing_time >= 0", name="processing_time_nonnegative"
        ),
        sa.CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
    )
    op.create_index(
        "ix_tickets_status_created_at", "tickets", ["status", "created_at"]
    )
    op.create_index(
        "ix_tickets_queue_status_created_at",
        "tickets",
        ["assigned_queue", "status", "created_at"],
    )
    op.create_index(
        "ix_tickets_category_urgency", "tickets", ["category", "urgency"]
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_category_urgency", table_name="tickets")
    op.drop_index("ix_tickets_queue_status_created_at", table_name="tickets")
    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
    op.drop_table("tickets")
