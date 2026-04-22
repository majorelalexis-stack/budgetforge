"""add portal_tokens table

Revision ID: e1_portal_tokens
Revises: d1_plan_fields
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'e1_portal_tokens'
down_revision = 'd1_plan_fields'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'portal_tokens' not in inspector.get_table_names():
        op.create_table(
            'portal_tokens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(), nullable=False),
            sa.Column('token', sa.String(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token'),
        )
        op.create_index('ix_portal_tokens_email', 'portal_tokens', ['email'])
        op.create_index('ix_portal_tokens_id', 'portal_tokens', ['id'])
        op.create_index('ix_portal_tokens_token', 'portal_tokens', ['token'])


def downgrade():
    op.drop_index('ix_portal_tokens_token', table_name='portal_tokens')
    op.drop_index('ix_portal_tokens_id', table_name='portal_tokens')
    op.drop_index('ix_portal_tokens_email', table_name='portal_tokens')
    op.drop_table('portal_tokens')
