"""add plan and stripe fields to projects

Revision ID: d1_plan_fields
Revises: c3_members
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1_plan_fields'
down_revision = 'c3_members'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('plan', sa.String(), nullable=False, server_default='free'))
    op.add_column('projects', sa.Column('stripe_customer_id', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('stripe_subscription_id', sa.String(), nullable=True))


def downgrade():
    op.drop_column('projects', 'stripe_subscription_id')
    op.drop_column('projects', 'stripe_customer_id')
    op.drop_column('projects', 'plan')
