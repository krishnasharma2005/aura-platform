"""Cross-agent analytics: the one screen that tells an owner what their AI
staff actually did this week.

The deep dive is specific about why this exists (§6, 4:00–4:40): the demo turns
on a single tile — "34 conversations handled, 11 booked" — and the arithmetic
that follows it. So the numbers here are counts of things that really happened
in the database, never estimates, and the shape is fixed by the contract the
frontend is written against.

Definitions, stated once so the tile and the API agree:

* **conversations_handled** — distinct conversations that had at least one
  message inside the range. A thread started three weeks ago that got a reply
  yesterday counts yesterday, which is what an owner means by "handled".
* **messages_sent** — assistant turns. What the agents said, not what
  customers said.
* **actions_taken** — successful tool executions, from all three places one
  can happen: inline during a chat (recorded on the assistant message),
  after an owner approved it, and inside a workflow step.
* **approvals_pending / approvals_approved** — scoped to the same range as
  everything else, by when the request was raised.

Dates are UTC calendar days. Per-organization local-day bucketing is a real
follow-up once `organizations.timezone` is populated at onboarding (see
docs/needs-founder-input.md §8).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.approvals import ApprovalStatus, ToolApproval
from src.agents.runtime.loader import AgentNotFoundError, load_agent_config
from src.conversations.models import Conversation, Message
from src.core.db import get_db
from src.identity.deps import get_active_organization
from src.identity.models import Organization
from src.workflows.models import StepStatus, WorkflowRun, WorkflowStepRun

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AgentBreakdown(BaseModel):
    agent_slug: str
    display_name: str
    conversations: int
    messages: int
    actions: int


class DailyPoint(BaseModel):
    date: str
    conversations: int
    messages: int


class AnalyticsSummary(BaseModel):
    range_days: int
    conversations_handled: int
    messages_sent: int
    actions_taken: int
    approvals_pending: int
    approvals_approved: int
    by_agent: list[AgentBreakdown]
    daily: list[DailyPoint]


def _display_name(agent_slug: str) -> str:
    try:
        return load_agent_config(agent_slug).display_name
    except AgentNotFoundError:
        return "Assistant"


def _tool_call_count(tool_calls) -> int:
    if isinstance(tool_calls, list):
        return len(tool_calls)
    return 1 if tool_calls else 0


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    days: int = Query(default=7, ge=1, le=365),
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsSummary:
    org_id: uuid.UUID = organization.id
    now = datetime.now(UTC).replace(tzinfo=None)
    since = now - timedelta(days=days)

    # One pass over the org's messages in range. Joined to conversations so
    # every row is org-scoped at the database, not filtered in Python — a
    # message can only be counted if its conversation belongs to this org.
    rows = (
        await db.execute(
            select(
                Message.conversation_id,
                Message.role,
                Message.tool_calls,
                Message.created_at,
                Conversation.agent_slug,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.org_id == org_id, Message.created_at >= since)
        )
    ).all()

    conversation_ids: set = set()
    messages_sent = 0
    inline_actions = 0
    per_agent: dict[str, dict[str, object]] = {}
    per_day: dict[date, dict[str, object]] = {}

    for conversation_id, role, tool_calls, created_at, agent_slug in rows:
        conversation_ids.add(conversation_id)
        agent = per_agent.setdefault(
            agent_slug, {"conversations": set(), "messages": 0, "actions": 0}
        )
        agent["conversations"].add(conversation_id)  # type: ignore[union-attr]

        day = per_day.setdefault(created_at.date(), {"conversations": set(), "messages": 0})
        day["conversations"].add(conversation_id)  # type: ignore[union-attr]
        day["messages"] = int(day["messages"]) + 1  # type: ignore[arg-type]

        if role == "assistant":
            messages_sent += 1
            agent["messages"] = int(agent["messages"]) + 1  # type: ignore[arg-type]
            count = _tool_call_count(tool_calls)
            inline_actions += count
            agent["actions"] = int(agent["actions"]) + count  # type: ignore[arg-type]

    # Actions the owner approved. These executed server-side at approve time
    # and were never recorded on a message, so they'd otherwise be invisible.
    approved_rows = (
        await db.execute(
            select(ToolApproval.agent_slug, func.count(ToolApproval.id))
            .where(
                ToolApproval.org_id == org_id,
                ToolApproval.created_at >= since,
                ToolApproval.status == ApprovalStatus.approved,
            )
            .group_by(ToolApproval.agent_slug)
        )
    ).all()
    approvals_approved = 0
    for agent_slug, count in approved_rows:
        approvals_approved += int(count)
        agent = per_agent.setdefault(
            agent_slug, {"conversations": set(), "messages": 0, "actions": 0}
        )
        agent["actions"] = int(agent["actions"]) + int(count)  # type: ignore[arg-type]

    approvals_pending = int(
        (
            await db.execute(
                select(func.count(ToolApproval.id)).where(
                    ToolApproval.org_id == org_id,
                    ToolApproval.created_at >= since,
                    ToolApproval.status == ApprovalStatus.pending,
                )
            )
        ).scalar_one()
    )

    # Tools a workflow executed directly (i.e. the ones that didn't need a
    # human — the ones that did are counted above, once, as approvals).
    workflow_actions = int(
        (
            await db.execute(
                select(func.count(WorkflowStepRun.id))
                .join(WorkflowRun, WorkflowRun.id == WorkflowStepRun.run_id)
                .where(
                    WorkflowRun.org_id == org_id,
                    WorkflowStepRun.step_type == "tool",
                    WorkflowStepRun.status == StepStatus.success,
                    WorkflowStepRun.started_at >= since,
                )
            )
        ).scalar_one()
    )

    by_agent = sorted(
        (
            AgentBreakdown(
                agent_slug=slug,
                display_name=_display_name(slug),
                conversations=len(stats["conversations"]),  # type: ignore[arg-type]
                messages=int(stats["messages"]),  # type: ignore[arg-type]
                actions=int(stats["actions"]),  # type: ignore[arg-type]
            )
            for slug, stats in per_agent.items()
        ),
        key=lambda row: (-row.conversations, row.agent_slug),
    )

    # Zero-filled so a chart has a point for every day, including the quiet ones.
    daily: list[DailyPoint] = []
    for offset in range(days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date()
        stats = per_day.get(day)
        daily.append(
            DailyPoint(
                date=day.isoformat(),
                conversations=len(stats["conversations"]) if stats else 0,  # type: ignore[arg-type]
                messages=int(stats["messages"]) if stats else 0,  # type: ignore[arg-type]
            )
        )

    return AnalyticsSummary(
        range_days=days,
        conversations_handled=len(conversation_ids),
        messages_sent=messages_sent,
        actions_taken=inline_actions + approvals_approved + workflow_actions,
        approvals_pending=approvals_pending,
        approvals_approved=approvals_approved,
        by_agent=by_agent,
        daily=daily,
    )
