"""password reset: reset tokens and a password_changed_at marker

Revision ID: f2b6c0a9d413
Revises: c6f13a8e5d92
Create Date: 2026-10-24 09:00:00.000000

Adds the `password_reset_tokens` table (a hash of each emailed reset link,
single-use and short-lived) and `users.password_changed_at`, which lets a reset
sign the account out everywhere by refusing any token issued before it.

No data migration: existing users have a NULL marker, which means "no token has
ever been invalidated".
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b6c0a9d413'
down_revision: Union[str, Sequence[str], None] = 'c6f13a8e5d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(), nullable=True))
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_password_reset_tokens_token_hash'), 'password_reset_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_password_reset_tokens_token_hash'), table_name='password_reset_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_column('users', 'password_changed_at')
