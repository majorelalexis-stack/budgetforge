"""add previous_api_key and key_rotated_at to projects

Revision ID: c2_grace_rotation
Revises: c1_proxy_settings
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2_grace_rotation'
down_revision = 'c1_proxy_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('previous_api_key', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('key_rotated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('projects', 'key_rotated_at')
    op.drop_column('projects', 'previous_api_key')
