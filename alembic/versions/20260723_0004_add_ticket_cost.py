"""Persist estimated OpenAI token cost.

Revision ID: 20260723_0004
Revises: 20260723_0003
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0004"
down_revision: str | None = "20260723_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=12, scale=8),
            nullable=True,
            comment="Estimated OpenAI token cost in USD at processing time",
        ),
    )


def downgrade() -> None:
    op.drop_column("tickets", "estimated_cost_usd")
