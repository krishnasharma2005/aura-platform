"""Human-approval gate for consequential agent actions.

Guiding principle #6 of the architecture doc — "human approval precedes
critical operations" — is enforced here and in the agent runtime, on the
server, per tool call. An agent config declares which tools/actions need a
human (see `AgentConfig.requires_approval`); when the model asks for one, the
runtime writes a pending row here *instead of* executing, and the action only
runs after an owner or admin approves it through the API.

This is deliberately not something the model can talk its way around: the
check happens after the model has spoken, on data the model does not control
(the agent's YAML config), and the tool is never invoked on the pending path.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Enum, Index, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base
from src.core.exceptions import NotFoundError

# Plain-language verbs for the approval card an owner sees. Keyed by
# "tool" or "tool:action" — the same key format as `requires_approval`.
_ACTION_PHRASES = {
    "calendar:create_event": "book an appointment on your calendar",
    "calendar:cancel_event": "cancel an appointment on your calendar",
    "gmail:send_email": "send an email on your behalf",
    "whatsapp": "send a WhatsApp message to a customer",
    "slack": "post a message in your Slack",
    "hubspot:update_contact": "update a contact in your CRM",
}


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ToolApproval(Base):
    """One requested-but-not-yet-performed consequential action."""

    __tablename__ = "tool_approvals"
    # The approvals screen only ever asks "what's pending for this org?".
    __table_args__ = (Index("ix_tool_approvals_org_status", "org_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    agent_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"), nullable=False, default=ApprovalStatus.pending
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


def approval_key(tool_name: str, action: str | None) -> str:
    return f"{tool_name}:{action}" if action else tool_name


def requires_approval(requires: list[str], tool_name: str, arguments: dict[str, Any]) -> bool:
    """True when this specific call needs a human. Matches either the whole
    tool ("whatsapp") or one action within it ("calendar:cancel_event")."""
    if tool_name in requires:
        return True
    action = arguments.get("action")
    return isinstance(action, str) and f"{tool_name}:{action}" in requires


def describe(agent_display_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
    """The one-line, plain-language sentence an owner reads on the approval
    card — no tool names, no jargon (see docs/customer-profile.md)."""
    action = arguments.get("action") if isinstance(arguments.get("action"), str) else None
    phrase = _ACTION_PHRASES.get(approval_key(tool_name, action)) or _ACTION_PHRASES.get(tool_name)
    if phrase is None:
        phrase = "take an action on your behalf"
    return f"Your {agent_display_name} wants to {phrase}."


async def create_pending(
    db: AsyncSession,
    org_id: uuid.UUID,
    agent_slug: str,
    agent_display_name: str,
    conversation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolApproval:
    action = arguments.get("action") if isinstance(arguments.get("action"), str) else None
    approval = ToolApproval(
        org_id=org_id,
        agent_slug=agent_slug,
        conversation_id=conversation_id,
        tool_name=tool_name,
        action=action,
        arguments=arguments,
        summary=describe(agent_display_name, tool_name, arguments),
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    # Notify a human that a decision is waiting on them. Imported here (not at
    # module level) to avoid a circular import — notifications/notifier.py
    # type-hints ToolApproval for its interface. A notification failure must
    # never fail the request that queued the approval, so this is
    # fire-and-forget with its own error handling inside.
    from src.notifications.notifier import notify_approval_pending

    await notify_approval_pending(org_id, approval)

    return approval


async def get_for_org(db: AsyncSession, org_id: uuid.UUID, approval_id: uuid.UUID) -> ToolApproval:
    """Always filtered by org — an approval id from one tenant must never
    resolve for another."""
    result = await db.execute(
        select(ToolApproval).where(ToolApproval.id == approval_id, ToolApproval.org_id == org_id)
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise NotFoundError("We couldn't find that request to approve.")
    return approval


async def list_for_org(
    db: AsyncSession, org_id: uuid.UUID, status: ApprovalStatus | None = None, limit: int = 100
) -> list[ToolApproval]:
    stmt = select(ToolApproval).where(ToolApproval.org_id == org_id)
    if status is not None:
        stmt = stmt.where(ToolApproval.status == status)
    stmt = stmt.order_by(ToolApproval.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
