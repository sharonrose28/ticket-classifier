"""Create durable dead-letter records.

Revision ID: 20260723_0003
Revises: 20260723_0002
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0003"
down_revision: str | None = "20260723_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dead_letters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("error_type", sa.String(length=255), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name="fk_dead_letters_ticket_id_tickets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dead_letters"),
        sa.UniqueConstraint("task_id", name="uq_dead_letters_task_id"),
    )
    op.create_index(
        "ix_dead_letters_ticket_created_at",
        "dead_letters",
        ["ticket_id", "created_at"],
    )
    op.create_index(
        "ix_dead_letters_created_at", "dead_letters", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_dead_letters_created_at", table_name="dead_letters")
    op.drop_index("ix_dead_letters_ticket_created_at", table_name="dead_letters")
    op.drop_table("dead_letters")
