"""Bounded outbound phone test metadata.

Revision ID: 0005_outbound_test
Revises: 0004_operator_console
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_outbound_test"
down_revision: str | None = "0004_operator_console"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("voice_sessions", sa.Column("destination_last4", sa.String(4)))
    op.add_column("voice_sessions", sa.Column("provider_call_id", sa.String(128)))
    op.create_check_constraint(
        "ck_voice_sessions_channel", "voice_sessions", "channel IN ('browser', 'phone')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_voice_sessions_channel", "voice_sessions", type_="check")
    op.drop_column("voice_sessions", "provider_call_id")
    op.drop_column("voice_sessions", "destination_last4")
