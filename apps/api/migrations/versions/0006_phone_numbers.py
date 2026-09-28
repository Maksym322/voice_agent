"""Inbound phone-number inventory and per-call routing.

Revision ID: 0006_phone_numbers
Revises: 0005_outbound_test
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phone_numbers"
down_revision: str | None = "0005_outbound_test"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phone_numbers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("e164", sa.String(16), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column(
            "route_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("sip_trunk_id", sa.String(128), nullable=False, unique=True),
        sa.Column("dispatch_rule_id", sa.String(128), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("e164 ~ '^\\+[1-9][0-9]{6,14}$'", name="ck_phone_numbers_e164"),
    )
    op.alter_column("voice_sessions", "started_by", existing_type=postgresql.UUID(), nullable=True)
    op.add_column("voice_sessions", sa.Column("direction", sa.String(16)))
    op.execute(
        "UPDATE voice_sessions SET direction = "
        "CASE WHEN channel = 'phone' THEN 'outbound' ELSE 'browser' END"
    )
    op.alter_column("voice_sessions", "direction", existing_type=sa.String(16), nullable=False)
    op.add_column(
        "voice_sessions",
        sa.Column(
            "phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="SET NULL"),
        ),
    )
    op.create_check_constraint(
        "ck_voice_sessions_direction",
        "voice_sessions",
        "(channel = 'browser' AND direction = 'browser') OR "
        "(channel = 'phone' AND direction IN ('inbound', 'outbound'))",
    )
    op.create_index(
        "ix_voice_sessions_phone_number_created",
        "voice_sessions",
        ["phone_number_id", "created_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM phone_numbers")):
        raise RuntimeError("Remove LiveKit number routes before downgrading 0006")
    if connection.scalar(sa.text("SELECT count(*) FROM voice_sessions WHERE started_by IS NULL")):
        raise RuntimeError("Delete or export inbound sessions before downgrading 0006")
    op.drop_index("ix_voice_sessions_phone_number_created", table_name="voice_sessions")
    op.drop_constraint("ck_voice_sessions_direction", "voice_sessions", type_="check")
    op.drop_column("voice_sessions", "phone_number_id")
    op.drop_column("voice_sessions", "direction")
    op.alter_column("voice_sessions", "started_by", existing_type=postgresql.UUID(), nullable=False)
    op.drop_table("phone_numbers")
