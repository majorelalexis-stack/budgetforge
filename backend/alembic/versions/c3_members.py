"""add members table

Revision ID: c3_members
Revises: c2_grace_rotation
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3_members'
down_revision = 'c2_grace_rotation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('api_key'),
    )
    op.create_index('ix_members_email', 'members', ['email'])
    op.create_index('ix_members_id', 'members', ['id'])


def downgrade():
    op.drop_index('ix_members_id', table_name='members')
    op.drop_index('ix_members_email', table_name='members')
    op.drop_table('members')
