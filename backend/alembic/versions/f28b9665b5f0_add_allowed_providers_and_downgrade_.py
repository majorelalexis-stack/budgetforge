"""add allowed_providers and downgrade_chain to projects

Revision ID: f28b9665b5f0
Revises: 15aea399d13b
Create Date: 2026-04-21 09:37:51.010586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f28b9665b5f0'
down_revision: Union[str, Sequence[str], None] = '15aea399d13b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('allowed_providers', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('downgrade_chain', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'downgrade_chain')
    op.drop_column('projects', 'allowed_providers')
