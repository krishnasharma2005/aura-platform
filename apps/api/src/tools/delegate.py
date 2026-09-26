"""The Chief of Staff's one tool: hand a task to another agent and bring back
what it said. Modeled as an ordinary tool (not a special code path) so
delegation inherits everything `run_agent` already does for free — the
permission check (only `chief_of_staff.yaml` lists `delegate` in
`allowed_tools`, so no specialist agent can ever call this back, which is what
makes runaway delegation loops structurally impossible), argument validation,
and — most importantly — the target agent's own `requires_approval` gate. If
Sales asks to send an email because the Chief of Staff delegated to it, that
still queues for the owner's approval exactly as if the owner had talked to
Sales directly; nothing about delegation bypasses that.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuraError
from src.tools.base import Tool, ToolResult

# The six specialist agents a request can be handed to. Deliberately not the
# Chief of Staff itself — see the self-delegation guard in execute().
_DELEGATABLE_SLUGS = ("receptionist", "sales", "marketing", "executive_assistant", "support", "ecommerce")


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "Hand a task to one of the business's specialist agents and get back what they found or did. "
        "Use this whenever a request is really that specialist's job."
    )
    input_schema = {
        "type": "object",
        "properties": {
            # Named `action` (not e.g. `agent_slug`) so that
            # approvals.requires_approval()'s existing "tool:action" matching
            # already supports gating delegation to a specific agent (e.g.
            # "delegate:sales" in a future chief_of_staff.yaml) with zero
            # changes to approvals.py.
            "action": {
                "type": "string",
                "enum": list(_DELEGATABLE_SLUGS),
                "description": "Which specialist agent to delegate to.",
            },
            "task": {
                "type": "string",
                "description": (
                    "A complete, self-contained description of what you want that specialist to do or "
                    "answer. They cannot see this conversation, so include every detail they'll need."
                ),
            },
        },
        "required": ["action", "task"],
    }

    async def execute(self, db: AsyncSession, org_id: Any, **kwargs: Any) -> ToolResult:
        context = kwargs.pop("_context", None)
        if context is None:
            return ToolResult(success=False, message="Delegation isn't available outside a live conversation.")

        target_slug = kwargs.get("action")
        task = kwargs.get("task")
        if target_slug not in _DELEGATABLE_SLUGS:
            return ToolResult(success=False, message=f"'{target_slug}' isn't a specialist I can delegate to.")

        # Lazy import: pipeline.py -> tools/registry.py -> tools/delegate.py
        # would otherwise cycle back to pipeline.py at module load time. The
        # same pattern is already used in agents/approvals.py for
        # notify_approval_pending.
        from src.agents.runtime.pipeline import run_agent

        sub_conversation_id = f"{context.conversation_id}::{target_slug}"
        try:
            result = await run_agent(
                db,
                context.gateway,
                org_id,
                target_slug,
                sub_conversation_id,
                task,
                channel=context.channel,
                contact_id=context.contact_id,
            )
        except AuraError as exc:
            # A specialist's own failure (e.g. an unconnected integration)
            # must not crash the Chief of Staff's whole turn — every other
            # tool in this codebase reports its own failures as a message the
            # model can relay, not an exception, and delegation is no
            # different: the model should say "I checked with X and it
            # couldn't do that because ..." rather than the request 500ing.
            return ToolResult(
                success=False,
                data={"agent": target_slug},
                message=f"I checked with the {target_slug.replace('_', ' ')}, but: {exc.message}",
            )

        return ToolResult(
            success=True,
            data={
                "agent": target_slug,
                "response": result.response,
                "pending_approvals": [p.summary for p in result.pending_approvals],
            },
            message=result.response,
        )
