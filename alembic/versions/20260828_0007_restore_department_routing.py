"""Restore category-based department queues for existing tickets.

Revision ID: 20260828_0007
Revises: 20260828_0006
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0007"
down_revision: str | None = "20260828_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tickets
            SET assigned_queue = CASE
                WHEN urgency = 'critical' THEN 'emergency'
                WHEN category IN ('technical', 'bug') THEN 'engineering'
                WHEN category = 'billing' THEN 'finance'
                WHEN category = 'account' THEN 'customer-success'
                ELSE 'support'
            END
            WHERE status = 'complete'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE tickets SET assigned_queue = 'support' " "WHERE assigned_queue IS NOT NULL")
    )
