"""Update ticket statuses for the asynchronous classification workflow.

Revision ID: 20260723_0002
Revises: 20260723_0001
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0002"
down_revision: str | None = "20260723_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_tickets_ticket_status"), "tickets", type_="check")
    op.execute(
        """
        UPDATE tickets
        SET status = CASE status
            WHEN 'received' THEN 'pending'
            WHEN 'classified' THEN 'processing'
            WHEN 'routed' THEN 'complete'
            ELSE status
        END
        """
    )
    op.alter_column(
        "tickets",
        "status",
        existing_type=sa.String(length=10),
        server_default="pending",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ticket_status",
        "tickets",
        "status IN ('pending', 'processing', 'complete', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_tickets_ticket_status"), "tickets", type_="check")
    op.execute(
        """
        UPDATE tickets
        SET status = CASE status
            WHEN 'pending' THEN 'received'
            WHEN 'complete' THEN 'routed'
            ELSE status
        END
        """
    )
    op.alter_column(
        "tickets",
        "status",
        existing_type=sa.String(length=10),
        server_default="received",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ticket_status",
        "tickets",
        "status IN ('received', 'processing', 'classified', 'routed', 'failed')",
    )
