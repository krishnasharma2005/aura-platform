"""org pack entitlements

Revision ID: a91d4f7c2b83
Revises: e4a29d6f1c3a
Create Date: 2026-09-13

One table: which purchasable Business Packs (real estate, legal, dental, ...)
an organization has activated on top of the six base agents. Mirrors the
workflow_definitions design decision — entitlement state is a row, not a
config file, so activating a pack for one org has zero effect on any other.

Absence of a row for (org_id, pack_id) means "never activated"; there is no
default-on pack. Pack *definitions* themselves are not a table — they're
YAML, loaded by src/agents/runtime/pack_loader.py, the same way base agent
configs are YAML rather than rows. `pack_id` here is therefore a plain string,
not a foreign key.

This migration adds the entitlement bookkeeping only. It does not wire
billing/checkout, and it does not make any pack's agent_overrides actually
apply to an agent's behavior — see src/agents/entitlements.py's module
docstring for what's still open.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a91d4f7c2b83'
down_revision: Union[str, Sequence[str], None] = 'e4a29d6f1c3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'org_pack_entitlements',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('pack_id', sa.String(length=100), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('activated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'pack_id', name='uq_org_pack_entitlements_org_pack'),
    )
    op.create_index(
        op.f('ix_org_pack_entitlements_org_id'), 'org_pack_entitlements', ['org_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_org_pack_entitlements_org_id'), table_name='org_pack_entitlements')
    op.drop_table('org_pack_entitlements')
