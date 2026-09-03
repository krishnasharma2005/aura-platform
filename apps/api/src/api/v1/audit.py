"""Activity feed route: exposes the audit log written by
events/audit.py, in a shape the dashboard can render as plain-language
"Activity" entries rather than raw tool-call records."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.events.audit import AuditLog
from src.identity.deps import get_active_organization
from src.identity.models import Organization

router = APIRouter(prefix="/audit-logs", tags=["activity"])


class AuditLogEntry(BaseModel):
    id: str
    agent_slug: str
    action: str
    summary: Optional[str] = None
    created_at: datetime
    metadata: dict[str, Any] = {}


def _tool_name(call: Any) -> str:
    """The event bus publishes tool_calls as a list of tool-name strings (see
    agents/runtime/pipeline.py). Dicts are tolerated too so older rows written
    in a different shape can't take the whole Activity feed down."""
    if isinstance(call, str):
        return call
    if isinstance(call, dict):
        return str(call.get("tool") or call.get("name") or "a tool")
    return "a tool"


def _summarize(action: str, details: dict[str, Any]) -> Optional[str]:
    pending = details.get("pending_approvals") or []
    tool_calls = details.get("tool_calls") or []
    if tool_calls:
        tools_used = ", ".join(sorted({_tool_name(call) for call in tool_calls}))
        return f"Used {tools_used} to help answer a message"
    if pending:
        return "Asked for your approval before taking action"
    if action == "agent.action_approved":
        return details.get("approval_summary") or "You approved an action"
    if action == "agent.action_rejected":
        return details.get("approval_summary") or "You declined an action"
    if action == "agent.response_generated":
        return "Answered a message directly, no tools needed"
    if action == "agent.scripted_reply":
        # Temporary while the Receptionist runs the predefined menu flow
        # (see agents/scripted/) instead of the real AI pipeline — never
        # imply free-form reasoning happened.
        return "Answered using the guided menu"
    if action in ("conversation.taken_over", "conversation.handed_back", "conversation.human_message_sent"):
        return details.get("summary")
    return None


@router.get("", response_model=list[AuditLogEntry])
async def list_audit_logs(
    agent: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntry]:
    stmt = select(AuditLog).where(AuditLog.org_id == organization.id)
    if agent:
        stmt = stmt.where(AuditLog.actor == agent)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        AuditLogEntry(
            id=str(row.id),
            agent_slug=row.actor,
            action=row.action,
            summary=_summarize(row.action, row.details),
            created_at=row.created_at,
            metadata=row.details,
        )
        for row in rows
    ]
