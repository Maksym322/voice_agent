"""Pinned browser voice sessions and event history.

Revision ID: 0003_voice_sessions
Revises: 0002_agent_configurations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_voice_sessions"
down_revision: str | None = "0002_agent_configurations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "started_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("room_name", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_reason", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'ended', 'error')", name="ck_voice_sessions_status"
        ),
    )
    op.create_index("ix_voice_sessions_started_by", "voice_sessions", ["started_by"])
    op.create_index("ix_voice_sessions_agent_id", "voice_sessions", ["agent_id"])
    op.create_table(
        "session_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("speaker", sa.String(16)),
        sa.Column("text", sa.String(20000)),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_events_session_id", "session_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_session_events_session_id", table_name="session_events")
    op.drop_table("session_events")
    op.drop_index("ix_voice_sessions_agent_id", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_started_by", table_name="voice_sessions")
    op.drop_table("voice_sessions")
