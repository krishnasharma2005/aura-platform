"""Read/write helpers for durable conversation storage.

Every function here is organization-scoped by construction: a conversation is
only ever looked up by (org_id, key), never by key alone, so a conversation
identifier guessed or replayed from another tenant resolves to nothing.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.conversations.models import (
    Contact,
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Message,
)

# How many stored turns are replayed into the prompt when a conversation has
# fallen out of Redis. Matches short_term._MAX_TURNS so a cold conversation
# behaves the same as a warm one.
MAX_REPLAY_TURNS = 50


def _now() -> datetime:
    # Stored naive-UTC, matching every other timestamp column in the schema
    # (server_default=now() on Postgres is naive).
    return datetime.now(UTC).replace(tzinfo=None)


async def get_conversation(db: AsyncSession, org_id: uuid.UUID, key: str) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(Conversation.org_id == org_id, Conversation.key == key)
    )
    return result.scalar_one_or_none()


async def get_or_create_conversation(
    db: AsyncSession,
    org_id: uuid.UUID,
    key: str,
    agent_slug: str,
    channel: ConversationChannel = ConversationChannel.dashboard,
    contact_id: uuid.UUID | None = None,
) -> Conversation:
    conversation = await get_conversation(db, org_id, key)
    if conversation is not None:
        return conversation
    conversation = Conversation(
        org_id=org_id,
        key=key,
        agent_slug=agent_slug,
        channel=channel,
        contact_id=contact_id,
        status=ConversationStatus.active,
        started_at=_now(),
        last_message_at=_now(),
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def record_turns(
    db: AsyncSession,
    org_id: uuid.UUID,
    key: str,
    agent_slug: str,
    turns: list[tuple[str, str, list[Any] | None]],
    channel: ConversationChannel = ConversationChannel.dashboard,
    contact_id: uuid.UUID | None = None,
) -> Conversation:
    """Write-through persistence for a completed exchange. `turns` is a list of
    (role, content, tool_calls) in the order they happened."""
    conversation = await get_or_create_conversation(
        db, org_id=org_id, key=key, agent_slug=agent_slug, channel=channel, contact_id=contact_id
    )
    if contact_id is not None and conversation.contact_id is None:
        conversation.contact_id = contact_id

    for role, content, tool_calls in turns:
        db.add(
            Message(
                conversation_id=conversation.id,
                role=role,
                content=content,
                tool_calls=tool_calls or None,
                created_at=_now(),
            )
        )
    conversation.last_message_at = _now()
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def get_turns(
    db: AsyncSession, org_id: uuid.UUID, key: str, limit: int = MAX_REPLAY_TURNS
) -> list[dict[str, Any]]:
    """The most recent `limit` turns of a stored conversation, oldest first.
    This is the cold-read path the runtime falls back to when Redis has
    expired the conversation."""
    conversation = await get_conversation(db, org_id, key)
    if conversation is None:
        return []
    return await get_messages(db, conversation, limit=limit)


async def get_messages(db: AsyncSession, conversation: Conversation, limit: int = MAX_REPLAY_TURNS) -> list[dict[str, Any]]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    rows.reverse()
    return [
        {
            "role": row.role,
            "content": row.content,
            "tool_calls": row.tool_calls or [],
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def set_mode(db: AsyncSession, conversation: Conversation, mode: str) -> Conversation:
    """Switches who answers this thread. `"human"` = an owner/admin has taken
    over and the agent runtime must not autonomously reply; `"agent"` =
    handed back, AURA answers again. Called from the takeover/hand-back API
    routes and nowhere else, so this is the single place the transition
    happens."""
    conversation.mode = mode
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def add_human_message(
    db: AsyncSession, conversation: Conversation, content: str
) -> Conversation:
    """Records a message the *owner* typed directly into a live conversation,
    attributed with role "human" — never "assistant" — so the transcript and
    the Activity feed can never make it look like the agent said this."""
    db.add(
        Message(
            conversation_id=conversation.id,
            role="human",
            content=content,
            tool_calls=None,
            created_at=_now(),
        )
    )
    conversation.last_message_at = _now()
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def count_messages(db: AsyncSession, conversation: Conversation) -> int:
    stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation.id)
    return int((await db.execute(stmt)).scalar_one())


async def list_conversations(
    db: AsyncSession,
    org_id: uuid.UUID,
    agent_slug: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.org_id == org_id)
    if agent_slug:
        stmt = stmt.where(Conversation.agent_slug == agent_slug)
    stmt = stmt.order_by(Conversation.last_message_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def upsert_contact(
    db: AsyncSession,
    org_id: uuid.UUID,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    notes: str | None = None,
) -> Contact:
    """Finds an org's existing contact by email or phone, or creates one.
    Matching is always within the organization."""
    contact: Contact | None = None
    if email:
        result = await db.execute(
            select(Contact).where(Contact.org_id == org_id, Contact.email == email.lower())
        )
        contact = result.scalar_one_or_none()
    if contact is None and phone:
        result = await db.execute(select(Contact).where(Contact.org_id == org_id, Contact.phone == phone))
        contact = result.scalar_one_or_none()

    if contact is None:
        contact = Contact(
            org_id=org_id,
            name=name,
            phone=phone,
            email=email.lower() if email else None,
            notes=notes,
            first_seen_at=_now(),
            last_seen_at=_now(),
        )
        db.add(contact)
    else:
        contact.name = name or contact.name
        contact.phone = phone or contact.phone
        contact.email = (email.lower() if email else None) or contact.email
        contact.notes = notes or contact.notes
        contact.last_seen_at = _now()
    await db.flush()
    return contact
