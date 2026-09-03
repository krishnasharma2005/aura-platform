"""Approval routes: the human gate in front of consequential agent actions.

An owner sees "Your Receptionist wants to cancel an appointment on your
calendar — approve?", and nothing happens until they say yes. The action is
executed here, server-side, from the arguments recorded when the agent asked —
not from anything supplied by the client at approve time.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import approvals as approvals_service
from src.agents.approvals import ApprovalStatus, ToolApproval
from src.agents.runtime.loader import AgentNotFoundError, load_agent_config
from src.core.db import get_db
from src.core.exceptions import ConflictError, PermissionError
from src.core.logging import get_logger
from src.events.bus import event_bus
from src.identity.deps import get_current_user, require_org_role
from src.identity.models import MembershipRole, Organization, User
from src.tools.registry import get_tool

logger = get_logger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

_decider = require_org_role(MembershipRole.owner, MembershipRole.admin)


class ApprovalResponse(BaseModel):
    id: str
    agent_slug: str
    agent_display_name: str
    tool: str
    action: str | None = None
    summary: str
    details: dict[str, Any] = {}
    conversation_id: str
    status: ApprovalStatus
    result_message: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


def _display_name(agent_slug: str) -> str:
    try:
        return load_agent_config(agent_slug).display_name
    except AgentNotFoundError:
        return "assistant"


def _to_response(approval: ToolApproval) -> ApprovalResponse:
    return ApprovalResponse(
        id=str(approval.id),
        agent_slug=approval.agent_slug,
        agent_display_name=_display_name(approval.agent_slug),
        tool=approval.tool_name,
        action=approval.action,
        summary=approval.summary,
        details=approval.arguments or {},
        conversation_id=approval.conversation_id,
        status=approval.status,
        result_message=approval.result_message,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
    )


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: ApprovalStatus | None = Query(default=ApprovalStatus.pending),
    organization: Organization = Depends(_decider),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalResponse]:
    rows = await approvals_service.list_for_org(db, organization.id, status=status)
    return [_to_response(row) for row in rows]


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: uuid.UUID,
    organization: Organization = Depends(_decider),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalResponse:
    approval = await approvals_service.get_for_org(db, organization.id, approval_id)
    if approval.status is not ApprovalStatus.pending:
        raise ConflictError("That request has already been decided.")

    # Re-check the permission list at execution time: the agent's config may
    # have changed since the agent asked, and this is a second, independent
    # server-side gate on top of the one in the runtime.
    try:
        config = load_agent_config(approval.agent_slug)
    except AgentNotFoundError as exc:
        raise PermissionError("That assistant is no longer available.") from exc
    if approval.tool_name not in config.allowed_tools:
        raise PermissionError(f"The {config.display_name} isn't allowed to do that anymore.")

    tool = get_tool(approval.tool_name)
    if tool is None:
        raise PermissionError("That action is no longer available.")

    result = await tool.execute(db, organization.id, **(approval.arguments or {}))

    approval.status = ApprovalStatus.approved
    approval.decided_by_user_id = current_user.id
    approval.decided_at = datetime.now(UTC).replace(tzinfo=None)
    approval.result_message = result.message or ("Done." if result.success else "That didn't go through.")
    await db.commit()
    await db.refresh(approval)

    await _publish_decision(organization.id, approval, "agent.action_approved")
    return _to_response(approval)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject(
    approval_id: uuid.UUID,
    organization: Organization = Depends(_decider),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalResponse:
    approval = await approvals_service.get_for_org(db, organization.id, approval_id)
    if approval.status is not ApprovalStatus.pending:
        raise ConflictError("That request has already been decided.")

    approval.status = ApprovalStatus.rejected
    approval.decided_by_user_id = current_user.id
    approval.decided_at = datetime.now(UTC).replace(tzinfo=None)
    approval.result_message = "You declined this, so nothing was done."
    await db.commit()
    await db.refresh(approval)

    await _publish_decision(organization.id, approval, "agent.action_rejected")
    return _to_response(approval)


async def _publish_decision(org_id: uuid.UUID, approval: ToolApproval, action: str) -> None:
    await event_bus.publish(
        action,
        {
            "org_id": org_id,
            "actor": approval.agent_slug,
            "action": action,
            "details": {
                "conversation_id": approval.conversation_id,
                "tool_calls": [approval.tool_name] if action == "agent.action_approved" else [],
                "approval_summary": approval.summary,
                "result": approval.result_message,
            },
        },
    )
