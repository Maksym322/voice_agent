"""Operator views and bounded session diagnostics.

Revision ID: 0004_operator_console
Revises: 0003_voice_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_operator_console"
down_revision: str | None = "0003_voice_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "voice_sessions",
        sa.Column("room_cleanup_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "voice_sessions",
        sa.Column("channel", sa.String(16), nullable=False, server_default="browser"),
    )
    op.add_column(
        "session_events",
        sa.Column("source", sa.String(32), nullable=False, server_default="api"),
    )
    op.create_index("ix_voice_sessions_created_id", "voice_sessions", ["created_at", "id"])
    op.create_index(
        "ix_session_events_created_id", "session_events", ["session_id", "created_at", "id"]
    )
    op.create_table(
        "session_diagnostics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("component", sa.String(32), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.String(240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('info','warning','error')", name="ck_diagnostic_severity"),
    )
    op.create_index(
        "ix_session_diagnostics_session_created",
        "session_diagnostics",
        ["session_id", "created_at", "id"],
    )
    op.create_table(
        "operator_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("operator_views")
    op.drop_index("ix_session_diagnostics_session_created", table_name="session_diagnostics")
    op.drop_table("session_diagnostics")
    op.drop_index("ix_session_events_created_id", table_name="session_events")
    op.drop_index("ix_voice_sessions_created_id", table_name="voice_sessions")
    op.drop_column("session_events", "source")
    op.drop_column("voice_sessions", "room_cleanup_pending")
    op.drop_column("voice_sessions", "channel")
