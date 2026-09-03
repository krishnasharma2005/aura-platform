"""Cross-tenant isolation on the org-scoped read paths, plus the guarantee that
nothing a business owner reads is a stack trace, a provider error, or jargon."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.events.audit import AuditLog
from src.identity.models import Membership, MembershipRole, Organization, User
from src.memory import long_term
from src.memory.models import KnowledgeChunk
from src.tools.oauth_common import store_integration


async def _second_org(db_session: AsyncSession) -> tuple[Organization, dict]:
    user = User(email=f"other-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", name="Other")
    db_session.add(user)
    await db_session.flush()
    org = Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.owner, accepted=True))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}", "X-Organization-Id": str(org.id)}
    return org, headers


async def test_activity_feed_is_scoped_to_the_callers_org(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org_a, headers_a = user_and_org
    org_b, headers_b = await _second_org(db_session)

    db_session.add(AuditLog(org_id=org_a.id, actor="receptionist", action="agent.response_generated", details={}))
    db_session.add(AuditLog(org_id=org_b.id, actor="sales", action="agent.response_generated", details={}))
    await db_session.commit()

    a = await client.get("/api/v1/audit-logs", headers=headers_a)
    b = await client.get("/api/v1/audit-logs", headers=headers_b)
    assert [row["agent_slug"] for row in a.json()] == ["receptionist"]
    assert [row["agent_slug"] for row in b.json()] == ["sales"]


async def test_activity_feed_survives_tool_call_entries(client: AsyncClient, db_session: AsyncSession, user_and_org):
    """Regression: tool_calls is published as a list of strings; summarizing it
    as if it were a list of dicts crashed the whole feed with a 500."""
    _, org, headers = user_and_org
    db_session.add(
        AuditLog(
            org_id=org.id,
            actor="receptionist",
            action="agent.response_generated",
            details={"tool_calls": ["calendar", "whatsapp"]},
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/audit-logs", headers=headers)
    assert response.status_code == 200
    assert response.json()[0]["summary"] == "Used calendar, whatsapp to help answer a message"


async def test_knowledge_documents_are_scoped_to_the_callers_org(
    client: AsyncClient, db_session: AsyncSession, user_and_org
):
    _, org_a, headers_a = user_and_org
    org_b, _ = await _second_org(db_session)

    db_session.add(KnowledgeChunk(org_id=org_a.id, source="ours.pdf", content="ours", embedding=[0.0] * 1536))
    db_session.add(KnowledgeChunk(org_id=org_b.id, source="theirs.pdf", content="theirs", embedding=[0.0] * 1536))
    await db_session.commit()

    response = await client.get("/api/v1/knowledge", headers=headers_a)
    assert response.status_code == 200
    assert [doc["filename"] for doc in response.json()] == ["ours.pdf"]


async def test_integrations_are_scoped_to_the_callers_org(client: AsyncClient, db_session: AsyncSession, user_and_org):
    _, org_a, headers_a = user_and_org
    org_b, _ = await _second_org(db_session)
    await store_integration(db_session, org_id=org_b.id, provider="slack", access_token="theirs")

    response = await client.get("/api/v1/integrations", headers=headers_a)
    assert response.status_code == 200
    assert all(item["connected"] is False for item in response.json())


async def test_memory_facts_do_not_leak_across_orgs(db_session: AsyncSession, user_and_org):
    _, org_a, _ = user_and_org
    org_b, _ = await _second_org(db_session)

    await long_term.upsert_fact(db_session, org_a.id, "receptionist", "hours", "9-5")
    await long_term.upsert_fact(db_session, org_b.id, "receptionist", "hours", "24/7")

    facts_a = await long_term.get_facts(db_session, org_a.id, "receptionist")
    assert [f.value for f in facts_a] == ["9-5"]


async def test_org_header_the_caller_is_not_a_member_of_is_refused(client: AsyncClient, db_session, user_and_org):
    """The org id is client-supplied — it must always be checked against the
    caller's membership, never trusted."""
    _, _, headers_a = user_and_org
    org_b, _ = await _second_org(db_session)

    response = await client.get("/api/v1/audit-logs", headers={**headers_a, "X-Organization-Id": str(org_b.id)})
    assert response.status_code == 403
    assert response.json()["error"] == "You don't have access to this organization."


async def test_agent_list_never_exposes_system_prompts_or_tool_allowlists(client: AsyncClient, user_and_org):
    _, _, headers = user_and_org
    response = await client.get("/api/v1/agents", headers=headers)
    assert response.status_code == 200
    for agent in response.json():
        assert set(agent) == {"slug", "display_name", "description"}


async def test_malformed_token_reads_as_sign_in_again_not_a_crash(client: AsyncClient):
    """Regression: a token whose `sub` claim isn't a uuid used to raise
    ValueError/TypeError and surface as an opaque 500."""
    import jwt

    from src.core.config import get_settings

    settings = get_settings()
    bad = jwt.encode({"sub": "not-a-uuid", "type": "access"}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
    assert response.status_code == 401
    assert response.json() == {"error": "Please sign in again."}

    missing_sub = jwt.encode({"type": "refresh"}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": missing_sub})
    assert refresh.status_code == 401
    assert "error" in refresh.json()


async def test_validation_errors_are_plain_language_not_pydantic_internals(client: AsyncClient):
    response = await client.post("/api/v1/auth/signup", json={"email": "not-an-email"})
    assert response.status_code == 422
    body = response.json()
    assert body == {"error": "Some of the information provided isn't valid. Please check it and try again."}
    # No field paths, no type names, no "value_error" jargon.
    assert "detail" not in body


async def test_invite_to_an_unregistered_email_is_claimed_at_signup(client: AsyncClient):
    """Regression: an invite for someone without an account created a row with
    user_id=NULL that nothing ever claimed, so the invitee could never get in."""
    owner = await client.post(
        "/api/v1/auth/signup", json={"email": "owner-inv@example.com", "password": "hunter2pass", "name": "Owner"}
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Invite Org"}, headers=owner_headers)
    ).json()

    invite = await client.post(
        f"/api/v1/organizations/{org['id']}/invite",
        json={"email": "newcomer@example.com", "role": "member"},
        headers={**owner_headers, "X-Organization-Id": org["id"]},
    )
    assert invite.status_code == 201
    assert invite.json()["accepted"] is False

    newcomer = await client.post(
        "/api/v1/auth/signup", json={"email": "newcomer@example.com", "password": "hunter2pass", "name": "New"}
    )
    newcomer_headers = {
        "Authorization": f"Bearer {newcomer.json()['access_token']}",
        "X-Organization-Id": org["id"],
    }

    members = await client.get(f"/api/v1/organizations/{org['id']}/members", headers=newcomer_headers)
    assert members.status_code == 200


async def test_oversized_upload_is_refused_in_plain_language(client: AsyncClient, user_and_org, monkeypatch):
    """Regression: the whole upload was read into memory before any check, so a
    single large POST from any member could take the API down."""
    from src.core.config import get_settings

    _, _, headers = user_and_org
    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_BYTES", 1024, raising=False)

    response = await client.post(
        "/api/v1/knowledge/upload",
        headers=headers,
        files={"file": ("big.pdf", b"x" * 5000, "application/pdf")},
    )
    assert response.status_code == 422
    assert "too large" in response.json()["error"]


async def test_unsupported_file_type_message_has_no_jargon(client: AsyncClient, user_and_org):
    _, _, headers = user_and_org
    response = await client.post(
        "/api/v1/knowledge/upload",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "We can only read PDF or Word (.docx) documents right now."
