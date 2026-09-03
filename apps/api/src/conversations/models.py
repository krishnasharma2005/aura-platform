"""Durable conversation storage.

Short-term memory (Redis, `src/memory/short_term.py`) stays the hot path for the
active conversation window, but it expires after 24h of inactivity. An owner
reviewing what an agent said to a customer last week needs the transcript to
still exist, so every turn is also written through to Postgres here.

Key model note: `Conversation.key` is the conversation identifier every caller
already uses — the client-supplied `conversation_id` on `POST /agents/{slug}/chat`
and the id embedded in a public web-chat token. It is unique *per organization*,
never globally, so two tenants choosing the same string can never collide or
read each other's thread. The internal `id` UUID is not exposed by the API.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.db import Base


class ConversationStatus(str, enum.Enum):
    active = "active"
    closed = "closed"


class ConversationChannel(str, enum.Enum):
    """Where the customer (or owner) is talking to the agent from."""

    dashboard = "dashboard"
    web_chat = "web_chat"
    whatsapp = "whatsapp"


class Contact(Base):
    """A person outside the business the agents have talked to — a customer, a
    lead, an enquirer. Capturing leads is a core Receptionist function, and
    until now there was nowhere to put a customer's identity."""

    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_org_email", "org_id", "email"),
        Index("ix_contacts_org_phone", "org_id", "phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        # The conversation key is only unique within an organization.
        UniqueConstraint("org_id", "key", name="uq_conversations_org_key"),
        # The conversations list is always "this org's threads, newest first",
        # optionally filtered by agent.
        Index("ix_conversations_org_last_message", "org_id", "last_message_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel: Mapped[ConversationChannel] = mapped_column(
        Enum(ConversationChannel, name="conversation_channel"),
        nullable=False,
        default=ConversationChannel.dashboard,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id"), nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.active,
    )
    # Who is currently answering this thread: "agent" (the default — AURA
    # replies automatically) or "human" (an owner/admin has taken over; the
    # runtime records the customer's message but does not generate a reply
    # until someone hands the conversation back). Plain string, not an enum,
    # so a new mode is a code change here, not a migration.
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    contact: Mapped["Contact | None"] = relationship(lazy="selectin")


class Message(Base):
    """One turn in a conversation. `role` mirrors the LLM message roles
    ("user" | "assistant"); `tool_calls` records which tools the runtime
    actually ran for that turn, so the Activity story is reconstructable from
    the transcript alone."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
