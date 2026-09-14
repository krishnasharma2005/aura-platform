"""business contexts

Revision ID: c6f13a8e5d92
Revises: a91d4f7c2b83
Create Date: 2026-09-13

One table, one row per organization: the customer's own business identity,
offerings, customer profile, brand voice, policies, and operating procedures
— seven JSON sections (see src/agents/business_context.py). Ported from
dist/mesnium-business/context-store.js in the openclaw/claw fork.

Unrelated to, and does not touch, organizations.business_type/primary_goal —
those stay exactly as they are (see business_context.py's module docstring
for why). No data migration: every existing organization simply has no row
here yet, and src/agents/business_context.py::get_context() returns an
empty, unpersisted context for that case rather than requiring a backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6f13a8e5d92'
down_revision: Union[str, Sequence[str], None] = 'a91d4f7c2b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'business_contexts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('identity', sa.JSON(), nullable=False),
        sa.Column('offerings', sa.JSON(), nullable=False),
        sa.Column('customers', sa.JSON(), nullable=False),
        sa.Column('brand', sa.JSON(), nullable=False),
        sa.Column('policies', sa.JSON(), nullable=False),
        sa.Column('operations', sa.JSON(), nullable=False),
        sa.Column('contacts', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', name='uq_business_contexts_org_id'),
    )
    op.create_index(
        op.f('ix_business_contexts_org_id'), 'business_contexts', ['org_id'], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_business_contexts_org_id'), table_name='business_contexts')
    op.drop_table('business_contexts')
