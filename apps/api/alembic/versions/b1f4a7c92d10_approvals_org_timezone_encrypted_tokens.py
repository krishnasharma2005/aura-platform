"""human approval gate, org timezone, encrypted integration tokens

Revision ID: b1f4a7c92d10
Revises: 66cffa72aeeb
Create Date: 2026-08-15

Three changes:

1. `tool_approvals` — the pending queue behind the human-approval gate on
   consequential agent actions (see src/agents/approvals.py).
2. `organizations.timezone` — nullable; NULL means "use settings.DEFAULT_TIMEZONE".
   Needed so the calendar tool books "3pm" in the business's own time.
3. Integration tokens are now encrypted at rest with an app-level Fernet key
   (src/core/crypto.py). No data migration is required: encrypted values carry
   an `enc:v1:` prefix and anything without it is read as legacy plaintext, so
   existing rows keep working and are re-encrypted the next time they're
   saved. The column type is unchanged (Text) — ciphertext is longer than the
   plaintext it replaces, which Text already accommodates.

   To re-encrypt existing rows immediately rather than lazily, an operator can
   re-POST each connection through /api/v1/integrations once ENCRYPTION_KEY is
   set. There is no automatic backfill here on purpose: the key lives only in
   the environment, so a migration has no safe way to read it on every host.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1f4a7c92d10'
down_revision: Union[str, Sequence[str], None] = '66cffa72aeeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('organizations', sa.Column('timezone', sa.String(length=64), nullable=True))

    op.create_table(
        'tool_approvals',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('agent_slug', sa.String(length=100), nullable=False),
        sa.Column('conversation_id', sa.String(length=255), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=True),
        sa.Column('arguments', sa.JSON(), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'approved', 'rejected', name='approval_status'),
            nullable=False,
        ),
        sa.Column('decided_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('result_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tool_approvals_org_id'), 'tool_approvals', ['org_id'], unique=False)
    # The Activity/approvals screen only ever asks "what is pending for this org?"
    op.create_index('ix_tool_approvals_org_status', 'tool_approvals', ['org_id', 'status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tool_approvals_org_status', table_name='tool_approvals')
    op.drop_index(op.f('ix_tool_approvals_org_id'), table_name='tool_approvals')
    op.drop_table('tool_approvals')
    sa.Enum(name='approval_status').drop(op.get_bind(), checkfirst=True)
    op.drop_column('organizations', 'timezone')
