"""Human-approval gate: the queued action must not run until an owner says so,
must run exactly once when they do, and must never be visible or approvable
across tenants."""

import uuid
from unittest.mock import AsyncMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import approvals as approvals_service
from src.agents.approvals import ApprovalStatus
from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User
from src.tools.base import ToolResult
from src.tools.registry import TOOL_REGISTRY


async def _pending(db: AsyncSession, org_id: uuid.UUID) -> "approvals_service.ToolApproval":
    return await approvals_service.create_pending(
        db,
        org_id=org_id,
        agent_slug="receptionist",
        agent_display_name="Receptionist",
        conversation_id="conv-1",
        tool_name="calendar",
        arguments={"action": "create_event", "start_time": "2026-08-18T15:00:00", "end_time": "2026-08-18T16:00:00"},
    )


async def test_pending_approval_is_listed_in_plain_language(client: AsyncClient, db_session, user_and_org):
    _, org, headers = user_and_org
    await _pending(db_session, org.id)

    response = await client.get("/api/v1/approvals", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["summary"] == "Your Receptionist wants to book an appointment on your calendar."
    assert body[0]["status"] == "pending"
    assert body[0]["agent_display_name"] == "Receptionist"
    assert body[0]["details"]["start_time"] == "2026-08-18T15:00:00"


async def test_approving_executes_the_action_once(client: AsyncClient, db_session, user_and_org, monkeypatch):
    _, org, headers = user_and_org
    approval = await _pending(db_session, org.id)

    fake_calendar = AsyncMock(return_value=ToolResult(success=True, message="Appointment booked."))
    monkeypatch.setattr(TOOL_REGISTRY["calendar"], "execute", fake_calendar)

    response = await client.post(f"/api/v1/approvals/{approval.id}/approve", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["result_message"] == "Appointment booked."
    fake_calendar.assert_awaited_once()

    # A second approve must not run it again.
    repeat = await client.post(f"/api/v1/approvals/{approval.id}/approve", headers=headers)
    assert repeat.status_code == 409
    assert fake_calendar.await_count == 1


async def test_rejecting_never_executes_the_action(client: AsyncClient, db_session, user_and_org, monkeypatch):
    _, org, headers = user_and_org
    approval = await _pending(db_session, org.id)

    fake_calendar = AsyncMock()
    monkeypatch.setattr(TOOL_REGISTRY["calendar"], "execute", fake_calendar)

    response = await client.post(f"/api/v1/approvals/{approval.id}/reject", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    fake_calendar.assert_not_awaited()


async def test_approval_from_another_org_is_not_visible_or_approvable(
    client: AsyncClient, db_session: AsyncSession, user_and_org, monkeypatch
):
    """Tenant isolation on the approval id itself: knowing another org's
    approval uuid must not be enough to see it or trigger it."""
    _, org_a, _ = user_and_org
    approval_a = await _pending(db_session, org_a.id)

    attacker = User(email="attacker@example.com", hashed_password="x", name="Attacker")
    db_session.add(attacker)
    await db_session.flush()
    org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}")
    db_session.add(org_b)
    await db_session.flush()
    db_session.add(
        Membership(user_id=attacker.id, organization_id=org_b.id, role=MembershipRole.owner, accepted=True)
    )
    await db_session.commit()

    headers_b = {
        "Authorization": f"Bearer {create_access_token(attacker.id)}",
        "X-Organization-Id": str(org_b.id),
    }

    fake_calendar = AsyncMock()
    monkeypatch.setattr(TOOL_REGISTRY["calendar"], "execute", fake_calendar)

    listing = await client.get("/api/v1/approvals", headers=headers_b)
    assert listing.status_code == 200
    assert listing.json() == []

    hijack = await client.post(f"/api/v1/approvals/{approval_a.id}/approve", headers=headers_b)
    assert hijack.status_code == 404
    fake_calendar.assert_not_awaited()

    still_pending = await approvals_service.list_for_org(db_session, org_a.id, status=ApprovalStatus.pending)
    assert len(still_pending) == 1


async def test_plain_member_cannot_approve(client: AsyncClient, db_session: AsyncSession, user_and_org, monkeypatch):
    """Approving is an owner/admin decision — a regular member must not be able
    to wave through an action on the business's behalf."""
    _, org, _ = user_and_org
    approval = await _pending(db_session, org.id)

    member = User(email="member@example.com", hashed_password="x", name="Member")
    db_session.add(member)
    await db_session.flush()
    db_session.add(
        Membership(user_id=member.id, organization_id=org.id, role=MembershipRole.member, accepted=True)
    )
    await db_session.commit()

    headers = {
        "Authorization": f"Bearer {create_access_token(member.id)}",
        "X-Organization-Id": str(org.id),
    }

    fake_calendar = AsyncMock()
    monkeypatch.setattr(TOOL_REGISTRY["calendar"], "execute", fake_calendar)

    response = await client.post(f"/api/v1/approvals/{approval.id}/approve", headers=headers)
    assert response.status_code == 403
    fake_calendar.assert_not_awaited()
