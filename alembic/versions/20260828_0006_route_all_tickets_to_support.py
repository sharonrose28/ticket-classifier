"""Route every existing classified ticket to the central support queue.

Revision ID: 20260828_0006
Revises: 20260723_0005
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0006"
down_revision: str | None = "20260723_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE tickets SET assigned_queue = 'support' "
            "WHERE assigned_queue IS NOT NULL AND assigned_queue <> 'support'"
        )
    )


def downgrade() -> None:
    # Previous routing cannot be reconstructed reliably from stored data because
    # critical urgency overrode category routing. Retaining support is lossless.
    pass
