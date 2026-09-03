"""Conversation takeover: the state machine that lets an owner post messages
directly into a live conversation, and that stops the agent from
autonomously answering while a human is in control.

Trust-critical per docs/customer-profile.md, so the tests focus on the states
being unambiguous: agent-controlled by default, human-controlled only after
an explicit takeover, and agent control restored only by an explicit
hand-back — never anything in between.
"""

import uuid
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime import pipeline as pipeline_module
from src.agents.runtime.pipeline import run_agent
from src.ai_gateway.providers.base import LLMResponse
from src.conversations import service as conversation_service
from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User


@pytest_asyncio.fixture(autouse=True)
def _no_knowledge_search(monkeypatch):
    async def _empty_search(*args, **kwargs):
        return []

    monkeypatch.setattr(pipeline_module, "search_knowledge", _empty_search)


class FakeGateway:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.complete = AsyncMock(side_effect=self._pop_response)
        self.embed = AsyncMock(return_value=[[0.0] * 1536])

    async def _pop_response(self, *args, **kwargs) -> LLMResponse:
        return self._responses.pop(0)


async def _member_headers(db_session: AsyncSession, org: Organization) -> dict:
    """A plain member (not owner/admin) — takeover/handback/messages must be
    refused for them, same bar as approvals."""
    user = User(email=f"member-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", name="Member")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.member, accepted=True))
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}", "X-Organization-Id": str(org.id)}


async def test_agent_answers_normally_by_default(db_session: AsyncSession, user_and_org):
    _, org, _ = user_and_org
    gateway = FakeGateway([LLMResponse(content="We're open until 5:30pm today.")])

    result = await run_agent(
        db=db_session,
        gateway=gateway,
        org_id=org.id,
        agent_slug="receptionist",
        conversation_id="conv-default",
        user_message="Are you open?",
    )

    assert result.human_controlled is False
    assert result.response == "We're open until 5:30pm today."
    gateway.complete.assert_awaited()


async def test_agent_does_not_respond_once_a_human_has_taken_over(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org, headers = user_and_org
    gateway = FakeGateway([LLMResponse(content="First reply.")])

    # One normal turn creates the conversation.
    await run_agent(
        db=db_session,
        gateway=gateway,
        org_id=org.id,
        agent_slug="receptionist",
        conversation_id="conv-takeover",
        user_message="Hi there",
    )

    response = await client.post("/api/v1/conversations/conv-takeover/takeover", headers=headers)
    assert response.status_code == 200
    assert response.json()["mode"] == "human"

    # A second gateway that would fail the test if it were ever called.
    never_called_gateway = FakeGateway([])

    result = await run_agent(
        db=db_session,
        gateway=never_called_gateway,
        org_id=org.id,
        agent_slug="receptionist",
        conversation_id="conv-takeover",
        user_message="Are you still there?",
    )

    assert result.human_controlled is True
    never_called_gateway.complete.assert_not_awaited()

    # The customer's message is still recorded even though the agent didn't
    # answer — nothing about a takeover should make the transcript incomplete.
    turns = await conversation_service.get_turns(db_session, org.id, "conv-takeover")
    assert turns[-1]["role"] == "user"
    assert turns[-1]["content"] == "Are you still there?"


async def test_hand_back_restores_agent_control(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org, headers = user_and_org
    setup_gateway = FakeGateway([LLMResponse(content="Sure, one moment.")])
    await run_agent(
        db=db_session, gateway=setup_gateway, org_id=org.id, agent_slug="receptionist",
        conversation_id="conv-handback", user_message="Hello",
    )

    await client.post("/api/v1/conversations/conv-handback/takeover", headers=headers)

    handback = await client.post("/api/v1/conversations/conv-handback/handback", headers=headers)
    assert handback.status_code == 200
    assert handback.json()["mode"] == "agent"

    gateway = FakeGateway([LLMResponse(content="Welcome back, the agent's got it.")])
    result = await run_agent(
        db=db_session, gateway=gateway, org_id=org.id, agent_slug="receptionist",
        conversation_id="conv-handback", user_message="Anyone there?",
    )
    assert result.human_controlled is False
    assert result.response == "Welcome back, the agent's got it."
    gateway.complete.assert_awaited()


async def test_taking_over_twice_is_a_conflict(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org, headers = user_and_org
    gateway = FakeGateway([LLMResponse(content="Hi!")])
    await run_agent(
        db=db_session, gateway=gateway, org_id=org.id, agent_slug="receptionist",
        conversation_id="conv-dup", user_message="Hello",
    )
    first = await client.post("/api/v1/conversations/conv-dup/takeover", headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/v1/conversations/conv-dup/takeover", headers=headers)
    assert second.status_code == 409


async def test_human_message_requires_takeover_first(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org, headers = user_and_org
    gateway = FakeGateway([LLMResponse(content="Hi!")])
    await run_agent(
        db=db_session, gateway=gateway, org_id=org.id, agent_slug="receptionist",
        conversation_id="conv-nohandoff", user_message="Hello",
    )

    response = await client.post(
        "/api/v1/conversations/conv-nohandoff/messages", json={"content": "I'll take it from here."},
        headers=headers,
    )
    assert response.status_code == 409


async def test_human_message_is_attributed_to_the_human_not_the_agent(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org, headers = user_and_org
    gateway = FakeGateway([LLMResponse(content="Hi!")])
    await run_agent(
        db=db_session, gateway=gateway, org_id=org.id, agent_slug="receptionist",
        conversation_id="conv-attr", user_message="Hello",
    )
    await client.post("/api/v1/conversations/conv-attr/takeover", headers=headers)

    response = await client.post(
        "/api/v1/conversations/conv-attr/messages",
        json={"content": "This is Dana from the front desk — I've got this."},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "human"
    assert body["content"] == "This is Dana from the front desk — I've got this."

    transcript = await client.get("/api/v1/conversations/conv-attr", headers=headers)
    roles = [turn["role"] for turn in transcript.json()]
    assert "human" in roles
    assert "assistant" in roles  # the earlier agent turn is still there, distinctly


async def test_members_cannot_take_over_or_hand_back(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org, owner_headers = user_and_org
    gateway = FakeGateway([LLMResponse(content="Hi!")])
    await run_agent(
        db=db_session, gateway=gateway, org_id=org.id, agent_slug="receptionist",
        conversation_id="conv-member", user_message="Hello",
    )
    member_headers = await _member_headers(db_session, org)

    response = await client.post("/api/v1/conversations/conv-member/takeover", headers=member_headers)
    assert response.status_code == 403

    await client.post("/api/v1/conversations/conv-member/takeover", headers=owner_headers)
    response = await client.post(
        "/api/v1/conversations/conv-member/messages", json={"content": "hi"}, headers=member_headers
    )
    assert response.status_code == 403
