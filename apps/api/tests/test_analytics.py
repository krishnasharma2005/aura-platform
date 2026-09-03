"""Analytics summary: the numbers have to be right, and they have to be this
organization's numbers only.

A dashboard that quietly mixes two tenants' counts is a worse failure than one
that returns nothing, so tenant isolation gets a test of its own with a second
org holding deliberately different volumes.
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import approvals as approvals_service
from src.agents.approvals import ApprovalStatus
from src.conversations.models import Conversation, ConversationChannel, Message
from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _thread(
    db: AsyncSession,
    org_id: uuid.UUID,
    key: str,
    agent_slug: str,
    days_ago: float,
    turns: list[tuple[str, list | None]],
) -> None:
    started = _now() - timedelta(days=days_ago)
    conversation = Conversation(
        org_id=org_id,
        key=key,
        agent_slug=agent_slug,
        channel=ConversationChannel.web_chat,
        started_at=started,
        last_message_at=started,
    )
    db.add(conversation)
    await db.flush()
    for index, (role, tool_calls) in enumerate(turns):
        db.add(
            Message(
                conversation_id=conversation.id,
                role=role,
                content=f"{role} message {index}",
                tool_calls=tool_calls,
                created_at=started + timedelta(minutes=index),
            )
        )
    await db.commit()


async def test_summary_counts_are_correct(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org, headers = user_and_org

    # 3 conversations in range: 4 assistant turns, 3 tool calls on them.
    await _thread(db_session, org.id, "a", "receptionist", 1, [("user", None), ("assistant", ["calendar"])])
    await _thread(
        db_session,
        org.id,
        "b",
        "receptionist",
        2,
        [("user", None), ("assistant", ["calendar", "whatsapp"]), ("user", None)],
    )
    await _thread(db_session, org.id, "c", "support", 3, [("user", None), ("assistant", None)])
    # ...and one that is older than the window and must not be counted.
    await _thread(db_session, org.id, "old", "sales", 30, [("user", None), ("assistant", ["gmail"])])

    pending = await approvals_service.create_pending(
        db_session,
        org_id=org.id,
        agent_slug="receptionist",
        agent_display_name="Receptionist",
        conversation_id="a",
        tool_name="calendar",
        arguments={"action": "create_event"},
    )
    approved = await approvals_service.create_pending(
        db_session,
        org_id=org.id,
        agent_slug="support",
        agent_display_name="Customer Support",
        conversation_id="c",
        tool_name="gmail",
        arguments={"action": "send_email"},
    )
    approved.status = ApprovalStatus.approved
    await db_session.commit()

    response = await client.get("/api/v1/analytics/summary?days=7", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["range_days"] == 7
    assert body["conversations_handled"] == 3
    assert body["messages_sent"] == 3
    # 3 inline tool calls + 1 approved action.
    assert body["actions_taken"] == 4
    assert body["approvals_pending"] == 1
    assert body["approvals_approved"] == 1

    by_agent = {row["agent_slug"]: row for row in body["by_agent"]}
    assert set(by_agent) == {"receptionist", "support"}
    assert by_agent["receptionist"]["display_name"] == "Receptionist"
    assert by_agent["receptionist"]["conversations"] == 2
    assert by_agent["receptionist"]["messages"] == 2
    assert by_agent["receptionist"]["actions"] == 3
    assert by_agent["support"]["actions"] == 1  # the approved one

    # Seven zero-filled days, oldest first, so a chart has no gaps.
    assert len(body["daily"]) == 7
    assert [point["date"] for point in body["daily"]] == sorted(point["date"] for point in body["daily"])
    assert sum(point["messages"] for point in body["daily"]) == 7
    assert sum(point["conversations"] for point in body["daily"]) == 3
    assert pending.id  # referenced so the fixture reads as intentional


async def test_the_range_is_respected(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org, headers = user_and_org
    await _thread(db_session, org.id, "recent", "receptionist", 1, [("user", None), ("assistant", None)])
    await _thread(db_session, org.id, "older", "receptionist", 20, [("user", None), ("assistant", None)])

    week = (await client.get("/api/v1/analytics/summary?days=7", headers=headers)).json()
    month = (await client.get("/api/v1/analytics/summary?days=30", headers=headers)).json()

    assert week["conversations_handled"] == 1
    assert month["conversations_handled"] == 2
    assert len(month["daily"]) == 30


async def test_one_organizations_numbers_never_include_anothers(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org, headers = user_and_org

    other = Organization(
        name="Lumen Aesthetics", slug=f"lumen-{uuid.uuid4().hex[:8]}", public_id=generate_public_id()
    )
    db_session.add(other)
    await db_session.flush()
    other_user = User(email="other@example.com", hashed_password="x", name="Other")
    db_session.add(other_user)
    await db_session.flush()
    db_session.add(
        Membership(
            user_id=other_user.id, organization_id=other.id, role=MembershipRole.owner, accepted=True
        )
    )
    await db_session.commit()

    await _thread(db_session, org.id, "mine", "receptionist", 1, [("user", None), ("assistant", ["calendar"])])
    for index in range(5):
        await _thread(
            db_session,
            other.id,
            f"theirs-{index}",
            "receptionist",
            1,
            [("user", None), ("assistant", ["calendar"]), ("assistant", ["whatsapp"])],
        )
    await approvals_service.create_pending(
        db_session,
        org_id=other.id,
        agent_slug="receptionist",
        agent_display_name="Receptionist",
        conversation_id="theirs-0",
        tool_name="whatsapp",
        arguments={"to": "x", "message": "y"},
    )

    mine = (await client.get("/api/v1/analytics/summary?days=7", headers=headers)).json()
    assert mine["conversations_handled"] == 1
    assert mine["messages_sent"] == 1
    assert mine["actions_taken"] == 1
    assert mine["approvals_pending"] == 0

    other_headers = {
        "Authorization": f"Bearer {create_access_token(other_user.id)}",
        "X-Organization-Id": str(other.id),
    }
    theirs = (await client.get("/api/v1/analytics/summary?days=7", headers=other_headers)).json()
    assert theirs["conversations_handled"] == 5
    assert theirs["messages_sent"] == 10
    assert theirs["approvals_pending"] == 1

    # Asking for someone else's org with your own token is a permission error,
    # not a silent empty dashboard.
    cross = await client.get(
        "/api/v1/analytics/summary",
        headers={"Authorization": headers["Authorization"], "X-Organization-Id": str(other.id)},
    )
    assert cross.status_code == 403
    assert cross.json() == {"error": "You don't have access to this organization."}


async def test_an_empty_organization_returns_zeroes_not_an_error(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    body = (await client.get("/api/v1/analytics/summary?days=7", headers=headers)).json()
    assert body["conversations_handled"] == 0
    assert body["by_agent"] == []
    assert len(body["daily"]) == 7
    assert all(point["messages"] == 0 for point in body["daily"])


async def test_the_seeded_demo_produces_numbers_worth_showing(
    client: AsyncClient, db_session: AsyncSession
):
    """An analytics dashboard showing zeroes is worse than no dashboard, so the
    demo seed has to put real volume behind it."""
    from scripts.seed_demo import ORG_SLUG, seed
    from sqlalchemy import select

    await seed(db_session)
    org = (
        await db_session.execute(select(Organization).where(Organization.slug == ORG_SLUG))
    ).scalar_one()

    user = (
        await db_session.execute(select(User).where(User.email == "sarah@riversidedental.co.uk"))
    ).scalar_one()
    headers = {
        "Authorization": f"Bearer {create_access_token(user.id)}",
        "X-Organization-Id": str(org.id),
    }

    body = (await client.get("/api/v1/analytics/summary?days=7", headers=headers)).json()

    assert body["conversations_handled"] >= 20
    assert body["messages_sent"] >= 20
    assert body["actions_taken"] > 0
    assert body["approvals_pending"] == 1
    assert len(body["by_agent"]) >= 3
    # Every day of the week has something on it — no empty-looking chart.
    assert all(point["conversations"] > 0 for point in body["daily"])

    workflows = (await client.get("/api/v1/workflows", headers=headers)).json()
    assert len(workflows) == 3
    assert all(item["enabled"] for item in workflows)
    assert all(item["run_count"] > 0 for item in workflows)

    runs = (
        await client.get(f"/api/v1/workflows/{workflows[0]['id']}/runs", headers=headers)
    ).json()
    assert runs
    assert any(step["status"] == "awaiting_approval" for run in runs for step in run["steps"])
