"""add missing project columns

Revision ID: daaa6555f2ce
Revises: f28b9665b5f0
Create Date: 2026-04-21 10:07:17.999108

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'daaa6555f2ce'
down_revision: Union[str, Sequence[str], None] = 'f28b9665b5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("projects")}

    candidates = [
        ("alert_email",          sa.Column("alert_email",          sa.String(),  nullable=True)),
        ("webhook_url",          sa.Column("webhook_url",          sa.String(),  nullable=True)),
        ("alert_sent",           sa.Column("alert_sent",           sa.Boolean(), nullable=True)),
        ("reset_period",         sa.Column("reset_period",         sa.String(),  nullable=True)),
        ("max_cost_per_call_usd", sa.Column("max_cost_per_call_usd", sa.Float(), nullable=True)),
    ]
    for name, col in candidates:
        if name not in existing:
            op.add_column("projects", col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("projects")}

    for name in ("max_cost_per_call_usd", "reset_period", "alert_sent", "webhook_url", "alert_email"):
        if name in existing:
            op.drop_column("projects", name)
