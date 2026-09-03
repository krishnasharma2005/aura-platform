"""Conversation history routes: the list of threads an org's agents have had,
and the transcript of any one of them.

These are the durable-storage counterparts to the Redis working set — this is
what lets an owner review what an agent said to a customer last week, which the
Activity/trust story depends on.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime.loader import AgentNotFoundError, load_agent_config
from src.conversations import service as conversation_service
from src.conversations.models import Conversation, ConversationStatus, Message
from src.core.db import get_db
from src.core.exceptions import ConflictError, NotFoundError
from src.events.bus import event_bus
from src.identity.deps import get_active_organization, get_current_user, require_org_role
from src.identity.models import MembershipRole, Organization, User

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Taking a conversation over, sending a message as the human, and handing it
# back are all consequential ("a customer sees this") — same bar as the
# approval-gated tools, so they're owner/admin only, like approvals.py.
_operator = require_org_role(MembershipRole.owner, MembershipRole.admin)

PREVIEW_LENGTH = 160


class ContactSummary(BaseModel):
    id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ConversationSummary(BaseModel):
    """`id` is the same conversation identifier used by
    `POST /agents/{slug}/chat` and `GET /agents/{slug}/conversations/{id}` —
    the internal database uuid is deliberately never exposed."""

    id: str
    agent_slug: str
    agent_display_name: str
    channel: str
    status: ConversationStatus
    # "agent" (AURA is answering) or "human" (an owner/admin has taken over —
    # see POST .../takeover). Drives the "Take over" / "Hand back" control.
    mode: str = "agent"
    contact: Optional[ContactSummary] = None
    message_count: int = 0
    preview: Optional[str] = None
    started_at: datetime
    last_message_at: datetime


class ConversationTurn(BaseModel):
    role: str
    content: str
    tool_calls: list[Any] = []
    created_at: Optional[datetime] = None


def _display_name(agent_slug: str) -> str:
    try:
        return load_agent_config(agent_slug).display_name
    except AgentNotFoundError:
        return "Assistant"


def _to_summary(conversation: Conversation, message_count: int, preview: Optional[str]) -> ConversationSummary:
    contact = conversation.contact
    return ConversationSummary(
        id=conversation.key,
        agent_slug=conversation.agent_slug,
        agent_display_name=_display_name(conversation.agent_slug),
        channel=conversation.channel.value,
        status=conversation.status,
        mode=conversation.mode,
        contact=(
            ContactSummary(
                id=str(contact.id), name=contact.name, phone=contact.phone, email=contact.email
            )
            if contact is not None
            else None
        ),
        message_count=message_count,
        preview=preview,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
    )


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    agent: Optional[str] = Query(default=None, description="Filter to one agent's conversations."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    conversations = await conversation_service.list_conversations(
        db, organization.id, agent_slug=agent, limit=limit, offset=offset
    )
    if not conversations:
        return []

    # One grouped query for the counts and one for the last line of each
    # thread, rather than two queries per row.
    ids = [c.id for c in conversations]
    counts = dict(
        (await db.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(ids))
            .group_by(Message.conversation_id)
        )).all()
    )
    previews: dict[Any, str] = {}
    rows = (
        await db.execute(
            select(Message.conversation_id, Message.content, Message.created_at)
            .where(Message.conversation_id.in_(ids))
            .order_by(Message.conversation_id, Message.created_at.desc())
        )
    ).all()
    for conversation_id, content, _created_at in rows:
        previews.setdefault(conversation_id, content[:PREVIEW_LENGTH])

    return [
        _to_summary(conversation, counts.get(conversation.id, 0), previews.get(conversation.id))
        for conversation in conversations
    ]


@router.get("/{conversation_id}", response_model=list[ConversationTurn])
async def get_conversation(
    conversation_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationTurn]:
    """The full transcript of one thread. Looked up by (org, key), so a
    conversation id belonging to another business is simply not found."""
    conversation = await conversation_service.get_conversation(db, organization.id, conversation_id)
    if conversation is None:
        raise NotFoundError("We couldn't find that conversation.")
    turns = await conversation_service.get_messages(db, conversation, limit=limit)
    return [ConversationTurn(**turn) for turn in turns]


class HumanMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


async def _get_conversation_for_org(
    db: AsyncSession, organization: Organization, conversation_id: str
) -> Conversation:
    conversation = await conversation_service.get_conversation(db, organization.id, conversation_id)
    if conversation is None:
        raise NotFoundError("We couldn't find that conversation.")
    return conversation


async def _publish_takeover_event(
    org_id: Any, actor_user: User, agent_slug: str, conversation_id: str, action: str, summary: str
) -> None:
    """Piggybacks on the same audit-log pipeline every other agent action
    goes through (src/events/audit.py), attributed to the conversation's
    agent so it groups with that agent's other Activity entries — the
    summary makes clear a human acted, not the agent."""
    await event_bus.publish(
        action,
        {
            "org_id": org_id,
            "actor": agent_slug,
            "action": action,
            "details": {
                "conversation_id": conversation_id,
                "by": actor_user.name or actor_user.email,
                "summary": summary,
            },
        },
    )


@router.post("/{conversation_id}/takeover", response_model=ConversationSummary)
async def take_over_conversation(
    conversation_id: str,
    organization: Organization = Depends(_operator),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    """Puts a human in control of this thread. From this point, the agent
    records inbound messages but does not reply — see
    `agents/runtime/pipeline.py::run_agent` — until someone hands it back."""
    conversation = await _get_conversation_for_org(db, organization, conversation_id)
    if conversation.mode == "human":
        raise ConflictError("You're already handling this conversation directly.")
    conversation = await conversation_service.set_mode(db, conversation, "human")
    await _publish_takeover_event(
        organization.id,
        current_user,
        conversation.agent_slug,
        conversation_id,
        "conversation.taken_over",
        f"{current_user.name or current_user.email} took over this conversation.",
    )
    count = await conversation_service.count_messages(db, conversation)
    return _to_summary(conversation, count, None)


@router.post("/{conversation_id}/handback", response_model=ConversationSummary)
async def hand_back_conversation(
    conversation_id: str,
    organization: Organization = Depends(_operator),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    """Restores agent control. The agent answers the next inbound message
    normally again."""
    conversation = await _get_conversation_for_org(db, organization, conversation_id)
    if conversation.mode != "human":
        raise ConflictError("The agent is already handling this conversation.")
    conversation = await conversation_service.set_mode(db, conversation, "agent")
    display_name = _display_name(conversation.agent_slug)
    await _publish_takeover_event(
        organization.id,
        current_user,
        conversation.agent_slug,
        conversation_id,
        "conversation.handed_back",
        f"{current_user.name or current_user.email} handed this conversation back to the {display_name}.",
    )
    count = await conversation_service.count_messages(db, conversation)
    return _to_summary(conversation, count, None)


@router.post("/{conversation_id}/messages", response_model=ConversationTurn, status_code=201)
async def send_human_message(
    conversation_id: str,
    payload: HumanMessageRequest,
    organization: Organization = Depends(_operator),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationTurn:
    """Posts a message into the conversation as the human operator — not the
    agent. Requires the conversation to already be taken over, so it's never
    ambiguous, mid-thread, whether the next message a customer sees came from
    AURA or from a person; "Take over" is the one explicit switch.

    Delivery: for WhatsApp threads this also sends the message to the
    customer's number. Website-chat and dashboard threads have no open
    channel to push to outside of the request/response cycle, so the message
    is recorded and appears the next time that thread is viewed or polled —
    documented in docs/scope-ledger.md.
    """
    conversation = await _get_conversation_for_org(db, organization, conversation_id)
    if conversation.mode != "human":
        raise ConflictError("Take over this conversation before sending a message directly.")

    content = payload.content.strip()
    if not content:
        raise ConflictError("Type a message first.")

    conversation = await conversation_service.add_human_message(db, conversation, content)

    if conversation.channel.value == "whatsapp" and conversation.contact is not None and conversation.contact.phone:
        from src.tools.whatsapp import send_text

        await send_text(db, organization.id, to=conversation.contact.phone, message=content)

    await _publish_takeover_event(
        organization.id,
        current_user,
        conversation.agent_slug,
        conversation_id,
        "conversation.human_message_sent",
        f"{current_user.name or current_user.email} sent a message directly.",
    )

    return ConversationTurn(role="human", content=content, tool_calls=[], created_at=conversation.last_message_at)
