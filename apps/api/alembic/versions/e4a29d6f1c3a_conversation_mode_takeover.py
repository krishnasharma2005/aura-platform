"""conversation takeover mode

Revision ID: e4a29d6f1c3a
Revises: d7a2f5c81b64
Create Date: 2026-08-16

Adds `conversations.mode` ("agent" | "human"): an owner can take over a live
conversation and answer as themselves, and the agent runtime must stop
autonomously responding to that thread until it's handed back. Plain string
column (not an enum) so a future mode is a code change, not a migration.
Defaults to "agent" so every existing conversation keeps behaving exactly as
it did before this feature existed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4a29d6f1c3a'
down_revision: Union[str, Sequence[str], None] = 'd7a2f5c81b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'conversations',
        sa.Column('mode', sa.String(length=20), nullable=False, server_default='agent'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'mode')
