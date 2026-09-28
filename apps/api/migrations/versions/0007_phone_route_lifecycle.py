"""Track safe deprovisioning and reuse of inbound phone routes.

Revision ID: 0007_phone_route_lifecycle
Revises: 0006_phone_numbers
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phone_route_lifecycle"
down_revision: str | None = "0006_phone_numbers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "phone_numbers",
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "ck_phone_numbers_status",
        "phone_numbers",
        "status IN ('active', 'deprovisioning', 'retired')",
    )
    op.alter_column("phone_numbers", "status", server_default=None)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM phone_numbers WHERE status != 'active'")):
        raise RuntimeError("Reactivate or remove inactive phone routes before downgrading 0007")
    op.drop_constraint("ck_phone_numbers_status", "phone_numbers", type_="check")
    op.drop_column("phone_numbers", "status")
