"""Durable conversation storage: write-through from the runtime, the cold-read
fallback when Redis has expired a thread, and tenant isolation on the new
history endpoints."""

import uuid
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime import pipeline as pipeline_module
from src.agents.runtime.pipeline import run_agent
from src.ai_gateway.providers.base import LLMResponse
from src.conversations import service as conversation_service
from src.conversations.models import ConversationChannel
from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id
from src.memory import short_term


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


async def _second_org(db_session: AsyncSession) -> tuple[Organization, dict]:
    user = User(email=f"other-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", name="Other")
    db_session.add(user)
    await db_session.flush()
    org = Organization(
        name="Other Org", slug=f"other-{uuid.uuid4().hex[:8]}", public_id=generate_public_id()
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.owner, accepted=True))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}", "X-Organization-Id": str(org.id)}
    return org, headers


async def test_turns_are_persisted_to_postgres_not_only_redis(db_session: AsyncSession, user_and_org):
    """Regression for the core gap: conversation history used to evaporate
    after 24h because Redis was the only store."""
    _, org, _ = user_and_org
    gateway = FakeGateway([LLMResponse(content="We're open until 5:30pm today.")])

    await run_agent(
        db=db_session,
        gateway=gateway,
        org_id=org.id,
        agent_slug="receptionist",
        conversation_id="conv-persist",
        user_message="Are you open this afternoon?",
    )

    stored = await conversation_service.get_turns(db_session, org.id, "conv-persist")
    assert [(t["role"], t["content"]) for t in stored] == [
        ("user", "Are you open this afternoon?"),
        ("assistant", "We're open until 5:30pm today."),
    ]

    conversation = await conversation_service.get_conversation(db_session, org.id, "conv-persist")
    assert conversation is not None
    assert conversation.agent_slug == "receptionist"
    assert conversation.channel is ConversationChannel.dashboard


async def test_cold_conversation_is_read_back_from_postgres(db_session: AsyncSession, user_and_org):
    """After Redis expires the thread, the next message must still arrive with
    the earlier turns in the prompt — otherwise the agent has amnesia."""
    _, org, _ = user_and_org

    first = FakeGateway([LLMResponse(content="Of course — what day suits you?")])
    await run_agent(
        db=db_session,
        gateway=first,
        org_id=org.id,
        agent_slug="receptionist",
        conversation_id="conv-cold",
        user_message="I'd like to book a check-up.",
    )

    # Simulate the 24h TTL expiring.
    await short_term.clear_conversation(str(org.id), "conv-cold")
    assert await short_term.get_turns(str(org.id), "conv-cold") == []

    second = FakeGateway([LLMResponse(content="Thursday at 10am is free.")])
    await run_agent(
        db=db_session,
        gateway=second,
        org_id=org.id,
        agent_slug="receptionist",
        conversation_id="conv-cold",
        user_message="Thursday please.",
    )

    messages = second.complete.await_args_list[0].args[0]
    contents = [m["content"] for m in messages]
    assert "I'd like to book a check-up." in contents
    assert "Of course — what day suits you?" in contents

    # And the rehydrated turns are back in the hot path for the next request.
    assert len(await short_term.get_turns(str(org.id), "conv-cold")) == 4


async def test_conversation_list_is_scoped_to_the_callers_org(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org_a, headers_a = user_and_org
    org_b, headers_b = await _second_org(db_session)

    await conversation_service.record_turns(
        db_session, org_id=org_a.id, key="a-thread", agent_slug="receptionist",
        turns=[("user", "ours", None), ("assistant", "ours reply", None)],
    )
    await conversation_service.record_turns(
        db_session, org_id=org_b.id, key="b-thread", agent_slug="sales",
        turns=[("user", "theirs", None), ("assistant", "theirs reply", None)],
    )

    a = await client.get("/api/v1/conversations", headers=headers_a)
    b = await client.get("/api/v1/conversations", headers=headers_b)
    assert [row["id"] for row in a.json()] == ["a-thread"]
    assert [row["id"] for row in b.json()] == ["b-thread"]
    assert a.json()[0]["message_count"] == 2
    assert a.json()[0]["agent_display_name"] == "Receptionist"


async def test_conversation_list_can_be_filtered_by_agent(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org, headers = user_and_org
    await conversation_service.record_turns(
        db_session, org_id=org.id, key="r-1", agent_slug="receptionist",
        turns=[("user", "hi", None)],
    )
    await conversation_service.record_turns(
        db_session, org_id=org.id, key="s-1", agent_slug="sales", turns=[("user", "hi", None)]
    )

    response = await client.get("/api/v1/conversations?agent=sales", headers=headers)
    assert [row["id"] for row in response.json()] == ["s-1"]


async def test_another_orgs_conversation_id_is_not_readable(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    """Conversation keys are only unique per org and are client-supplied, so
    knowing one must never be enough to read it."""
    _, _, headers_a = user_and_org
    org_b, _ = await _second_org(db_session)
    await conversation_service.record_turns(
        db_session, org_id=org_b.id, key="secret-thread", agent_slug="receptionist",
        turns=[("user", "their private message", None)],
    )

    detail = await client.get("/api/v1/conversations/secret-thread", headers=headers_a)
    assert detail.status_code == 404
    assert "private" not in detail.text

    via_agent = await client.get(
        "/api/v1/agents/receptionist/conversations/secret-thread", headers=headers_a
    )
    assert via_agent.status_code == 200
    assert via_agent.json() == []


async def test_agent_history_endpoint_reads_the_durable_transcript(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org, headers = user_and_org
    await conversation_service.record_turns(
        db_session, org_id=org.id, key="conv-history", agent_slug="receptionist",
        turns=[("user", "What time do you close?", None), ("assistant", "5:30pm today.", ["calendar"])],
    )

    response = await client.get("/api/v1/agents/receptionist/conversations/conv-history", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [turn["content"] for turn in body] == ["What time do you close?", "5:30pm today."]
    assert body[1]["tool_calls"] == ["calendar"]
