"""Org creation and tenant isolation tests — org A must never see org B's data."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _signup(client: AsyncClient, email: str) -> tuple[str, dict]:
    response = await client.post("/api/v1/auth/signup", json={"email": email, "password": "hunter2pass", "name": "N"})
    body = response.json()
    return body["access_token"], {"Authorization": f"Bearer {body['access_token']}"}


async def test_create_organization_makes_creator_owner(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _signup(client, "founder@example.com")
    response = await client.post("/api/v1/organizations", json={"name": "Acme", "slug": "acme"}, headers=headers)
    assert response.status_code == 201
    org_id = response.json()["id"]

    members = await client.get(f"/api/v1/organizations/{org_id}/members", headers={**headers, "X-Organization-Id": org_id})
    assert members.status_code == 200
    roles = [m["role"] for m in members.json()]
    assert roles == ["owner"]


async def test_user_cannot_access_organization_they_do_not_belong_to(client: AsyncClient):
    _, headers_a = await _signup(client, "usera@example.com")
    org_a = (await client.post("/api/v1/organizations", json={"name": "Org A", "slug": "org-a"}, headers=headers_a)).json()

    _, headers_b = await _signup(client, "userb@example.com")
    org_b = (await client.post("/api/v1/organizations", json={"name": "Org B", "slug": "org-b"}, headers=headers_b)).json()

    # User B tries to read Org A's members using their own token.
    response = await client.get(
        f"/api/v1/organizations/{org_a['id']}/members",
        headers={**headers_b, "X-Organization-Id": org_a["id"]},
    )
    assert response.status_code == 403

    # And vice versa.
    response = await client.get(
        f"/api/v1/organizations/{org_b['id']}/members",
        headers={**headers_a, "X-Organization-Id": org_b["id"]},
    )
    assert response.status_code == 403


async def test_invite_creates_pending_membership(client: AsyncClient):
    _, headers = await _signup(client, "owner2@example.com")
    org = (await client.post("/api/v1/organizations", json={"name": "Org C", "slug": "org-c"}, headers=headers)).json()

    response = await client.post(
        f"/api/v1/organizations/{org['id']}/invite",
        json={"email": "invitee@example.com", "role": "member"},
        headers={**headers, "X-Organization-Id": org["id"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["invited_email"] == "invitee@example.com"
    assert body["accepted"] is False
