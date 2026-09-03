"""durable conversations, contacts, messages, and the public web-chat id

Revision ID: c3e91b4d75a2
Revises: b1f4a7c92d10
Create Date: 2026-08-15

Two features, one migration:

1. **Conversation persistence.** Conversation history lived only in Redis with
   a 24h TTL, so an owner could not review what an agent said to a customer
   last week. `contacts`, `conversations` and `messages` are the durable copy.
   Redis stays the hot path for the active window; the runtime writes through
   to these tables and falls back to them on a cold conversation.

   `conversations.key` is the conversation identifier callers already use (the
   client-supplied `conversation_id`, or the id inside a public web-chat
   token). It is unique *per organization*, never globally — two tenants
   picking the same string must never collide, and a key from one tenant must
   never resolve in another.

2. **Public web chat.** `organizations.public_id` is the opaque, non-guessable
   identifier the embeddable widget addresses the business by. It is
   deliberately neither the internal UUID (used as the tenant key everywhere
   else) nor the slug (derived from the business name, so guessable).
   Nullable so existing rows migrate without a backfill: an org without one
   gets an id minted the first time `GET /organizations/{id}` is read, and
   `public_chat_enabled` defaults to true so behaviour is unchanged for
   anyone who never embeds the widget.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3e91b4d75a2'
down_revision: Union[str, Sequence[str], None] = 'b1f4a7c92d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('organizations', sa.Column('public_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_organizations_public_id'), 'organizations', ['public_id'], unique=True)
    op.add_column(
        'organizations',
        sa.Column('public_chat_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        'contacts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contacts_org_id'), 'contacts', ['org_id'], unique=False)
    op.create_index('ix_contacts_org_email', 'contacts', ['org_id', 'email'], unique=False)
    op.create_index('ix_contacts_org_phone', 'contacts', ['org_id', 'phone'], unique=False)

    op.create_table(
        'conversations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('agent_slug', sa.String(length=100), nullable=False),
        sa.Column(
            'channel',
            sa.Enum('dashboard', 'web_chat', 'whatsapp', name='conversation_channel'),
            nullable=False,
        ),
        sa.Column('contact_id', sa.Uuid(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('active', 'closed', name='conversation_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_message_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        # Conversation keys are only unique inside an organization.
        sa.UniqueConstraint('org_id', 'key', name='uq_conversations_org_key'),
    )
    op.create_index(op.f('ix_conversations_org_id'), 'conversations', ['org_id'], unique=False)
    op.create_index(op.f('ix_conversations_agent_slug'), 'conversations', ['agent_slug'], unique=False)
    # The list screen is always "this org's threads, newest first".
    op.create_index(
        'ix_conversations_org_last_message', 'conversations', ['org_id', 'last_message_at'], unique=False
    )

    op.create_table(
        'messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(
        'ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')

    op.drop_index('ix_conversations_org_last_message', table_name='conversations')
    op.drop_index(op.f('ix_conversations_agent_slug'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_org_id'), table_name='conversations')
    op.drop_table('conversations')
    sa.Enum(name='conversation_channel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='conversation_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_contacts_org_phone', table_name='contacts')
    op.drop_index('ix_contacts_org_email', table_name='contacts')
    op.drop_index(op.f('ix_contacts_org_id'), table_name='contacts')
    op.drop_table('contacts')

    op.drop_column('organizations', 'public_chat_enabled')
    op.drop_index(op.f('ix_organizations_public_id'), table_name='organizations')
    op.drop_column('organizations', 'public_id')
