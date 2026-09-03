"""Workflow engine.

The load-bearing test in this file is
`test_a_workflow_cannot_bypass_the_approval_gate`. Everything else can be
rebuilt; that one is the promise the product is sold on — "you can stop it
before it sends" — and a workflow is exactly the shape of thing that would
quietly route around it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.approvals import ApprovalStatus, ToolApproval
from src.agents.runtime.pipeline import AgentRunResult
from src.conversations.models import Conversation, ConversationChannel, Message
from src.core.db import async_session_factory
from src.events.audit import AuditLog, register_audit_subscriber
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id
from src.tools.base import ToolResult
from src.tools.registry import TOOL_REGISTRY
from src.workflows import engine, runner, service
from src.workflows.models import (
    RunStatus,
    StepStatus,
    TriggerType,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)
from src.workflows.templates import APPOINTMENT_REMINDER, NEW_LEAD_ESCALATION


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _definition(
    db: AsyncSession,
    org_id: uuid.UUID,
    steps: list[dict],
    slug: str = "test-workflow",
    trigger_type: TriggerType = TriggerType.schedule,
    trigger_config: dict | None = None,
    enabled: bool = True,
    next_run_at: datetime | None = None,
) -> WorkflowDefinition:
    definition = WorkflowDefinition(
        org_id=org_id,
        slug=slug,
        name="Test workflow",
        description="",
        trigger_type=trigger_type,
        trigger_config=trigger_config or {"interval_minutes": 60},
        steps=steps,
        enabled=enabled,
        next_run_at=next_run_at,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition


async def _steps_of(db: AsyncSession, run: WorkflowRun) -> list[WorkflowStepRun]:
    return list(
        (
            await db.execute(
                select(WorkflowStepRun)
                .where(WorkflowStepRun.run_id == run.id)
                .order_by(WorkflowStepRun.position)
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# End-to-end execution
# ---------------------------------------------------------------------------


async def test_a_workflow_runs_end_to_end_and_records_every_step(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """Tool step -> branch -> agent step -> escalation, with the whole thing
    reconstructable afterwards from the step rows."""
    _, org, _ = user_and_org

    monkeypatch.setattr(
        TOOL_REGISTRY["calendar"],
        "execute",
        AsyncMock(
            return_value=ToolResult(
                success=True, data={"events": [{"id": "1"}, {"id": "2"}]}, message="Read the diary."
            )
        ),
    )
    monkeypatch.setattr(
        engine,
        "run_agent",
        AsyncMock(
            return_value=AgentRunResult(
                response="Your appointment is tomorrow at 3pm.", conversation_id="c", tool_calls_made=[]
            )
        ),
    )

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "read_diary",
                "name": "Read tomorrow's appointments",
                "type": "tool",
                "tool": "calendar",
                "as_agent": "receptionist",
                "arguments": {"action": "list_events"},
            },
            {
                "id": "anything",
                "name": "Is there anything booked?",
                "type": "branch",
                "check": "context_not_empty",
                "params": {"path": "steps.read_diary.events"},
            },
            {
                "id": "draft",
                "name": "Write the reminder",
                "type": "agent",
                "agent": "receptionist",
                "prompt": "Write a reminder.",
            },
            {
                "id": "flag",
                "name": "Flag it for a human",
                "type": "escalate",
                "reason": "Reminder ready: {{steps.draft.response}}",
            },
        ],
    )

    run = await engine.start_run(db_session, definition, trigger_source="manual")
    run = await engine.execute_run(db_session, run, definition)

    assert run.status is RunStatus.success
    assert run.finished_at is not None

    steps = await _steps_of(db_session, run)
    assert [step.name for step in steps] == [
        "Read tomorrow's appointments",
        "Is there anything booked?",
        "Write the reminder",
        "Flag it for a human",
    ]
    assert all(step.status is StepStatus.success for step in steps)
    assert steps[1].detail == "Found 2 to work through."
    # The placeholder pulled the drafted text out of the previous step.
    assert "Your appointment is tomorrow at 3pm." in (steps[3].detail or "")

    await db_session.refresh(definition)
    assert definition.run_count == 1
    assert definition.success_count == 1


async def test_a_workflow_cannot_bypass_the_approval_gate(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """A workflow must never become the back door around "you can stop it
    before it sends".

    The Receptionist's config requires a human for `whatsapp`. A workflow step
    asking for it has to queue an approval and leave the tool uncalled — even
    though nobody typed anything and no model was involved.
    """
    _, org, _ = user_and_org

    send = AsyncMock(return_value=ToolResult(success=True, message="Sent."))
    monkeypatch.setattr(TOOL_REGISTRY["whatsapp"], "execute", send)

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "send",
                "name": "Send the reminder",
                "type": "tool",
                "tool": "whatsapp",
                "as_agent": "receptionist",
                "arguments": {"to": "+447700900412", "message": "See you tomorrow at 3pm."},
            }
        ],
    )

    run = await engine.start_run(db_session, definition, trigger_source="schedule")
    run = await engine.execute_run(db_session, run, definition)

    # The tool was never called.
    send.assert_not_awaited()

    steps = await _steps_of(db_session, run)
    assert len(steps) == 1
    assert steps[0].status is StepStatus.awaiting_approval
    assert "Nothing was sent until you say so." in (steps[0].detail or "")

    # ...and it is sitting in the owner's queue, in the same plain language a
    # chat-initiated request uses, with the arguments recorded server-side.
    approval = (
        await db_session.execute(select(ToolApproval).where(ToolApproval.org_id == org.id))
    ).scalar_one()
    assert approval.status is ApprovalStatus.pending
    assert approval.summary == "Your Receptionist wants to send a WhatsApp message to a customer."
    assert approval.arguments["message"] == "See you tomorrow at 3pm."


async def test_a_workflow_cannot_use_a_tool_its_agent_is_not_allowed(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """The second half of the same guarantee: a stored definition must not be
    able to hand an agent a capability its config never gave it."""
    _, org, _ = user_and_org
    shopify = AsyncMock(return_value=ToolResult(success=True, message="Done."))
    monkeypatch.setattr(TOOL_REGISTRY["shopify"], "execute", shopify)

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "sneaky",
                "name": "Do something else entirely",
                "type": "tool",
                "tool": "shopify",
                "as_agent": "receptionist",
                "arguments": {"action": "list_orders"},
            }
        ],
    )
    run = await engine.start_run(db_session, definition, trigger_source="manual")
    run = await engine.execute_run(db_session, run, definition)

    shopify.assert_not_awaited()
    assert run.status is RunStatus.failed
    steps = await _steps_of(db_session, run)
    assert steps[0].status is StepStatus.failed
    assert "isn't allowed to use that" in (steps[0].detail or "")


async def test_a_wait_step_suspends_the_run_and_resumes_later(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    _, org, _ = user_and_org
    monkeypatch.setattr(
        engine,
        "run_agent",
        AsyncMock(return_value=AgentRunResult(response="Drafted.", conversation_id="c")),
    )

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {"id": "hold", "name": "Wait a day", "type": "wait", "minutes": 1440},
            {"id": "draft", "name": "Write it", "type": "agent", "agent": "receptionist", "prompt": "hi"},
        ],
    )

    run = await engine.start_run(db_session, definition, trigger_source="schedule")
    run = await engine.execute_run(db_session, run, definition)

    # Parked, not finished, and it knows where to pick up.
    assert run.status is RunStatus.running
    assert run.finished_at is None
    assert run.next_step_index == 1
    assert run.resume_at is not None and run.resume_at > _now()

    # Nothing is due yet, so a tick does not advance it.
    assert (await runner.tick())["advanced"] == 0

    # Fast-forward the clock by making it due, exactly as time passing would.
    run.resume_at = _now() - timedelta(seconds=1)
    await db_session.commit()

    result = await runner.tick()
    assert result["advanced"] == 1

    await db_session.refresh(run)
    assert run.status is RunStatus.success
    steps = await _steps_of(db_session, run)
    assert [(step.name, step.status) for step in steps] == [
        ("Wait a day", StepStatus.waiting),
        ("Write it", StepStatus.success),
    ]


async def test_a_failing_step_is_retried_then_fails_the_run_cleanly(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """A failure must leave a *closed* run with a readable reason — never a run
    stuck in `running` that no tick will ever pick up again."""
    _, org, _ = user_and_org

    attempts = {"count": 0}

    async def _flaky(*args, **kwargs):
        attempts["count"] += 1
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(TOOL_REGISTRY["calendar"], "execute", _flaky)

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "read",
                "name": "Read the diary",
                "type": "tool",
                "tool": "calendar",
                "as_agent": "receptionist",
                "arguments": {"action": "list_events"},
            },
            {"id": "never", "name": "Should not run", "type": "wait", "minutes": 0},
        ],
    )
    run = await engine.start_run(db_session, definition, trigger_source="schedule")
    run = await engine.execute_run(db_session, run, definition)

    assert attempts["count"] == 3  # WORKFLOW_STEP_MAX_ATTEMPTS
    assert run.status is RunStatus.failed
    assert run.finished_at is not None
    assert run.resume_at is None  # nothing will silently retry it forever
    assert run.error

    steps = await _steps_of(db_session, run)
    assert len(steps) == 1  # the run stopped, it did not carry on
    assert steps[0].attempts == 3


async def test_a_transient_failure_recovers_on_retry(db_session: AsyncSession, user_and_org, monkeypatch):
    _, org, _ = user_and_org
    attempts = {"count": 0}

    async def _flaky(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("connection reset")
        return ToolResult(success=True, data={"events": []}, message="Read the diary.")

    monkeypatch.setattr(TOOL_REGISTRY["calendar"], "execute", _flaky)

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "read",
                "name": "Read the diary",
                "type": "tool",
                "tool": "calendar",
                "as_agent": "receptionist",
                "arguments": {"action": "list_events"},
            }
        ],
    )
    run = await engine.start_run(db_session, definition, trigger_source="schedule")
    run = await engine.execute_run(db_session, run, definition)

    assert run.status is RunStatus.success
    steps = await _steps_of(db_session, run)
    assert steps[0].attempts == 2


async def test_an_optional_step_failing_does_not_lose_the_escalation(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """The escalation template marks its AI summary optional on purpose: if the
    provider is down, the human still gets told."""
    _, org, _ = user_and_org
    # Idempotent; the app normally does this at startup, and this test doesn't
    # build an app.
    register_audit_subscriber()
    monkeypatch.setattr(engine, "run_agent", AsyncMock(side_effect=RuntimeError("provider down")))

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "summarise",
                "name": "Summarise it",
                "type": "agent",
                "agent": "support",
                "optional": True,
                "prompt": "summarise",
            },
            {"id": "flag", "name": "Flag it for a human", "type": "escalate", "reason": "Nobody replied."},
        ],
    )
    run = await engine.start_run(db_session, definition, trigger_source="event")
    run = await engine.execute_run(db_session, run, definition)

    assert run.status is RunStatus.success
    steps = await _steps_of(db_session, run)
    assert steps[0].status is StepStatus.failed
    assert steps[1].status is StepStatus.success

    # It reached the Activity feed, which is where the owner actually sees it.
    async with async_session_factory() as fresh:
        entries = list(
            (
                await fresh.execute(
                    select(AuditLog).where(AuditLog.action == "workflow.escalation_raised")
                )
            )
            .scalars()
            .all()
        )
    assert len(entries) == 1
    assert entries[0].details["reason"] == "Nobody replied."


# ---------------------------------------------------------------------------
# Scheduling, locking and idempotency
# ---------------------------------------------------------------------------


async def test_two_runners_ticking_at_once_do_not_double_fire(
    db_session: AsyncSession, user_and_org
):
    """The whole reason there's no broker. Claiming is a conditional UPDATE
    that advances `next_run_at` in the same statement, so a second worker
    matches zero rows."""
    _, org, _ = user_and_org
    definition = await _definition(
        db_session,
        org.id,
        steps=[{"id": "noop", "name": "Do nothing", "type": "wait", "minutes": 0}],
        next_run_at=_now() - timedelta(minutes=1),
    )

    async with async_session_factory() as a, async_session_factory() as b:
        claimed_a = await service.claim_due_definitions(a, "worker-a", 600)
        claimed_b = await service.claim_due_definitions(b, "worker-b", 600)

    assert len(claimed_a) == 1
    assert claimed_b == []

    await db_session.refresh(definition)
    # The schedule moved forward as part of the claim, so it isn't due again.
    assert definition.next_run_at > _now()


async def test_repeated_ticks_do_not_start_the_same_scheduled_run_twice(
    db_session: AsyncSession, user_and_org
):
    _, org, _ = user_and_org
    await _definition(
        db_session,
        org.id,
        steps=[{"id": "noop", "name": "Do nothing", "type": "wait", "minutes": 0}],
        next_run_at=_now() - timedelta(minutes=1),
    )

    first = await runner.tick()
    second = await runner.tick()

    assert first["started"] == 1
    assert second["started"] == 0

    runs = list((await db_session.execute(select(WorkflowRun))).scalars().all())
    assert len(runs) == 1
    assert runs[0].status is RunStatus.success


async def test_a_disabled_workflow_is_never_claimed(db_session: AsyncSession, user_and_org):
    _, org, _ = user_and_org
    await _definition(
        db_session,
        org.id,
        steps=[{"id": "noop", "name": "Do nothing", "type": "wait", "minutes": 0}],
        enabled=False,
        next_run_at=_now() - timedelta(minutes=1),
    )
    assert (await runner.tick())["started"] == 0


async def test_a_stale_lock_is_taken_over_but_a_live_one_is_not(
    db_session: AsyncSession, user_and_org
):
    """An instance that dies mid-run must not strand the work forever — but a
    healthy one must not have it stolen either."""
    _, org, _ = user_and_org
    definition = await _definition(
        db_session,
        org.id,
        steps=[{"id": "noop", "name": "Do nothing", "type": "wait", "minutes": 0}],
        next_run_at=_now() - timedelta(minutes=1),
    )
    definition.locked_at = _now() - timedelta(seconds=30)
    definition.locked_by = "dead-worker"
    await db_session.commit()

    async with async_session_factory() as db:
        assert await service.claim_due_definitions(db, "worker-b", lock_timeout_seconds=600) == []

    async with async_session_factory() as db:
        claimed = await service.claim_due_definitions(db, "worker-b", lock_timeout_seconds=10)
    assert len(claimed) == 1


# ---------------------------------------------------------------------------
# Event triggers
# ---------------------------------------------------------------------------


async def test_an_inbound_message_starts_the_escalation_workflow(
    db_session: AsyncSession, user_and_org
):
    _, org, _ = user_and_org
    definitions = await service.seed_templates(db_session, org.id, enable=[NEW_LEAD_ESCALATION])
    escalation = next(d for d in definitions if d.slug == NEW_LEAD_ESCALATION)

    await runner.handle_event(
        "conversation.message_received",
        {
            "org_id": org.id,
            "conversation_key": "web-abc",
            "channel": "web_chat",
            "last_message": "do you have anything Thursday?",
        },
    )

    runs = list(
        (
            await db_session.execute(
                select(WorkflowRun).where(WorkflowRun.workflow_id == escalation.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].trigger_source == "event"
    assert runs[0].context["conversation_key"] == "web-abc"


async def test_an_event_workflow_ignores_channels_it_does_not_watch(
    db_session: AsyncSession, user_and_org
):
    _, org, _ = user_and_org
    await service.seed_templates(db_session, org.id, enable=[NEW_LEAD_ESCALATION])

    await runner.handle_event(
        "conversation.message_received",
        {"org_id": org.id, "conversation_key": "dash-1", "channel": "dashboard"},
    )
    assert list((await db_session.execute(select(WorkflowRun))).scalars().all()) == []


async def test_an_unanswered_enquiry_escalates_but_an_answered_one_does_not(
    db_session: AsyncSession, user_and_org
):
    """The escalation template's actual decision, exercised against real
    conversation rows rather than a mock."""
    _, org, _ = user_and_org

    async def _conversation(key: str, last_role: str) -> None:
        conversation = Conversation(
            org_id=org.id, key=key, agent_slug="receptionist", channel=ConversationChannel.web_chat
        )
        db_session.add(conversation)
        await db_session.flush()
        db_session.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content="are you open Saturday?",
                created_at=_now() - timedelta(minutes=40),
            )
        )
        if last_role == "assistant":
            db_session.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content="Yes, 9am to 1pm.",
                    created_at=_now() - timedelta(minutes=39),
                )
            )
        await db_session.commit()

    await _conversation("ignored-thread", "user")
    await _conversation("answered-thread", "assistant")

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "still_waiting",
                "name": "Is it still unanswered?",
                "type": "branch",
                "check": "conversation_unanswered",
                "params": {"minutes": 15},
                "on_false": "stop",
            },
            {"id": "flag", "name": "Flag it for a human", "type": "escalate", "reason": "Nobody replied."},
        ],
        trigger_type=TriggerType.event,
        enabled=False,
    )

    ignored = await engine.start_run(
        db_session, definition, "event", {"conversation_key": "ignored-thread"}
    )
    ignored = await engine.execute_run(db_session, ignored, definition)
    assert [s.status for s in await _steps_of(db_session, ignored)] == [
        StepStatus.success,
        StepStatus.success,
    ]

    answered = await engine.start_run(
        db_session, definition, "event", {"conversation_key": "answered-thread"}
    )
    answered = await engine.execute_run(db_session, answered, definition)
    steps = await _steps_of(db_session, answered)
    assert len(steps) == 1
    assert steps[0].status is StepStatus.skipped
    assert steps[0].detail == "It's already been answered."
    assert answered.status is RunStatus.success  # stopping early is not failing


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


async def test_listing_workflows_installs_the_three_templates_switched_off(
    client: AsyncClient, user_and_org
):
    _, org, headers = user_and_org
    response = await client.get("/api/v1/workflows", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert len(body) == 3
    assert all(item["enabled"] is False for item in body)
    assert {item["trigger"] for item in body} == {"Every day", "Every week", "When a new enquiry comes in"}
    # Plain language throughout — no cron strings, no step JSON leaked.
    assert all(set(item) == {
        "id", "name", "description", "trigger", "enabled", "last_run_at", "run_count", "success_count"
    } for item in body)


async def test_enabling_and_disabling_a_workflow(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    workflow_id = (await client.get("/api/v1/workflows", headers=headers)).json()[0]["id"]

    enabled = await client.post(f"/api/v1/workflows/{workflow_id}/enable", headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    disabled = await client.post(f"/api/v1/workflows/{workflow_id}/disable", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False


async def test_run_history_is_returned_with_its_steps(
    client: AsyncClient, db_session: AsyncSession, user_and_org, monkeypatch
):
    _, org, headers = user_and_org
    monkeypatch.setattr(TOOL_REGISTRY["whatsapp"], "execute", AsyncMock())

    definition = await _definition(
        db_session,
        org.id,
        steps=[
            {
                "id": "send",
                "name": "Send the reminder",
                "type": "tool",
                "tool": "whatsapp",
                "as_agent": "receptionist",
                "arguments": {"to": "+447700900412", "message": "Hello"},
            }
        ],
    )
    run = await engine.start_run(db_session, definition, "schedule")
    await engine.execute_run(db_session, run, definition)

    response = await client.get(f"/api/v1/workflows/{definition.id}/runs", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "success"
    assert body[0]["workflow_id"] == str(definition.id)
    assert body[0]["steps"] == [
        {
            "name": "Send the reminder",
            "status": "awaiting_approval",
            "detail": "Your Receptionist wants to send a WhatsApp message to a customer. "
            "Nothing was sent until you say so.",
        }
    ]


async def test_another_organizations_workflow_is_simply_not_found(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org, headers = user_and_org
    other = Organization(name="Other", slug=f"other-{uuid.uuid4().hex[:8]}", public_id=generate_public_id())
    db_session.add(other)
    await db_session.commit()

    theirs = await _definition(db_session, other.id, steps=[], slug="theirs")

    assert (await client.get(f"/api/v1/workflows/{theirs.id}/runs", headers=headers)).status_code == 404
    assert (await client.post(f"/api/v1/workflows/{theirs.id}/enable", headers=headers)).status_code == 404
    # ...and in plain language, with no hint that it exists elsewhere.
    body = (await client.post(f"/api/v1/workflows/{theirs.id}/disable", headers=headers)).json()
    assert body == {"error": "We couldn't find that automation."}


async def test_a_member_cannot_switch_an_automation_on(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    """Enabling one means it starts messaging customers, so it's an owner/admin
    decision — the same bar as approving an action."""
    from src.core.security import create_access_token

    _, org, headers = user_and_org
    workflow_id = (await client.get("/api/v1/workflows", headers=headers)).json()[0]["id"]

    member = User(email="nurse@example.com", hashed_password="x", name="Nurse")
    db_session.add(member)
    await db_session.flush()
    db_session.add(
        Membership(user_id=member.id, organization_id=org.id, role=MembershipRole.member, accepted=True)
    )
    await db_session.commit()

    member_headers = {
        "Authorization": f"Bearer {create_access_token(member.id)}",
        "X-Organization-Id": str(org.id),
    }
    response = await client.post(f"/api/v1/workflows/{workflow_id}/enable", headers=member_headers)
    assert response.status_code == 403
    # Reading them is fine.
    assert (await client.get("/api/v1/workflows", headers=member_headers)).status_code == 200


async def test_seeding_templates_is_idempotent(db_session: AsyncSession, user_and_org):
    _, org, _ = user_and_org
    first = await service.seed_templates(db_session, org.id, enable=[APPOINTMENT_REMINDER])
    second = await service.seed_templates(db_session, org.id)

    assert len(first) == len(second) == 3
    assert {d.id for d in first} == {d.id for d in second}
    # A re-seed must not quietly switch off something the owner turned on.
    assert next(d for d in second if d.slug == APPOINTMENT_REMINDER).enabled is True


@pytest.mark.parametrize(
    "steps,expected",
    [
        ([{"id": "x", "name": "Odd step", "type": "teleport"}], "step we don't recognise"),
        (
            [{"id": "x", "name": "Odd check", "type": "branch", "check": "rm_rf"}],
            "condition we don't recognise",
        ),
    ],
)
async def test_a_nonsense_definition_fails_readably_instead_of_crashing(
    db_session: AsyncSession, user_and_org, steps, expected
):
    """Definitions are database rows, so they can say anything. Whatever they
    say must never become executable — an unknown step type or condition is a
    failed step with a sentence in it, not an eval()."""
    _, org, _ = user_and_org
    definition = await _definition(db_session, org.id, steps=steps)
    run = await engine.start_run(db_session, definition, "manual")
    run = await engine.execute_run(db_session, run, definition)

    assert run.status is RunStatus.failed
    assert expected in (await _steps_of(db_session, run))[0].detail
