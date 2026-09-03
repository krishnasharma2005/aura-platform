"""The workflow executor.

Design notes worth knowing before changing anything here:

**The approval gate is not optional inside a workflow.** A `tool` step names
the agent whose config governs it (`as_agent`). Before anything executes, the
engine checks the tool is in that agent's `allowed_tools` and runs the exact
same `approvals.requires_approval` check the chat runtime uses, against the
same YAML the model cannot influence. If it needs a human, a row goes into
`tool_approvals` and the tool is **not called** — the step ends
`awaiting_approval`. Autonomy is about who starts the work, never about who
authorises the consequential part of it. `tests/test_workflows.py` pins this.

**A failure must not wedge a run.** Every step is retried with exponential
backoff on transient failure, and whatever happens the run is closed out
(`success` or `failed`, `finished_at` set) and its lock released in a
`finally`. A run left in `running` with no `resume_at` would be invisible work
that never happens again — the worst possible outcome for an owner who was
told the follow-ups are handled.

**Waits suspend, they don't sleep.** Hitting a `wait` step persists
`next_step_index` and `resume_at` and returns. The runner picks the run back up
when it is due, which is why "remind them, then check tomorrow whether they
replied" survives a deploy, a restart, and a machine going away.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import approvals as approvals_service
from src.agents.runtime.loader import AgentNotFoundError, load_agent_config
from src.agents.runtime.pipeline import run_agent
from src.ai_gateway.gateway import AIGateway
from src.core.config import get_settings
from src.core.exceptions import AuraError
from src.core.logging import get_logger
from src.events.bus import event_bus
from src.tools.registry import get_tool
from src.workflows import steps as step_lib
from src.workflows.models import (
    RunStatus,
    StepStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class _StepOutcome:
    """What one step did. `suspend` parks the run; `stop` finishes it early and
    successfully (a branch that legitimately found nothing to do)."""

    def __init__(
        self,
        status: StepStatus,
        detail: str,
        data: dict[str, Any] | None = None,
        stop: bool = False,
        suspend_minutes: int | None = None,
    ) -> None:
        self.status = status
        self.detail = detail
        self.data = data or {}
        self.stop = stop
        self.suspend_minutes = suspend_minutes


# --------------------------------------------------------------------------
# Run lifecycle
# --------------------------------------------------------------------------


async def start_run(
    db: AsyncSession,
    definition: WorkflowDefinition,
    trigger_source: str,
    context: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Creates the run row. Deliberately does *not* execute it: an event
    handler firing on the request path should never make a customer wait for a
    workflow. The runner picks it up on the next tick."""
    run = WorkflowRun(
        org_id=definition.org_id,
        workflow_id=definition.id,
        status=RunStatus.running,
        trigger_source=trigger_source,
        context={"run_id": str(uuid.uuid4()), "workflow": definition.slug, **(context or {})},
        next_step_index=0,
        resume_at=_now(),
        started_at=_now(),
    )
    db.add(run)

    definition.last_run_at = _now()
    definition.run_count = (definition.run_count or 0) + 1
    await db.commit()
    await db.refresh(run)
    return run


async def execute_run(
    db: AsyncSession,
    run: WorkflowRun,
    definition: WorkflowDefinition,
    gateway: AIGateway | None = None,
) -> WorkflowRun:
    """Advances a run from `next_step_index` until it finishes, fails, or
    parks on a wait. Safe to call again on a parked run."""
    settings = get_settings()
    all_steps = list(definition.steps or [])
    index = run.next_step_index or 0

    try:
        while index < len(all_steps):
            step = all_steps[index]
            outcome = await _run_step_with_retries(db, run, definition, step, gateway, settings)

            if outcome.suspend_minutes is not None:
                await _record_step(db, run, index, step, outcome, attempts=outcome.data.pop("_attempts", 1))
                run.next_step_index = index + 1
                run.resume_at = _now() + timedelta(minutes=outcome.suspend_minutes)
                await db.commit()
                return run

            await _record_step(db, run, index, step, outcome, attempts=outcome.data.pop("_attempts", 1))

            step_id = _step_id(step, index)
            run.context = {
                **(run.context or {}),
                "steps": {**((run.context or {}).get("steps") or {}), step_id: outcome.data},
            }

            if outcome.status is StepStatus.failed and not step.get("optional"):
                return await _finish(db, run, definition, RunStatus.failed, outcome.detail)
            if outcome.stop:
                break
            index += 1

        return await _finish(db, run, definition, RunStatus.success, None)
    except Exception as exc:  # pragma: no cover - defensive; a wedged run is worse than a failed one
        logger.error("workflow_run_crashed", exc_info=exc, extra={"extra_fields": {"run_id": str(run.id)}})
        return await _finish(
            db, run, definition, RunStatus.failed, "This automation stopped unexpectedly. We've logged it."
        )


