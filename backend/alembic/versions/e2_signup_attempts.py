"""add signup_attempts table for persistent IP rate limiting

Revision ID: e2_signup_attempts
Revises: e1_portal_tokens
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'e2_signup_attempts'
down_revision = 'e1_portal_tokens'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'signup_attempts' not in inspector.get_table_names():
        op.create_table(
            'signup_attempts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ip', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_signup_attempts_id', 'signup_attempts', ['id'])
        op.create_index('ix_signup_attempts_ip', 'signup_attempts', ['ip'])


def downgrade():
    op.drop_index('ix_signup_attempts_ip', table_name='signup_attempts')
    op.drop_index('ix_signup_attempts_id', table_name='signup_attempts')
    op.drop_table('signup_attempts')
