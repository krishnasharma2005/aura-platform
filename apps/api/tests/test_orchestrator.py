"""Chief of Staff / delegation tests. Follows the FakeGateway + TOOL_REGISTRY
monkeypatch conventions in test_agent_runtime.py — see that file's module
docstring for why no OpenAI key or network access is required here."""

from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime import pipeline as pipeline_module
from src.agents.runtime.pipeline import AgentRunResult, RunContext, run_agent
from src.ai_gateway.providers.base import LLMResponse, ToolCall
from src.conversations.models import ConversationChannel
from src.tools.base import ToolResult
from src.tools.delegate import DelegateTool
from src.tools.registry import TOOL_REGISTRY
from tests.test_agent_runtime import FakeGateway


async def test_chief_of_staff_delegates_and_reports_the_specialists_answer(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """Unit-level: the Chief of Staff's own run_agent loop permission-checks
    and invokes `delegate` like any other tool. What DelegateTool.execute
    actually does is stubbed here — covered on its own below and in the
    end-to-end test."""
    _, org, _ = user_and_org

    fake_delegate = AsyncMock(
        return_value=ToolResult(
            success=True,
            data={"agent": "sales", "response": "You have 4 open leads; 2 need a follow-up today.", "pending_approvals": []},
            message="You have 4 open leads; 2 need a follow-up today.",
        )
    )
    monkeypatch.setattr(TOOL_REGISTRY["delegate"], "execute", fake_delegate)

    tool_call = ToolCall(id="call_1", name="delegate", arguments={"action": "sales", "task": "Any leads need follow-up today?"})
    gateway = FakeGateway(
        [
            LLMResponse(content=None, tool_calls=[tool_call], finish_reason="tool_calls"),
            LLMResponse(content="Sales says you have 4 open leads; 2 need a follow-up today."),
        ]
    )

    result = await run_agent(
        db=db_session,
        gateway=gateway,
        org_id=org.id,
        agent_slug="chief-of-staff",
        conversation_id="conv-cos-1",
        user_message="Anything I should follow up on today?",
    )

    assert result.tool_calls_made == ["delegate"]
    assert result.pending_approvals == []
    assert "4 open leads" in result.response
    fake_delegate.assert_awaited_once()
    _, kwargs = fake_delegate.call_args
    assert kwargs["action"] == "sales"
    assert kwargs["task"] == "Any leads need follow-up today?"


async def test_a_specialist_agent_cannot_call_delegate(db_session: AsyncSession, user_and_org):
    """Regression guard for the "no runaway delegation loops" invariant: only
    chief_of_staff.yaml lists `delegate` in allowed_tools, so a specialist
    asking for it must be refused, not executed."""
    _, org, _ = user_and_org

    from src.core.exceptions import PermissionError

    tool_call = ToolCall(id="call_1", name="delegate", arguments={"action": "marketing", "task": "help"})
    gateway = FakeGateway([LLMResponse(content=None, tool_calls=[tool_call], finish_reason="tool_calls")])

    try:
        await run_agent(
            db=db_session,
            gateway=gateway,
            org_id=org.id,
            agent_slug="sales",
            conversation_id="conv-cos-2",
            user_message="Do something",
        )
        assert False, "expected a PermissionError"
    except PermissionError:
        pass


async def test_delegate_tool_calls_run_agent_with_a_derived_sub_conversation(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """Isolated unit test of DelegateTool.execute itself, not the outer loop:
    monkeypatches the lazily-imported `run_agent` target directly."""
    _, org, _ = user_and_org

    fake_run_agent = AsyncMock(
        return_value=AgentRunResult(response="Booked for Tuesday.", conversation_id="conv-3::receptionist")
    )
    monkeypatch.setattr(pipeline_module, "run_agent", fake_run_agent)

    gateway = FakeGateway([])
    context = RunContext(
        conversation_id="conv-3",
        channel=ConversationChannel.dashboard,
        contact_id=None,
        gateway=gateway,
    )

    result = await DelegateTool().execute(
        db_session, org.id, action="receptionist", task="Book Tuesday 3pm.", _context=context
    )

    assert result.success is True
    assert result.data["agent"] == "receptionist"
    assert result.message == "Booked for Tuesday."
    fake_run_agent.assert_awaited_once()
    args, kwargs = fake_run_agent.call_args
    # run_agent(db, gateway, org_id, agent_slug, conversation_id, user_message, channel=..., contact_id=...)
    assert args[1] is gateway
    assert args[3] == "receptionist"
    assert args[4] == "conv-3::receptionist"
    assert args[5] == "Book Tuesday 3pm."
    assert kwargs["channel"] == ConversationChannel.dashboard
    assert kwargs["contact_id"] is None


async def test_delegate_tool_reports_a_specialists_aura_error_instead_of_crashing(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """Regression: a specialist's own failure (e.g. an unconnected
    integration) must come back as a ToolResult the Chief of Staff can relay
    in its own reply, not an exception that 500s the whole delegated turn."""
    from src.core.exceptions import ProviderNotConfiguredError

    _, org, _ = user_and_org

    fake_run_agent = AsyncMock(side_effect=ProviderNotConfiguredError("Please connect Google first."))
    monkeypatch.setattr(pipeline_module, "run_agent", fake_run_agent)

    gateway = FakeGateway([])
    context = RunContext(conversation_id="conv-6", channel=ConversationChannel.dashboard, contact_id=None, gateway=gateway)

    result = await DelegateTool().execute(
        db_session, org.id, action="executive_assistant", task="What's on the calendar?", _context=context
    )

    assert result.success is False
    assert "Please connect Google first." in result.message


async def test_delegate_tool_rejects_self_delegation_and_unknown_agents(db_session: AsyncSession, user_and_org):
    _, org, _ = user_and_org
    gateway = FakeGateway([])
    context = RunContext(conversation_id="conv-4", channel=ConversationChannel.dashboard, contact_id=None, gateway=gateway)

    result = await DelegateTool().execute(db_session, org.id, action="chief-of-staff", task="x", _context=context)
    assert result.success is False

    result = await DelegateTool().execute(db_session, org.id, action="not-a-real-agent", task="x", _context=context)
    assert result.success is False


async def test_a_delegated_specialists_consequential_action_still_needs_approval(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """End to end, real DelegateTool, one shared FakeGateway driving both the
    Chief of Staff's turn AND the nested Sales turn it delegates to. Proves
    that delegating to Sales doesn't bypass Sales's own requires_approval —
    the resulting approval must be attributed to "sales", not
    "chief-of-staff", and must live under the nested conversation id."""
    from src.agents.approvals import ApprovalStatus, list_for_org

    _, org, _ = user_and_org

    fake_hubspot = AsyncMock(return_value=ToolResult(success=True))
    monkeypatch.setattr(TOOL_REGISTRY["hubspot"], "execute", fake_hubspot)

    delegate_call = ToolCall(
        id="call_1",
        name="delegate",
        arguments={"action": "sales", "task": "Update Acme Corp's deal stage to won."},
    )
    hubspot_call = ToolCall(
        id="call_2", name="hubspot", arguments={"action": "update_contact", "contact_id": "acme-1"}
    )
    gateway = FakeGateway(
        [
            # Chief of Staff's first turn: decides to delegate.
            LLMResponse(content=None, tool_calls=[delegate_call], finish_reason="tool_calls"),
            # Sales's (nested) first turn: asks for a CRM update, which needs approval.
            LLMResponse(content=None, tool_calls=[hubspot_call], finish_reason="tool_calls"),
            # Sales's follow-up, after being told the update is pending approval.
            LLMResponse(content="I've asked the owner to approve that CRM update."),
            # Chief of Staff's follow-up, after hearing back from Sales.
            LLMResponse(content="Sales has asked for your approval to update that deal."),
        ]
    )

    result = await run_agent(
        db=db_session,
        gateway=gateway,
        org_id=org.id,
        agent_slug="chief-of-staff",
        conversation_id="conv-cos-5",
        user_message="Mark Acme Corp's deal as won.",
    )

    assert result.tool_calls_made == ["delegate"]
    assert "approval" in result.response.lower()
    fake_hubspot.assert_not_awaited()

    pending = await list_for_org(db_session, org.id, status=ApprovalStatus.pending)
    assert len(pending) == 1
    assert pending[0].agent_slug == "sales"
    assert pending[0].conversation_id == "conv-cos-5::sales"