async def _finish(
    db: AsyncSession,
    run: WorkflowRun,
    definition: WorkflowDefinition,
    status: RunStatus,
    error: str | None,
) -> WorkflowRun:
    run.status = status
    run.error = (error or None) and error[:500]
    run.finished_at = _now()
    run.resume_at = None
    if status is RunStatus.success:
        definition.success_count = (definition.success_count or 0) + 1
    await db.commit()
    await db.refresh(run)
    return run


async def _record_step(
    db: AsyncSession,
    run: WorkflowRun,
    index: int,
    step: dict[str, Any],
    outcome: _StepOutcome,
    attempts: int,
) -> None:
    db.add(
        WorkflowStepRun(
            run_id=run.id,
            position=index,
            step_id=_step_id(step, index),
            name=str(step.get("name") or step.get("id") or f"Step {index + 1}")[:200],
            step_type=str(step.get("type") or "unknown")[:50],
            status=outcome.status,
            detail=(outcome.detail or None) and outcome.detail[:1000],
            attempts=attempts,
            started_at=_now(),
            finished_at=_now(),
        )
    )
    await db.commit()


def _step_id(step: dict[str, Any], index: int) -> str:
    return str(step.get("id") or f"step_{index}")[:100]


# --------------------------------------------------------------------------
# Step execution
# --------------------------------------------------------------------------


async def _run_step_with_retries(
    db: AsyncSession,
    run: WorkflowRun,
    definition: WorkflowDefinition,
    step: dict[str, Any],
    gateway: AIGateway | None,
    settings: Any,
) -> _StepOutcome:
    """Retries only *transient* failures. A `PermissionError` or a missing
    integration will fail identically on the third attempt as on the first, so
    those short-circuit — an owner shouldn't wait 14 seconds to be told
    WhatsApp isn't connected."""
    max_attempts = max(1, int(getattr(settings, "WORKFLOW_STEP_MAX_ATTEMPTS", 3)))
    backoff = float(getattr(settings, "WORKFLOW_RETRY_BACKOFF_SECONDS", 2.0))

    last_detail = "That step didn't work."
    for attempt in range(1, max_attempts + 1):
        try:
            outcome = await _execute_step(db, run, step, gateway)
            outcome.data["_attempts"] = attempt
            return outcome
        except step_lib.WorkflowDefinitionError as exc:
            return _StepOutcome(StepStatus.failed, str(exc), {"_attempts": attempt})
        except AuraError as exc:
            # Permission / not-configured / validation — deterministic, don't retry.
            return _StepOutcome(StepStatus.failed, exc.message, {"_attempts": attempt})
        except Exception as exc:
            last_detail = "Something went wrong running this step. We'll try again."
            logger.warning(
                "workflow_step_failed",
                exc_info=exc,
                extra={"extra_fields": {"run_id": str(run.id), "step": step.get("id"), "attempt": attempt}},
            )
            if attempt < max_attempts and backoff > 0:
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
            # Roll back a half-applied transaction so the next attempt starts
            # clean. The rollback expires every loaded object, and an expired
            # attribute cannot be lazily reloaded under asyncio, so the two rows
            # this function and its caller keep touching are reloaded here.
            await db.rollback()
            await db.refresh(run)
            await db.refresh(definition)

    return _StepOutcome(StepStatus.failed, last_detail, {"_attempts": max_attempts})


async def _execute_step(
    db: AsyncSession, run: WorkflowRun, step: dict[str, Any], gateway: AIGateway | None
) -> _StepOutcome:
    step_type = step.get("type")
    context = run.context or {}

    if step_type == "wait":
        minutes = int(step.get("minutes") or 0)
        if minutes <= 0:
            return _StepOutcome(StepStatus.success, "No wait needed.")
        return _StepOutcome(
            StepStatus.waiting,
            f"Paused here — picking this back up in {minutes} minutes.",
            suspend_minutes=minutes,
        )

    if step_type == "branch":
        params = step_lib.render(step.get("params") or {}, context)
        result = await step_lib.run_check(str(step.get("check") or "always"), db, run.org_id, context, params)
        if result.passed:
            return _StepOutcome(StepStatus.success, result.detail, dict(result.data))
        if str(step.get("on_false", "stop")) == "continue":
            return _StepOutcome(StepStatus.skipped, result.detail, dict(result.data))
        return _StepOutcome(StepStatus.skipped, result.detail, dict(result.data), stop=True)

    if step_type == "escalate":
        return await _execute_escalate(db, run, step, context)

    if step_type == "agent":
        return await _execute_agent(db, run, step, context, gateway)

    if step_type == "tool":
        return await _execute_tool(db, run, step, context)

    raise step_lib.WorkflowDefinitionError(
        f"This workflow contains a step we don't recognise: '{step_type}'."
    )


