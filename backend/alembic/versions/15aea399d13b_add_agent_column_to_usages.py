"""add agent column to usages

Revision ID: 15aea399d13b
Revises: 7c491c3629b4
Create Date: 2026-04-21 09:27:13.255892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '15aea399d13b'
down_revision: Union[str, Sequence[str], None] = '7c491c3629b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usages', sa.Column('agent', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('usages', 'agent')
