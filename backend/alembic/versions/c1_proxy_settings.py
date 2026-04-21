"""add proxy_timeout_ms and proxy_retries to projects

Revision ID: c1_proxy_settings
Revises: b2c3d4e5f6a7
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1_proxy_settings'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('proxy_timeout_ms', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('proxy_retries', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    op.drop_column('projects', 'proxy_retries')
    op.drop_column('projects', 'proxy_timeout_ms')
