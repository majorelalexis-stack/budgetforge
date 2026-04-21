"""add alert_sent_at to projects

Revision ID: a1b2c3d4e5f6
Revises: daaa6555f2ce
Create Date: 2026-04-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'daaa6555f2ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("projects")}
    if "alert_sent_at" not in existing:
        op.add_column("projects", sa.Column("alert_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("projects")}
    if "alert_sent_at" in existing:
        op.drop_column("projects", "alert_sent_at")