async def _execute_escalate(
    db: AsyncSession, run: WorkflowRun, step: dict[str, Any], context: dict[str, Any]
) -> _StepOutcome:
    """Hands the thread to a person. Deliberately needs no integration and no
    approval: telling the owner something needs them is never the consequential
    action, and an escalation that could itself be blocked is not an escalation.
    It lands in the Activity feed via the existing audit subscriber."""
    reason = str(step_lib.render(step.get("reason") or "This needs a person to look at it.", context))
    conversation_key = context.get("conversation_key")

    await event_bus.publish(
        "workflow.escalation_raised",
        {
            "org_id": run.org_id,
            "actor": str(context.get("workflow") or "workflow"),
            "action": "workflow.escalation_raised",
            "details": {
                "conversation_id": conversation_key,
                "reason": reason,
                "workflow_run_id": str(run.id),
                "tool_calls": [],
            },
        },
    )
    return _StepOutcome(StepStatus.success, reason, {"reason": reason, "escalated": True})


async def _execute_agent(
    db: AsyncSession, run: WorkflowRun, step: dict[str, Any], context: dict[str, Any], gateway: AIGateway | None
) -> _StepOutcome:
    slug = str(step.get("agent") or "")
    try:
        config = load_agent_config(slug)
    except AgentNotFoundError as exc:
        raise step_lib.WorkflowDefinitionError(
            f"This workflow asks for an assistant that doesn't exist: '{slug}'."
        ) from exc

    prompt = str(step_lib.render(step.get("prompt") or "", context))
    conversation_key = str(
        step_lib.render(step.get("conversation_key") or f"workflow-{run.id}", context)
    )

    result = await run_agent(
        db=db,
        gateway=gateway or AIGateway(),
        org_id=run.org_id,
        agent_slug=slug,
        conversation_id=conversation_key,
        user_message=prompt,
    )
    detail = f"{config.display_name} drafted a reply."
    if result.pending_approvals:
        detail = f"{config.display_name} replied, and {len(result.pending_approvals)} action is waiting for you."
    return _StepOutcome(
        StepStatus.success,
        detail,
        {
            "response": result.response,
            "conversation_key": conversation_key,
            "tool_calls": result.tool_calls_made,
            "pending_approvals": [p.summary for p in result.pending_approvals],
        },
    )


async def _execute_tool(
    db: AsyncSession, run: WorkflowRun, step: dict[str, Any], context: dict[str, Any]
) -> _StepOutcome:
    """The security-critical path. Three server-side gates, in order:

    1. the tool must exist;
    2. it must be in the governing agent's `allowed_tools` (a workflow cannot
       grant an agent a capability its config doesn't give it);
    3. if the agent's config says a human approves this action, it queues and
       **does not run**.
    """
    tool_name = str(step.get("tool") or "")
    agent_slug = str(step.get("as_agent") or "")

    try:
        config = load_agent_config(agent_slug)
    except AgentNotFoundError as exc:
        raise step_lib.WorkflowDefinitionError(
            "This workflow doesn't say which assistant is responsible for this action, "
            "so it wasn't run."
        ) from exc

    tool = get_tool(tool_name)
    if tool is None:
        raise step_lib.WorkflowDefinitionError(
            f"This workflow asks for something we don't know how to do: '{tool_name}'."
        )
    if tool_name not in config.allowed_tools:
        raise step_lib.WorkflowDefinitionError(
            f"The {config.display_name} isn't allowed to use that, so this step was skipped."
        )

    raw_arguments = step_lib.render(step.get("arguments") or {}, context)
    arguments, argument_error = tool.validate_arguments(raw_arguments)
    if argument_error:
        return _StepOutcome(StepStatus.failed, argument_error)

    if approvals_service.requires_approval(config.requires_approval, tool_name, arguments):
        approval = await approvals_service.create_pending(
            db,
            org_id=run.org_id,
            agent_slug=agent_slug,
            agent_display_name=config.display_name,
            conversation_id=str(context.get("conversation_key") or f"workflow-{run.id}"),
            tool_name=tool_name,
            arguments=arguments,
        )
        logger.info(
            "workflow_step_awaiting_approval",
            extra={"extra_fields": {"run_id": str(run.id), "tool": tool_name}},
        )
        return _StepOutcome(
            StepStatus.awaiting_approval,
            f"{approval.summary} Nothing was sent until you say so.",
            {"approval_id": str(approval.id), "executed": False},
        )

    result = await tool.execute(db, run.org_id, **arguments)
    if not result.success:
        return _StepOutcome(StepStatus.failed, result.message or "That didn't go through.")
    return _StepOutcome(
        StepStatus.success,
        result.message or "Done.",
        {"executed": True, **(result.data or {})},
    )
